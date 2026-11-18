#!/usr/bin/env python3
"""Benchmark the primary model with CUDA graphs off vs on, through the fenced GPU operator protocol.

Waits for a genuinely idle app and model, takes GPU ownership exactly as lend-model-capacity.py does,
runs two unlabelled pods copied from the primary's pod template (only GGML_CUDA_DISABLE_GRAPHS differs;
no service or router can reach them), then always restores the primary through the controller.
  benchmark-cuda-graphs.py --evidence /data/ai/helper-scripts/reports/<new dir>
"""
import argparse,copy,fcntl,json,os,pathlib,signal,statistics,subprocess,sys,time,urllib.request,urllib.error
ap=argparse.ArgumentParser();ap.add_argument("--evidence",required=True,type=pathlib.Path);ap.add_argument("--runs",type=int,default=3);a=ap.parse_args()
out=a.evidence.resolve();assert out.is_relative_to(pathlib.Path("/data/ai/helper-scripts/reports")) and not out.exists()
out.mkdir(mode=0o700);lock=(out/"benchmark.lock").open("a");fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
sys.path.insert(0,"/data/ai/helper-scripts/gpu-controller")
from g3h_service import Runtime,atomic,process_identity
from controller import State
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"watoom-code"))
from maintenance_guard import Maintenance
config=json.loads(pathlib.Path("/data/ai/helper-scripts/config/gpu-controller.json").read_text())
runtime=Runtime(config);maintenance=Maintenance("watoom-code","watoom-code",out,True,True)
owner="operator-"+str(os.getpid())+"-"+str(process_identity(os.getpid()))
NS="llama-cpp";PRIMARY=config["primary"];held=False;generation=None;error=None;results={}
def status(phase,**kw):atomic(out/"status.json",dict(status=phase,pid=os.getpid(),owner=owner,generation=generation,**kw))
def idle():
 active=maintenance.request("/api/session/active")
 assert isinstance(active,dict) and set(active)=={"data"} and active["data"]=={},"Native execution is active; preserve it"
 with urllib.request.urlopen(config["urls"][PRIMARY]+"/slots",timeout=10) as response:slots=json.load(response)
 assert isinstance(slots,list) and slots and all(x.get("is_processing") is False for x in slots),"Inference active or unverifiable"
def kubectl(*args,input=None):
 return subprocess.run(["kubectl","-n",NS,*args],input=input,capture_output=True,text=True,check=True).stdout
def post(url,body,timeout=600):
 request=urllib.request.Request(url,data=json.dumps(body).encode(),headers={"Content-Type":"application/json"})
 with urllib.request.urlopen(request,timeout=timeout) as response:return json.load(response)
# Fixed, deterministic workload: a long coding context (prompt processing) and two generations.
CONTEXT="\n".join(f"def handler_{i}(request):\n    # validate, transform and store record {i}\n    payload=request.json()\n    if not payload.get('id'):raise ValueError('id required')\n    return store.save({{'id':payload['id'],'n':{i}}})\n" for i in range(60))
PROMPTS=[("long-context",CONTEXT+"\n# Review the handlers above. List three concrete bugs or risks, then write a corrected handler_0.\n",384),
         ("short",'# Python: parse an ISO-8601 duration like "P1DT2H30M" into seconds, with unit tests.\nimport re\n\ndef parse_duration(text):\n',384)]
def bench(name,graphs):
 template=json.loads(kubectl("get","deploy",PRIMARY,"-o","json"))["spec"]["template"]
 spec=copy.deepcopy(template["spec"]);container=spec["containers"][0]
 container["env"]=[e for e in container.get("env",[]) if e["name"]!="GGML_CUDA_DISABLE_GRAPHS"]+([] if graphs else [{"name":"GGML_CUDA_DISABLE_GRAPHS","value":"1"}])
 container.pop("livenessProbe",None);spec["restartPolicy"]="Never"
 pod={"apiVersion":"v1","kind":"Pod","metadata":{"name":name,"namespace":NS,"labels":{"watoom-test-owner":"cuda-graphs-benchmark"}},"spec":spec}
 kubectl("create","-f","-",input=json.dumps(pod))
 try:
  deadline=time.monotonic()+900;ip=None
  while time.monotonic()<deadline:
   p=json.loads(kubectl("get","pod",name,"-o","json"))
   if p["status"].get("phase") in ("Failed","Succeeded"):raise RuntimeError(name+" exited during load")
   ip=p["status"].get("podIP")
   if ip:
    try:
     with urllib.request.urlopen(f"http://{ip}:8000/health",timeout=5) as r:
      if r.status==200:break
    except (urllib.error.URLError,OSError):pass
   time.sleep(5)
  else:raise RuntimeError(name+" did not become healthy")
  runs={};post(f"http://{ip}:8000/completion",{"prompt":"Hello","n_predict":8,"temperature":0,"seed":1,"cache_prompt":False})  # warm-up
  for label,prompt,n in PROMPTS:
   rows=[]
   for _ in range(a.runs):
    r=post(f"http://{ip}:8000/completion",{"prompt":prompt,"n_predict":n,"temperature":0,"top_k":1,"seed":1,"cache_prompt":False})
    t=r["timings"];rows.append({"predicted_per_second":t.get("predicted_per_second"),"prompt_per_second":t.get("prompt_per_second"),"prompt_n":t.get("prompt_n"),
     "predicted_n":t.get("predicted_n"),"draft_n":t.get("draft_n"),"draft_n_accepted":t.get("draft_n_accepted"),"text_sha":__import__("hashlib").sha256(r["content"].encode()).hexdigest()[:16]})
   runs[label]=rows
  logs=kubectl("logs",name,"--tail=400");(out/(name+".log")).write_text(logs)
  return runs
 finally:subprocess.run(["kubectl","-n",NS,"delete","pod",name,"--wait=true","--timeout=120s"],capture_output=True)
def stop(*_):raise KeyboardInterrupt()
signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
try:
 deadline=time.monotonic()+3600
 while time.monotonic()<deadline:
  try:idle();break
  except (AssertionError,urllib.error.URLError) as wait:status("WAITING_FOR_IDLE",reason=str(wait));time.sleep(15)
 else:raise RuntimeError("No safe idle window within one hour; nothing changed")
 with runtime.store.exclusive():
  before=runtime.store.load()
  assert before.phase=="qwen-ready" and not before.owner and not before.uncertain and not runtime.journal.pending()
  inventory={n:runtime.actuator._get(n) for n in runtime.actuator.allowed}
  assert inventory[PRIMARY]["spec"]["replicas"]==1 and all(d["spec"]["replicas"]==0 for n,d in inventory.items() if n!=PRIMARY)
  atomic(out/"models-before.private.json",inventory);os.chmod(out/"models-before.private.json",0o600)
  idle();generation=before.generation+1
  atomic(runtime.owner_path,dict(kind="operator",job=owner,pid=os.getpid(),start=process_identity(os.getpid())))
  runtime.store.save(State("acquiring",owner,generation));held=True;runtime.actuator.generation=generation
  status("DRAINING_IDLE_PRIMARY")
  for _ in range(3):time.sleep(2);idle()
  runtime.actuator.scale(PRIMARY,0,generation);assert runtime.actuator.stopped(PRIMARY)
  runtime.audit("CUDA_GRAPHS_BENCHMARK_ACQUIRED",runtime.store.load())
 for graphs in (False,True):
  status("BENCHMARKING",graphs=graphs)
  results["graphs_on" if graphs else "graphs_off"]=bench("watoom-bench-graphs-"+("on" if graphs else "off"),graphs)
  atomic(out/"results.json",results)
except BaseException as e:error=type(e).__name__+": "+str(e)
finally:
 if held:
  status("RESTORING",reason=error)
  with runtime.store.exclusive():
   state=runtime.store.load()
   assert (state.owner,state.generation)==(owner,generation),"Ownership moved; use supported reconciliation"
   runtime.store.save(State("restoring",owner,generation,True))
   runtime.controller._restore(owner,generation)
   runtime.audit("CUDA_GRAPHS_BENCHMARK_RELEASED",runtime.store.load())
 summary={}
 for k,v in results.items():
  summary[k]={label:{"decode_tps_median":statistics.median(r["predicted_per_second"] for r in rows),"prompt_tps_median":statistics.median(r["prompt_per_second"] for r in rows),
   "draft_acceptance":round(sum(r["draft_n_accepted"] or 0 for r in rows)/max(1,sum(r["draft_n"] or 0 for r in rows)),3),"outputs":sorted({r["text_sha"] for r in rows})} for label,rows in v.items()}
 status("RESTORED" if held else "NOT_STARTED",reason=error,summary=summary,inference_restored=held)
 print(json.dumps({"error":error,"summary":summary},indent=1))
if error:raise SystemExit(1)
