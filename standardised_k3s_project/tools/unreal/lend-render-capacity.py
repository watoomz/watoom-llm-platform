#!/usr/bin/env python3
"""Lend Enshrouded capacity to one checkpointed editor attempt; restore exact replicas."""
import argparse,fcntl,json,os,pathlib,signal,subprocess,sys,time,urllib.request,urllib.error
ap=argparse.ArgumentParser();ap.add_argument("--evidence",required=True,type=pathlib.Path);ap.add_argument("--keep-game",action="store_true",help="Leave game replicas untouched; renderer still profiles actual headroom");a=ap.parse_args()
r=a.evidence.resolve();assert r.is_relative_to("/data/ai/helper-scripts/reports")
lock=(r/"render-capacity.lock").open("a");fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
sys.path.insert(0,"/data/ai/helper-scripts/gpu-controller")
from g3h_service import Runtime,atomic,process_identity
config=json.loads(pathlib.Path("/data/ai/helper-scripts/config/gpu-controller.json").read_text())
runtime=Runtime(config)
game=None;stopped=False;child=None;code=2;error=None
def status(phase,**kw):atomic(r/"render-capacity-status.json",{"status":phase,"pid":os.getpid(),"start":process_identity(os.getpid()),**kw})
def kub(*args):return json.loads(subprocess.check_output(["kubectl",*args,"-o","json"],timeout=40))
def replicas(deployment,count):
 return kub("-n","enshrouded","patch","deploy","enshrouded","--type=json","-p",json.dumps([
  {"op":"test","path":"/metadata/uid","value":deployment["metadata"]["uid"]},
  {"op":"test","path":"/spec/replicas","value":deployment["spec"]["replicas"]},
  {"op":"replace","path":"/spec/replicas","value":count}]))
def stop(*_):raise KeyboardInterrupt
signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
try:
 sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"watoom-code"))
 from maintenance_guard import Maintenance
 maintenance=Maintenance("watoom-code","watoom-code",r,True,True)
 idle_deadline=time.monotonic()+3600
 while time.monotonic()<idle_deadline:
  active=maintenance.request("/api/session/active")
  assert isinstance(active,dict) and set(active)=={"data"} and isinstance(active["data"],dict),"Execution contract invalid"
  state=json.loads((pathlib.Path(config["state_root"])/"state.json").read_text())
  idle=False
  if not active["data"] and state["phase"]=="qwen-ready" and not state["owner"] and not state["uncertain"]:
   try:
    with urllib.request.urlopen(config["urls"][config["primary"]]+"/slots",timeout=10) as response:slots=json.load(response)
    idle=isinstance(slots,list) and bool(slots) and all(slot.get("is_processing") is False for slot in slots)
   except urllib.error.URLError:idle=False
  if idle:break
  status("WAITING_FOR_IDLE",active_executions=len(active["data"]))
  time.sleep(15)
 else:raise RuntimeError("No safe idle window within one-hour waiting budget; no capacity taken")
 game=kub("-n","enshrouded","get","deploy","enshrouded")
 assert game["spec"]["template"]["spec"].get("terminationGracePeriodSeconds",30)>=30
 snapshot=r/"render-capacity-game-before.private.json"
 atomic(snapshot,game);os.chmod(snapshot,0o600)
 if game["spec"]["replicas"] and not a.keep_game:
  status("STOPPING_GAME_GRACEFULLY")
  replicas(game,0);stopped=True
  deadline=time.monotonic()+150
  while time.monotonic()<deadline:
   deployment=kub("-n","enshrouded","get","deploy","enshrouded")
   pods=kub("-n","enshrouded","get","pods","-l","app=enshrouded")["items"]
   if not pods and deployment.get("status",{}).get("replicas",0)==0:break
   time.sleep(3)
  else:raise RuntimeError("Game graceful shutdown not verified")
 status("WAITING_PRIOR_GPU_RESTORATION")
 deadline=time.monotonic()+1200
 while time.monotonic()<deadline:
  state=json.loads((pathlib.Path(config["state_root"])/"state.json").read_text())
  if state["phase"]=="qwen-ready" and not state["owner"] and not state["uncertain"]:break
  saved=json.loads((r/"render-gpu-status.json").read_text())
  if state["owner"]!=saved["owner"]:raise RuntimeError("GPU ownership moved to unrelated work; do not interfere")
  if state["phase"]=="recovery-required" and process_identity(saved["pid"]) is None:
   runtime.handle({"action":"recover","job":state["owner"],"generation":state["generation"]},private=True,pid=os.getpid(),uid=0)
   after=json.loads((pathlib.Path(config["state_root"])/"state.json").read_text())
   assert after["phase"]=="qwen-ready" and not after["uncertain"]
   saved.update(status="RESTORED",reason="Verified dead prior operator recovered through controller")
   atomic(r/"render-gpu-status.json",saved)
  time.sleep(3)
 else:raise RuntimeError("Prior restoration exceeded bounded waiting budget")
 # The previous continuation owns the same lock until its failed attempt is fully reconciled.
 deadline=time.monotonic()+30
 while time.monotonic()<deadline:
  old=json.loads((r/"render-continuation-status.json").read_text())
  if old["status"] not in ("RENDERING","PLUGIN_API_PREFLIGHT","WAITING_EXISTING_PLUGIN_BUILD"):break
  time.sleep(1)
 else:raise RuntimeError("Prior continuation has not ended; refusing duplicate")
 status("STARTING_EXPANDED_RENDER",cpu_thread_ceiling=min(10,max(1,len(os.sched_getaffinity(0))-2)),
        memory_ceiling_bytes=24*1024**3,host_reserve_bytes=2*1024**3)
 environment={**os.environ,"WATOOM_RENDER_EXPANDED":"1"}
 with (r/"expanded-render-continuation.log").open("ab") as out:
  child=subprocess.Popen(["python3",str(pathlib.Path(__file__).with_name("continue-render.py")),"--evidence",str(r),"--resume"],
   env=environment,stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT)
  try:code=child.wait(timeout=6600)
  except subprocess.TimeoutExpired:
   child.terminate()
   raise RuntimeError("Expanded continuation exceeded bounded budget")
except BaseException as e:error=type(e).__name__+": "+str(e)
finally:
 if child is not None and child.poll() is None:
  child.terminate()
  try:child.wait(timeout=900)
  except subprocess.TimeoutExpired:
   status("RECOVERY_REQUIRED",reason="GPU continuation still alive; do not bypass its ownership")
   raise RuntimeError("Continuation cleanup incomplete; retain capacity snapshot")
 if stopped:
  status("RESTORING_GAME",reason=error)
  current=kub("-n","enshrouded","get","deploy","enshrouded")
  assert current["metadata"]["uid"]==game["metadata"]["uid"] and current["spec"]["replicas"]==0
  assert {k:v for k,v in current["spec"].items() if k!="replicas"}=={k:v for k,v in game["spec"].items() if k!="replicas"},"Game configuration changed; preserve user changes"
  replicas(current,game["spec"]["replicas"])
 status("RESTORED",continuation_exit=code,reason=error)
if error:raise RuntimeError(error)
raise SystemExit(code)
