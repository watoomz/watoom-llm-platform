#!/usr/bin/env python3
"""Serial receipt-backed CPU compatibility probes beside the single existing FAB queue."""

import argparse, copy, datetime, fcntl, hashlib, json, os, pathlib, shutil, subprocess, time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", required=True, type=pathlib.Path)
    a = ap.parse_args()
    out = a.evidence.resolve()
    assert out.is_relative_to(pathlib.Path("/data/ai/helper-scripts/reports")) and out.is_dir()
    lock = (out / "accept-owned.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    repo = pathlib.Path(__file__).resolve().parents[2]
    fab = pathlib.Path(pathlib.Path("/data/ai/helper-scripts/reports/dungeon-fab-current.txt").read_text().strip())
    dungeon = pathlib.Path(
        pathlib.Path("/data/ai/helper-scripts/reports/dungeon-integration-current.txt").read_text().strip()
    )
    template = json.loads((dungeon / "forge-inspection-pod.json").read_text())
    items = json.loads((fab / "server-download-selection.json").read_text())
    results = {}
    started = time.monotonic()

    def save(status, **extra):
        value = {
            "status": status,
            "results": results,
            "selected": len(items),
            "updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            **extra,
        }
        temp = out / "pack-compatibility.new"
        temp.write_text(json.dumps(value, indent=2))
        os.replace(temp, out / "pack-compatibility.json")

    def kub(*args, check=True):
        p = subprocess.run(["kubectl", "-n", "watoom-code", *args], capture_output=True, text=True, timeout=30)
        if check and p.returncode:
            raise RuntimeError(p.stderr[-500:])
        return p

    def available():
        return (
            int(
                next(
                    x.split()[1]
                    for x in pathlib.Path("/proc/meminfo").read_text().splitlines()
                    if x.startswith("MemAvailable:")
                )
            )
            * 1024
        )

    # Full accepted Builder/Forge tests are retained rather than repeated.
    for item, key in zip(items[:2], ["builder", "forge"]):
        receipt = dungeon / (key + "-vertical-landing-candidate-acceptance.json")
        j = json.loads(receipt.read_text())
        assert j["status"] == "PASS"
        results[item["id"]] = {
            "status": "PASS_FULL_ACCEPTED",
            "evidence": str(receipt),
            "scope": "Existing textured native/collision/Recast/editable map/GLB/Godot two-level acceptance",
        }
    save("RUNNING")
    while time.monotonic() - started < 24 * 3600:
        download = json.loads((fab / "download-status.json").read_text())
        for item in items:
            ident = item["id"]
            if ident in results or not (fab / ("download-" + ident + ".json")).exists():
                continue
            if available() < 8 * 1024**3:
                save("WAITING_FOR_HEADROOM", required_free_gib=8, current_asset=ident)
                break
            receipt = json.loads((fab / ("download-" + ident + ".json")).read_text())
            assert receipt["asset"]["id"] == ident
            completed = next((x for x in download.get("completed", []) if x["id"] == ident), None)
            if not completed:
                continue
            source = pathlib.Path(completed["path"]).resolve()
            assert source.parent == pathlib.Path("/data/ai/assets/fab") and not source.is_symlink()
            content = source / "Content"
            if not content.is_dir():
                results[ident] = {
                    "status": "BLOCKED_NO_NATIVE_CONTENT",
                    "source": str(source),
                    "formats": sorted({p.suffix.lower() for p in source.rglob("*") if p.is_file()}),
                    "scope": "Needs source-format-specific acceptance; no guessed Unreal project",
                }
                continue
            fixture = out / ("pack-" + ident[:8])
            fixture.mkdir(mode=0o770, exist_ok=True)
            jobname = "watoom-fab-" + hashlib.sha256((out.name + ident).encode()).hexdigest()[:16]
            result_path = fixture / "pack-native.json"
            if not (fixture / "job.json").exists():
                project = {
                    "FileVersion": 3,
                    "EngineAssociation": "",
                    "DisableEnginePluginsByDefault": True,
                    "Plugins": [
                        {"Name": "PythonScriptPlugin", "Enabled": True},
                        {"Name": "GLTFExporter", "Enabled": True},
                    ],
                }
                engine = pathlib.Path("/data/ai/builds/unreal-recovery-20261016T213935Z/source")
                if (
                    engine / "Engine/Plugins/Runtime/GeometryCache/Binaries/Linux/libUnrealEditor-GeometryCache.so"
                ).is_file():
                    project["Plugins"].append({"Name": "GeometryCache", "Enabled": True})
                (fixture / "Inspection.uproject").write_text(json.dumps(project))
                shutil.copyfile(repo / "tools/fab/pack-native-probe.py", fixture / "inspect.py")
                shutil.copyfile(repo / "tools/fab/pack-geometry.gd", fixture / "pack-geometry.gd")
                spec = copy.deepcopy(template["spec"])
                spec["activeDeadlineSeconds"] = 600
                c = spec["containers"][0]
                c["image"] = (
                    "127.0.0.1:5000/watoom-toolkit@sha256:3b2368f5c45c8ebced2644ac6f316ef499512de912afa4c6be85a3e37212ef39"
                )
                code = """import pathlib,subprocess,json,shutil
root=pathlib.Path("/job");pathlib.Path("/tmp/home").mkdir(exist_ok=True)
p=subprocess.run(["/unreal-engine/Engine/Binaries/Linux/UnrealEditor-Cmd","/job/Inspection.uproject","-run=PythonScript","-script=/job/inspect.py","-NullRHI","-unattended","-nosound","-nop4","-stdout","-FullStdOutLogOutput","-ddc=NoZenLocalFallback","-LocalDataCachePath=/job/DerivedDataCache"],timeout=420)
if p.returncode:raise SystemExit(p.returncode)
value=json.loads((root/"pack-native.json").read_text())
if value["status"]=="PASS":
 g=root/"godot";g.mkdir(exist_ok=True);shutil.copyfile(root/"geometry.glb",g/"geometry.glb");shutil.copyfile(root/"pack-geometry.gd",g/"verify.gd")
 (g/"project.godot").write_text('config_version=5\\n[application]\\nconfig/name="PackGeometryProbe"\\n[rendering]\\nrenderer/rendering_method="gl_compatibility"\\n')
 binary=shutil.which("godot");assert binary
 subprocess.run([binary,"--headless","--editor","--path",str(g),"--quit"],check=True,timeout=60)
 subprocess.run([binary,"--headless","--path",str(g),"--script","res://verify.gd"],check=True,timeout=30)
"""
                c["command"] = ["python3", "-c", code]
                next(v for v in spec["volumes"] if v["name"] == "job")["hostPath"]["path"] = str(fixture)
                next(v for v in spec["volumes"] if v["name"] == "content")["hostPath"]["path"] = str(content)
                job = {
                    "apiVersion": "batch/v1",
                    "kind": "Job",
                    "metadata": {
                        "name": jobname,
                        "namespace": "watoom-code",
                        "labels": {"watoom-test-owner": out.name},
                    },
                    "spec": {
                        "backoffLimit": 0,
                        "activeDeadlineSeconds": 600,
                        "template": {"metadata": {"labels": {"watoom-test-owner": out.name}}, "spec": spec},
                    },
                }
                (fixture / "job.json").write_text(json.dumps(job, indent=2))
                for p in [fixture, *fixture.iterdir()]:
                    os.chown(p, 1009, 1009)
            old = kub("get", "job", jobname, "-o", "json", check=False)
            if old.returncode:
                kub("create", "-f", str(fixture / "job.json"))
            else:
                assert json.loads(old.stdout)["metadata"]["labels"]["watoom-test-owner"] == out.name
            save("RUNNING", current_asset=ident, job=jobname)
            begin = time.monotonic()
            while True:
                job = json.loads(kub("get", "job", jobname, "-o", "json").stdout)
                status = job.get("status", {})
                if status.get("succeeded") or status.get("failed"):
                    break
                if time.monotonic() - begin > 660:
                    raise RuntimeError("Owned job did not reach terminal state; inspect before any retry")
                time.sleep(5)
            logs = kub("logs", "job/" + jobname, check=False)
            (fixture / "worker.log").write_text(logs.stdout + logs.stderr)
            native = (
                json.loads(result_path.read_text())
                if result_path.exists()
                else {"status": "FAIL", "reason": "Native receipt absent; inspect worker log", "job_status": status}
            )
            godot = (
                json.loads((fixture / "godot/godot-geometry.json").read_text())
                if (fixture / "godot/godot-geometry.json").exists()
                else None
            )
            ok = status.get("succeeded") and native["status"] == "PASS" and godot and godot["status"] == "PASS"
            results[ident] = {
                "status": (
                    "PASS_SAMPLED_NATIVE_GEOMETRY"
                    if ok
                    else (
                        "NATIVE_DYNAMIC_LOAD_PASS"
                        if status.get("succeeded") and native["status"] == "NATIVE_DYNAMIC_LOAD_PASS"
                        else "FAIL"
                    )
                ),
                "evidence": str(fixture),
                "native": native,
                "godot": godot,
                "whole_pack_certified": False,
                "material_render": "NOT TESTED except prior Builder/Forge acceptance",
            }
            save("RUNNING")
        if download["status"] in ("PASS", "BLOCKED") and all(x["id"] in results for x in download.get("completed", [])):
            missing = [x["id"] for x in items if x["id"] not in results]
            save(
                (
                    "PASS_SCOPED"
                    if not missing and all(v["status"].startswith("PASS") for v in results.values())
                    else "PARTIAL"
                ),
                download_status=download["status"],
                pending_downloads=missing,
                limits="Sampled static native mesh and geometry compatibility only; dynamic effects/motion and additional shader baking are separate gates",
            )
            return
        time.sleep(20)
    save("BLOCKED", reason="24-hour acceptance budget; no duplicate work started")


if __name__ == "__main__":
    main()
