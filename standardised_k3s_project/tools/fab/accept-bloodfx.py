"""Single bounded CPU-only BloodFX acceptance; waits for actual spare RAM."""

import argparse, pathlib, subprocess, json, time, os, fcntl, hashlib, shutil, importlib.util

p = argparse.ArgumentParser()
p.add_argument("--project", required=True, type=pathlib.Path)
p.add_argument("--engine", required=True, type=pathlib.Path)
p.add_argument("--content", required=True, type=pathlib.Path)
p.add_argument("--godot", required=True, type=pathlib.Path)
p.add_argument("--wait-seconds", type=int, default=3600)
a = p.parse_args()
root = a.project.resolve()
source = a.content.resolve()
tools = pathlib.Path(__file__).resolve().parent
assert (
    root.is_relative_to("/data/ai/projects")
    and source.is_relative_to("/data/ai/assets/fab")
    and 0 <= a.wait_seconds <= 3600
)
lock = (root / "acceptance.lock").open("a")
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
out = root / "acceptance.json"
status = {
    "state": "STARTING",
    "pid": os.getpid(),
    "started": time.time(),
    "GPU": "NOT USED",
    "scope": "16 native cache motions plus fixed-view sprite conversion, not 3D geometry translation",
}


def save(state, **kwargs):
    status.update(state=state, **kwargs)
    temporary = out.with_suffix(".new")
    temporary.write_text(json.dumps(status, indent=2))
    os.replace(temporary, out)


def hashes():
    result = {}
    for path in source.rglob("*"):
        if path.is_file():
            with path.open("rb") as f:
                result[str(path.relative_to(source))] = hashlib.file_digest(f, "sha256").hexdigest()
    return result


try:
    native = root / "native"
    inspection = json.loads((native / "bloodfx-inspection.json").read_text())
    assert len(inspection["assets"]) == 16
    assert all(
        len({json.dumps((s["origin"], s["extent"])) for s in x["samples"]}) > 1 for x in inspection["assets"]
    ), "No decoded native bound motion"
    before = hashes()
    save("WAITING_FOR_HEADROOM", source_hashes=before, native_motion="PASS16_DECODED_BOUND_CHANGES")
    deadline = time.monotonic() + a.wait_seconds
    consecutive = 0
    while True:
        available = (
            int(
                next(
                    x.split()[1]
                    for x in pathlib.Path("/proc/meminfo").read_text().splitlines()
                    if x.startswith("MemAvailable:")
                )
            )
            * 1024
        )
        consecutive = consecutive + 1 if available >= 7 * 1024**3 else 0
        save("WAITING_FOR_HEADROOM", available_bytes=available, required_bytes=7 * 1024**3)
        if consecutive >= 3:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError("Actual7GiB headroom unavailable within bounded wait; active jobs preserved")
        time.sleep(20)
    save("RENDERING_SOFTWARE_ONLY")
    subprocess.run(
        [
            os.sys.executable,
            str(tools / "bloodfx-software-runner.py"),
            "--project",
            str(native),
            "--engine",
            str(a.engine),
            "--content",
            str(source),
            "--script",
            str(native / "render.py"),
        ],
        check=True,
        timeout=1600,
    )
    save("BAKING_GODOT_LIBRARY")
    baked = root / "godot-bake"
    subprocess.run(
        [os.sys.executable, str(tools / "bloodfx-bake.py"), "--source", str(native), "--destination", str(baked)],
        check=True,
        timeout=180,
    )
    shutil.copyfile(tools / "bloodfx-playback.gd", baked / "verify.gd")
    for parent, dirs, files in os.walk(baked):
        os.chown(parent, 1009, 1009)
        for n in dirs + files:
            os.chown(pathlib.Path(parent) / n, 1009, 1009)
    save("VALIDATING_GODOT_SOFTWARE_PLAYBACK")
    subprocess.run(
        [os.sys.executable, str(tools / "bloodfx-godot.py"), "--project", str(baked), "--godot", str(a.godot)],
        check=True,
        timeout=480,
    )
    assert hashes() == before, "Original source changed"
    save(
        "TECHNICAL_PASS_VISUAL_REVIEW_PENDING",
        native_render=str(native / "software-render-receipt.json"),
        godot=str(baked / "godot.json"),
        source_unchanged=True,
        next="Inspect actual native/Godot temporal pixels, then publish only derived sprites through existing shared Catalog",
    )
except BaseException as error:
    save("BLOCKED", error=str(error)[:1000], no_gpu_capacity_borrowed=True)
    raise
