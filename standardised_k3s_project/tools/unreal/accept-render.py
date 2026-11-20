#!/usr/bin/env python3
"""Temporarily claim idle GPU through the existing controller for bounded editor acceptance."""

import argparse, json, os, pathlib, sys, subprocess, time, signal, fcntl

ap = argparse.ArgumentParser()
ap.add_argument("--evidence", required=True, type=pathlib.Path)
ap.add_argument("--dungeon-export", action="store_true")
ap.add_argument("--detach", action="store_true")
a = ap.parse_args()
if a.detach and not a.dungeon_export:
    ap.error("--detach is for the bounded dungeon task")
r = a.evidence.resolve()
assert r.is_relative_to("/data/ai/helper-scripts/reports")
if not a.detach:
    lock = (r / "render.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "watoom-code"))
from maintenance_guard import Maintenance
from release_guard import active_clear

sys.path.insert(0, "/data/ai/helper-scripts/gpu-controller")
from g3h_service import Runtime, atomic, process_identity
from controller import State

config = json.loads(pathlib.Path("/data/ai/helper-scripts/config/gpu-controller.json").read_text())
if a.dungeon_export:
    task = json.loads((r / "dungeon-export-plan.json").read_text())
    project = pathlib.Path(task["project"]).resolve()
    assert project.is_relative_to("/data/ai/builds")
    import hashlib

    assert {"probe.py", "RenderProbe.uproject", "selected-modules.json"} <= set(
        task["sha256"]
    ), "Required task pins missing"
    for name in task["sha256"]:
        assert (
            not pathlib.PurePosixPath(name).is_absolute()
            and ".." not in pathlib.PurePosixPath(name).parts
            and not (project / name).is_symlink()
            and (project / name).resolve().is_relative_to(project)
        ), "Unsafe task input"
        assert (
            hashlib.sha256((project / name).read_bytes()).hexdigest() == task["sha256"][name]
        ), "Pinned dungeon task changed"
runtime = Runtime(config)
owner = "operator-" + str(os.getpid()) + "-" + str(process_identity(os.getpid()))
if a.detach:
    launch_lock = (r / "dungeon-launch.lock").open("a")
    fcntl.flock(launch_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    journal = r / "dungeon-bake-supervisor.json"
    if journal.exists():
        previous = json.loads(journal.read_text())
        unit = previous.get("unit")
        if not isinstance(unit, str) or not unit.startswith("watoom-dungeon-bake-"):
            raise RuntimeError("Unrecognized prior supervisor identity")
        observation = subprocess.run(
            ["systemctl", "show", unit, "-p", "ActiveState", "--value"], capture_output=True, text=True, timeout=10
        )
        if observation.returncode != 0:
            raise RuntimeError("Cannot verify prior supervisor state")
        if observation.stdout.strip() not in ("inactive", "failed"):
            raise RuntimeError("An existing dungeon supervisor has not ended")
    current = runtime.handle({"action": "status"}, private=True, pid=os.getpid(), uid=0)
    if current["phase"] != "qwen-ready" or current["owner"] is not None or current["uncertain"]:
        raise RuntimeError("GPU ownership is not ready for a new bounded task")
    budget = max(2700, 1200 + config["startup_timeout"] + 2 * config["stop_timeout"] + 300)
    stop_budget = config["startup_timeout"] + config["stop_timeout"] + 120
    if budget + stop_budget > 7200:
        raise RuntimeError("Configured recovery exceeds two-hour outer bound")
    unit = "watoom-dungeon-bake-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    command = [
        "systemd-run",
        "--unit=" + unit,
        "--property=RuntimeMaxSec=" + str(budget),
        "--property=TimeoutStopSec=" + str(stop_budget),
        "--property=KillMode=mixed",
        "/usr/bin/python3",
        str(pathlib.Path(__file__).resolve()),
        "--evidence",
        str(r),
        "--dungeon-export",
    ]
    atomic(
        journal,
        {
            "unit": unit,
            "status": "LAUNCH_INTENT",
            "command": command,
            "task_seconds": 1200,
            "restore_startup_seconds": config["startup_timeout"],
            "outer_seconds": budget,
            "stop_seconds": stop_budget,
        },
    )
    launched = subprocess.run(command, capture_output=True, text=True, timeout=20)
    atomic(
        journal,
        {
            "unit": unit,
            "status": "LAUNCHED" if launched.returncode == 0 else "LAUNCH_FAILED",
            "command": command,
            "launch_exit_code": launched.returncode,
            "outer_seconds": budget,
            "stop_seconds": stop_budget,
        },
    )
    if launched.returncode:
        raise RuntimeError("Bounded dungeon supervisor launch failed")
    print(json.dumps({"status": "LAUNCHED", "unit": unit, "outer_seconds": budget, "stop_seconds": stop_budget}))
    raise SystemExit()
generation = None
held = False
child = None
error = None
code = 2
cleanup = False


def check_idle():
    m = Maintenance("watoom-code", "watoom-code", r, True, True)
    active_clear(m.request("/api/session/active"))
    import urllib.request

    with urllib.request.urlopen(config["urls"][config["primary"]] + "/slots", timeout=10) as response:
        v = json.load(response)
    assert (
        isinstance(v, list) and v and all(x.get("is_processing") is False for x in v)
    ), "Active inference; refusing unload"


def status(phase, **kw):
    atomic(
        r / "render-gpu-status.json",
        {"status": phase, "pid": os.getpid(), "owner": owner, "generation": generation, **kw},
    )


def stop(*_):
    if not cleanup:
        raise KeyboardInterrupt


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
try:
    subprocess.run(
        [
            "setpriv",
            "--reuid=1009",
            "--regid=1009",
            "--clear-groups",
            "python3",
            str(pathlib.Path(__file__).with_name("render-editor.py")),
            "--probe-display",
        ],
        check=True,
        timeout=20,
        stdout=subprocess.DEVNULL,
    )
    with runtime.store.exclusive():
        before = runtime.store.load()
        assert (
            before.phase == "qwen-ready" and not before.owner and not before.uncertain and not runtime.journal.pending()
        )
        inventory = {n: runtime.actuator._get(n) for n in runtime.actuator.allowed}
        assert inventory[config["primary"]]["spec"]["replicas"] == 1
        assert all(v["spec"]["replicas"] == 0 for n, v in inventory.items() if n != config["primary"])
        check_idle()
        atomic(r / "render-models-before.private.json", inventory)
        os.chmod(r / "render-models-before.private.json", 0o600)
        generation = before.generation + 1
        atomic(
            runtime.owner_path,
            {"kind": "operator", "job": owner, "pid": os.getpid(), "start": process_identity(os.getpid())},
        )
        runtime.store.save(State("acquiring", owner, generation))
        held = True
        runtime.actuator.generation = generation
        for _ in range(3):
            time.sleep(2)
            check_idle()
        runtime.actuator.scale(config["primary"], 0, generation)
        assert runtime.actuator.stopped(config["primary"])
        runtime.audit("UNREAL_RENDER_ACCEPTANCE_ACQUIRED", runtime.store.load())
    if not a.dungeon_export and os.environ.get("WATOOM_RENDER_EXPANDED") == "1":
        from render_resources import profile as resource_profile

        mem = {
            x.split(":")[0]: int(x.split()[1]) * 1024 for x in pathlib.Path("/proc/meminfo").read_text().splitlines()
        }
        logical = len(os.sched_getaffinity(0))
        profile = resource_profile(mem["MemAvailable"], logical)
        workers = profile["shader_workers"]
        atomic(r / "render-resource-plan.json", profile)
        plan = json.loads((r / "build-plan.json").read_text())
        engine_ini = pathlib.Path(plan["isolated_root"]) / "acceptance/RenderProbe/Config/DefaultEngine.ini"
        text = engine_ini.read_text()
        import re

        text = re.sub(
            r"(?m)^NumUnusedShaderCompilingThreads=.*$",
            "NumUnusedShaderCompilingThreads=" + str(logical - workers),
            text,
        )
        text = re.sub(
            r"(?m)^NumUnusedShaderCompilingThreadsDuringGame=.*$",
            "NumUnusedShaderCompilingThreadsDuringGame=" + str(logical - workers),
            text,
        )
        engine_ini.write_text(text)
    status("RENDERING")
    child = subprocess.Popen(
        ["python3", str(pathlib.Path(__file__).with_name("dungeon-export-runner.py")), "--evidence", str(r)]
        if a.dungeon_export
        else [
            "python3",
            str(pathlib.Path(__file__).with_name("recover-editor.py")),
            "--evidence",
            str(r),
            "--acceptance",
            "render",
            "--run",
        ]
    )
    code = child.wait()
except BaseException as e:
    error = type(e).__name__ + ": " + str(e)
finally:
    cleanup = True
    if child is not None and child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=30)
        except subprocess.TimeoutExpired:
            raise RuntimeError("Acceptance runner did not stop; retain GPU ownership for safe recovery")
    if held:
        status("RESTORING", reason=error)
        try:
            with runtime.store.exclusive():
                state = runtime.store.load()
                assert (state.owner, state.generation) == (owner, generation)
                runtime.store.save(State("restoring", owner, generation, True))
                runtime.controller._restore(owner, generation)
                runtime.audit("UNREAL_RENDER_ACCEPTANCE_RELEASED", runtime.store.load())
        except BaseException as restore_error:
            status(
                "RECOVERY_REQUIRED",
                render_exit_code=code,
                reason=type(restore_error).__name__ + ": " + str(restore_error),
            )
            raise
    status("RESTORED", render_exit_code=code, reason=error)
if error:
    raise RuntimeError(error)
raise SystemExit(code)
