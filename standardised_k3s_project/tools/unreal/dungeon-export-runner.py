#!/usr/bin/env python3
"""Bound one owner-authorized pack bake under the existing GPU operator supervisor."""
import argparse,pathlib,json,subprocess,os,time,hashlib,signal,fcntl,sys
ap=argparse.ArgumentParser();ap.add_argument("--evidence",required=True,type=pathlib.Path);a=ap.parse_args()
e=a.evidence.resolve()
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"watoom-toolkit"))
from asset_catalog import atomic
if not e.is_relative_to("/data/ai/helper-scripts/reports"):raise ValueError("Evidence root")
plan=json.loads((e/"dungeon-export-plan.json").read_text())
root=pathlib.Path(plan["project"]).resolve();engine=pathlib.Path(plan["engine"]).resolve()
if not root.is_relative_to("/data/ai/builds"):raise ValueError("Isolated project root required")
if not engine.is_relative_to("/data/ai/builds"):
 if not engine.is_relative_to("/data/ai/toolchains/unreal"):raise ValueError("Accepted engine root required")
 expected=plan.get("engine_sha256","")
 if len(expected)!=64 or hashlib.file_digest((engine/"Engine/Binaries/Linux/UnrealEditor").open("rb"),"sha256").hexdigest()!=expected:
  raise ValueError("Published runtime editor checksum differs from pinned acceptance")
assert {"probe.py","RenderProbe.uproject","selected-modules.json"} <= set(plan["sha256"]),"Required task pins missing"
for name in plan["sha256"]:
 assert not pathlib.PurePosixPath(name).is_absolute() and ".." not in pathlib.PurePosixPath(name).parts and not (root/name).is_symlink() and (root/name).resolve().is_relative_to(root),"Unsafe task input"
 if hashlib.sha256((root/name).read_bytes()).hexdigest()!=plan["sha256"][name]:raise ValueError("Pinned task changed")
lock=(e/"dungeon-export.lock").open("a");fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
available=int(next(x.split()[1] for x in pathlib.Path("/proc/meminfo").read_text().splitlines() if x.startswith("MemAvailable:")))*1024
hard=min(12*1024**3,available-2*1024**3)
if hard<6*1024**3:raise RuntimeError("Insufficient post-drain memory for pack bake")
group=pathlib.Path("/sys/fs/cgroup")/("watoom-dungeon-export-"+str(os.getpid()));group.mkdir()
for name,value in {"memory.max":hard,"memory.high":hard-1024**3,"memory.swap.max":0,"cpu.max":"600000 100000","pids.max":512}.items():(group/name).write_text(str(value))
def child_setup():
 (group/"cgroup.procs").write_text(str(os.getpid()))
 os.unshare(os.CLONE_NEWNS)
 subprocess.run(["mount","--make-rprivate","/"],check=True)
 for target in [engine,pathlib.Path("/data/ai/assets")]:
  subprocess.run(["mount","--bind",str(target),str(target)],check=True)
  subprocess.run(["mount","-o","remount,bind,ro",str(target)],check=True)
 os.setgroups([]);os.setgid(1009);os.setuid(1009)
command=["setpriv","--no-new-privs","python3",str(pathlib.Path(__file__).with_name("render-editor.py")),str(root),str(engine),str(root/"probe.py")]
environment={**os.environ,"HOME":str(root/"home"),"XDG_CACHE_HOME":str(root/"home/.cache"),"XDG_CONFIG_HOME":str(root/"home/.config"),"XDG_DATA_HOME":str(root/"home/.local/share")}
process=None;started=time.monotonic();reason=None;last_status=0
def stop(*_):raise KeyboardInterrupt
signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
try:
 with (e/"dungeon-export-editor.log").open("ab") as log:
  process=subprocess.Popen(command,env=environment,preexec_fn=child_setup,stdout=log,stderr=subprocess.STDOUT)
  while process.poll() is None:
   if time.monotonic()-last_status>=10:
    atomic(e/"dungeon-export-status.json",{"status":"RUNNING","pid":os.getpid(),"editor_runner_pid":process.pid,"seconds":round(time.monotonic()-started,2),"memory_current":int((group/"memory.current").read_text()),"memory_max":hard,"cgroup":str(group)})
    last_status=time.monotonic()
   if time.monotonic()-started>1200:raise TimeoutError("Pack bake exceeded20minute budget")
   free=int(next(x.split()[1] for x in pathlib.Path("/proc/meminfo").read_text().splitlines() if x.startswith("MemAvailable:")))*1024
   if free<2*1024**3:raise RuntimeError("Host memory reserve reached")
   time.sleep(2)
  if process.returncode:raise RuntimeError("Editor exit "+str(process.returncode))
 receipt=json.loads((root/"dungeon-export-receipt.json").read_text())
 if receipt["status"]!="PASS":raise RuntimeError("Pack export receipt did not pass")
except BaseException as error:
 reason=type(error).__name__+": "+str(error)
finally:
 if process is not None and process.poll() is None:
  process.terminate()
  try:process.wait(timeout=15)
  except subprocess.TimeoutExpired:(group/"cgroup.kill").write_text("1");process.wait()
 if (group/"cgroup.procs").read_text().strip():(group/"cgroup.kill").write_text("1")
 result={"status":"FAIL" if reason else "PASS","reason":reason,"seconds":round(time.monotonic()-started,2),"memory_max":hard,"memory_peak":int((group/"memory.peak").read_text()),"memory_events":(group/"memory.events").read_text(),"cgroup":str(group)}
 atomic(e/"dungeon-export-status.json",result)
if reason:raise RuntimeError(reason)
