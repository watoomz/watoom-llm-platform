#!/usr/bin/env python3
"""The ONLY way scripts in this skill start Godot. Builds argv, runs it under xvfb, reads the result, scans the log.

  from gg_godot import run;  r = run(project, "capture", {...})   -> Result(code, why, result, job_dir, report)

Exit codes (shared by every gg_*.py):  0 pass | 1 check failed | 2 refused (bad input) | 3 fatal line in the engine log
| 4 no verdict (timeout, crash, GPU init failure, no result, no @@GG_DONE@@) | 5 runner reported ok:false.
Precedence when several apply: 4, 3, 5, 1.  Godot's own exit code is never trusted: errors print ERROR: and exit 0.
Render ops run under xvfb-run (the dummy --headless renderer draws no pixels); data-only ops use --headless.
In an environment with no real GPU (llvmpipe/software Mesa, e.g. a plain Xvfb host), export
LIBGL_ALWAYS_SOFTWARE=1 before running anything in this skill that touches the engine (render=True or not --
the --import preflight below needs it too): without it Godot can fail GPU/display init with "ERROR: Parameter
"singleton" is null." even under --headless (T-0069, 2026-11-18). The project's own import cache is also
display/renderer-version sensitive: if you switch GG_GODOT to a different godot binary, re-run
`gg_verify.py selftest` for that binary before trusting a render=True op's result (it caches a per-binary pass
report; a mismatched binary is refused, not silently re-checked).
"""
import collections
import datetime
import json
import os
import shutil
import signal
import subprocess
import sys
import time

import gg_log

HERE = os.path.dirname(os.path.abspath(__file__))
RUNTIME = os.path.join(os.path.dirname(HERE), "runtime")
DRIVER = {"forward_plus": "vulkan", "mobile": "vulkan", "gl_compatibility": "opengl3"}
Result = collections.namedtuple("Result", "code why result job_dir report argv")


class Refused(Exception):
    pass


def find_godot():
    for c in (os.environ.get("GG_GODOT"), shutil.which("godot"), "/data/ai/toolchains/godot/4.7.2/godot"):
        if c and os.path.exists(c):
            return c
    return None


LOCK = "runtime.lock.json"


def _sha(path):
    import hashlib
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _runtime_files(base):
    out = {}
    for b, _, files in os.walk(base):
        for f in files:
            if f.endswith(".uid") or f == LOCK:
                continue
            p = os.path.join(b, f)
            out[os.path.relpath(p, base)] = _sha(p)
    return out


def runtime_drift(project):
    """[] when <project>/addons/gg matches runtime.lock.json (and the skill's runtime/); else lines naming the file and both hashes."""
    dest = os.path.join(project, "addons", "gg")
    lock = os.path.join(dest, LOCK)
    if not os.path.exists(lock):
        return []
    with open(lock) as f:
        want = json.load(f)["files"]
    have = _runtime_files(dest)
    msgs = []
    for k in sorted(set(want) | set(have)):
        if want.get(k) != have.get(k):
            msgs.append("addons/gg/%s: lock %s != file %s" % (k, (want.get(k) or "missing")[:10], (have.get(k) or "missing")[:10]))
    return msgs


def install_runtime(project, dry_run=False):
    """Copy runtime/ to <project>/addons/gg, write runtime.lock.json and gg_data/.gdignore. Returns list of files written."""
    dest = os.path.join(project, "addons", "gg")
    wrote = []
    for base, _, files in os.walk(RUNTIME):
        for f in files:
            if f.endswith(".uid"):
                continue
            src = os.path.join(base, f)
            dst = os.path.join(dest, os.path.relpath(src, RUNTIME))
            wrote.append(dst)
            if not dry_run:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copyfile(src, dst)
    if not dry_run:
        with open(os.path.join(dest, LOCK), "w") as f:
            json.dump({"schema": 1, "files": _runtime_files(RUNTIME)}, f, indent=1, sort_keys=True)
    ign = os.path.join(project, "gg_data", ".gdignore")
    if not dry_run and not os.path.exists(ign):
        os.makedirs(os.path.dirname(ign), exist_ok=True)
        open(ign, "w").close()
    return wrote


def build_argv(godot, project, job_dir, *, render, renderer, size, quit_after=3000, xvfb="xvfb-run"):  # quit_after counts main-loop iterations
    base = [godot, "--path", project, "--audio-driver", "Dummy", "--log-file", os.path.join(job_dir, "godot.log")]
    if render:
        if renderer not in DRIVER:
            raise Refused("unknown renderer '%s' (have %s)" % (renderer, ", ".join(sorted(DRIVER))))
        base += ["--rendering-method", renderer, "--rendering-driver", DRIVER[renderer],
                 "--resolution", "%dx%d" % tuple(size), "--fixed-fps", "60"]
        pre = [xvfb, "-a", "-s", "-screen 0 1920x1080x24"]
    else:
        base += ["--headless"]
        pre = []
    base += ["--quit-after", str(quit_after), "-s", "res://addons/gg/gg_runner.gd", "--",
             "--spec=" + os.path.join(job_dir, "spec.json"), "--result=" + os.path.join(job_dir, "result.json")]
    return pre + base


def subprocess_runner(argv, timeout, cwd=None):
    """-> (returncode, combined output, timed_out). Kills the whole process group on timeout."""
    p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
                         start_new_session=True, cwd=cwd)
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out, False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        out, _ = p.communicate()
        return -9, out or "", True


def where(entry):
    """Godot prints the failing file on the next lines ('at: res://x.gd:12', 'GDScript backtrace'); the engine log stays
    on the worker, so the summary must carry it or the model cannot tell which script failed (T-0114)."""
    at = [x.strip() for x in entry.get("at") or [] if x.strip()][:2]
    return (" [" + " | ".join(at) + "]") if at else ""


def decide(rc, timed_out, report, result, job, strict_warnings=False):
    """Pure verdict: (code, why). Precedence 4, 3, 5."""
    classes = {f["cls"] for f in report["fatal"]}
    if timed_out:
        return 4, "timeout: no verdict (a script error inside an awaited op hangs the run)"
    if classes & {"gpu_error", "crash"}:
        first = [f for f in report["fatal"] if f["cls"] in ("gpu_error", "crash")][0]
        return 4, "%s at log line %d: %s" % (first["cls"], first["line_no"], first["text"])
    if result is None or not report["done"]:
        return 4, "no verdict: %s" % ("no result.json" if result is None else "no @@GG_DONE@@ sentinel")
    if result.get("job") != job:
        return 4, "result.json is for job '%s', expected '%s'" % (result.get("job"), job)
    if report["fatal"] or (strict_warnings and report["warnings"]):
        f = (report["fatal"] or report["warnings"])[0]
        return 3, "engine log %s at line %d: %s%s" % (f["cls"], f["line_no"], f["text"], where(f))
    if not result.get("ok"):
        return 5, "runner reported failure: %s" % result.get("error")
    return 0, "ok"


def _new_job(project, op):
    root = os.path.join(project, "gg_data", "jobs")
    os.makedirs(root, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
    n = 0
    while True:
        job = "%s-%s-%d" % (stamp, op, n)
        d = os.path.join(root, job)
        try:
            os.mkdir(d)
            return job, d
        except FileExistsError:
            n += 1


def run(project, op, args=None, *, render=True, renderer="forward_plus", size=(1280, 720), timeout=180,
        strict_warnings=False, runner=subprocess_runner, godot=None, retry_gpu=True, sleep=time.sleep, ensure_import=True):
    project = os.path.abspath(project)
    if not os.path.isfile(os.path.join(project, "project.godot")):
        raise Refused("%s has no project.godot (not a Godot project)" % project)
    if not os.path.isfile(os.path.join(project, "addons", "gg", "gg_runner.gd")):
        raise Refused("%s has no addons/gg runtime; run gg_project.py sync-runtime" % project)
    drift = runtime_drift(project)
    if drift:
        raise Refused("runtime drift (someone edited addons/gg): %s; fix with gg_project.py sync-runtime" % "; ".join(drift[:3]))
    godot = godot or find_godot()
    if not godot:
        raise Refused("godot not found (set GG_GODOT or install godot 4.7.2)")
    job, job_dir = _new_job(project, op)
    spec = {"schema": 1, "op": op, "job": job, "args": args or {}}
    with open(os.path.join(job_dir, "spec.json"), "w") as f:
        json.dump(spec, f, indent=1)
    if ensure_import:
        rc, out, to = runner([godot, "--headless", "--audio-driver", "Dummy", "--path", project, "--import"], 300)
        with open(os.path.join(job_dir, "import.log"), "w") as f:
            f.write(out)
        rep = gg_log.classify(out)
        if to or rep["fatal"]:
            r = rep["fatal"][0]["text"] if rep["fatal"] else "timeout"
            return Result(4 if to else gg_log.exit_code(rep), "project import failed (see import.log; a missing/bad asset or script): " + r, None, job_dir, rep, None)
    nviews = max(len((args or {}).get("views", [])), 1)
    quit_after = 1200 + nviews * (int((args or {}).get("frames", 8)) + 30) * 2
    argv = build_argv(godot, project, job_dir, render=render, renderer=renderer, size=size, quit_after=quit_after)
    open(os.path.join(job_dir, "argv.txt"), "w").write(" ".join(argv) + "\n")
    attempt = 0
    while True:
        attempt += 1
        for stale in ("result.json",):
            p = os.path.join(job_dir, stale)
            if os.path.exists(p):
                os.remove(p)
        rc, out, timed_out = runner(argv, timeout)
        logf = os.path.join(job_dir, "godot.log")
        text = open(logf, errors="replace").read() if os.path.exists(logf) and os.path.getsize(logf) > 0 else out
        with open(os.path.join(job_dir, "console.txt"), "w") as f:
            f.write(out)
        report = gg_log.classify(text)
        result = None
        rp = os.path.join(job_dir, "result.json")
        if os.path.exists(rp):
            try:
                result = json.load(open(rp))
            except ValueError:
                result = None
        code, why = decide(rc, timed_out, report, result, job, strict_warnings)
        if code == 0 and result and not (result.get("engine") or {}).get("rendering_method") and render:
            code, why = 4, "engine did not report its rendering method: cannot confirm the renderer"
        gpu = any(f["cls"] == "gpu_error" for f in report["fatal"])
        if code == 4 and gpu and retry_gpu and attempt == 1:
            sleep(20)  # GPU is shared with LLM servers; contention is transient
            continue
        return Result(code, why, result, job_dir, report, argv)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="low-level: run one runner op and print the verdict")
    ap.add_argument("--project", required=True)
    ap.add_argument("--op", required=True)
    ap.add_argument("--args", default="{}", help="JSON args for the op")
    ap.add_argument("--renderer", default="forward_plus")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--timeout", type=int, default=180)
    a = ap.parse_args(argv)
    try:
        r = run(a.project, a.op, json.loads(a.args), render=not a.no_render, renderer=a.renderer, timeout=a.timeout)
    except Refused as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2
    print("exit %d: %s (job %s)" % (r.code, r.why, r.job_dir))
    return r.code


if __name__ == "__main__":
    sys.exit(main())
