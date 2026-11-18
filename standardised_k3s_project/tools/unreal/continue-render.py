#!/usr/bin/env python3
"""Continue one existing dependency build through isolated render and Godot technical gates."""
import argparse,pathlib,json,subprocess,time,os,fcntl,shutil,struct,hashlib,signal
ap=argparse.ArgumentParser();ap.add_argument("--evidence",required=True,type=pathlib.Path);ap.add_argument("--compile-pid",type=int);ap.add_argument("--resume",action="store_true");a=ap.parse_args()
if a.resume==(a.compile_pid is not None):ap.error("choose either --compile-pid or --resume")
def interrupted(*_):raise KeyboardInterrupt
signal.signal(signal.SIGTERM,interrupted)
r=a.evidence.resolve();tools=pathlib.Path(__file__).parent
lock=(r/"render-continuation.lock").open("a");fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
def receipt(state,**kw):
 (r/"render-continuation-status.json").write_text(json.dumps({"status":state,"pid":os.getpid(),**kw},indent=2))
def run(args,log,timeout):
 with (r/log).open("ab") as out:
  child=subprocess.Popen(args,stdout=out,stderr=subprocess.STDOUT,cwd="/data/ai/builds")
  try:code=child.wait(timeout=timeout)
  except BaseException:
   if child.poll() is None:
    child.terminate()
    try:child.wait(timeout=900)
    except subprocess.TimeoutExpired:raise RuntimeError("Child supervisor still alive; preserve its ownership and inspect before recovery")
   raise
  if code:raise subprocess.CalledProcessError(code,args)
try:
 b=pathlib.Path(json.loads((r/"build-plan.json").read_text())["isolated_root"])
 root=b/"acceptance/RenderProbe"
 if a.resume:
  previous=json.loads((r/"acceptance-render-status.json").read_text())
  checkpoint=previous["status"]=="BLOCKED" and previous.get("stop_reason")=="bounded_time_checkpoint"
  retry=json.loads((r/"render-resume-plan.json").read_text()).get("verified_pre_engine_failure",{})
  repaired=previous["status"]=="FAIL" and previous.get("log")==retry.get("log") and hashlib.sha256(pathlib.Path(previous["log"]).read_bytes()).hexdigest()==retry.get("sha256")
  export_retry=json.loads((r/"render-resume-plan.json").read_text()).get("verified_export_result_failure",{})
  export_repaired=(previous["status"]=="FAIL" and previous.get("log")==export_retry.get("log")
    and hashlib.sha256(pathlib.Path(previous["log"]).read_bytes()).hexdigest()==export_retry.get("sha256")
    and hashlib.sha256((root/"render-probe-error.txt").read_bytes()).hexdigest()==export_retry.get("error_sha256")
    and hashlib.sha256((tools/"render-probe.py").read_bytes()).hexdigest()==export_retry.get("repaired_probe_sha256"))
  async_retry=json.loads((r/"render-resume-plan.json").read_text()).get("verified_async_lifetime_failure",{})
  async_repaired=(previous["status"]=="PASS" and previous.get("exit_code")==0
    and previous.get("log")==async_retry.get("log")
    and hashlib.sha256(pathlib.Path(previous["log"]).read_bytes()).hexdigest()==async_retry.get("sha256")
    and hashlib.sha256((root/"render-probe.json").read_bytes()).hexdigest()==async_retry.get("receipt_sha256")
    and hashlib.sha256((tools/"render-probe.py").read_bytes()).hexdigest()==async_retry.get("repaired_probe_sha256"))
  diagnostic=json.loads((r/"render-resume-plan.json").read_text()).get("verified_visual_shutdown_diagnostic",{})
  diagnostic_ready=(previous["status"]=="FAIL"
    and previous.get("log")==diagnostic.get("log")
    and hashlib.sha256(pathlib.Path(previous["log"]).read_bytes()).hexdigest()==diagnostic.get("sha256")
    and all(hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()==h for p,h in diagnostic.get("helpers",{}).items())
    and bool(diagnostic.get("helpers")))
  assert checkpoint or repaired or export_repaired or async_repaired or diagnostic_ready,"Resume requires a pinned and inspected checkpoint/repair"
  assert json.loads((r/"acceptance-render-compile-status.json").read_text())["status"]=="PASS"
  assert json.loads((root/"render-api-probe.json").read_text())["status"]=="PASS"
  pins=json.loads((r/"render-resume-plan.json").read_text())["pins"]
  for path,digest in pins.items():
   assert hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()==digest,"Accepted engine/plugin/fixture changed; revalidation required"
 else:
  receipt("WAITING_EXISTING_PLUGIN_BUILD",compile_pid=a.compile_pid)
  deadline=time.monotonic()+1900
  while pathlib.Path("/proc",str(a.compile_pid)).exists():
   if time.monotonic()>deadline:raise RuntimeError("Existing compile exceeded continuation wait budget; do not launch another build")
   time.sleep(5)
  compile_status=json.loads((r/"acceptance-render-compile-status.json").read_text())
  assert compile_status["status"]=="PASS","Dependency compile did not pass"
  # Verify plugins before unloading a model again.
  receipt("PLUGIN_API_PREFLIGHT")
  run(["python3",str(tools/"recover-editor.py"),"--evidence",str(r),"--acceptance","render-api","--run"],"render-api-coordinator.log",1950)
  b=pathlib.Path(json.loads((r/"build-plan.json").read_text())["isolated_root"])
  root=b/"acceptance/RenderProbe"
  assert json.loads((root/"render-api-probe.json").read_text())["status"]=="PASS"
 deadline=time.monotonic()+600
 while json.loads((r/"render-gpu-status.json").read_text())["status"]!="RESTORED":
  if time.monotonic()>deadline:raise RuntimeError("Prior GPU restoration not verified; refusing acquisition")
  time.sleep(5)
 receipt("RENDERING")
 run(["python3",str(tools/"accept-render.py"),"--evidence",str(r)],"render-second-coordinator.log",5400)
 assert json.loads((r/"render-gpu-status.json").read_text())["status"]=="RESTORED"
 probe=json.loads((root/"render-probe.json").read_text())
 assert probe["status"]=="PASS","Rendered scene receipt did not pass"
 assert (root/"editor-viewport.png").stat().st_size>1000
 glb=(root/"recovery-room.glb").read_bytes()
 assert struct.unpack_from("<4sII",glb)==(b"glTF",2,len(glb))
 receipt("GODOT_IMPORT")
 target=b/"acceptance/GodotRegression";target.mkdir(exist_ok=True)
 shutil.copyfile(root/"recovery-room.glb",target/"recovery-room.glb")
 shutil.copyfile(tools/"godot-regression.gd",target/"verify.gd")
 (target/"project.godot").write_text('config_version=5\n[application]\nconfig/name="Unreal recovery regression"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n')
 for p in [target,*target.iterdir()]:os.chown(p,1009,1009)
 godot="/data/ai/toolchains/godot/4.7.2/godot"
 command=["env","HOME="+str(b/"home"),"XDG_DATA_HOME="+str(b/"home/.local/share"),"XDG_CONFIG_HOME="+str(b/"home/.config"),"XDG_CACHE_HOME="+str(b/"home/.cache"),"USER=opencode","LOGNAME=opencode","setpriv","--reuid=1009","--regid=1009","--clear-groups","--no-new-privs",godot,"--headless","--path",str(target)]
 # GNU timeout owns the entire Godot process group and bounds import/verification.
 run(["timeout","--signal=TERM","--kill-after=10s","120s",*command,"--editor","--import"],"godot-import.log",135)
 run(["timeout","--signal=TERM","--kill-after=10s","60s",*command,"--script","res://verify.gd"],"godot-regression.log",75)
 assert json.loads((target/"godot-regression.json").read_text())["status"]=="PASS"
 receipt("TECHNICAL_PASS_VISUAL_REVIEW_INTEGRATION_PENDING",render_receipt=str(root/"render-probe.json"),capture=str(root/"editor-viewport.png"),godot_receipt=str(target/"godot-regression.json"))
except BaseException as e:
 receipt("BLOCKED",reason=type(e).__name__+": "+str(e))
 raise
