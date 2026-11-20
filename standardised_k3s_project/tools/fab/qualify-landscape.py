#!/usr/bin/env python3
"""Landscape Mesh Builder: bounded native load/compile qualification, no generation."""

import pathlib, json, subprocess, hashlib, time, os, argparse, shutil, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "watoom-code"))
from lmb_provenance import native_input_files, native_input_sha256, compare_native_inputs, NATIVE_ALGORITHM

p = argparse.ArgumentParser()
p.add_argument("--evidence", type=pathlib.Path, required=True)
p.add_argument("--memory-gib", type=int, choices=[3, 4], default=3)
a = p.parse_args()
out = a.evidence.resolve()
assert out.is_relative_to("/data/ai/helper-scripts/reports") and not out.exists()
source = pathlib.Path("/data/ai/assets/fab/landscape-mesh-builder-48364dff")
assert (source / "LandscapeMeshBuilder.uproject").is_file()
assert (
    source / "Content/LandscapeMeshBuilder/Blueprints/BP_LandscapeMeshBuilder.uasset"
).is_file(), "Required native Blueprint missing"
mem = (
    int(
        next(
            x.split()[1]
            for x in pathlib.Path("/proc/meminfo").read_text().splitlines()
            if x.startswith("MemAvailable:")
        )
    )
    * 1024
)
assert mem >= (a.memory_gib + 2) * 1024**3, "Worker plus2GiB reserve unavailable; do not alter inference"
out.mkdir(mode=0o770)
native_before = native_input_files(source)
before = {
    str(x.relative_to(source)): hashlib.sha256(x.read_bytes()).hexdigest() for x in source.rglob("*") if x.is_file()
}
(out / "source-hashes.json").write_text(json.dumps(before, indent=2))
project = json.loads((source / "LandscapeMeshBuilder.uproject").read_text())
project["EngineAssociation"] = ""
project["Plugins"].append({"Name": "PythonScriptPlugin", "Enabled": True})
(out / "LandscapeMeshBuilder.uproject").write_text(json.dumps(project))
shutil.copytree(source / "Config", out / "Config")
probe = """import unreal,json,pathlib,traceback
r={'status':'FAIL','scope':'Native Blueprint load/compile only; terrain generation/export/visual fidelity NOT TESTED'}
try:
 registry=unreal.AssetRegistryHelpers.get_asset_registry();registry.scan_paths_synchronous(['/Game/LandscapeMeshBuilder'],True)
 bp=unreal.load_asset('/Game/LandscapeMeshBuilder/Blueprints/BP_LandscapeMeshBuilder');assert isinstance(bp,unreal.Blueprint),'Blueprint did not load'
 unreal.BlueprintEditorLibrary.compile_blueprint(bp)
 status=str(bp.get_editor_property('status'));assert 'ERROR' not in status.upper(),status
 assert bp.generated_class() is not None,'No generated class'
 r.update(status='NATIVE_COMPILE_PASS',blueprint_status=status,generated_class=bp.generated_class().get_path_name(),engine=unreal.SystemLibrary.get_engine_version(),assets=[{'path':str(x.package_name),'class':str(x.asset_class_path.asset_name)} for x in registry.get_assets_by_path('/Game/LandscapeMeshBuilder',True)])
except Exception:r['error']=traceback.format_exc()
pathlib.Path('/job/native-result.json').write_text(json.dumps(r,indent=2))
if r['status']=='FAIL':raise RuntimeError(r.get('error','failed'))
"""
(out / "probe.py").write_text(probe)
base = pathlib.Path("/data/ai/helper-scripts/reports/remaining-acceptance-20261017T202822Z/pack-9cdd1f83/job.json")
job = json.loads(base.read_text())
name = "watoom-landscape-" + hashlib.sha256(str(out).encode()).hexdigest()[:12]
job["metadata"] = {"name": name, "namespace": "watoom-code", "labels": {"watoom-test-owner": "landscape-qualification"}}
job["spec"]["ttlSecondsAfterFinished"] = 3600
job["spec"]["backoffLimit"] = 0
job["spec"]["activeDeadlineSeconds"] = 300
spec = job["spec"]["template"]["spec"]
spec["activeDeadlineSeconds"] = 300
for v in spec["volumes"]:
    if v["name"] == "engine":
        v["hostPath"]["path"] = "/data/ai/toolchains/unreal/5.8.3/runtime-74dc43e1a653"
    if v["name"] == "content":
        v["hostPath"]["path"] = str(source / "Content")
    if v["name"] == "job":
        v["hostPath"]["path"] = str(out)
c = spec["containers"][0]
c["resources"] = {
    "requests": {"cpu": "100m", "memory": "512Mi"},
    "limits": {"cpu": "2", "memory": str(a.memory_gib) + "Gi"},
}
c["command"] = [
    "python3",
    "-c",
    "import pathlib,subprocess,sys;pathlib.Path('/job/cgroup-memory-max.txt').write_text(pathlib.Path('/sys/fs/cgroup/memory.max').read_text().strip());pathlib.Path('/tmp/home').mkdir(exist_ok=True);sys.exit(subprocess.run(sys.argv[1:],timeout=240).returncode)",
    "/unreal-engine/Engine/Binaries/Linux/UnrealEditor-Cmd",
    "/job/LandscapeMeshBuilder.uproject",
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
for folder, dirs, files in os.walk(out):
    for x in [pathlib.Path(folder), *[pathlib.Path(folder) / f for f in files]]:
        os.chown(x, 1009, 1009)
(out / "job.json").write_text(json.dumps(job))
subprocess.run(["kubectl", "create", "-f", str(out / "job.json")], check=True, stdout=subprocess.DEVNULL)
for i in range(65):
    j = json.loads(subprocess.check_output(["kubectl", "-n", "watoom-code", "get", "job", name, "-o", "json"]))
    if j.get("status", {}).get("succeeded") or j.get("status", {}).get("failed"):
        break
    time.sleep(5)
logs = subprocess.run(["kubectl", "-n", "watoom-code", "logs", "job/" + name], capture_output=True, text=True)
(out / "native.private.log").write_text(logs.stdout + logs.stderr)
os.chmod(out / "native.private.log", 0o600)
native_after = native_input_files(source)
native_changes = compare_native_inputs(native_before, native_after)
after = {
    str(x.relative_to(source)): hashlib.sha256(x.read_bytes()).hexdigest() for x in source.rglob("*") if x.is_file()
}
source_unchanged = after == before and not any(native_changes.values())
result = (
    json.loads((out / "native-result.json").read_text())
    if (out / "native-result.json").exists()
    else {"status": "NATIVE_QUALIFICATION_FAILED", "job": name}
)
result["source_unchanged"] = source_unchanged
result["job"] = name
result.update(
    native_input_files=native_before,
    native_input_sha256=native_input_sha256(native_before),
    native_input_algorithm=NATIVE_ALGORITHM,
    native_input_changes=native_changes,
    native_provenance_scope="Declared purchased source pack, not an actual-open trace; engine and plugin dependencies excluded",
)
if not source_unchanged:
    result.update(status="NATIVE_SOURCE_CHANGED")
(out / "qualification.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result))
raise SystemExit(0 if result["status"] == "NATIVE_COMPILE_PASS" else 1)
