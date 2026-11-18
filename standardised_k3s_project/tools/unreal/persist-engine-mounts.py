#!/usr/bin/env python3
"""Persist only the exact, accepted isolated overlay; never unmount the original engine."""
import argparse,pathlib,json,subprocess,hashlib
ap=argparse.ArgumentParser();ap.add_argument("--evidence",required=True,type=pathlib.Path);ap.add_argument("--install",action="store_true");a=ap.parse_args()
r=a.evidence.resolve();assert r.is_relative_to("/data/ai/helper-scripts/reports")
plan=json.loads((r/"build-plan.json").read_text())
b=pathlib.Path(plan["isolated_root"]).resolve();original=pathlib.Path(plan["source"]).resolve()
assert b.is_relative_to("/data/ai/builds") and original==pathlib.Path("/data/ai/assets/unreal-engine")
assert json.loads((r/"acceptance-render-status.json").read_text())["status"]=="PASS"
visual=json.loads((r/"visual-review.json").read_text())
assert visual["status"]=="PASS" and hashlib.sha256(pathlib.Path(visual["capture"]).read_bytes()).hexdigest()==visual["sha256"]
assert json.loads((r/"container-commandlet-result.json").read_text())["status"]=="PASS"
for path,digest in json.loads((r/"render-resume-plan.json").read_text())["pins"].items():
 assert hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()==digest,"Accepted engine or fixture changed"
assert json.loads((b/"acceptance/GodotRegression/godot-regression.json").read_text())["status"]=="PASS"
units={}
def name(p):return subprocess.check_output(["systemd-escape","--path","--suffix=mount",str(p)],text=True).strip()
lower=name(b/"lower");overlay=name(b/"source")
for target in [b/"lower",b/"source"]:
 v=json.loads(subprocess.check_output(["findmnt","-J","-M",str(target)],text=True))["filesystems"][0]
 assert v["target"]==str(target)
 if target.name=="lower":
  assert "ro" in v["options"].split(","),"Original lower must remain read-only"
 else:
  assert v["fstype"]=="overlay"
  for key,value in [("lowerdir",b/"lower"),("upperdir",b/"upper"),("workdir",b/"overlay-work")]:
   assert key+"="+str(value) in v["options"].split(",")
units[lower]=f"""[Unit]
Description=Read-only original Unreal source for accepted isolated recovery
RequiresMountsFor={original} {b}
Before={overlay}

[Mount]
What={original}
Where={b}/lower
Type=none
Options=bind,ro
"""
units[overlay]=f"""[Unit]
Description=Accepted isolated Unreal 5.8.3 overlay
Requires={lower}
After={lower}
RequiresMountsFor={b}

[Mount]
What=overlay
Where={b}/source
Type=overlay
Options=lowerdir={b}/lower,upperdir={b}/upper,workdir={b}/overlay-work

[Install]
WantedBy=local-fs.target
"""
review=r/"accepted-mount-units";review.mkdir(exist_ok=True)
for n,text in units.items():(review/n).write_text(text)
subprocess.run(["systemd-analyze","verify",*[str(review/n) for n in units]],check=True,timeout=30)
if a.install:
 for n,text in units.items():
  target=pathlib.Path("/etc/systemd/system")/n
  assert not target.exists() or target.read_text()==text,"Preserve unrelated existing unit"
  target.write_text(text)
 subprocess.run(["systemctl","daemon-reload"],check=True,timeout=30)
 subprocess.run(["systemctl","enable",overlay],check=True,timeout=30)
 # Adopt existing mounts only. No start/restart/unmount occurs.
 for n in units:
  assert subprocess.check_output(["systemctl","show",n,"-p","ActiveState","--value"],text=True).strip()=="active"
(r/"mount-persistence.json").write_text(json.dumps({"status":"PASS" if a.install else "PLAN_VERIFIED","root":str(b/"source"),"units":list(units),"original_source":str(original),"unmount_performed":False},indent=2))
print("MOUNT_PERSISTENCE_"+("PASS" if a.install else "PLAN_VERIFIED"))
