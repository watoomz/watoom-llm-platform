"""Root-only bounded registration broker. No scale/exec or arbitrary kubectl API.

Production installation supplies an immutable, reviewed configuration. UI sends
only an installation identity; records and file digests are re-read locally.
"""
import contextlib,hashlib,json,os,socket,subprocess,time,urllib.request,base64,re,shutil
from pathlib import Path
from file_lock import lock_file
from admission_errors import AdmissionBusy
from workload import build
from download import digest,safe_path
def rpc(path,request):
 with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
  sock.settimeout(1800);sock.connect(path);sock.sendall(json.dumps(request).encode()+b"\n")
  raw=b""
  while not raw.endswith(b"\n"):
   chunk=sock.recv(65536)
   if not chunk or len(raw)+len(chunk)>1024*1024:raise ValueError("Invalid controller response")
   raw+=chunk
  response=json.loads(raw)
  if "error" in response:raise ValueError(response.get("detail","Controller rejected operation"))
  return response["result"]
def identity(obj):
 spec=dict(obj["spec"]);spec.pop("replicas",None)
 return {"uid":obj["metadata"]["uid"],"spec_sha256":hashlib.sha256(json.dumps(spec,sort_keys=True,separators=(",",":")).encode()).hexdigest()}
def prune_native_profiles(path,aliases,backup):
 if any(not re.fullmatch(r"mm-[a-f0-9]{16}",alias) for alias in aliases):raise ValueError("Only owned managed profiles may be removed")
 path=Path(path);raw=path.read_bytes();config=json.loads(raw)
 # WatooM Code's config keeps them under "providers" (as enable-model-context.py writes them); "provider" is the older
 # layout. Reading only "provider" meant no removal ever pruned a profile (T-0103, 2026-11-20).
 profiles=(config.get("providers") or config.get("provider") or {}).get("watoom",{}).get("models",{})
 removed=[alias for alias in aliases if alias in profiles]
 if not removed:return False
 backup=Path(backup);backup.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
 with backup.open("xb") as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
 os.chmod(backup,0o600);original=path.stat()
 for alias in removed:del profiles[alias]
 temporary=path.with_name("."+path.name+".managed-prune-"+str(time.time_ns()))
 try:
  with temporary.open("x") as stream:json.dump(config,stream,indent=2);stream.flush();os.fsync(stream.fileno())
  os.chown(temporary,original.st_uid,original.st_gid);os.chmod(temporary,original.st_mode&0o777)
  if path.read_bytes()!=raw:raise ValueError("Application config changed independently")
  os.replace(temporary,path)
 finally:temporary.unlink(missing_ok=True)
 return True
LLM_KINDS=("gguf","gguf-lora")
def application_budget(served):
 """WatooM Code's budget for a model served at `served` tokens: 100K per 128K (owner 2026-11-19), so a 128K 27B model
 gets 100K and a 256K small model 200K. Same rule as the router's application_budget."""
 return max(min(served,100000),int(served*100000/131072)//1000*1000) if served else 100000
def display_name(record,store=None):
 """Human name for a managed install: '<repository> (<file>)', or '<adapter> on <base>' for a GGUF LoRA."""
 if not record.get("repository"):return None
 files=[Path(row[0]).name for row in (store.db.execute("SELECT path FROM artifacts WHERE id=?",(record["artifacts"][0],)).fetchall() if store and record.get("artifacts") else [])]
 name=record["repository"]+(" ("+files[0]+")" if files else "")
 if record.get("kind")=="gguf-lora" and store and record.get("dependencies"):
  row=store.db.execute("SELECT record FROM models WHERE id=?",(record["dependencies"][0],)).fetchone()
  if row:name=record["repository"]+" on "+json.loads(row[0])["repository"]
 if (record.get("settings") or {}).get("speculation")=="draft-mtp":name+=" · MTP"
 if (record.get("settings") or {}).get("projector"):name+=" · Vision"
 return name[:200]
def server_settings(container):
 """The llama-server settings an inventory row shows, from a Deployment container's args and LLAMA_ARG_* env."""
 args=list(container.get("args") or []);env={e["name"]:e.get("value") for e in container.get("env") or [] if "value" in e}
 def arg(*flags):
  for i,a in enumerate(args):
   if a in flags and i+1<len(args):return args[i+1]
  return None
 pick=lambda flags,var:arg(*flags) or env.get(var)
 return {"model":pick(("--model","-m"),"LLAMA_ARG_MODEL"),"lora":arg("--lora"),"mmproj":pick(("--mmproj","-mm"),"LLAMA_ARG_MMPROJ"),
  "context":pick(("--ctx-size","-c"),"LLAMA_ARG_CTX_SIZE"),"cache_k":pick(("--cache-type-k","-ctk"),"LLAMA_ARG_CACHE_TYPE_K"),
  "cache_v":pick(("--cache-type-v","-ctv"),"LLAMA_ARG_CACHE_TYPE_V"),"reasoning":pick(("--reasoning",),"LLAMA_ARG_REASONING"),
  "speculation":pick(("--spec-type",),"LLAMA_ARG_SPEC_TYPE"),"draft_count":pick(("--spec-draft-n-max",),"LLAMA_ARG_SPEC_DRAFT_N_MAX"),
  "temperature":pick(("--temp",),"LLAMA_ARG_TEMP"),"top_p":pick(("--top-p",),"LLAMA_ARG_TOP_P"),"top_k":pick(("--top-k",),"LLAMA_ARG_TOP_K"),
  "min_p":pick(("--min-p",),"LLAMA_ARG_MIN_P"),"cpu_ffn":arg("--n-cpu-ffn")}

REASONING_VARIANTS=Path("/data/ai/watoom-code/config/reasoning-variants.json")
def apply_reasoning_variants(application,spec_path=None,script=None):
 """Re-offer the owner's reasoning variants (xhigh/medium/low/off) after a registration rewrote model profiles.
 Retire prunes a model's profile and register adds a plain one, so a re-registered thinking model lost its picker
 variants until the watoom-code playbook ran again (mm-aa6b02, 2026-11-21). The spec is written by the watoom-code
 role (reasoning_variants.yml); without it nothing changes. Returns True when the application config changed."""
 spec_path=Path(spec_path or REASONING_VARIANTS)
 if not spec_path.is_file():return False
 script=Path(script or Path(__file__).with_name("enable-reasoning-variants.py"))
 result=subprocess.run(["python3",str(script),application,spec_path.read_text()],capture_output=True,text=True,timeout=30)
 if result.returncode:raise ValueError("Reasoning variant registration failed")
 return result.stdout.strip()=="CHANGED"

class Broker:
 def __init__(self,config,store):
  self.config=config;self.store=store;self.root=Path(config["state"]);self.root.mkdir(parents=True,exist_ok=True)
 def kube(self,args,obj=None,missing=False):
  # Only internal callers construct args; HTTP cannot provide arguments.
  result=subprocess.run(["kubectl","--kubeconfig",self.config["kubeconfig"],"-n","llama-cpp",*args],input=json.dumps(obj) if obj is not None else None,text=True,capture_output=True,timeout=45)
  if result.returncode:
   if missing and "NotFound" in result.stderr:return None
   raise ValueError("Scoped Kubernetes operation failed")
  return json.loads(result.stdout) if result.stdout.strip() else None
 def delete_owned(self,kind,name,uid):
  current=self.kube(["get",kind,name,"-o","json"],missing=True)
  if current is None:return
  if current["metadata"]["uid"]!=uid:raise ValueError("Refusing replacement resource deletion")
  prefix="/apis/apps/v1" if kind=="deployment" else "/api/v1"
  plural="deployments" if kind=="deployment" else "services"
  options={"apiVersion":"v1","kind":"DeleteOptions","preconditions":{"uid":uid,"resourceVersion":current["metadata"]["resourceVersion"]},"propagationPolicy":"Foreground"}
  self.kube(["delete","--raw",prefix+"/namespaces/llama-cpp/"+plural+"/"+name,"-f","-"],options)
 def snapshot(self,path,name,obj):
  destination=path/(name+".json");temporary=path/(name+".new")
  with temporary.open("w") as stream:
   json.dump(obj,stream,indent=2);stream.flush();os.fsync(stream.fileno())
  os.chmod(temporary,0o600);os.replace(temporary,destination)
  fd=os.open(path,os.O_RDONLY)
  try:os.fsync(fd)
  finally:os.close(fd)
 def role(self,name,add):
  role=self.kube(["get","role","watoom-gpu-controller","-o","json"])
  original=json.loads(json.dumps(role))
  matches=[rule for rule in role["rules"] if "deployments" in rule.get("resources",[]) and "patch" in rule.get("verbs",[])]
  if len(matches)!=1 or "resourceNames" not in matches[0]:raise ValueError("Unexpected controller RBAC")
  names=set(matches[0]["resourceNames"])
  names.add(name) if add else names.discard(name)
  matches[0]["resourceNames"]=sorted(names)
  services=next((rule for rule in role["rules"] if rule.get("apiGroups")==[""] and rule.get("resources")==["services"] and rule.get("verbs")==["get"] and "resourceNames" in rule),None)
  if add and services is None:
   services={"apiGroups":[""],"resources":["services"],"verbs":["get"],"resourceNames":[]};role["rules"].append(services)
  if services is not None:
   names=set(services["resourceNames"]);names.add(name) if add else names.discard(name)
   if names:services["resourceNames"]=sorted(names)
   else:role["rules"].remove(services)
  self.kube(["replace","-f","-","-o","json"],role)
  return original
 def publish_routes(self):
  ledger=Path(self.config["controller_state"])/"managed-models.json"
  entries=json.loads(ledger.read_text())["models"] if ledger.exists() else {}
  records={"llama-cpp-mm-"+row[0][:16]:json.loads(row[1]) for row in self.store.db.execute("SELECT id,record FROM models")}
  # The router shows this name in its model list (and WatooM Code picks it up), so it is the real source, not the alias.
  routes={entry["alias"]:{"deployment":name,"url":"http://"+name+".llama-cpp.svc.cluster.local:8080","name":(display_name(records[name],self.store) if name in records else None) or entry["alias"],"backend":entry["backend"],"context_limit":entry.get("context_limit"),"application_context":application_budget(records[name]["settings"].get("context")) if name in records else entry.get("application_context",100000),"vision":bool(records[name]["settings"].get("projector")) if name in records else entry.get("vision")} for name,entry in entries.items()}
  path=Path(self.config["router_view"]);path.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
  previous=json.loads(path.read_text()).get("models",{}) if path.exists() else {}
  removed=set(previous)-set(routes)
  temporary=path.with_suffix(".new");temporary.write_text(json.dumps({"version":1,"models":routes},sort_keys=True));os.chmod(temporary,0o644);os.replace(temporary,path)
  application=self.config.get("application_config")
  if application:
   if application!="/data/ai/watoom-code/config/opencode.json":raise ValueError("Unexpected application config path")
   inventory=path.parent/"context-inventory.json"
   inventory.write_text(json.dumps({"data":[{"id":key,"name":entry["name"],"context_limit":entry.get("context_limit"),"application_context":entry.get("application_context"),"vision":entry.get("vision")} for key,entry in routes.items() if entry["backend"]=="gguf"]}))
   pruned=prune_native_profiles(application,removed,self.root/"profile-history"/(str(time.time_ns())+".json")) if removed else False
   migration=Path(__file__).parent/"enable-model-context.py"
   result=subprocess.run(["python3",str(migration),application,str(inventory),"100000"],capture_output=True,text=True,timeout=30)
   if result.returncode:raise ValueError("Application profile registration failed")
   variants=apply_reasoning_variants(application)
   from maintenance_guard import Maintenance
   if pruned or variants or result.stdout.strip() in ("CHANGED","UPDATED"):Maintenance("watoom-code","watoom-code",self.root,True,True).request("/api/location/reload",{})
 def artifacts(self,record):
  artifacts=[]
  for aid in record["artifacts"]:
   item=self.store.db.execute("SELECT path,bytes,digest FROM artifacts WHERE id=?",(aid,)).fetchone()
   if not item:raise ValueError("Missing dependency")
   path=Path(item[0])
   roots=[Path("/data/ai/models")/category/"model-manager" for category in ("gguf","diffusion","loras")]
   root=next((root for root in roots if path.is_relative_to(root)),None)
   if root is None:raise ValueError("Artifact outside manager-owned storage")
   safe_path(root,str(path.relative_to(root)))
   if path.stat().st_size!=item[1] or digest(path)!=item[2]:raise ValueError("Artifact integrity changed")
   artifacts.append({"path":str(path),"bytes":item[1],"digest":item[2]})
  if record["kind"] in LLM_KINDS:
   from gguf_header import inspect
   from settings import validate
   model=artifacts[1 if record["kind"]=="gguf-lora" else 0]["path"]
   header=inspect(model)
   if record["kind"]=="gguf-lora":
    adapter=inspect(artifacts[0]["path"])
    if adapter.get("type")!="adapter" or adapter.get("adapter_type")!="lora" or adapter.get("architecture")!=header.get("architecture"):raise ValueError("Adapter does not match the base model architecture")
   vision=False
   if record["settings"].get("projector"):
    projector=inspect(artifacts[-1]["path"])
    vision=projector.get("type")=="mmproj" and bool(projector.get("vision_encoder")) and projector.get("projection_dim")==header.get("embedding_length")
   validate(record["settings"],record["kind"],capabilities={"mtp":header["nextn_predict_layers"]>0,"vision":vision},max_context=header["context_length"])
  return artifacts
 def inventory(self):
  """Read-only: every model the router serves (managed or not) with its deployment, file, size and settings."""
  config=json.loads(Path("/data/ai/helper-scripts/config/gpu-controller.json").read_text())
  state_root=Path(self.config["controller_state"])
  def read(path,default):
   try:return json.loads(Path(path).read_text())
   except (OSError,ValueError):return default
  state=read(state_root/"state.json",{});selected=read(state_root/"selected-model.json",{}).get("deployment")
  ledger=read(state_root/"managed-models.json",{}).get("models",{})
  if state.get("phase")=="qwen-ready":selected=config["primary"]
  deployments={d["metadata"]["name"]:d for d in self.kube(["get","deployment","-o","json"])["items"] if d["metadata"]["name"].startswith("llama-cpp-")}
  volumes_pv={pv["spec"]["claimRef"]["name"]:pv["spec"].get("hostPath",{}).get("path") for pv in json.loads(subprocess.run(["kubectl","--kubeconfig",self.config["kubeconfig"],"get","pv","-o","json"],capture_output=True,text=True,timeout=45).stdout or '{"items":[]}')["items"] if pv["spec"].get("claimRef",{}).get("namespace")=="llama-cpp"}
  router=self.kube(["get","service","llm-router","-o","json"])["spec"]["clusterIP"]
  def fetch(path):
   with urllib.request.urlopen("http://"+router+":8000"+path,timeout=5) as response:return json.load(response)
  names={m["id"]:m.get("name") for m in fetch("/v1/models").get("data",[])}
  records={"llama-cpp-mm-"+row[0][:16]:json.loads(row[1]) for row in self.store.db.execute("SELECT id,record FROM models")}
  rows=[]
  for model in fetch("/models").get("models",[]):
   name=model["deployment"];deployment=deployments.get(name)
   public=next((a for a in [model["id"],*model.get("aliases",[])] if a in names),model["id"])
   row={"id":public,"name":names.get(public) or public,"deployment":name,"managed":name in ledger,"model_id":records[name]["id"] if name in records else None,
        "primary":name==config["primary"],"mesh":name==config["mesh"],"loaded":name==selected and state.get("phase") in ("qwen-ready","model-ready","mesh-ready"),
        "exists":deployment is not None}
   if deployment:
    spec=deployment["spec"]["template"]["spec"];container=spec["containers"][0]
    hosts={}
    for volume in spec.get("volumes",[]):
     host=(volume.get("hostPath") or {}).get("path") or volumes_pv.get((volume.get("persistentVolumeClaim") or {}).get("claimName"))
     if host:hosts[volume["name"]]=host
    settings=server_settings(container)
    def host_file(value):
     for mount in container.get("volumeMounts",[]):
      if value and mount["name"] in hosts and (value==mount["mountPath"] or value.startswith(mount["mountPath"].rstrip("/")+"/")):
       candidate=Path(hosts[mount["name"]]) if value==mount["mountPath"] else Path(hosts[mount["name"]])/value[len(mount["mountPath"].rstrip("/"))+1:]
       try:return {"path":str(candidate.resolve()),"bytes":candidate.resolve().stat().st_size}
       except OSError:return {"path":str(candidate),"bytes":None}
     return None
    row.update(replicas=deployment["spec"].get("replicas",0),ready=deployment.get("status",{}).get("readyReplicas",0),image=container.get("image"),
               settings=settings,file=host_file(settings["model"]),lora_file=host_file(settings["lora"]),mmproj_file=host_file(settings["mmproj"]))
   rows.append(row)
  return {"controller":{"phase":state.get("phase"),"owner":state.get("owner"),"uncertain":state.get("uncertain"),"selected":selected,"primary":config["primary"]},"models":rows}
 def hardware_admission(self,record):
  if shutil.disk_usage("/").free<8*1024**3:raise ValueError("Root image filesystem reserve unavailable")
  nodes=self.kube(["get","nodes","-o","json"])
  if any(c.get("type")=="DiskPressure" and c.get("status")=="True" for n in nodes["items"] for c in n.get("status",{}).get("conditions",[])):raise ValueError("Node disk pressure blocks GPU switching")
  if record["kind"]!="gguf":
   from runtime_payload import verify
   verify(self.config["images"]["sdxl_runtime"])
   actual=self.kube(["get","deployment",record["deployment"],"-o","json"])
   container=actual["spec"]["template"]["spec"]["containers"][0]
   if container["image"]!=self.config["images"]["sdxl"] or container.get("command",[])[0]!="/app/runtime/bin/python":raise ValueError("Retired disk-heavy backend: unregister keeping files and reinstall")
 def inference(self,record,request,run,progress=None):
  # Stage reporting is advisory: it must never alter or abort the GPU transaction.
  report=progress or (lambda stage:None)
  self.hardware_admission(record)
  from native_admission import hold
  config=json.loads(Path("/data/ai/helper-scripts/config/gpu-controller.json").read_text())
  primary=config["primary"];socket_path=self.config["controller_socket"];restoration_verified=None
  def quiet():
   if restoration_verified is False:raise ValueError("Prior chat-model restoration failed; native admission remains fenced")
   state=rpc(socket_path,{"action":"status"})
   if state["uncertain"]:raise ValueError("GPU controller outcome uncertain; reconciliation required")
   if state["owner"] or state.get("active_requests",0):
    if restoration_verified is None:raise AdmissionBusy("GPU controller busy before execution; image remains queued until idle")
    raise ValueError("GPU controller busy after execution; reconciliation required")
  name=record["deployment"];lease=None;restore=primary;outcome=None
  with hold(run,quiet):
   state=rpc(socket_path,{"action":"status"})
   if state.get("phase") in ("qwen-ready","model-ready"):
    selected=json.loads((Path(self.config["controller_state"])/"selected-model.json").read_text())["deployment"]
    # Restore the actual prior chat model, including registered GGUFs; never Mesh or an image worker.
    managed=json.loads((Path(self.config["controller_state"])/"managed-models.json").read_text()).get("models",{})
    if (selected in config.get("models",[]) and selected!=config["mesh"]) or managed.get(selected,{}).get("backend")=="gguf":restore=selected
   try:
    report("loading-model")
    lease=rpc(socket_path,{"action":"begin-inference","deployment":name,"allow_switch":True})["lease"]
    report("generating")
    headers={"Authorization":"Bearer "+Path(self.config["images"]["backend_auth_file"]).read_text().strip(),"Content-Type":"application/json"}
    ledger=json.loads((Path(self.config["controller_state"])/"managed-models.json").read_text())["models"]
    base=ledger[name]["url"]
    if record["kind"] in LLM_KINDS:
     body={"model":record["alias"],"messages":[{"role":"user","content":request["prompt"]}],"max_tokens":128,"stream":False}
     with urllib.request.urlopen(urllib.request.Request(base+"/v1/chat/completions",json.dumps(body).encode(),headers),timeout=300) as response:result=json.load(response)
     text=result["choices"][0]["message"]["content"]
     if result.get("model")!=record["alias"] or not isinstance(text,str) or not text:raise ValueError("Actual generation failed validation")
     outcome={"backend":"gguf","model":record["alias"],"text":text,"tested":True}
    else:
     from image_mcp import generation_settings
     overrides=generation_settings(request["settings"]) if "settings" in request else {}
     body={**record["settings"],**overrides,"prompt":request["prompt"],"negative_prompt":request.get("negative_prompt","")};body.pop("base_model",None);body.pop("precision",None)
     with urllib.request.urlopen(urllib.request.Request(base+"/generate",json.dumps(body).encode(),headers),timeout=600) as response:result=json.load(response)
     with urllib.request.urlopen(urllib.request.Request(base+"/artifacts/"+result["artifact"],headers=headers),timeout=30) as response:png=response.read(16*1024*1024+1)
     if len(png)>16*1024*1024 or png[:8]!=bytes([137,80,78,71,13,10,26,10]) or hashlib.sha256(png).hexdigest()!=result["sha256"]:raise ValueError("Rendered PNG failed integrity validation")
     outcome={**result,"backend":"sdxl","png_base64":base64.b64encode(png).decode(),"tested":True,"generation_settings":{k:v for k,v in body.items() if k!="prompt"}}
   finally:
    if lease:
     ended=rpc(socket_path,{"action":"end-inference","lease":lease})
     if not ended.get("released"):
      restoration_verified=False
      raise ValueError("Inference not confirmed idle; GPU remains fenced")
    restoration_verified=False
    report("restoring-chat-model")
    restored=rpc(socket_path,{"action":"request-model","deployment":restore,"allow_switch":True})
    if restored.get("allowed") is not True:raise ValueError("Prior chat-model restoration unverified")
    restoration_verified=True
   outcome["restoration"]={"verified":True,"deployment":restore,"alias":config.get("aliases",{}).get(restore),"controller":"exclusive-gpu-lease"}
   if outcome["backend"]=="sdxl" and self.config.get("image_output_root"):
    from image_publish import publish
    report("publishing")
    receipt={k:outcome.get(k) for k in ["model","sha256","width","height","restoration","generation_settings"]}
    outcome["published"]=publish(self.config["image_output_root"],run.name,png,receipt,self.config.get("image_output_gid"))
   return outcome
 def admission(self,evidence):
  from native_admission import hold
  def quiet():
   state=rpc(self.config["controller_socket"],{"action":"status"})
   if state["owner"] or state["uncertain"] or state.get("active_requests",0):raise ValueError("Active work blocks catalog reconfiguration")
  return hold(evidence,quiet)
 def __call__(self,action,record,request=None,progress=None):
  if action=="generate":return self._dispatch(action,record,request,progress)
  if os.geteuid()!=0:raise PermissionError("Registration broker requires root")
  evidence=self.root/"admission"/str(time.time_ns())
  with self.admission(evidence):return self._dispatch(action,record,request)
 def _dispatch(self,action,record,request=None,progress=None):
  if os.geteuid()!=0:raise PermissionError("Registration broker requires root")
  with (self.root/"broker.lock").open("a") as lock:
   lock_file(lock)
   if (self.root/"maintenance.json").exists():raise ValueError("Model manager is in maintenance")
   if action=="generate":
    from native_admission import check_native_idle
    from maintenance_guard import Maintenance
    if progress:progress("checking-native-idle")
    check_native_idle(Maintenance("watoom-code","watoom-code",self.root,True,True))
   status=rpc(self.config["controller_socket"],{"action":"status"})
   if status["uncertain"]:raise ValueError("Controller ownership uncertain; reconciliation required")
   if action=="generate" and (status["owner"] or status.get("active_requests",0)):raise AdmissionBusy("GPU controller busy before execution; image remains queued until idle")
   if status["owner"]:raise ValueError("Controller ownership is busy")
   modelid=record["id"]
   if not re.fullmatch("[a-f0-9]{64}",modelid):raise ValueError("Invalid managed identity")
   row=self.store.db.execute("SELECT record FROM models WHERE id=?",(modelid,)).fetchone()
   if not row or json.loads(row[0])["revision"]!=record["revision"]:raise ValueError("Stale catalog identity")
   record=json.loads(row[0])
   artifacts=self.artifacts(record) if action in ("register","generate") else []
   name="llama-cpp-mm-"+modelid[:16]
   run=self.root/"transactions"/(str(time.time_ns())+"-"+modelid[:16]);run.mkdir(parents=True,mode=0o700)
   checkpoint={"action":action,"id":modelid,"stage":"preflight"}
   def save(stage):checkpoint["stage"]=stage;(run/"transaction.json").write_text(json.dumps(checkpoint))
   if action=="generate":
    prompt=(request or {}).get("prompt","")
    if not isinstance(prompt,str) or not 1<=len(prompt)<=4096:raise ValueError("Bounded prompt required")
    if not record.get("registered"):raise ValueError("Model is not registered")
    generation_request={"prompt":prompt}
    if "negative_prompt" in (request or {}):
     from settings import validate_negative_prompt
     if record["kind"] in LLM_KINDS:raise ValueError("Negative prompts are image parameters")
     generation_request["negative_prompt"]=validate_negative_prompt(request["negative_prompt"])
    if "settings" in (request or {}):
     from image_mcp import generation_settings
     if record["kind"] in LLM_KINDS:raise ValueError("Image generation settings are not chat parameters")
     generation_request["settings"]=generation_settings(request["settings"])
    return self.inference(record,generation_request,run,progress)
   if action=="register":
    deployment,service,alias=build(record,artifacts,self.config["images"])
    existing=self.kube(["get","deployment",name,"-o","json"],missing=True)
    if existing is not None:
     ledger_path=Path(self.config["controller_state"])/"managed-models.json"
     ledger=json.loads(ledger_path.read_text())["models"] if ledger_path.exists() else {}
     entry=ledger.get(name)
     service_actual=self.kube(["get","service",name,"-o","json"],missing=True)
     if not entry or entry["identity"]!=identity(existing) or not service_actual:raise ValueError("Incomplete prior transaction requires identity-scoped reconciliation")
     def subset(expected,actual):
      if isinstance(expected,dict):return isinstance(actual,dict) and all(k in actual and subset(v,actual[k]) for k,v in expected.items())
      if isinstance(expected,list):return isinstance(actual,list) and len(expected)==len(actual) and all(subset(a,b) for a,b in zip(expected,actual))
      return expected==actual
     if not subset(deployment["spec"],existing["spec"]) or not subset(service["spec"],service_actual["spec"]):raise ValueError("Prior registered configuration differs")
     self.publish_routes();save("reconciled-complete")
     return {"configured":True,"registered":True,"tested":record.get("tested",False),"resources":[{"kind":"deployment","name":name,"uid":existing["metadata"]["uid"]},{"kind":"service","name":name,"uid":service_actual["metadata"]["uid"]}],"controller_identity":identity(existing),"alias":alias,"deployment":name,"transaction":str(run)}
    ledger_path=Path(self.config["controller_state"])/"managed-models.json"
    abandoned=json.loads(ledger_path.read_text())["models"].get(name) if ledger_path.exists() else None
    if abandoned:
     # Recover only an exact prior enrollment whose deployment is proven absent.
     service_actual=self.kube(["get","service",name,"-o","json"],missing=True)
     if service_actual and identity(service_actual)!=abandoned.get("service_identity"):raise ValueError("Replacement service protected")
     self.role(name,True)
     rpc(self.config["controller_socket"],{"action":"retire-model","deployment":name,"identity":abandoned["identity"]})
     if service_actual:self.delete_owned("service",name,service_actual["metadata"]["uid"])
     self.role(name,False);self.publish_routes();save("abandoned-enrollment-reconciled")
    previous_role=None;created=[];enrolled=False
    try:
     save("creating-zero-replica-resources")
     for obj in (deployment,service):
      result=self.kube(["create","-f","-","-o","json"],obj);created.append((obj["kind"].lower(),result))
      self.snapshot(run,obj["kind"].lower(),result)
     actual=created[0][1];uid=identity(actual)
     authority=self.root/"installations";authority.mkdir(exist_ok=True,mode=0o700)
     self.snapshot(authority,modelid,{"identity":uid,"resources":[{"kind":kind,"uid":obj["metadata"]["uid"]} for kind,obj in created]})
     previous_role=self.role(name,True);self.snapshot(run,"previous-role",previous_role);save("named-rbac")
     entry={"context_limit":record.get("max_context"),"application_context":application_budget(record["settings"].get("context")),"vision":bool(record["settings"].get("projector")),"identity":uid,"backend":"gguf" if record["kind"] in LLM_KINDS else "sdxl","alias":alias,"url":"http://"+created[1][1]["spec"]["clusterIP"]+":8080","service_identity":identity(created[1][1])}
     rpc(self.config["controller_socket"],{"action":"enroll-model","deployment":name,"record":entry});enrolled=True;save("enrolled");self.publish_routes()
     # Router consumes a derived view of the sole manager catalog, never hand-edited dictionaries.
     resources=[{"kind":kind,"name":name,"uid":obj["metadata"]["uid"]} for kind,obj in created]
     save("complete")
     return {"configured":True,"registered":True,"tested":False,"resources":resources,"controller_identity":uid,"alias":alias,"deployment":name,"transaction":str(run)}
    except Exception:
     save("rollback")
     ledger_path=Path(self.config["controller_state"])/"managed-models.json"
     committed=json.loads(ledger_path.read_text())["models"].get(name) if ledger_path.exists() else None
     if enrolled or (created and committed and committed.get("identity")==identity(created[0][1])):
      # A failed RPC reply does not establish that enrollment did not commit.
      rpc(self.config["controller_socket"],{"action":"retire-model","deployment":name,"identity":identity(created[0][1])})
     for kind,obj in reversed(created):
      current=self.kube(["get",kind,name,"-o","json"],missing=True)
      if current and current["metadata"]["uid"]==obj["metadata"]["uid"]:
       self.delete_owned(kind,name,obj["metadata"]["uid"])
     if previous_role:self.role(name,False)
     self.publish_routes();save("rolled-back");raise
   if action=="retire":
    if record.get("protected"):raise ValueError("Recovery model protected")
    authority_path=self.root/"installations"/(modelid+".json")
    if not authority_path.is_file():raise ValueError("Root-owned installation receipt required")
    authority=json.loads(authority_path.read_text())
    if authority["identity"]!=record.get("controller_identity"):raise ValueError("Controller identity differs from root receipt")
    ledger_path=Path(self.config["controller_state"])/"managed-models.json"
    entries=json.loads(ledger_path.read_text())["models"] if ledger_path.exists() else {}
    if name in entries:
     selected=Path(self.config["controller_state"])/"selected-model.json"
     if selected.exists() and json.loads(selected.read_text()).get("deployment")==name:
      config=json.loads(Path("/data/ai/helper-scripts/config/gpu-controller.json").read_text())
      rpc(self.config["controller_socket"],{"action":"request-model","deployment":config["primary"],"allow_switch":True})
     rpc(self.config["controller_socket"],{"action":"retire-model","deployment":name,"identity":authority["identity"]})
    save("controller-retired")
    for resource in authority["resources"]:
     if resource["kind"] not in ("deployment","service"):raise ValueError("Invalid owned resource kind")
     current=self.kube(["get",resource["kind"],name,"-o","json"],missing=True)
     if current:
      if current["metadata"]["uid"]!=resource["uid"]:raise ValueError("Resource identity changed")
      if resource["kind"]=="deployment" and (identity(current)!=authority["identity"] or current["spec"].get("replicas",0)!=0):raise ValueError("Deployment still running or identity changed")
      self.delete_owned(resource["kind"],name,resource["uid"])
    self.role(name,False);self.publish_routes();save("complete");return {"retired":True,"transaction":str(run)}
   raise ValueError("Unsupported broker action")
