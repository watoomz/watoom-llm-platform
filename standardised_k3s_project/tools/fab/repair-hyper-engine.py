#!/usr/bin/env python3
"""Genuine plugin-only target build in an isolated accepted-engine CoW overlay."""
import argparse,fcntl,hashlib,json,os,pathlib,shutil,subprocess,time
ap=argparse.ArgumentParser();ap.add_argument("--evidence",required=True,type=pathlib.Path);ap.add_argument("--resume",action="store_true",help="Reuse verified prior overlay and project paths after terminal owned job");ap.add_argument("--finalize-target",action="store_true",help="Complete cached isolated project target including UBT metadata; never edits manifests");ap.add_argument("--hold-capacity",action="store_true",help="Bounded acceptance-wide capacity owner; release through acceptance-release.json");a=ap.parse_args()
out=a.evidence.resolve();assert out.is_relative_to(pathlib.Path("/data/ai/helper-scripts/reports"));out.mkdir(mode=0o770,exist_ok=True)
lock=pathlib.Path("/data/ai/helper-scripts/reports/hyper-engine-repair.lock").open("a");fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
def status(value,**kw):
 temp=out/"native-status.new";temp.write_text(json.dumps(dict(status=value,pid=os.getpid(),**kw),indent=2));os.replace(temp,out/"native-status.json")
if a.hold_capacity:
 assert not a.resume
 status("ACCEPTANCE_CAPACITY_HOLD")
 deadline=time.monotonic()+12*3600
 release=out/"acceptance-release.json"
 assert not release.exists(),"Use fresh hold evidence"
 while time.monotonic()<deadline:
  if release.exists():
   assert json.loads(release.read_text())["release"] is True
   status("PASS_HYPER_ENGINE",scope="Capacity owner released; not engine acceptance proof")
   raise SystemExit(0)
  time.sleep(10)
 status("BLOCKED_HYPER_ENGINE",reason="Acceptance capacity 12-hour boundary")
 raise SystemExit(2)
prior=None;attempt=time.strftime("%Y%m%dT%H%M%SZ",time.gmtime())
if a.resume:
 prior=json.loads((out/"build-plan.json").read_text())
 old=json.loads((out/"job.json").read_text());oldname=old["metadata"]["name"]
 oldjob=json.loads(subprocess.check_output(["kubectl","-n","watoom-code","get","job",oldname,"-o","json"]))
 assert (oldjob.get("status",{}).get("failed") or oldjob.get("status",{}).get("succeeded")) and not oldjob.get("status",{}).get("active") and not oldjob.get("status",{}).get("terminating"),"Prior job not terminal"
 pods=json.loads(subprocess.check_output(["kubectl","-n","watoom-code","get","pods","-l","job-name="+oldname,"-o","json"]))["items"]
 assert all(p["status"]["phase"] not in ("Running","Pending") for p in pods),"Prior worker remains"
 assert json.loads((out/"native-status.json").read_text())["status"]=="BLOCKED_HYPER_ENGINE","Only a blocked attempt may resume"
 archive=out/"attempt-history"/attempt;archive.mkdir(parents=True)
 for name in ["build-plan.json","job.json","native-status.json","build.private.log"]:
  if (out/name).exists():shutil.copy2(out/name,archive/name)
status("WAITING_FOR_HEADROOM",resume=a.resume)

deadline=time.monotonic()+3600
while time.monotonic()<deadline:
 free=int(next(x.split()[1] for x in pathlib.Path("/proc/meminfo").read_text().splitlines() if x.startswith("MemAvailable:")))*1024
 if free>14*1024**3:break
 time.sleep(10)
else:status("BLOCKED_HYPER_ENGINE",reason="Headroom budget");raise SystemExit(2)
base=out.parent/"hyper-native-explicit-plugins"
profile=json.loads((pathlib.Path(__file__).resolve().parents[1]/"unreal/profiles/hyper-combat.json").read_text())
engine=pathlib.Path(profile["accepted_engine"])
build=pathlib.Path("/data/ai/builds")/out.name
if a.resume:
 assert pathlib.Path(prior["isolated_engine"])==build/"source" and build.is_dir()
 mount=json.loads(subprocess.check_output(["findmnt","-J","-T",str(build/"source"),"-o","TARGET,FSTYPE,OPTIONS"]))["filesystems"][0]
 assert mount["target"]==str(build/"source") and mount["fstype"]=="overlay" and "upperdir="+str(build/"upper") in mount["options"]
 lower=json.loads(subprocess.check_output(["findmnt","-J","-T",str(build/"lower"),"-o","TARGET,OPTIONS"]))["filesystems"][0]
 assert lower["target"]==str(build/"lower") and "ro" in lower["options"].split(",")
else:
 assert not build.exists(),"Inspect previous attempt"
 assert shutil.disk_usage("/data").free>300*1024**3
 build.mkdir(mode=0o750)
 for name in ["lower","upper","work","source"]:
  (build/name).mkdir(mode=0o750);os.chown(build/name,1009,1009)
 subprocess.run(["mount","--bind",str(engine),str(build/"lower")],check=True)
 subprocess.run(["mount","-o","remount,bind,ro",str(build/"lower")],check=True)
 subprocess.run(["mount","-t","overlay","overlay","-o","lowerdir="+str(build/"lower")+",upperdir="+str(build/"upper")+",workdir="+str(build/"work"),str(build/"source")],check=True)
manifest=engine/"Engine/Binaries/Linux/UnrealEditor.modules";before=hashlib.sha256(manifest.read_bytes()).hexdigest()
if prior:assert before==prior["accepted_engine_manifest_before"],"Base engine changed"
build_seconds=profile["build_seconds"];runtime_seconds=profile["native_test_seconds"];total_seconds=build_seconds+runtime_seconds+45
directories=profile["plugin_directories"]
modules=[]
for directory in directories:
 path=engine/"Engine/Plugins"/directory/"Binaries/Linux/UnrealEditor.modules"
 modules+=list(json.loads(path.read_text())["Modules"])
if not a.resume:
 for name in ["CombatFramework.uproject","probe.py"]:shutil.copyfile(base/name,out/name)
 shutil.copytree(base/"Config",out/"Config")
command=["bash","/unreal-engine/Engine/Build/BatchFiles/Linux/Build.sh","UnrealEditor","Linux","Development","-Project=/job/CombatFramework.uproject","-Module="+"+".join(modules),"-NoUBA","-NoDumpSyms","-MaxParallelActions="+str(profile["parallel_actions"])]
if a.finalize_target:
 assert a.resume,"Target finalization requires preserved incremental cache"
 command=[x for x in command if not x.startswith("-Module=")]
runtime=["/unreal-engine/Engine/Binaries/Linux/UnrealEditor-Cmd","/job/CombatFramework.uproject","-run=PythonScript","-script=/job/probe.py","-NullRHI","-unattended","-nosound","-nop4","-stdout","-ddc=NoZenLocalFallback","-LocalDataCachePath=/job/DerivedDataCache"]
job=json.loads((base/"job.json").read_text());name="watoom-hyper-repair-"+hashlib.sha256((str(out)+attempt).encode()).hexdigest()[:12]
job["metadata"]={"name":name,"namespace":"watoom-code"};job["spec"]["activeDeadlineSeconds"]=total_seconds
spec=job["spec"]["template"]["spec"];spec["activeDeadlineSeconds"]=total_seconds
next(v for v in spec["volumes"] if v["name"]=="engine")["hostPath"]["path"]=str(build/"source")
next(v for v in spec["volumes"] if v["name"]=="job")["hostPath"]["path"]=str(out)
c=spec["containers"][0]
next(v for v in c["volumeMounts"] if v["name"]=="engine")["readOnly"]=False
c["resources"]={"requests":{"cpu":"500m","memory":"1Gi"},"limits":{"cpu":str(profile["cpu_limit"]),"memory":str(profile["memory_gib"])+"Gi"}}
code="import pathlib,subprocess,sys;pathlib.Path('/tmp/home').mkdir(exist_ok=True);a="+repr(command)+";b="+repr(runtime)+";r=subprocess.run(a,timeout="+str(build_seconds)+");sys.exit(r.returncode or subprocess.run(b,timeout="+str(runtime_seconds)+").returncode)"
c["command"]=["python3","-c",code]
for directory,dirs,files in os.walk(out):
 for p in [pathlib.Path(directory),*[pathlib.Path(directory)/f for f in files]]:os.chown(p,1009,1009)
(out/"job.json").write_text(json.dumps(job));os.chown(out/"job.json",1009,1009)
(out/"build-plan.json").write_text(json.dumps({"modules":modules,"argv":command,"isolated_engine":str(build/"source"),"accepted_engine_manifest_before":before,"memory_gib":12,"parallel":4,"seconds":build_seconds,"resume":a.resume,"finalize_target":a.finalize_target,"attempt":attempt},indent=2))
subprocess.run(["kubectl","create","-f",str(out/"job.json")],check=True,stdout=subprocess.DEVNULL);status("RUNNING",job=name)
begin=time.monotonic()
while time.monotonic()-begin<total_seconds+60:
 value=json.loads(subprocess.check_output(["kubectl","-n","watoom-code","get","job",name,"-o","json"]))
 if value.get("status",{}).get("succeeded") or value.get("status",{}).get("failed"):break
 time.sleep(10)
logs=subprocess.run(["kubectl","-n","watoom-code","logs","job/"+name],capture_output=True,text=True)
(out/"build.private.log").write_text(logs.stdout+logs.stderr);os.chmod(out/"build.private.log",0o600)
assert hashlib.sha256(manifest.read_bytes()).hexdigest()==before,"Accepted engine changed"
passed=(out/"hyper-native.json").exists() and json.loads((out/"hyper-native.json").read_text())["status"]=="PASS"
status("PASS_HYPER_ENGINE" if passed else "BLOCKED_HYPER_ENGINE",job=name,accepted_engine_unchanged=True,scope="Isolated plugin build/core Blueprint compile only; play/render still untested")
raise SystemExit(0 if passed else 2)
