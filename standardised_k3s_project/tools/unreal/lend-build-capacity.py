#!/usr/bin/env python3
"""Hold the existing GPU ownership lock protocol while lending idle model RAM to Unreal."""

import argparse, dataclasses, fcntl, json, os, pathlib, signal, subprocess, sys, time, urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("--evidence", required=True, type=pathlib.Path)
ap.add_argument("--restore", action="store_true")
a = ap.parse_args()
r = a.evidence.resolve()
assert r.is_relative_to("/data/ai/helper-scripts/reports")
receipt = r / "capacity-status.json"
if a.restore:
    state = json.loads(receipt.read_text())
    pid = state["guardian_pid"]
    assert b"lend-build-capacity.py" in pathlib.Path("/proc", str(pid), "cmdline").read_bytes()
    os.kill(pid, signal.SIGTERM)
    print("RESTORE_REQUESTED")
    raise SystemExit()
lock = (r / "capacity.lock").open("w")
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
sys.path.insert(0, "/data/ai/helper-scripts/gpu-controller")
from g3h_service import Runtime, atomic, process_identity
from controller import State

config = json.loads(pathlib.Path("/data/ai/helper-scripts/config/gpu-controller.json").read_text())
runtime = Runtime(config)
owner = "operator-" + str(os.getpid()) + "-" + str(process_identity(os.getpid()))
generation = None
game = None
held = False
ready = False
why = None


def status(phase, **kw):
    atomic(
        receipt,
        {
            "status": phase,
            "guardian_pid": os.getpid(),
            "gpu_owner": owner,
            "generation": generation,
            "primary": config["primary"],
            **kw,
        },
    )


def kub(*args):
    return json.loads(subprocess.check_output(["kubectl", *args, "-o", "json"], timeout=40))


def replicas(d, count):
    return kub(
        "-n",
        "enshrouded",
        "patch",
        "deployment",
        "enshrouded",
        "--type=json",
        "-p",
        json.dumps(
            [
                {"op": "test", "path": "/metadata/uid", "value": d["metadata"]["uid"]},
                {"op": "test", "path": "/spec/replicas", "value": d["spec"]["replicas"]},
                {"op": "replace", "path": "/spec/replicas", "value": count},
            ]
        ),
    )


def slots():
    with urllib.request.urlopen(config["urls"][config["primary"]] + "/slots", timeout=10) as response:
        v = json.load(response)
    assert (
        isinstance(v, list) and v and all(x.get("is_processing") is False for x in v)
    ), "Active or unverifiable inference; refusing unload"


def stop(*_):
    raise KeyboardInterrupt


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
try:
    with runtime.store.exclusive():
        before = runtime.store.load()
        assert (
            before.phase == "qwen-ready" and not before.owner and not before.uncertain and not runtime.journal.pending()
        ), "GPU ownership not idle"
        inventory = {n: runtime.actuator._get(n) for n in runtime.actuator.allowed}
        assert inventory[config["primary"]]["spec"]["replicas"] == 1
        assert all(d["spec"]["replicas"] == 0 for n, d in inventory.items() if n != config["primary"])
        atomic(r / "capacity-models-before.private.json", inventory)
        os.chmod(r / "capacity-models-before.private.json", 0o600)
        slots()
        generation = before.generation + 1
        atomic(
            runtime.owner_path,
            {"kind": "operator", "job": owner, "pid": os.getpid(), "start": process_identity(os.getpid())},
        )
        runtime.store.save(State("acquiring", owner, generation))
        held = True
        runtime.actuator.generation = generation
        status("DRAINING_MODEL")
        # New routed requests cannot acquire GPU ownership after the durable claim.
        for _ in range(3):
            time.sleep(2)
            slots()
        runtime.actuator.scale(config["primary"], 0, generation)
        assert runtime.actuator.stopped(config["primary"]), "Model shutdown unverified"
        runtime.audit("UNREAL_BUILD_CAPACITY_ACQUIRED", runtime.store.load())
    game = kub("-n", "enshrouded", "get", "deployment", "enshrouded")
    assert game["spec"]["template"]["spec"].get("terminationGracePeriodSeconds", 30) >= 30
    atomic(r / "capacity-enshrouded-before.private.json", game)
    os.chmod(r / "capacity-enshrouded-before.private.json", 0o600)
    if game["spec"]["replicas"]:
        replicas(game, 0)
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            current = kub("-n", "enshrouded", "get", "deployment", "enshrouded")
            pods = kub("-n", "enshrouded", "get", "pods", "-l", "app=enshrouded")["items"]
            if current.get("status", {}).get("replicas", 0) == 0 and not pods:
                break
            time.sleep(3)
        else:
            raise RuntimeError("Enshrouded graceful shutdown incomplete")
    repo = pathlib.Path("/data/github/watoom-standardised-homelab/standardised_k3s_project")
    subprocess.run(
        [
            "python3",
            str(repo / "tools/unreal/tune-build.py"),
            "--evidence",
            str(r),
            "--parallel-actions",
            "4",
            "--apply",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    ready = True
    status("CAPACITY_LENT", parallel_actions=4, memory_max_bytes=12 * 1024**3, cpu_cores=6)  # replaced below
    while True:
        try:
            state = json.loads((r / "coordinator-status.json").read_text())
        except json.JSONDecodeError:
            time.sleep(1)
            continue
        if state["status"] != "RUNNING":
            break
        time.sleep(10)
except KeyboardInterrupt:
    why = "Operator requested restoration"
except BaseException as e:
    why = str(e)
finally:
    if held:
        status("RESTORING", reason=why)
        # Return to the baseline envelope before bringing the 9GiB model back.
        # Avoid terminating a compiler: queue baseline for the next existing checkpoint.
        planpath = r / "build-plan.json"
        plan = json.loads(planpath.read_text())
        if ready and json.loads((r / "coordinator-status.json").read_text())["status"] == "RUNNING":
            plan.update(
                parallel_actions=1,
                memory_max_bytes=3 * 1024**3,
                memory_high_bytes=int(2.75 * 1024**3),
                cpu_quota="150000 100000",
                flags=["-NoUBA", "-NoDumpSyms", "-MaxParallelActions=1"],
            )
            atomic(planpath, plan)
            while True:
                active = json.loads((r / "build-plan.json").read_text())
                cg = pathlib.Path(active["cgroup"])
                if not (cg / "cgroup.procs").read_text().strip() or int((cg / "memory.max").read_text()) <= 3 * 1024**3:
                    break
                time.sleep(5)
        with runtime.store.exclusive():
            state = runtime.store.load()
            assert (state.owner, state.generation) == (owner, generation), "Ownership changed; refusing restoration"
            runtime.store.save(State("restoring", owner, generation, True))
            runtime.controller._restore(owner, generation)
            runtime.audit("UNREAL_BUILD_CAPACITY_RELEASED", runtime.store.load())
    if game and game["spec"]["replicas"]:
        current = kub("-n", "enshrouded", "get", "deployment", "enshrouded")
        assert current["metadata"]["uid"] == game["metadata"]["uid"] and current["spec"]["replicas"] == 0
        assert {k: v for k, v in current["spec"].items() if k != "replicas"} == {
            k: v for k, v in game["spec"].items() if k != "replicas"
        }, "Game configuration changed; preserve user changes"
        replicas(current, game["spec"]["replicas"])
    status("RESTORED", reason=why)
