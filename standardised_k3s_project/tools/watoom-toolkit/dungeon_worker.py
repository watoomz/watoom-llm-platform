"""Fixed bounded CPU native-world worker; invoked only by the maintained Toolkit dispatch."""

import pathlib, json, sys, subprocess, os, hashlib, shutil, time, signal, re
from asset_catalog import Catalog, checksum
import dungeon_pipeline


def run(request, *, candidate_adapters=None):
    expected = request.get("expected_engine_sha256", "")
    if (
        not re.fullmatch("[a-f0-9]{64}", expected)
        or checksum(pathlib.Path("/unreal-engine/Engine/Binaries/Linux/UnrealEditor")) != expected
    ):
        raise ValueError("Native worker engine does not match accepted checksum")
    started = time.monotonic()
    output = pathlib.Path(request["output"])
    base = output.parent
    if output.exists():
        raise ValueError("An existing result cannot be silently replaced")
    project = base / "dungeon-project"
    project.mkdir(parents=True, exist_ok=True)
    catalog = Catalog("/assets", "/catalog.json")
    plan = dungeon_pipeline.prepare(request, catalog, candidate_adapters=candidate_adapters)
    if plan["plan_sha256"] != request.get("expected_plan_sha256"):
        raise ValueError("Catalog or verified plan changed after admission")
    if not plan.get("portable_modules"):
        raise ValueError("Verified textured module derivatives are required")
    if plan["layout"]["stairs"] and plan.get("vertical_contract") != "east-bay-v1":
        raise ValueError("Multi-level traversal requires the verified vertical contract")
    dungeon_pipeline.stage(plan, project)
    (project / "dungeon-assembly.json").write_text(json.dumps(plan, indent=2))
    (project / "Dungeon.uproject").write_text(
        json.dumps(
            {
                "FileVersion": 3,
                "EngineAssociation": "",
                "DisableEnginePluginsByDefault": True,
                "Plugins": [{"Name": "PythonScriptPlugin", "Enabled": True}, {"Name": "GLTFExporter", "Enabled": True}],
            }
        )
    )

    def invoke(args, limit, name):
        remaining = 780 - (time.monotonic() - started)
        if remaining < 5:
            raise TimeoutError("Native dungeon total budget exhausted")
        process = None
        deadline = time.monotonic() + min(limit, remaining)
        with (base / (name + ".log")).open("ab") as log:
            try:
                process = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                while process.poll() is None:
                    if time.monotonic() > deadline:
                        raise TimeoutError(name + " exceeded bounded stage deadline")
                    available = (
                        int(
                            next(
                                line.split()[1]
                                for line in pathlib.Path("/proc/meminfo").read_text().splitlines()
                                if line.startswith("MemAvailable:")
                            )
                        )
                        * 1024
                    )
                    if available < 2 * 1024**3:
                        raise RuntimeError("Host memory reserve reached; stopping only owned worker stage")
                    time.sleep(0.5)
            finally:
                if process is not None and process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
        if process.returncode:
            raise RuntimeError(name + " failed, exit " + str(process.returncode))

    invoke(
        [
            "/unreal-engine/Engine/Binaries/Linux/UnrealEditor",
            str(project / "Dungeon.uproject"),
            "-ExecutePythonScript=/opt/watoom/dungeon_unreal.py",
            "-NullRHI",
            "-unattended",
            "-nosound",
            "-nop4",
            "-stdout",
            "-FullStdOutLogOutput",
            "-ddc=NoZenLocalFallback",
            "-LocalDataCachePath=" + str(project / "DerivedDataCache"),
        ],
        450,
        "unreal",
    )
    native = json.loads((project / "native-assembly-receipt.json").read_text())
    if native["status"] != "NATIVE_QA_PASS_EXPORT_RENDER_PENDING" or not native["engine_version"].startswith("5.8.3-"):
        raise RuntimeError("Actual native collision/navigation acceptance did not pass")
    bakes = base / "verified-portable-modules.json"
    bakes.write_text(json.dumps({"status": "PASS", "modules": plan["portable_modules"]}, indent=2))
    invoke(
        [
            "blender",
            "--factory-startup",
            "--disable-autoexec",
            "--background",
            "--threads",
            "2",
            "--python-exit-code",
            "1",
            "--python",
            "/opt/watoom/dungeon_blender.py",
            "--",
            json.dumps({"plan": str(project / "dungeon-assembly.json"), "bakes": str(bakes), "output": str(output)}),
        ],
        210,
        "blender",
    )
    engine = base / "godot-project"
    engine.mkdir()
    shutil.copyfile(output / "asset.glb", engine / "asset.glb")
    (engine / "project.godot").write_text(
        'config_version=5\n[application]\nconfig/name="Dungeon Acceptance"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n'
    )
    (engine / "scene.tscn").write_text(
        '[gd_scene load_steps=2 format=3]\n[ext_resource type="PackedScene" path="res://asset.glb" id="1"]\n[node name="Dungeon" type="Node3D"]\n[node name="GeneratedDungeon" parent="." instance=ExtResource("1")]\n'
    )
    shutil.copyfile("/opt/watoom/dungeon_verify.gd", engine / "verify.gd")
    invoke(["godot", "--headless", "--path", str(engine), "--editor", "--import"], 60, "godot-import")
    invoke(["godot", "--headless", "--path", str(engine), "--script", "res://verify.gd"], 30, "godot-verify")
    godot = json.loads((engine / "acceptance.json").read_text())
    if godot.get("status") != "PASS":
        raise RuntimeError("Actual Godot import did not pass")
    native_map = project / "Content/GeneratedDungeon/Dungeon.umap"
    if checksum(native_map) != native["map_sha256"]:
        raise ValueError("Native map changed after physical acceptance")
    shutil.copyfile(native_map, output / "dungeon.umap")
    (output / "dungeon-layout.json").write_text(json.dumps(plan["layout"], indent=2))
    (output / "dungeon-assembly.json").write_text(
        json.dumps({k: v for k, v in plan.items() if k not in ("files", "portable_modules")}, indent=2)
    )
    validation = json.loads((output / "validation.json").read_text())
    validation.update(native=native, godot=godot)
    (output / "validation.json").write_text(json.dumps(validation, indent=2))
    provenance = {
        "schema": 1,
        "plan_sha256": plan["plan_sha256"],
        "packs": plan["provenance"],
        "material_bakes": json.loads((output / "portable-materials.json").read_text()),
        "source_integrity": "PASS",
        "native_project_reference": "state:jobs/" + request["job_id"] + "/worker/dungeon-project",
        "source_files": [
            {"content_path": name, **{key: record[key] for key in ("id", "sha256", "bytes")}}
            for name, record in plan["files"].items()
        ],
        "editable_map_dependencies": "Shared Catalog source closure must be staged in the recorded /Game namespaces when opening the map in another project.",
    }
    for relative, record in plan["files"].items():
        if checksum(pathlib.Path(record["source"])) != record["sha256"]:
            raise ValueError("Source changed during execution")
    (output / "provenance.json").write_text(json.dumps(provenance, indent=2))
    (output / "portable-materials.json").unlink()
    manifest = {
        "schema": 1,
        "status": "PASS",
        "job_id": request["job_id"],
        "generator_id": "world.compose",
        "seed": request.get("seed", 0),
        "plan_sha256": plan["plan_sha256"],
        "export_reimport": True,
        "native_collision": "PASS",
        "native_navigation": "PASS",
        "inspection_candidate": candidate_adapters is not None,
        "engine_editor_sha256": expected,
        "godot_acceptance": godot,
        "source_integrity": "PASS",
        "outputs": [],
    }
    actual = {p.name for p in output.iterdir() if p.is_file()}
    if actual != set(dungeon_pipeline.output_names(request["dungeon"])) - {"manifest.json"}:
        raise ValueError("Native dungeon artifact set mismatch")
    manifest["outputs"] = [
        {"path": p.name, "bytes": p.stat().st_size, "sha256": checksum(p)}
        for p in sorted(output.iterdir())
        if p.is_file()
    ]
    if any(p["bytes"] > 64 * 1024**2 for p in manifest["outputs"]):
        raise ValueError("Artifact publication budget exceeded")
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(
        json.dumps(
            {
                "status": "PASS",
                "native_collision": "PASS",
                "native_navigation": "PASS",
                "godot": "PASS",
                "plan_sha256": plan["plan_sha256"],
            }
        )
    )


if __name__ == "__main__":
    run(json.loads(sys.argv[1]))
