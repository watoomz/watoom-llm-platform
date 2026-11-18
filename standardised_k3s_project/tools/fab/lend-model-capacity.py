#!/usr/bin/env python3
"""Lend idle primary model memory through the existing fenced GPU operator protocol."""
import argparse,fcntl,json,os,pathlib,signal,sys,time,urllib.request,urllib.error
ap=argparse.ArgumentParser();ap.add_argument("--evidence",required=True,type=pathlib.Path);ap.add_argument("--completion-file",type=pathlib.Path,help="Existing bounded symbol coordinator status; restores on terminal status");ap.add_argument("--allow-loading-primary",action="store_true");a=ap.parse_args()
out=a.evidence.resolve();assert out.is_relative_to(pathlib.Path("/data/ai/helper-scripts/reports")) and out.is_dir()
lock=(out/"model-capacity.lock").open("a");fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
sys.path.insert(0,"/data/ai/helper-scripts/gpu-controller")
from g3h_service import Runtime,atomic,process_identity
from controller import State
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"watoom-code"))
from maintenance_guard import Maintenance
config=json.loads(pathlib.Path("/data/ai/helper-scripts/config/gpu-controller.json").read_text())
runtime=Runtime(config);maintenance=Maintenance("watoom-code","watoom-code",out,True,True)
owner="operator-"+str(os.getpid())+"-"+str(process_identity(os.getpid()))
held=False;generation=None;error=None
def status(phase,**kw):atomic(out/"model-capacity-status.json",dict(status=phase,pid=os.getpid(),start=process_identity(os.getpid()),owner=owner,generation=generation,**kw))
def idle():
 active=maintenance.request("/api/session/active")
 assert isinstance(active,dict) and set(active)=={"data"} and active["data"]=={},"Native execution is active; preserve it"
 try:
  with urllib.request.urlopen(config["urls"][config["primary"]]+"/slots",timeout=10) as response:slots=json.load(response)
 except urllib.error.URLError:
  if not a.allow_loading_primary:raise
  import subprocess
  deployment=runtime.actuator._get(config["primary"])
  selector=",".join(k+"="+v for k,v in deployment["spec"]["selector"]["matchLabels"].items())
  pods=json.loads(subprocess.check_output(["kubectl","-n","llama-cpp","get","pods","-l",selector,"-o","json"]))["items"]
  assert pods and all(not x.get("ready") for p in pods for x in p["status"].get("containerStatuses",[]))
  for pod in pods:
   url="http://"+pod["status"]["podIP"]+":8000/health"
   try:
    with urllib.request.urlopen(url,timeout=3):raise AssertionError("Primary is serving; use real slots")
   except urllib.error.HTTPError as response:
    body=json.load(response)
    assert response.code==503 and body.get("error",{}).get("message")=="Loading model","Not proven loading-only"
  return
 assert isinstance(slots,list) and slots and all(x.get("is_processing") is False for x in slots),"Inference active or unverifiable"
def stop(*_):raise KeyboardInterrupt()
signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
try:
 deadline=time.monotonic()+3600
 while time.monotonic()<deadline:
  if a.completion_file:
   end=json.loads(a.completion_file.read_text())
   if end["status"] in {"COMPLETE","BLOCKED_MODULE_FAILURE","BLOCKED_TIME_BUDGET","PASS_CORE_BLUEPRINTS","BLOCKED_HEADROOM","BLOCKED_NATIVE_LOAD_OR_COMPILE","PASS_HYPER_ENGINE","BLOCKED_HYPER_ENGINE"}:
    status("RESTORED",reason="Target already terminal; no capacity taken",inference_verified=False);raise SystemExit(0)
  try:idle();break
  except (AssertionError,urllib.error.URLError) as wait:
   status("WAITING_FOR_IDLE",reason=str(wait));time.sleep(15)
 else:raise RuntimeError("No safe idle window within one hour; no capacity taken")
 with runtime.store.exclusive():
  before=runtime.store.load()
  assert before.phase=="qwen-ready" and not before.owner and not before.uncertain and not runtime.journal.pending()
  inventory={n:runtime.actuator._get(n) for n in runtime.actuator.allowed}
  assert inventory[config["primary"]]["spec"]["replicas"]==1
  assert all(d["spec"]["replicas"]==0 for n,d in inventory.items() if n!=config["primary"])
  snapshot=out/"models-before.private.json";assert not snapshot.exists()
  atomic(snapshot,inventory);os.chmod(snapshot,0o600)
  idle();generation=before.generation+1
  atomic(runtime.owner_path,dict(kind="operator",job=owner,pid=os.getpid(),start=process_identity(os.getpid())))
  runtime.store.save(State("acquiring",owner,generation));held=True;runtime.actuator.generation=generation
  status("DRAINING_IDLE_PRIMARY")
  for _ in range(3):time.sleep(2);idle()
  runtime.actuator.scale(config["primary"],0,generation)
  assert runtime.actuator.stopped(config["primary"])
  runtime.audit("FAB_CAPACITY_ACQUIRED",runtime.store.load())
 status("CAPACITY_LENT")
 if a.completion_file:
  completion=a.completion_file.resolve()
  assert completion.is_relative_to(pathlib.Path("/data/ai/helper-scripts/reports")) and completion.name in {"symbol-coverage.json","native-status.json"}
  current=json.loads(completion.read_text());watched_pid=current["pid"];watched_start=process_identity(watched_pid)
  assert watched_start is not None
  command=pathlib.Path("/proc",str(watched_pid),"cmdline").read_bytes()
  assert (completion.name=="symbol-coverage.json" and b"backfill-crash-symbols.py" in command) or (completion.name=="native-status.json" and any(x in command for x in [b"accept-hyper-combat.py",b"repair-hyper-engine.py"]))
  terminal={"COMPLETE","BLOCKED_MODULE_FAILURE","BLOCKED_TIME_BUDGET","PASS_CORE_BLUEPRINTS","BLOCKED_HEADROOM","BLOCKED_NATIVE_LOAD_OR_COMPILE","PASS_HYPER_ENGINE","BLOCKED_HYPER_ENGINE"}
 else:
  coordinator=json.loads((out.parent/"fab-capacity-coordinator.json").read_text())
  completion=pathlib.Path(coordinator["evidence"])/"fab-capacity-status.json"
  current=json.loads(completion.read_text());watched_pid=current["pid"];watched_start=process_identity(watched_pid)
  terminal={"RESTORED"}
 deadline=time.monotonic()+24*3600
 while time.monotonic()<deadline:
  current=json.loads(completion.read_text())
  if current["status"] in terminal:break
  if current["pid"]!=watched_pid or process_identity(watched_pid)!=watched_start:raise RuntimeError("Watched coordinator ended or changed identity; restore model")
  time.sleep(15)
 else:raise RuntimeError("24-hour capacity budget reached")
except SystemExit as e:
 if e.code:error=str(e)
except BaseException as e:error=type(e).__name__+": "+str(e)
finally:
 if held:
  status("RESTORING",reason=error)
  with runtime.store.exclusive():
   state=runtime.store.load()
   assert (state.owner,state.generation)==(owner,generation),"Ownership moved; use supported reconciliation"
   runtime.store.save(State("restoring",owner,generation,True))
   runtime.controller._restore(owner,generation)
   runtime.audit("FAB_CAPACITY_RELEASED",runtime.store.load())
 status("RESTORED",reason=error,inference_verified=held)
if error:raise RuntimeError(error)
