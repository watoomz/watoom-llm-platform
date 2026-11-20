#!/usr/bin/env python3
"""One detached coordinator; resume bounded owned build phases, stop on any real fault."""

import argparse, pathlib, json, subprocess, time, os, fcntl, signal, re, hashlib

ap = argparse.ArgumentParser()
ap.add_argument("--evidence", required=True, type=pathlib.Path)
ap.add_argument("--max-hours", type=int, default=24)
a = ap.parse_args()
assert 1 <= a.max_hours <= 24
r = a.evidence
plan = json.loads((r / "build-plan.json").read_text())
build = pathlib.Path(plan["isolated_root"])
lock = (build / "coordinator.lock").open("w")
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
deadline = time.monotonic() + a.max_hours * 3600
child = None


def save(value):
    value.update({"coordinator_pid": os.getpid(), "max_hours": a.max_hours})
    (r / "coordinator-status.json").write_text(json.dumps(value, indent=2))


def interrupt(*_):
    raise KeyboardInterrupt


signal.signal(signal.SIGTERM, interrupt)


def cancel():
    if child is not None and child.poll() is None:
        child.send_signal(signal.SIGINT)
        try:
            child.wait(timeout=25)
        except subprocess.TimeoutExpired:
            # The inner supervisor remains responsible for its already bounded cgroup;
            # never kill it and abandon the owned compiler group.
            save({"status": "BLOCKED", "reason": "Inner build supervisor cancellation requires attention"})
            raise RuntimeError("Inner supervisor did not acknowledge cancellation")


try:
    # Keep prior phase evidence intact when resuming a stopped coordinator.
    phase = max(
        [
            0,
            *[
                int(match.group(1))
                for file in r.glob("phase-*-*.json")
                if (match := re.fullmatch(r"phase-(\d+)-(UnrealEditor|ShaderCompileWorker)\.json", file.name))
            ],
        ]
    )
    for target in ["UnrealEditor", "ShaderCompileWorker"]:
        receipt = r / ("target-" + target + ".json")
        if receipt.exists() and json.loads(receipt.read_text()).get("status") == "PASS":
            continue
        while True:
            remaining = int(deadline - time.monotonic())
            if remaining < 240:
                save({"status": "BLOCKED", "reason": "24-hour recovery budget reached", "target": target})
                raise SystemExit(2)
            phase += 1
            current = json.loads((r / "build-plan.json").read_text())
            current["maximum_build_seconds"] = min(1800, remaining - 120)
            (r / "build-plan.json").write_text(json.dumps(current, indent=2))
            save(
                {
                    "status": "RUNNING",
                    "target": target,
                    "phase": phase,
                    "reason": "Bounded isolated compilation; acceptance and promotion pending",
                }
            )
            with (r / ("coordinator-phase-" + str(phase) + "-" + target + ".log")).open("wb") as log:
                child = subprocess.Popen(
                    [
                        "python3",
                        str(pathlib.Path(__file__).with_name("recover-editor.py")),
                        "--evidence",
                        str(r),
                        "--target",
                        target,
                        "--run",
                    ],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                while child.poll() is None:
                    try:
                        state = json.loads((r / "build-status.json").read_text())
                        path = pathlib.Path(state["log"])
                        with path.open("rb") as stream:
                            stream.seek(max(0, path.stat().st_size - 32768))
                            tail = stream.read().decode(errors="replace")
                        actions = re.findall(r"\[(\d+)/(\d+)\][^\n]*", tail)
                        progress = {
                            "status": "RUNNING",
                            "target": target,
                            "phase": phase,
                            "runner_pid": child.pid,
                            "build": state,
                            "latest_actions": actions[-3:],
                            "log": str(path),
                        }
                        save(progress)
                    except (FileNotFoundError, KeyError, json.JSONDecodeError):
                        pass
                    time.sleep(10)
                code = child.wait()
                child = None
            state = json.loads((r / "build-status.json").read_text())
            (r / ("phase-" + str(phase) + "-" + target + ".json")).write_text(json.dumps(state, indent=2))
            if code == 0 and state.get("status") == "PASS" and state.get("target") == target:
                binary = build / "source/Engine/Binaries/Linux" / target
                if not binary.is_file():
                    raise RuntimeError("Build reported success without the expected real executable")
                receipt.write_text(
                    json.dumps(
                        {
                            "status": "PASS",
                            "target": target,
                            "binary": str(binary),
                            "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                            "build": state,
                        },
                        indent=2,
                    )
                )
                break
            if state.get("stop_reason") == "bounded_time_checkpoint":
                continue
            save(
                {
                    "status": "BLOCKED" if state.get("status") == "BLOCKED" else "FAIL",
                    "target": target,
                    "phase": phase,
                    "build": state,
                    "reason": "Build/resource failure; original preserved, no promotion attempted",
                }
            )
            raise SystemExit(2)
    save(
        {
            "status": "BUILD_COMPLETE_ACCEPTANCE_PENDING",
            "editor_build": "PASS",
            "shader_worker_build": "PASS",
            "next": "Validate real version/shared libraries and an isolated C++ project/commandlet, then integrate using the existing Toolkit architecture. Original wrapper/configuration remain unchanged.",
        }
    )
except KeyboardInterrupt:
    cancel()
    save({"status": "INTERRUPTED", "reason": "Operator requested stop; isolated intermediate outputs retained"})
    raise SystemExit(2)
except Exception as error:
    cancel()
    save({"status": "FAIL", "reason": str(error), "original_preserved": True})
    raise
