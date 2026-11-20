#!/usr/bin/env python3
"""Restartable isolated Unreal editor build with measured resource boundaries."""

import argparse, pathlib, json, os, subprocess, time, signal, shutil, fcntl, datetime, hashlib

ap = argparse.ArgumentParser()
ap.add_argument("--evidence", required=True, type=pathlib.Path)
ap.add_argument("--target", default="UnrealEditor", choices=["UnrealEditor", "ShaderCompileWorker"])
ap.add_argument("--run", action="store_true")
ap.add_argument("--acceptance", choices=["compile", "commandlet", "render", "render-compile", "render-api"])
a = ap.parse_args()
r = a.evidence
plan = json.loads((r / "build-plan.json").read_text())
build = pathlib.Path(plan["isolated_root"]).resolve()
source = build / "source"
original = pathlib.Path(plan["source"]).resolve()
status_name = "build-status.json"
if a.acceptance:
    acceptance = json.loads((r / "acceptance-plan.json").read_text())
    project = pathlib.Path(acceptance["project"]).resolve()
    assert project.is_relative_to(build / "acceptance")
    for target in ["UnrealEditor", "ShaderCompileWorker"]:
        assert json.loads((r / ("target-" + target + ".json")).read_text())["status"] == "PASS"
    for relative, digest in acceptance["files"].items():
        file = (project.parent / relative).resolve()
        assert file.is_relative_to(project.parent) and hashlib.sha256(file.read_bytes()).hexdigest() == digest, str(
            file
        )
    plan = dict(
        plan,
        parallel_actions=2,
        memory_max_bytes=6 * 1024**3,
        memory_high_bytes=5 * 1024**3,
        cpu_quota="300000 100000",
        maximum_build_seconds=1800,
    )
    if a.acceptance == "render":
        plan.update(parallel_actions=4, memory_max_bytes=12 * 1024**3, memory_high_bytes=11 * 1024**3)
        if os.environ.get("WATOOM_RENDER_EXPANDED") == "1":
            profile = json.loads((r / "render-resource-plan.json").read_text())
            assert profile["status"] == "MEASURED_PREFLIGHT_PASS" and profile["host_reserve_bytes"] >= 2 * 1024**3
            assert 12 * 1024**3 <= profile["memory_max_bytes"] <= 24 * 1024**3
            assert 0 < profile["maximum_build_seconds"] <= 3600
            plan.update(
                {
                    k: profile[k]
                    for k in [
                        "parallel_actions",
                        "memory_max_bytes",
                        "memory_high_bytes",
                        "cpu_quota",
                        "maximum_build_seconds",
                    ]
                }
            )

    status_name = "acceptance-" + a.acceptance + "-status.json"

assert build.is_relative_to(pathlib.Path("/data/ai/builds")) and source != original
assert json.loads((r / "isolated-copy-result.json").read_text())["status"] == "PASS"
mount = json.loads(subprocess.check_output(["findmnt", "--json", "-T", str(source), "-o", "TARGET,FSTYPE,OPTIONS"]))[
    "filesystems"
][0]
assert mount["target"] == str(source) and mount["fstype"] == "overlay"
assert "lowerdir=" + str(build / "lower") in mount["options"] and "upperdir=" + str(build / "upper") in mount["options"]
lower = json.loads(subprocess.check_output(["findmnt", "--json", "-T", str(build / "lower"), "-o", "TARGET,OPTIONS"]))[
    "filesystems"
][0]
assert lower["target"] == str(build / "lower") and "ro" in lower["options"].split(",")
assert plan["uid"] == 1009 and plan["gid"] == 1009
lock = (build / "build.lock").open("w")
if a.run:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
# Never follow a copied absolute symlink back into the protected original.
links = []
# Accepted engine receipts prove the immutable lower tree was already audited.
# Recheck only changed CoW entries during acceptance; never repeat a library-wide walk.
walk_root = build / "upper" if a.acceptance else source
for directory, dirs, files in os.walk(walk_root, followlinks=False):
    if ".git" in dirs:
        dirs.remove(".git")
    for name in dirs + files:
        physical = pathlib.Path(directory) / name
        link = source / physical.relative_to(walk_root) if a.acceptance else physical
        if not link.is_symlink():
            continue
        target = os.readlink(link)
        if target == str(original) or target.startswith(str(original) + "/"):
            replacement = str(source) + target[len(str(original)) :]
            links.append({"path": str(link), "before": target, "after": replacement})
            if a.run:
                link.unlink()
                link.symlink_to(replacement)
(r / "isolated-symlink-plan.json").write_text(json.dumps(links, indent=2))


def available():
    mem = {}
    for line in pathlib.Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        mem[key] = int(value.split()[0]) * 1024
    return {
        "available_memory": mem["MemAvailable"],
        "free_swap": mem["SwapFree"],
        "data_free": shutil.disk_usage(build).free,
        "root_free": shutil.disk_usage("/").free,
    }


pre = available()
(r / "resource-before-build.json").write_text(json.dumps(pre, indent=2))
if pre["available_memory"] < plan["memory_max_bytes"] + 1073741824:
    raise RuntimeError("Insufficient host headroom for the bounded build")
if pre["data_free"] < plan["minimum_data_free_bytes"]:
    raise RuntimeError("Insufficient data disk headroom")
actions = plan.get("parallel_actions", 1)
assert type(actions) is int and 1 <= actions <= 8
assert 0 < plan["memory_high_bytes"] < plan["memory_max_bytes"] <= actions * 3 * 1024**3
args = [
    "setpriv",
    "--no-new-privs",
    "bash",
    str(source / "Engine/Build/BatchFiles/Linux/Build.sh"),
    a.target,
    "Linux",
    "Development",
    "-NoUBA",
    "-NoDumpSyms",
    "-MaxParallelActions=" + str(actions),
]
if a.acceptance:
    args = ["setpriv", "--no-new-privs"] + list(
        json.loads((r / "acceptance-render-plan.json").read_text())["argv"]
        if a.acceptance == "render"
        else (
            json.loads((r / "acceptance-render-plan.json").read_text())["api_argv"]
            if a.acceptance == "render-api"
            else (
                json.loads((r / "acceptance-render-plan.json").read_text())["compile_argv"]
                if a.acceptance == "render-compile"
                else acceptance["compile_argv"] if a.acceptance == "compile" else acceptance["commandlet_argv"]
            )
        )
    )
    if a.acceptance == "compile":
        args = [x for x in args if not x.startswith("-MaxParallelActions=")] + ["-MaxParallelActions=2", "-NoDumpSyms"]
(r / ("acceptance-" + a.acceptance + "-command.json" if a.acceptance else "build-command.json")).write_text(
    json.dumps({"args": args, "uid": 1009, "gid": 1009, "network_build_acceleration": False}, indent=2)
)
if not a.run:
    print(json.dumps({"status": "PREFLIGHT_PASS", "command": args}))
    raise SystemExit(0)
# A new cgroup per attempt retains independent OOM/peak evidence.
stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
group = pathlib.Path("/sys/fs/cgroup") / ("watoom-unreal-" + stamp)
group.mkdir()
for name, value in [
    ("memory.high", str(plan["memory_high_bytes"])),
    ("memory.max", str(plan["memory_max_bytes"])),
    ("memory.swap.max", "0"),
    ("memory.oom.group", "1"),
    ("cpu.max", plan["cpu_quota"]),
    ("pids.max", "256"),
]:
    (group / name).write_text(value)
env = {
    **os.environ,
    "HOME": str(build / "home"),
    "TMPDIR": str(build / "tmp"),
    "XDG_CACHE_HOME": str(build / "home/.cache"),
    "DOTNET_CLI_HOME": str(build / "home"),
    "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
    "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
}


def isolate():
    (group / "cgroup.procs").write_text(str(os.getpid()))
    # The child cannot bypass CoW using an old absolute source path.
    os.unshare(os.CLONE_NEWNS)
    subprocess.run(["mount", "--make-rprivate", "/"], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["mount", "--bind", str(original), str(original)], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["mount", "-o", "remount,bind,ro", str(original)], check=True, stdout=subprocess.DEVNULL)
    options = (
        subprocess.check_output(["findmnt", "-n", "-o", "OPTIONS", "-T", str(original)]).decode().strip().split(",")
    )
    if "ro" not in options:
        raise RuntimeError("Original source is writable in build namespace")
    os.setgroups([])
    os.setgid(1009)
    os.setuid(1009)


def stop(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        if (group / "cgroup.procs").read_text().strip():
            (group / "cgroup.kill").write_text("1")
        return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
    # Descendants may outlive their original shell/process group. This cgroup is owned by this attempt.
    if (group / "cgroup.procs").read_text().strip():
        (group / "cgroup.kill").write_text("1")


def interrupted(*_):
    raise KeyboardInterrupt


signal.signal(signal.SIGTERM, interrupted)
started = time.monotonic()
reason = None
process = None
log = build / "logs" / (("acceptance-" + a.acceptance if a.acceptance else a.target) + "-" + stamp + ".log")
try:
    with log.open("wb") as output:
        process = subprocess.Popen(
            args,
            cwd=source,
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            preexec_fn=isolate,
        )
        plan["full_build_started"] = True
        plan["active_log"] = str(log)
        plan["cgroup"] = str(group)
        (r / ("acceptance-active-plan.json" if a.acceptance else "build-plan.json")).write_text(
            json.dumps(plan, indent=2)
        )
        while process.poll() is None:
            state = available()
            if state["data_free"] < plan["minimum_data_free_bytes"]:
                reason = "data_disk_floor"
            elif pre["data_free"] - state["data_free"] > 214748364800:
                reason = "200GiB_attempt_output_budget"
            elif state["available_memory"] < plan["minimum_host_available_bytes"]:
                reason = "host_memory_floor"
            elif state["root_free"] < 6442450944:
                reason = "root_disk_floor"
            elif time.monotonic() - started > plan["maximum_build_seconds"]:
                reason = "bounded_time_checkpoint"
            status = {
                "status": "RUNNING",
                "pid": process.pid,
                "target": (
                    "WatoomRecoveryProbeEditor"
                    if a.acceptance == "compile"
                    else (
                        "UnrealEditorRender"
                        if a.acceptance == "render"
                        else "WatoomRecoveryVerify" if a.acceptance else a.target
                    )
                ),
                "elapsed_seconds": int(time.monotonic() - started),
                "log": str(log),
                "resources": state,
                "memory_current": int((group / "memory.current").read_text()),
                "memory_events": (group / "memory.events").read_text(),
            }
            (r / status_name).write_text(json.dumps(status, indent=2))
            if reason:
                stop(process)
                break
            time.sleep(5)
        code = process.wait()
except KeyboardInterrupt:
    reason = "operator_interrupt"
    if process is not None:
        stop(process)
        code = process.returncode
    else:
        raise
except BaseException:
    if process is not None:
        stop(process)
    raise
finally:
    metrics = {name: (group / name).read_text() for name in ["memory.events", "memory.peak", "cpu.stat", "pids.events"]}
    (r / ("build-metrics-" + stamp + ".json")).write_text(json.dumps(metrics, indent=2))
events = {line.split()[0]: int(line.split()[1]) for line in metrics["memory.events"].splitlines()}
result = {
    "status": "BLOCKED" if reason or events.get("oom_kill", 0) > 0 else "PASS" if code == 0 else "FAIL",
    "target": (
        "WatoomRecoveryProbeEditor"
        if a.acceptance == "compile"
        else "UnrealEditorRender" if a.acceptance == "render" else "WatoomRecoveryVerify" if a.acceptance else a.target
    ),
    "exit_code": code,
    "stop_reason": reason,
    "elapsed_seconds": int(time.monotonic() - started),
    "log": str(log),
    "metrics": metrics,
    "original_source_unmodified": True,
    "restartable": True,
}
(r / status_name).write_text(json.dumps(result, indent=2))
if a.acceptance == "commandlet" and code == 0:
    text = log.read_text(errors="replace")
    receipt = pathlib.Path(acceptance["required_persistent_receipt"])
    raw = receipt.read_bytes() if receipt.exists() else b""
    version = raw.decode(
        "utf-16" if raw.startswith((bytes.fromhex("fffe"), bytes.fromhex("feff"))) else "utf-8-sig", errors="replace"
    ).strip()
    result["runtime_version"] = version
    if acceptance["required_marker"] not in text or not version.startswith("5.8.3"):
        result["status"] = "FAIL"
        result["stop_reason"] = "runtime_marker_or_persistent_receipt_missing"
        code = 2
    (r / status_name).write_text(json.dumps(result, indent=2))
if reason and code == 0:
    code = 2
print(json.dumps(result))
if code:
    raise SystemExit(2)
