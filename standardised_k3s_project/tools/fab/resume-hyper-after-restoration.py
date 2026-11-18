#!/usr/bin/env python3
"""Resume an interrupted cached Hyper target only after existing guardians restore."""
import argparse,datetime,fcntl,json,pathlib,subprocess,time
ap=argparse.ArgumentParser();ap.add_argument("--acquisition-evidence",required=True,type=pathlib.Path);ap.add_argument("--capacity-evidence",required=True,type=pathlib.Path);a=ap.parse_args()
R=pathlib.Path(__file__).resolve().parents[2];E=a.acquisition_evidence.resolve();O=a.capacity_evidence.resolve()
assert all(p.is_relative_to(pathlib.Path("/data/ai/helper-scripts/reports")) for p in [E,O])
lock=(O/"hyper-resume.lock").open("a");fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
prior=json.loads((E/"native-coordinator.json").read_text());P=pathlib.Path(prior["evidence"])
old=json.loads((O/"hyper-capacity-coordinators.json").read_text())
def write(p,d):
 t=p.with_suffix(".new");t.write_text(json.dumps(d,indent=2)+"\n");t.replace(p)
def state(value,**kw):write(O/"hyper-resume-status.json",dict(status=value,**kw))
state("WAITING_FOR_PRIOR_RESTORATION")
deadline=time.monotonic()+1800
while time.monotonic()<deadline:
 current=json.loads((P/"native-status.json").read_text())
 if current["status"]=="PASS_HYPER_ENGINE":state("TARGET_ALREADY_PASSED");raise SystemExit(0)
 restored=[]
 for kind,entry in old.items():
  name="model-capacity-status.json" if kind=="model" else "fab-capacity-status.json"
  f=pathlib.Path(entry["evidence"])/name
  restored.append(f.exists() and json.loads(f.read_text())["status"]=="RESTORED")
 if current["status"]=="BLOCKED_HYPER_ENGINE" and all(restored):break
 time.sleep(5)
else:state("BLOCKED_RESTORATION_TIMEOUT");raise SystemExit(2)
config=json.loads(pathlib.Path("/data/ai/helper-scripts/config/gpu-controller.json").read_text())
gpu=json.loads((pathlib.Path(config["state_root"])/"state.json").read_text())
assert gpu["phase"]=="qwen-ready" and not gpu.get("owner") and not gpu.get("uncertain"),"Supported GPU recovery required before resume"
stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
unit="watoom-hyper-finalize-"+stamp.lower()
def launch(unit,args):
 subprocess.run(["systemd-run","--unit",unit,"--property=Type=exec","/usr/bin/python3",*args],check=True,capture_output=True)
launch(unit,[str(R/"tools/fab/repair-hyper-engine.py"),"--evidence",str(P),"--resume","--finalize-target"])
time.sleep(2)
current=json.loads((P/"native-status.json").read_text());assert current["status"] in ["WAITING_FOR_HEADROOM","RUNNING"]
write(E/"native-coordinator.json",dict(unit=unit,evidence=str(P),resume=True,finalize_target=True,build_seconds=10800,scope="Cached isolated target; genuine UBT metadata"))
guards={}
for kind,helper in [("model","lend-model-capacity.py"),("game","lend-game-capacity.py")]:
 out=O/("hyper-"+kind+"-capacity-"+stamp);out.mkdir()
 u="watoom-hyper-"+kind+"-capacity-"+stamp.lower()
 launch(u,[str(R/"tools/fab"/helper),"--evidence",str(out),"--completion-file",str(P/"native-status.json")])
 guards[kind]=dict(unit=u,evidence=str(out),completion=str(P/"native-status.json"))
write(O/"hyper-capacity-coordinators.json",guards)
state("RESUMED",unit=unit,parallel_actions=json.loads((R/"tools/unreal/profiles/hyper-combat.json").read_text())["parallel_actions"])
