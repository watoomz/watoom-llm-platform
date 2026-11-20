#!/usr/bin/env python3
"""Bounded isolated Hyper project Blueprint acceptance; no source pack writes or GPU."""

import argparse, copy, fcntl, json, os, pathlib, shutil, subprocess, time

ap = argparse.ArgumentParser()
ap.add_argument("--evidence", required=True, type=pathlib.Path)
a = ap.parse_args()
out = a.evidence.resolve()
assert out.is_relative_to(pathlib.Path("/data/ai/helper-scripts/reports"))
out.mkdir(mode=0o770, exist_ok=True)
lock = pathlib.Path("/data/ai/helper-scripts/reports/hyper-native-acceptance.lock").open("a")
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
acq = out.parent
receipt = json.loads((acq / "download-f92bbc40041c421ea22505ef57c76ce1.json").read_text())
assert receipt["asset"]["id"] == "f92bbc40041c421ea22505ef57c76ce1"
download = json.loads((acq / "download-status.json").read_text())
item = next(x for x in download["completed"] if x["id"] == receipt["asset"]["id"])
source = pathlib.Path(item["path"]).resolve()
assert source.parent == pathlib.Path("/data/ai/assets/fab")


def status(state, **extra):
    value = dict(status=state, pid=os.getpid(), **extra)
    tmp = out / "native-status.new"
    tmp.write_text(json.dumps(value, indent=2))
    os.replace(tmp, out / "native-status.json")


deadline = time.monotonic() + 7200
while time.monotonic() < deadline:
    free = (
        int(
            next(
                x.split()[1]
                for x in pathlib.Path("/proc/meminfo").read_text().splitlines()
                if x.startswith("MemAvailable:")
            )
        )
        * 1024
    )
    # Reserve concurrent existing6GiB symbol worker + this6GiB worker + host2GiB.
    if free > 14 * 1024**3:
        break
    status("WAITING_FOR_HEADROOM", required_gib=14)
    time.sleep(15)
else:
    status("BLOCKED_HEADROOM")
    raise SystemExit(2)
assert not (out / "job.json").exists(), "Inspect prior job rather than duplicate"
project = json.loads((source / "CombatFramework.uproject").read_text())
project["EngineAssociation"] = ""
project.pop("DisableEnginePluginsByDefault", None)
project.setdefault("Plugins", []).append({"Name": "PythonScriptPlugin", "Enabled": True})
(out / "CombatFramework.uproject").write_text(json.dumps(project))
shutil.copytree(source / "Config", out / "Config", dirs_exist_ok=True)
script = """import unreal,json,pathlib
packages=["/Game/Hyper/CombatSystem/Map/GM_Combat","/Game/Hyper/CombatSystem/Map/PC_Combat"]
results=[]
for package in packages:
 bp=unreal.load_asset(package)
 assert isinstance(bp,unreal.Blueprint),"Missing Blueprint: "+package
 compiled=unreal.BlueprintEditorLibrary.compile_blueprint(bp)
 assert compiled,"Blueprint compilation failed: "+package
 results.append({"package":package,"loaded":True,"compiled":True})
pathlib.Path("/job/hyper-native.json").write_text(json.dumps({"status":"PASS","engine":unreal.SystemLibrary.get_engine_version(),"blueprints":results,"scope":"Core Blueprint load/compile only; actual combat/input/damage/play/render NOT TESTED","source_content_read_only":True},indent=2))
"""
(out / "probe.py").write_text(script)
base = pathlib.Path("/data/ai/helper-scripts/reports/remaining-acceptance-20261017T202822Z/pack-9cdd1f83/job.json")
job = json.loads(base.read_text())
name = "watoom-hyper-" + __import__("hashlib").sha256(str(out).encode()).hexdigest()[:12]
job["metadata"] = {"name": name, "namespace": "watoom-code", "labels": {"watoom-test-owner": out.name}}
job["spec"]["template"]["metadata"] = {"labels": {"watoom-test-owner": out.name}}
job["spec"]["activeDeadlineSeconds"] = 645
spec = job["spec"]["template"]["spec"]
spec["activeDeadlineSeconds"] = 645
for volume in spec["volumes"]:
    if volume["name"] == "job":
        volume["hostPath"]["path"] = str(out)
    if volume["name"] == "content":
        volume["hostPath"]["path"] = str(source / "Content")
c = spec["containers"][0]
c["resources"] = {"requests": {"cpu": "100m", "memory": "512Mi"}, "limits": {"cpu": "2", "memory": "6Gi"}}
c["command"] = [
    "/unreal-engine/Engine/Binaries/Linux/UnrealEditor-Cmd",
    "/job/CombatFramework.uproject",
    "-run=PythonScript",
    "-script=/job/probe.py",
    "-NullRHI",
    "-unattended",
    "-nosound",
    "-nop4",
    "-stdout",
    "-ddc=NoZenLocalFallback",
    "-LocalDataCachePath=/job/DerivedDataCache",
]
c["command"] = [
    "python3",
    "-c",
    "import pathlib,subprocess,sys;pathlib.Path('/tmp/home').mkdir(exist_ok=True);sys.exit(subprocess.run(sys.argv[1:],timeout=600).returncode)",
    *c["command"],
]
for directory, dirs, files in os.walk(out):
    for p in [pathlib.Path(directory), *[pathlib.Path(directory) / f for f in files]]:
        os.chown(p, 1009, 1009)
(out / "job.json").write_text(json.dumps(job))
os.chown(out / "job.json", 1009, 1009)
subprocess.run(["kubectl", "create", "-f", str(out / "job.json")], check=True, stdout=subprocess.DEVNULL)
status("RUNNING", job=name)
begin = time.monotonic()
while time.monotonic() - begin < 690:
    value = json.loads(subprocess.check_output(["kubectl", "-n", "watoom-code", "get", "job", name, "-o", "json"]))
    if value.get("status", {}).get("succeeded") or value.get("status", {}).get("failed"):
        break
    time.sleep(5)
logs = subprocess.run(["kubectl", "-n", "watoom-code", "logs", "job/" + name], capture_output=True, text=True)
(out / "native.private.log").write_text(logs.stdout + logs.stderr)
os.chmod(out / "native.private.log", 0o600)
if not (out / "hyper-native.json").exists():
    status("BLOCKED_NATIVE_LOAD_OR_COMPILE", job=name)
    raise SystemExit(2)
assert json.loads((out / "hyper-native.json").read_text())["status"] == "PASS"
status("PASS_CORE_BLUEPRINTS", job=name)
