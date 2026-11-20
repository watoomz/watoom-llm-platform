"""Existing Toolkit isolated inspection plus real Blender/Godot/Unreal acceptance."""

import pathlib, json, sys, subprocess, os, hashlib, shutil, time, signal


def run(request):
    output = pathlib.Path(request["output"])
    base = output.parent
    started = time.monotonic()
    if output.exists():
        raise ValueError("Existing output cannot be silently replaced")
    engine = pathlib.Path("/unreal-engine/Engine/Binaries/Linux/UnrealEditor")
    expected = request.get("expected_engine_sha256")
    if not expected or hashlib.sha256(engine.read_bytes()).hexdigest() != expected:
        raise ValueError("Pinned engine mismatch")

    def invoke(name, argv, seconds):
        remaining = 420 - (time.monotonic() - started)
        if remaining < 5:
            raise TimeoutError("Total engine-validation budget exhausted")
        process = None
        with (base / (name + ".log")).open("w") as log:
            try:
                process = subprocess.Popen(
                    argv,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    env={**os.environ, "OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "1"},
                )
                deadline = time.monotonic() + min(seconds, remaining)
                while process.poll() is None:
                    free = (
                        int(
                            next(
                                line.split()[1]
                                for line in pathlib.Path("/proc/meminfo").read_text().splitlines()
                                if line.startswith("MemAvailable:")
                            )
                        )
                        * 1024
                    )
                    if free < 2 * 1024**3:
                        raise RuntimeError("Host memory reserve reached")
                    if time.monotonic() > deadline:
                        raise TimeoutError(name + " exceeded stage deadline")
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
            raise RuntimeError(name + " failed; bounded worker log retained")

    ordinary = {k: v for k, v in request.items() if k not in ["parameters", "expected_engine_sha256"]}
    invoke(
        "blender-inspection",
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
            "/opt/watoom/blender_3d.py",
            "--",
            json.dumps(ordinary),
        ],
        150,
    )
    project = base / "engine-project"
    project.mkdir()
    invoke(
        "fbx-export",
        [
            "blender",
            "--background",
            str(output / "asset.blend"),
            "--disable-autoexec",
            "--threads",
            "2",
            "--python-exit-code",
            "1",
            "--python",
            "/opt/watoom/engine_export.py",
            "--",
            str(project),
        ],
        60,
    )
    source = json.loads((project / "source.json").read_text())
    (project / "EngineValidation.uproject").write_text(
        json.dumps(
            {
                "FileVersion": 3,
                "EngineAssociation": "",
                "DisableEnginePluginsByDefault": True,
                "Plugins": [
                    {"Name": "PythonScriptPlugin", "Enabled": True},
                    {"Name": "EditorScriptingUtilities", "Enabled": True},
                    {"Name": "SkeletalReduction", "Enabled": True},
                ],
            }
        )
    )
    shutil.copy2("/opt/watoom/engine_verify_unreal.py", project / "verify.py")
    # Warm the editor's asset registry from the pinned engine-content seed; re-verified here, cold start otherwise.
    import three_d

    seed = base / "asset-registry-seed"
    files = three_d.seed_files_valid(seed, expected) if seed.is_dir() else None
    if files:
        cache = project / "Intermediate" / "CachedAssetRegistry"
        cache.mkdir(parents=True)
        for name, data in files.items():
            (cache / name).write_bytes(data)
    registry_seed = "USED" if files else "REJECTED" if seed.is_dir() else "ABSENT"
    if seed.is_dir():
        shutil.rmtree(seed)
    invoke(
        "unreal",
        [
            str(engine.parent / "UnrealEditor-Cmd"),
            str(project / "EngineValidation.uproject"),
            "-run=pythonscript",
            "-script=" + str(project / "verify.py"),
            "-NullRHI",
            "-unattended",
            "-nosound",
            "-nosplash",
            "-nop4",
            "-stdout",
            "-FullStdOutLogOutput",
            "-ddc=NoZenLocalFallback",
            "-LocalDataCachePath=" + str(project / "DerivedDataCache"),
        ],
        210,
    )
    ue = json.loads((project / "unreal-result.json").read_text())
    if ue["status"] != "PASS":
        raise RuntimeError("Unreal acceptance did not pass")
    shutil.copy2("/opt/watoom/engine_playback_unreal.py", project / "playback.py")
    invoke(
        "unreal-playback",
        [
            str(engine),
            str(project / "EngineValidation.uproject"),
            "-ExecutePythonScript=" + str(project / "playback.py"),
            "-NullRHI",
            "-unattended",
            "-nosound",
            "-nosplash",
            "-nop4",
            "-stdout",
            "-FullStdOutLogOutput",
            "-ddc=NoZenLocalFallback",
            "-LocalDataCachePath=" + str(project / "DerivedDataCache"),
        ],
        120,
    )
    playback = json.loads((project / "unreal-playback.json").read_text())
    if playback["status"] != "PASS":
        raise RuntimeError("Actual Unreal playback/LOD acceptance did not pass")
    ue["playback_and_lods"] = playback
    ue["asset_registry_seed"] = registry_seed
    godot = base / "godot-project"
    godot.mkdir()
    shutil.copy2(output / "asset.glb", godot / "asset.glb")
    shutil.copy2("/opt/watoom/engine_verify.gd", godot / "playback.gd")
    (godot / "project.godot").write_text(
        'config_version=5\n[application]\nconfig/name="Engine acceptance"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n'
    )
    if source["animations"]:
        (godot / "animated.required").touch()
    invoke("godot-import", ["godot", "--headless", "--editor", "--path", str(godot), "--quit"], 60)
    invoke("godot-playback", ["godot", "--headless", "--path", str(godot), "-s", "res://playback.gd"], 30)
    gd = json.loads((godot / "result.json").read_text())
    if gd["status"] != "PASS":
        raise RuntimeError("Godot acceptance did not pass")
    acceptance = {
        "status": "PASS",
        "gpu": 0,
        "engine_sha256": expected,
        "source": source,
        "godot": gd,
        "unreal": ue,
        "visual_review": "REQUIRED_SEPARATELY",
    }
    validation = json.loads((output / "validation.json").read_text())
    validation["engine_validation"] = acceptance
    (output / "validation.json").write_text(json.dumps(validation, indent=2))
    manifest = json.loads((output / "manifest.json").read_text())
    manifest["engine_validation"] = acceptance
    for item in manifest["outputs"]:
        data = (output / item["path"]).read_bytes()
        item.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"status": "PASS", "godot": gd["status"], "unreal": ue["status"], "gpu": 0}))


if __name__ == "__main__":
    run(json.loads(sys.argv[1]))
