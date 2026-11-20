#!/usr/bin/env python3
"""Temporarily lend game RAM to the existing FAB owners; preserve active inference."""

import argparse, fcntl, json, os, pathlib, signal, subprocess, time

ap = argparse.ArgumentParser()
ap.add_argument("--evidence", required=True, type=pathlib.Path)
ap.add_argument("--completion-file", type=pathlib.Path)
a = ap.parse_args()
out = a.evidence.resolve()
assert out.is_relative_to(pathlib.Path("/data/ai/helper-scripts/reports")) and out.is_dir()
lock = (out / "fab-capacity.lock").open("a")
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)


def atomic(path, value):
    temp = path.with_suffix(".new")
    temp.write_text(json.dumps(value, indent=2))
    os.replace(temp, path)


def status(value, **extra):
    atomic(out / "fab-capacity-status.json", dict(status=value, pid=os.getpid(), **extra))


def kub(*args):
    return json.loads(subprocess.check_output(["kubectl", *args, "-o", "json"], timeout=40))


def change(d, count):
    return kub(
        "-n",
        "enshrouded",
        "patch",
        "deploy",
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


def stop(*_):
    raise KeyboardInterrupt()


def unit(name):
    return subprocess.check_output(
        ["systemctl", "show", name, "--property=ActiveState", "--value"], text=True, timeout=20
    ).strip()


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
game = None
changed = False
frozen = None
reason = None
result = "FAILED"
started = time.monotonic()
try:
    # Freeze only the existing admission coordinator, never its Kubernetes jobs.
    # Existing remote probes finish naturally; no new 6GiB probe competes with download.
    compatibility = {} if a.completion_file else json.loads((out.parent / "compatibility-coordinator.json").read_text())
    if not a.completion_file and unit(compatibility["unit"]) == "active":
        subprocess.run(["systemctl", "freeze", compatibility["unit"]], check=True, timeout=30)
        frozen = compatibility["unit"]
    game = kub("-n", "enshrouded", "get", "deploy", "enshrouded")
    assert game["spec"]["template"]["spec"].get("terminationGracePeriodSeconds", 30) >= 30
    snapshot = out / "fab-game-before.private.json"
    assert not snapshot.exists(), "Use fresh evidence to preserve original snapshot"
    atomic(snapshot, game)
    os.chmod(snapshot, 0o600)
    if game["spec"]["replicas"]:
        status("STOPPING_GAME_GRACEFULLY")
        change(game, 0)
        changed = True
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            d = kub("-n", "enshrouded", "get", "deploy", "enshrouded")
            if not kub("-n", "enshrouded", "get", "pods", "-l", "app=enshrouded")["items"] and not d.get(
                "status", {}
            ).get("replicas", 0):
                break
            time.sleep(3)
        else:
            raise RuntimeError("Game did not stop gracefully")
    if a.completion_file:
        completion = a.completion_file.resolve()
        assert completion.is_relative_to(pathlib.Path("/data/ai/helper-scripts/reports")) and completion.name in {
            "native-status.json",
            "symbol-coverage.json",
        }
        initial = json.loads(completion.read_text())
        watched = initial["pid"]
        identity = pathlib.Path("/proc", str(watched), "stat").read_text().split()[21]
        assert any(
            x in pathlib.Path("/proc", str(watched), "cmdline").read_bytes()
            for x in [b"accept-hyper-combat.py", b"repair-hyper-engine.py", b"backfill-crash-symbols.py"]
        )
        status("CAPACITY_LENT", watched_pid=watched)
        while time.monotonic() - started < 24 * 3600:
            value = json.loads(completion.read_text())
            if value["status"] in {
                "COMPLETE",
                "BLOCKED_MODULE_FAILURE",
                "BLOCKED_TIME_BUDGET",
                "PASS_CORE_BLUEPRINTS",
                "BLOCKED_HEADROOM",
                "BLOCKED_NATIVE_LOAD_OR_COMPILE",
                "PASS_HYPER_ENGINE",
                "BLOCKED_HYPER_ENGINE",
            }:
                result = value["status"]
                break
            assert (
                value["pid"] == watched
                and pathlib.Path("/proc", str(watched), "stat").read_text().split()[21] == identity
            ), "Watched coordinator exited or changed"
            time.sleep(10)
        else:
            raise RuntimeError("24-hour capacity boundary")
    else:
        parent = out.parent
        download = json.loads((parent / "download-coordinator.json").read_text())
        compatibility = json.loads((parent / "compatibility-coordinator.json").read_text())
        fab = pathlib.Path(download["evidence"])
        # A single restart only after sustained child+host reserve; no retry loop.
        stable = 0
        deadline = time.monotonic() + 1200
        while time.monotonic() < deadline:
            free = available()
            stable = stable + 1 if free >= int(4.5 * 1024**3) else 0
            status(
                "WAITING_FOR_DOWNLOAD_HEADROOM",
                memory_available=free,
                required_bytes=int(4.5 * 1024**3),
                models_unchanged=True,
            )
            if stable >= 3:
                break
            time.sleep(5)
        else:
            raise RuntimeError("No sustained download headroom within20min; active inference preserved")
        if json.loads((fab / "download-status.json").read_text())["status"] != "PASS":
            assert unit(download["unit"]) in ("failed", "inactive"), "Existing downloader already owns queue"
            subprocess.run(["systemctl", "reset-failed", download["unit"]], check=False, stderr=subprocess.DEVNULL)
            load = subprocess.check_output(
                ["systemctl", "show", download["unit"], "--property=LoadState", "--value"], text=True, timeout=20
            ).strip()
            if load == "not-found":
                repo = pathlib.Path(__file__).resolve().parents[2]
                subprocess.run(
                    [
                        "systemd-run",
                        "--unit",
                        download["unit"],
                        "--property=MemoryMax=2G",
                        "--property=CPUQuota=100%",
                        "--property=Nice=15",
                        "python3",
                        str(repo / "tools/fab/download-owned.py"),
                        "--evidence",
                        str(fab),
                        "--concurrency",
                        "4",
                        "--asset-hours",
                        "3",
                        "--continue-on-error",
                    ],
                    check=True,
                )
            else:
                subprocess.run(["systemctl", "start", download["unit"]], check=True)
        status(
            "CAPACITY_LENT",
            memory_available=available(),
            models_unchanged=True,
            download_unit=download["unit"],
            compatibility_unit=compatibility["unit"],
        )
        while time.monotonic() - started < 24 * 3600:
            value = json.loads((fab / "download-status.json").read_text())
            status(
                "CAPACITY_LENT",
                completed=len(value.get("completed", [])),
                total=value["total"],
                memory_available=available(),
                models_unchanged=True,
            )
            if unit(download["unit"]) not in ("active", "activating") and value["status"] != "PASS":
                raise RuntimeError("Existing downloader stopped before acquisition PASS; inspect original evidence")
            if value["status"] == "PASS" and frozen:
                subprocess.run(["systemctl", "thaw", frozen], check=True, timeout=30)
                frozen = None
            if value["status"] == "PASS" and unit(compatibility["unit"]) not in ("active", "activating"):
                catalog = out / "catalog"
                catalog.mkdir()
                repo = pathlib.Path(__file__).resolve().parents[2]
                with (out / "catalog.log").open("wb") as log:
                    subprocess.run(
                        ["python3", str(repo / "tools/fab/reconcile-catalog.py"), "--evidence", str(catalog)],
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        check=True,
                        timeout=2100,
                    )
                result = "PASS"
                break
            time.sleep(30)
        else:
            raise RuntimeError("24-hour capacity boundary")
except BaseException as e:
    reason = type(e).__name__ + ": " + str(e)
finally:
    if frozen:
        subprocess.run(["systemctl", "thaw", frozen], check=True, timeout=30)
        frozen = None
    if changed:
        status("RESTORING_GAME", reason=reason)
        current = kub("-n", "enshrouded", "get", "deploy", "enshrouded")
        assert (
            current["metadata"]["uid"] == game["metadata"]["uid"] and current["spec"]["replicas"] == 0
        ), "Game ownership changed; manual reconciliation required"
        assert {k: v for k, v in current["spec"].items() if k != "replicas"} == {
            k: v for k, v in game["spec"].items() if k != "replicas"
        }, "Preserve changed game configuration"
        change(current, game["spec"]["replicas"])
    status("RESTORED", result=result, reason=reason, models_unchanged=True)
if reason:
    raise RuntimeError(reason)
