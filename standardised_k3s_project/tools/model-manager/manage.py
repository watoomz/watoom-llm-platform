"""Bounded build, isolated staging, validation and identity-scoped rollback."""
import argparse,base64,hashlib,json,os,re,secrets,shutil,subprocess,sys,time,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def run(args,timeout=60,**kwargs):
 if args and args[0]=="git":args=["git","-c","safe.directory="+str(ROOT),"-c","safe.directory="+str(ROOT.parent),*args[1:]]
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout,**kwargs)
 if p.returncode:raise RuntimeError("Command failed: "+args[0]+"; "+p.stderr[-300:])
 return p.stdout
def write(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
 descriptor,temporary=tempfile.mkstemp(prefix="."+path.name+".",dir=path.parent)
 try:
  with os.fdopen(descriptor,"w") as f:
   json.dump(value,f,indent=2);f.flush();os.fsync(f.fileno())
  os.chmod(temporary,0o600);os.replace(temporary,path)
  directory=os.open(path.parent,os.O_RDONLY)
  try:os.fsync(directory)
  finally:os.close(directory)
 finally:
  if os.path.exists(temporary):os.unlink(temporary)
def preflight():
 if os.geteuid()!=0:raise RuntimeError("Administrative runner requires root")
 ram=int(next(x.split()[1] for x in Path("/proc/meminfo").read_text().splitlines() if x.startswith("MemAvailable:")))*1024
 free=shutil.disk_usage("/data/ai").free
 if ram<2*1024**3 or free<300*1024**3:raise RuntimeError("Preserved memory/disk reserve unavailable")
 return {"available_ram":ram,"free_data_bytes":free}
def kube(*args):return json.loads(run(["kubectl","-n","model-manager-stage",*args,"-o","json"]))
def source():
 return run(["git","rev-parse","HEAD"],cwd=ROOT).strip()
def snapshot(out):
 if (out/"snapshot.json").exists():return json.loads((out/"snapshot.json").read_text())
 result={"source_commit":source(),"files":{},"objects":[],"at":time.time()}
 runtime=Path("/data/ai/helper-scripts/gpu-controller")
 for name in ["controller.py","durable_store.py","gateway.py","client.py","kubernetes_actuator.py","kubernetes_api.py","g3h_service.py","refresh_credentials.py","g3h_ops.py","g3h_cutover.py"]:
  p=runtime/name
  if p.is_file():
   dest=out/"before"/name;dest.parent.mkdir(parents=True,exist_ok=True,mode=0o700);shutil.copy2(p,dest)
   result["files"][str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
 for ns,kind,name in [("llama-cpp","cm","llm-router-app"),("llama-cpp","deployment","llm-router"),("llama-cpp","role","watoom-gpu-controller"),("glance","cm","glance-config"),("glance","cm","glance-helper")]:
  obj=json.loads(run(["kubectl","-n",ns,"get",kind,name,"-o","json"]))
  write(out/"before"/(ns+"-"+kind+"-"+name+".json"),obj)
  result["objects"].append({"namespace":ns,"kind":kind,"name":name,"uid":obj["metadata"]["uid"],"resourceVersion":obj["metadata"]["resourceVersion"]})
 write(out/"snapshot.json",result);return result
def clean_source():
 dirty=run(["git","status","--porcelain","--","tools/model-manager"],cwd=ROOT)
 if dirty.strip():raise RuntimeError("Commit reviewed manager source before building an immutable artifact")
 return source()
def build(out):
 clean_source();preflight();commit=source();tag="127.0.0.1:5000/watoom-model-manager:"+commit[:12]
 log=out/"build.log"
 p=subprocess.run(["docker","build","--label","org.opencontainers.image.revision="+source(),"--memory","512m","--cpuset-cpus","0","-t",tag,"-f",str(ROOT/"tools/model-manager/Dockerfile"),str(ROOT/"tools/model-manager")],stdout=log.open("w"),stderr=subprocess.STDOUT,timeout=600)
 if p.returncode:raise RuntimeError("CPU image build failed; inspect private build.log")
 run(["docker","push",tag],timeout=300)
 image=json.loads(run(["docker","image","inspect",tag]))[0]
 digest=next(x for x in image["RepoDigests"] if x.startswith("127.0.0.1:5000/watoom-model-manager@sha256:"))
 result={"image":digest,"source_commit":commit};write(out/"artifact.json",result);return result
def build_sdxl(out):
 if shutil.disk_usage("/").free<45*1024**3:raise RuntimeError("Software image build requires 45GiB root headroom; publish runtime on /data instead")
 clean_source();preflight();tag="127.0.0.1:5000/watoom-model-manager-sdxl:"+source()[:12]
 with (out/"sdxl-build.log").open("w") as log:
  process=subprocess.run(["docker","build","--label","org.opencontainers.image.revision="+source(),"--memory","512m","--cpuset-cpus","0","-t",tag,"-f",str(ROOT/"tools/model-manager/Dockerfile.sdxl"),str(ROOT/"tools/model-manager")],stdout=log,stderr=subprocess.STDOUT,timeout=1800)
 if process.returncode:raise RuntimeError("SDXL image build failed; inspect sdxl-build.log")
 run(["docker","push",tag],timeout=600)
 image=json.loads(run(["docker","image","inspect",tag]))[0]
 digest=next(x for x in image["RepoDigests"] if x.startswith("127.0.0.1:5000/watoom-model-manager-sdxl@sha256:"))
 result={"image":digest,"source_commit":source(),"generation":"NOT TESTED","gpu_used":False}
 write(out/"sdxl-artifact.json",result);return result
def stage(out):
 preflight();artifact=json.loads((out/"artifact.json").read_text());snapshot(out)
 private=Path("/data/ai/private/model-manager-stage");private.mkdir(parents=True,exist_ok=True,mode=0o700)
 password=private/"password"
 if not password.exists():
  password.write_text(secrets.token_urlsafe(36));os.chmod(password,0o640);os.chown(password,0,1009)
 variables={"model_manager_enabled":True,"model_manager_stage_only":True,"model_manager_image":artifact["image"],"model_manager_release":artifact["source_commit"],"model_manager_namespace":"model-manager-stage","model_manager_origin":"https://glance.internal.homelab.example","model_manager_state":"/data/ai/model-manager-stage","model_manager_password_file":str(password),"model_manager_broker_root":"/data/ai/helper-scripts/state/model-manager-stage-broker","model_manager_service_name":"watoom-model-manager-stage-broker"}
 write(out/"stage-vars.json",variables)
 env=dict(os.environ,ANSIBLE_CONFIG=str(ROOT/"ansible/ansible.cfg"),ANSIBLE_ROLES_PATH=str(ROOT/"ansible/roles"))
 p=subprocess.run(["ansible-playbook","-i",str(ROOT/"ansible/inventories/homelab/hosts.yml"),str(ROOT/"ansible/playbooks/model-manager.yml"),"--connection","local","--limit","watoom-homelab","-e","@"+str(out/"stage-vars.json")],cwd=ROOT,env=env,stdout=(out/"stage.log").open("w"),stderr=subprocess.STDOUT,timeout=300)
 if p.returncode:raise RuntimeError("Stage apply failed; inspect stage.log")
 run(["kubectl","-n","model-manager-stage","rollout","status","deployment/model-manager","--timeout=120s"],timeout=130)
 objects=[kube("get",kind,"model-manager") for kind in ("deployment","service")]
 write(out/"stage-resources.json",[{"kind":x["kind"],"name":x["metadata"]["name"],"uid":x["metadata"]["uid"]} for x in objects])
 return {"state":"STAGED_REGISTRATION_DISABLED","image":artifact["image"]}
def validate(out,namespace="model-manager-stage"):
 password=Path("/data/ai/private/"+("model-manager-stage" if namespace=="model-manager-stage" else "model-manager")+"/password").read_text().strip()
 code="""import sys,json,urllib.request,urllib.error,base64
password=sys.stdin.read()
base="http://127.0.0.1:8787/model-manager"
auth="Basic "+base64.b64encode(("admin:"+password).encode()).decode()
def call(path,body=None,csrf=None):
 h={"Authorization":auth}
 if body is not None:h.update({"Content-Type":"application/json","Origin":"https://glance.internal.homelab.example","X-CSRF-Token":csrf or ""})
 with urllib.request.urlopen(urllib.request.Request(base+path,None if body is None else json.dumps(body).encode(),h),timeout=60) as f:return json.load(f)
session=call("/api/session")
try:call("/api/cancel",{"id":"fixture"});raise RuntimeError("CSRF accepted")
except urllib.error.HTTPError as e:assert e.code==403
metadata=call("/api/inspect",{"url":"https://huggingface.co/thejagstudio/3d-animation-style-sdxl"},session["csrf"])
assert metadata["metadata"]["kind"]=="lora"
assert metadata["metadata"]["base_model"]=="stabilityai/stable-diffusion-xl-base-1.0"
assert "context" not in metadata["settings"]["values"]
assert call("/api/models")==[]
print(json.dumps({"authenticated_api":"PASS","csrf":"PASS","live_lora_metadata":metadata["metadata"]["revision"],"lora_bytes":[x["bytes"] for x in metadata["metadata"]["variants"]],"models_unchanged":True,"registration":"DISABLED","generation":"NOT TESTED"}))
"""
 result=json.loads(run(["kubectl","-n",namespace,"exec","-i","deployment/model-manager","--","python3","-c",code],input=password,timeout=100))
 write(out/("stage-validation.json" if namespace=="model-manager-stage" else "production-validation.json"),result);return result
def rollback(out):
 resources=json.loads((out/"stage-resources.json").read_text())
 for item in reversed(resources):
  current=kube("get",item["kind"],item["name"])
  if current["metadata"]["uid"]!=item["uid"]:raise RuntimeError("Replacement resource protected")
  prefix="/apis/apps/v1" if item["kind"]=="Deployment" else "/api/v1"
  plural="deployments" if item["kind"]=="Deployment" else "services"
  options={"apiVersion":"v1","kind":"DeleteOptions","preconditions":{"uid":item["uid"],"resourceVersion":current["metadata"]["resourceVersion"]}}
  run(["kubectl","delete","--raw",prefix+"/namespaces/model-manager-stage/"+plural+"/"+item["name"],"-f","-"],input=json.dumps(options))
 run(["systemctl","stop","watoom-model-manager-stage-broker.service"])
 result={"state":"STAGE_ROLLED_BACK","files":"retained","production":"unchanged"};write(out/"stage-rollback.json",result);return result
def main():
 parser=argparse.ArgumentParser();parser.add_argument("action",choices=["preflight","snapshot","build","build-sdxl","stage","validate","rollback-stage","publish-sdxl-runtime"]);parser.add_argument("--evidence",required=True)
 a=parser.parse_args();out=Path(a.evidence)
 if not out.is_absolute() or not out.is_relative_to("/data/ai/helper-scripts"):raise RuntimeError("Private operational evidence path required")
 out.mkdir(parents=True,exist_ok=True,mode=0o700)
 actions={"preflight":lambda:preflight(),"snapshot":lambda:snapshot(out),"build":lambda:build(out),"build-sdxl":lambda:build_sdxl(out),"stage":lambda:stage(out),"validate":lambda:validate(out),"rollback-stage":lambda:rollback(out),"publish-sdxl-runtime":lambda:__import__("runtime_payload").publish(out)}
 print(json.dumps(actions[a.action]()))
if __name__=="__main__":main()
