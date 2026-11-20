#!/usr/bin/env python3
"""Fixed owned-Poo VFX portable export; source read-only, isolated bounded worker."""

import pathlib, json, subprocess, hashlib, time, os, argparse, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "watoom-code"))
from game_validation import atomic, publish_receipt

p = argparse.ArgumentParser()
p.add_argument("--project", type=pathlib.Path, required=True)
p.add_argument("--evidence", type=pathlib.Path, required=True)
p.add_argument("--i-approve", action="store_true")
a = p.parse_args()
assert os.geteuid() == 0 and a.i_approve
project = a.project.resolve(strict=True)
out = a.evidence.resolve()
assert not a.project.is_symlink() and project.parent == pathlib.Path("/data/ai/projects/games")
assert out.is_relative_to("/data/ai/helper-scripts/reports") and not out.exists()
source = pathlib.Path("/data/ai/assets/fab/poo-vfx-0e2a097a")
assert (source / "Content/Vefects/VFX_Poo").is_dir()
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
assert mem >= 5 * 1024**3, "3GiB plus2GiB reserve unavailable"


def hashes():
    return {
        str(x.relative_to(source)): hashlib.sha256(x.read_bytes()).hexdigest() for x in source.rglob("*") if x.is_file()
    }


before = hashes()
out.mkdir(mode=0o770)
atomic(out / "source-hashes.json", before)
atomic(
    out / "Inspection.uproject",
    {
        "FileVersion": 3,
        "EngineAssociation": "",
        "Plugins": [{"Name": "PythonScriptPlugin", "Enabled": True}, {"Name": "Niagara", "Enabled": True}],
    },
)
probe = "import unreal,json,pathlib,traceback,hashlib,gc\nr={'status':'FAIL','scope':'Purchased-source portable texture/mesh export only; Godot wiring and rendered acceptance remain required.'}\ntry:\n registry=unreal.AssetRegistryHelpers.get_asset_registry();registry.scan_paths_synchronous(['/Game/Vefects/VFX_Poo'],True)\n rows=[{'path':str(x.package_name),'class':str(x.asset_class_path.asset_name)} for x in registry.get_assets_by_path('/Game/Vefects/VFX_Poo',True)]\n assert hasattr(unreal,'AssetExportTask') and hasattr(unreal.Exporter,'run_asset_export_task'),'Installed export interface unavailable'\n assets=[x for x in rows if '/Demo/' not in x['path'] and x['class'] in ['Texture2D','StaticMesh']]\n assert assets,'No eligible purchased source assets'\n exported=[];failed=[]\n for row in sorted(assets,key=lambda x:x['path']):\n  asset=unreal.load_asset(row['path']);assert asset is not None\n  rel=pathlib.PurePosixPath(row['path']).relative_to('/Game/Vefects/VFX_Poo')\n  target=pathlib.Path('/job/exported')/str(rel);target=target.with_suffix('.tga' if row['class']=='Texture2D' else '.obj');target.parent.mkdir(parents=True,exist_ok=True)\n  task=unreal.AssetExportTask()\n  fields={'object':asset,'filename':str(target),'automated':True,'prompt':False,'replace_identical':False}\n  for key,value in fields.items():task.get_editor_property(key);task.set_editor_property(key,value)\n  ok=unreal.Exporter.run_asset_export_task(task)\n  if not ok or not target.is_file() or target.stat().st_size==0:failed.append(row);continue\n  exported.append({**row,'file':str(target.relative_to('/job')),'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})\n  task=None;asset=None;gc.collect()\n assert sum(x['bytes'] for x in exported)<=1024**3,'Export exceeds reviewed1GiB output budget'\n r.update(status='PORTABLE_EXPORT_PASS' if exported and not failed else 'PARTIAL_EXPORT',engine=unreal.SystemLibrary.get_engine_version(),exported=exported,failed=failed,godot_adaptation_confirmed=False)\nexcept Exception:r['error']=traceback.format_exc()\npathlib.Path('/job/native-result.json').write_text(json.dumps(r,indent=2))\nif r['status']!='PORTABLE_EXPORT_PASS':raise RuntimeError(r.get('error','Some purchased source assets failed export; inspect exact receipt'))\n"
(out / "probe.py").write_text(probe)
base = pathlib.Path("/data/ai/helper-scripts/reports/remaining-acceptance-20261017T202822Z/pack-9cdd1f83/job.json")
job = json.loads(base.read_text())
name = "watoom-poo-export-" + hashlib.sha256(str(out).encode()).hexdigest()[:12]
job["metadata"] = {"name": name, "namespace": "watoom-code", "labels": {"watoom-test-owner": "owned-vfx-export"}}
job["spec"].update(ttlSecondsAfterFinished=3600, backoffLimit=0, activeDeadlineSeconds=300)
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
c["resources"] = {"requests": {"cpu": "100m", "memory": "512Mi"}, "limits": {"cpu": "2", "memory": "3Gi"}}
c["command"] = [
    "python3",
    "-c",
    "import pathlib,subprocess,sys;pathlib.Path('/tmp/home').mkdir(exist_ok=True);sys.exit(subprocess.run(sys.argv[1:],timeout=240).returncode)",
    "/unreal-engine/Engine/Binaries/Linux/UnrealEditor-Cmd",
    "/job/Inspection.uproject",
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
for f in [out, *out.iterdir()]:
    os.chown(f, 1009, 1009)
atomic(out / "job.json", job)
subprocess.run(["kubectl", "create", "-f", str(out / "job.json")], check=True, stdout=subprocess.DEVNULL)
for _ in range(65):
    j = json.loads(subprocess.check_output(["kubectl", "-n", "watoom-code", "get", "job", name, "-o", "json"]))
    if j.get("status", {}).get("succeeded") or j.get("status", {}).get("failed"):
        break
    time.sleep(5)
logs = subprocess.run(["kubectl", "-n", "watoom-code", "logs", "job/" + name], capture_output=True, text=True)
(out / "native.private.log").write_text(logs.stdout + logs.stderr)
os.chmod(out / "native.private.log", 0o600)
assert hashes() == before, "Purchased source changed"
result = (
    json.loads((out / "native-result.json").read_text())
    if (out / "native-result.json").exists()
    else {"status": "FAIL", "reason": "Worker produced no native inspection receipt"}
)
if not j.get("status", {}).get("succeeded"):
    result.update(status="FAIL", reason="Unreal worker did not terminate successfully")
result.update(
    source_unchanged=True, job=name, memory_limit="3GiB", worker_succeeded=bool(j.get("status", {}).get("succeeded"))
)
publish_receipt(project, out, result, log_name="native.private.log", receipt_folder="operator-unreal")
atomic(out / "result.json", result)
print(json.dumps(result))
raise SystemExit(0 if result["status"] == "PORTABLE_EXPORT_PASS" else 1)
