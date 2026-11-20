#!/usr/bin/env python3
"""Operator-side headless Blender job for a native game-worker request; the root dispatcher is the only caller.

Runs the qualified pinned Blender (server-cpu profile) in a transient systemd unit as the unprivileged worker user: no network, no devices,
read-only filesystem except .opencode/blender-out/<job>/, memory/CPU/task/time limits. The script is the model's
own project script or an installed skill script (skill:<skill>/scripts/<file>.py). Writes <evidence>/result.json and
an app-readable copy in .opencode/blender-out/<job>/result.json; exit 0 only when Blender exits 0.
"""

import argparse, hashlib, json, os, pathlib, re, subprocess, sys, time
import blender_job_spec

# The qualified server profile shared by every installed Blender skill script (worker_profile.py checks the same binary,
# version and 4 GiB cgroup), so a requalified profile moves this route and the skills together.
PROFILE = json.loads((blender_job_spec.SKILLS / "blender-export-pipelines/scripts/worker-profiles.json").read_text())[
    "server-cpu"
]
BLENDER = pathlib.Path(PROFILE["binary"])
BLENDER_SHA = PROFILE["sha256"]
WORKER = 1009
# run the script as __main__ with its own folder importable (skill scripts import their sibling helpers)
BOOT = "import sys,runpy,pathlib;s=pathlib.Path({script!r});sys.path.insert(0,str(s.parent));runpy.run_path(str(s),run_name='__main__')"


def atomic(path, value):
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2))
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


OOM_PATTERN = re.compile(r"oom-kill|out of memory|killed process|oom killer|memory cgroup out of memory", re.I)


def is_oom(code, journal):
    """True only for a real memory kill: SIGKILL exit (137) or the kernel/systemd saying so. The bare text 'OOM' is NOT evidence:
    it occurs inside names such as WATOOM_OUTPUT, which made ordinary script errors look like memory exhaustion."""
    return code == 137 or bool(OOM_PATTERN.search(journal or ""))


def diagnose(text):
    """The Python traceback (last one) and Blender error lines, so a failed script names its cause."""
    lines = text.splitlines()
    tb = []
    starts = [i for i, x in enumerate(lines) if x.startswith("Traceback (most recent call last):")]
    if starts:
        i = starts[-1]
        tb = lines[i : i + 40]
        end = next((j for j in range(1, len(tb)) if tb[j] and not tb[j].startswith((" ", "\t"))), None)
        tb = tb[: end + 1] if end is not None else tb
    errors = list(
        dict.fromkeys(x for x in lines if re.match(r"^(Error|ERROR|Warning: Unable|RuntimeError|Exception)\b", x))
    )[:20]
    result = None
    for x in reversed(lines):
        if x.startswith("@@JSON@@"):
            try:
                result = json.loads(x[8:])
            except ValueError:
                result = {"unparsed": x[8:300]}
            break
    if result is not None and len(json.dumps(result)) > 12000:
        # keep the summary fields and drop the bulky per-item list first; the full line stays in the private log
        small = {k: v for k, v in result.items() if len(json.dumps(v)) <= 4000} if isinstance(result, dict) else {}
        result = {**small, "truncated": "script result over 12 KB; large fields dropped"}
    return tb, errors, result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--project", type=pathlib.Path, required=True)
    p.add_argument("--evidence", type=pathlib.Path, required=True)
    p.add_argument("--i-approve", action="store_true")
    p.add_argument("--blender-job", required=True)
    a = p.parse_args()
    if os.geteuid() != 0:
        raise PermissionError("Operator only")
    project = a.project.resolve(strict=True)
    if not a.i_approve or a.project.is_symlink() or project.parent != pathlib.Path("/data/ai/projects/games"):
        raise ValueError("Approved existing game project required")
    a.evidence.mkdir(parents=True, exist_ok=False)
    os.chmod(a.evidence, 0o750)
    receipt = {
        "status": "FAIL",
        "job": a.blender_job,
        "engine": "Blender " + ".".join(map(str, PROFILE["version"])),
        "scope": "Headless Blender script run; visual, rig and engine acceptance stay separate.",
    }
    out = None
    try:
        spec = blender_job_spec.load(project, a.blender_job)
        receipt.update(
            blend=str(spec["blend"].relative_to(project)) if spec["blend"] else None,
            script=spec["script_name"],
            script_sha256=spec["script_sha256"],
            spec_sha256=spec["spec_sha256"],
            memory_limit=str(spec["memory_gib"]) + "GiB",
            deadline_sec=spec["deadline_sec"],
        )
        if hashlib.sha256(BLENDER.read_bytes()).hexdigest() != BLENDER_SHA:
            raise ValueError("pinned Blender changed; operator requalification required")
        dot = project / ".opencode"
        st = dot.stat()
        parent = dot / "blender-out"
        out = parent / a.blender_job
        if out.exists() or out.is_symlink():
            raise ValueError(".opencode/blender-out/" + a.blender_job + " already exists; use a new job name")
        for d in (parent, out):
            if not d.exists():
                d.mkdir(mode=0o2770)
                os.chown(d, st.st_uid, WORKER)
                os.chmod(d, 0o2770)
        if parent.is_symlink() or parent.resolve() != parent:
            raise ValueError(".opencode/blender-out must be a real folder")
        args = [x.replace("{out}", str(out)) for x in spec["args"]]
        unit = "watoom-blender-job-" + str(time.time_ns())
        boot = BOOT.format(script=str(spec["script"]))
        cmd = [
            "systemd-run",
            "--quiet",
            "--wait",
            "--collect",
            "--unit=" + unit,
            "-p",
            "MemoryMax=%dG" % spec["memory_gib"],
            "-p",
            "MemorySwapMax=0",
            "-p",
            "CPUQuota=200%",
            "-p",
            "TasksMax=256",
            "-p",
            "RuntimeMaxSec=%d" % spec["deadline_sec"],
            "-p",
            "TimeoutStopSec=10",
            "-p",
            "KillMode=control-group",
            "-p",
            "NoNewPrivileges=yes",
            "-p",
            "PrivateNetwork=yes",
            "-p",
            "PrivateDevices=yes",
            "-p",
            "PrivateTmp=yes",
            "-p",
            "ProtectSystem=strict",
            "-p",
            "ProtectHome=yes",
            "-p",
            "ReadWritePaths=" + str(out),
            "-p",
            "WorkingDirectory=" + str(project),
            "--setenv=HOME=/tmp",
            "--setenv=WATOOM_OUTPUT=" + str(out),
            "--setenv=WATOOM_SKILLS=" + str(blender_job_spec.SKILLS),
            "--setenv=OMP_NUM_THREADS=2",
            "--",
            "/usr/sbin/setpriv",
            "--reuid=%d" % WORKER,
            "--regid=%d" % WORKER,
            "--clear-groups",
            "--bounding-set=-all",
            "--",
            str(BLENDER),
            "--background",
            *([str(spec["blend"])] if spec["blend"] else []),
            "--factory-startup",
            "-noaudio",
            "--threads",
            "2",
            "--python-exit-code",
            "1",
            "--python-expr",
            boot,
            "--",
            *args,
        ]
        atomic(a.evidence / "prepared.json", {"unit": unit, "project": str(project), "command": cmd})
        started = time.time()
        with (a.evidence / "blender.log").open("w") as log:
            r = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=spec["deadline_sec"] + 60)
        elapsed = round(time.time() - started, 1)
        journal = subprocess.run(
            ["journalctl", "-u", unit, "--no-pager", "-o", "cat", "-n", "400"],
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout
        text = (a.evidence / "blender.log").read_text(errors="replace") + "\n" + journal
        (a.evidence / "blender.log").write_text(text)
        tb, errors, result = diagnose(text)
        files = [x for x in sorted(out.rglob("*")) if x.is_file() and not x.is_symlink()]
        for x in [out, *out.rglob("*")]:
            if not x.is_symlink():
                os.chown(x, st.st_uid, WORKER)
        timed_out = "Timeout" in journal or (r.returncode != 0 and elapsed >= spec["deadline_sec"] - 1)
        oom = is_oom(r.returncode, journal)
        receipt.update(
            exit=r.returncode,
            elapsed_sec=elapsed,
            unit=unit,
            traceback=tb,
            errors=errors,
            script_result=result,
            output_directory=".opencode/blender-out/" + a.blender_job,
            outputs=[{"file": str(x.relative_to(project)), "bytes": x.stat().st_size} for x in files][:200],
            log_tail=[x[:300] for x in text.splitlines()[-30:]],
        )
        if r.returncode == 0:
            receipt["status"] = "PASS"
        else:
            receipt["failure_reason"] = (
                "memory limit %dGiB exceeded; raise memory_gib (max 6) or reduce the scene" % spec["memory_gib"]
                if oom
                else (
                    "deadline %ds exceeded; raise deadline_sec (max 900) or split the job" % spec["deadline_sec"]
                    if timed_out
                    else (
                        "script raised: " + tb[-1][:300]
                        if tb
                        else (
                            "script reported: " + str(result["error"])[:300]
                            if isinstance(result, dict) and result.get("error")
                            else "Blender exited %d; see errors and log_tail" % r.returncode
                        )
                    )
                )
            )
    except (ValueError, OSError, subprocess.TimeoutExpired) as e:
        receipt["failure_reason"] = str(e)[:500]
        receipt.update(
            failure_stage="run" if isinstance(e, subprocess.TimeoutExpired) else "request",
            failure_code="timeout" if isinstance(e, subprocess.TimeoutExpired) else "unknown",
        )
    if receipt.get("status") != "PASS" and not receipt.get("failure_stage"):
        reason = str(receipt.get("failure_reason") or "").lower()
        if "memory limit" in reason or "out of memory" in reason:
            receipt.update(failure_stage="run", failure_code="oom")
        elif "deadline" in reason or "timeout" in reason:
            receipt.update(failure_stage="run", failure_code="timeout")
        elif "script raised" in reason or receipt.get("traceback"):
            receipt.update(failure_stage="run", failure_code="script_error")
        elif "source changed" in reason:
            receipt.update(failure_stage="reconcile", failure_code="source_changed")
        else:
            receipt.update(failure_stage="run", failure_code="worker_error")
        if str(receipt.get("failure_reason") or "").startswith("Command '["):
            receipt["failure_reason"] = "Worker command failed (%s)." % receipt.get("failure_code", "unknown")
    atomic(a.evidence / "result.json", receipt)
    if out is not None and out.is_dir() and not out.is_symlink():
        atomic(out / "result.json", receipt)
        os.chown(out / "result.json", (project / ".opencode").stat().st_uid, WORKER)
        receipt["app_receipt"] = str(out / "result.json")
        atomic(a.evidence / "result.json", receipt)
    print(json.dumps({k: receipt.get(k) for k in ("status", "failure_reason", "exit", "elapsed_sec")}))
    raise SystemExit(0 if receipt["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
