#!/usr/bin/env python3
"""Break-glass recovery for the LLM / inference stack.

Returns the stack to a known good state when gates, claims, holds or workers are stuck and nobody can
fix them by hand. Two modes, both started from the Glance Command Center (PIN protected) or by the root operator:

  stale  Clears only what is provably orphaned: execution claims whose owner is interrupted and idle, finished or
         very old worker pods/jobs/units, a GPU owner whose process has ended, and GPU deployment identity records
         left stale by a deployment that was deleted and recreated instead of scaled. Live work is never touched.
  force  Stops the app, stops workers, repairs the app database (claims, queued inbox, running jobs), removes a
         held deployment guard, reconciles stale GPU deployment identity records, recovers GPU ownership through
         the GPU controller, restarts the router, brings the app back and checks health. Running work is
         interrupted; session history is preserved.

Every run snapshots the app database first and writes an evidence bundle under STATE/runs/<timestamp>/.
`diagnose` is read-only. The root service runs `scan`, which also keeps STATE/status.json fresh for Glance.
"""
import argparse
import contextlib
import fcntl
import glob
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE = pathlib.Path(os.environ.get("BREAK_GLASS_STATE", "/data/ai/helper-scripts/state/break-glass"))
APP_DIR = pathlib.Path(os.environ.get("BREAK_GLASS_APP_DIR", "/data/ai/watoom-code"))
DB = APP_DIR / "application.sqlite"
GUARD_FILE = APP_DIR / "watoom-release-guard.json"
GPU_STATE = pathlib.Path("/data/ai/helper-scripts/state/gpu-controller")
GPU_SOCKET = pathlib.Path("/data/ai/helper-scripts/state/gpu-controller-private/worker.sock")
GPU_CODE = pathlib.Path("/data/ai/helper-scripts/gpu-controller")
GPU_CONTROLLER_CONFIG = pathlib.Path("/data/ai/helper-scripts/config/gpu-controller.json")
GPU_CONTROLLER_UNIT = "watoom-gpu-controller.service"
APP_NS, APP_DEPLOY = "watoom-code", "watoom-code"
LLM_NS, ROUTER_DEPLOY = "llama-cpp", "llm-router"
WORKER_LABEL = "app=watoom-toolkit-worker"
WORKER_UNIT_GLOBS = ("watoom-*-worker.service", "watoom-rig-async-stage.service", "watoom-workstation-render-stage-scan.service")
STALE_WORKER_AGE_S = 6 * 3600
MAX_REQUEST_AGE_S = 180
COOLDOWN_S = 120
KEEP_RUNS = 5
MODES = ("stale", "force")
REQUIRED_MODELS = {"swift-qwen38-coder", "gemma-4-e4b", "llama-mesh", "active-model"}


# ---------------------------------------------------------------- helpers
def now():
    return time.time()


def run(args, check=True, timeout=120, input=None):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, input=input)
    if check and result.returncode:
        raise RuntimeError("%s failed: %s" % (" ".join(args[:4]), (result.stderr or result.stdout).strip()[:300]))
    return result


def kub(*args, check=True, timeout=120):
    return run(["kubectl", *args], check=check, timeout=timeout)


def kub_json(*args):
    return json.loads(kub(*args, "-o", "json").stdout)


def atomic_write(path, value, mode=0o644):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name("." + path.name + ".new")
    temp.write_text(json.dumps(value, indent=2, default=str))
    os.chmod(temp, mode)
    os.replace(temp, path)


def safe(fn, *args, **kwargs):
    """Diagnosis must never abort on one broken probe; the error becomes part of the report."""
    try:
        return fn(*args, **kwargs)
    except Exception as error:  # noqa: BLE001 - reported, not hidden
        return {"error": "%s: %s" % (type(error).__name__, str(error)[:240])}


# ---------------------------------------------------------------- application database
def _ro(path):
    return sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=5)


def db_diagnose(path=DB):
    """Read-only view of every durable gate that can wedge the app (same sources as release_guard.durable_clearance)."""
    with contextlib.closing(_ro(path)) as db:
        tables = {name for (name,) in db.execute("select name from sqlite_master where type='table'")}
        claims = [dict(zip(("id", "parent_id", "time_suspended", "time_updated", "parent_idle", "parent_outcome"), row)) for row in db.execute(
            "SELECT s.id,s.parent_id,s.time_suspended,s.time_updated,p.time_idle,p.idle_outcome FROM session_v2 s "
            "LEFT JOIN session_v2 p ON p.id=s.parent_id WHERE s.time_suspended IS NOT NULL")]
        for claim in claims:
            claim["orphan"] = bool(claim["parent_id"]) and claim.pop("parent_idle") is not None and claim.pop("parent_outcome") == "interrupted"
            claim.pop("parent_idle", None)
            claim.pop("parent_outcome", None)
        out = {"claims": claims}
        out["inbox"] = db.execute("select count(*) from session_inbox").fetchone()[0] if "session_inbox" in tables else 0
        out["running_jobs"] = db.execute("select count(*) from job where status='running'").fetchone()[0] if "job" in tables else 0
        background = 0
        if "kv" in tables:
            for (value,) in db.execute("select value from kv where key like 'job.background/%'"):
                with contextlib.suppress(ValueError):
                    background += json.loads(value).get("status") == "running"
        out["background_jobs"] = background
        unsettled = uncertain_gpu = 0
        if "_watoom_specialist_job" in tables:
            for phase, body, generation in db.execute("select phase,specialist_body,generation from _watoom_specialist_job"):
                unsettled += phase not in ("completed", "failed", "uncertain")
                if phase == "uncertain":
                    with contextlib.suppress(ValueError, AttributeError):
                        uncertain_gpu += generation is not None or json.loads(body).get("execution") != "cpu"
        out["unsettled_specialists"], out["uncertain_gpu_specialists"] = unsettled, uncertain_gpu
    return out


def db_repair(path, evidence_file):
    """Force-mode repair. The app must be stopped. Saves every affected row, then clears them in one transaction."""
    path = pathlib.Path(path)
    owner = path.stat()
    with contextlib.closing(sqlite3.connect(str(path), timeout=30, isolation_level=None)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        try:
            tables = {row[0] for row in db.execute("select name from sqlite_master where type='table'")}
            evidence = {"time": now()}
            evidence["claims"] = [dict(r) for r in db.execute("select id,parent_id,time_suspended,time_updated,resume_attempts from session_v2 where time_suspended is not null")]
            counts = {"claims": len(evidence["claims"])}
            db.execute("UPDATE session_v2 SET time_suspended=NULL,resume_attempts=0,time_updated=time_updated WHERE time_suspended IS NOT NULL")
            if "session_inbox" in tables:
                evidence["inbox"] = [dict(r) for r in db.execute("select * from session_inbox")]
                counts["inbox"] = db.execute("DELETE FROM session_inbox").rowcount
            if "job" in tables:
                evidence["jobs"] = [dict(r) for r in db.execute("select notification_id,id,session_id,kind,status from job where status='running'")]
                counts["jobs"] = db.execute("UPDATE job SET status='cancelled',error='break-glass reset',time_updated=? WHERE status='running'", (int(now() * 1000),)).rowcount
            if "kv" in tables:
                evidence["background"], changed = [], 0
                for row in db.execute("select key,value from kv where key like 'job.background/%'").fetchall():
                    try:
                        value = json.loads(row["value"])
                    except ValueError:
                        continue
                    if isinstance(value, dict) and value.get("status") == "running":
                        evidence["background"].append({"key": row["key"], "value": row["value"]})
                        value["status"] = "cancelled"
                        db.execute("UPDATE kv SET value=? WHERE key=?", (json.dumps(value), row["key"]))
                        changed += 1
                counts["background"] = changed
            if "_watoom_specialist_job" in tables:
                evidence["specialists"] = [dict(r) for r in db.execute("select id,phase,generation from _watoom_specialist_job where phase not in ('completed','failed','uncertain')")]
                counts["specialists"] = db.execute("UPDATE _watoom_specialist_job SET phase='failed',error='break-glass reset' WHERE phase NOT IN ('completed','failed','uncertain')").rowcount
            atomic_write(evidence_file, evidence, 0o600)
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("Database integrity check failed after repair; restore the snapshot from this run")
    # Root must not leave root-owned WAL/SHM files behind: the app runs unprivileged.
    for suffix in ("", "-wal", "-shm"):
        side = pathlib.Path(str(path) + suffix)
        if side.exists():
            os.chown(side, owner.st_uid, owner.st_gid)
    return counts


# ---------------------------------------------------------------- application, workers, GPU, inference
def app_state():
    deploy = kub_json("-n", APP_NS, "get", "deploy", APP_DEPLOY)
    return {"replicas": deploy["spec"].get("replicas"), "ready": deploy["status"].get("readyReplicas", 0),
            "guard_file_present": GUARD_FILE.exists()}


def _age(timestamp):
    return int(now() - time.mktime(time.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")) + time.timezone)


def worker_state():
    pods = []
    for pod in kub_json("-n", APP_NS, "get", "pods", "-l", WORKER_LABEL)["items"]:
        phase = pod["status"].get("phase")
        age = _age(pod["metadata"]["creationTimestamp"])
        pods.append({"name": pod["metadata"]["name"], "phase": phase, "age_s": age,
                     "stale": phase in ("Succeeded", "Failed") or age > STALE_WORKER_AGE_S})
    jobs = [{"name": job["metadata"]["name"], "age_s": _age(job["metadata"]["creationTimestamp"])}
            for job in kub_json("-n", APP_NS, "get", "jobs", "-l", WORKER_LABEL)["items"]]
    units = []
    names = sorted({unit.split()[0] for pattern in WORKER_UNIT_GLOBS for unit in run(["systemctl", "list-units", pattern, "--no-legend", "--plain", "--all"], check=False).stdout.splitlines() if unit.strip()})
    names += [u.split()[0] for u in run(["systemctl", "list-units", "llama-mesh-*", "--no-legend", "--plain"], check=False).stdout.splitlines() if u.strip()]
    for name in names:
        show = dict(line.split("=", 1) for line in run(["systemctl", "show", name, "-p", "ActiveState,SubState,ExecMainStartTimestamp"], check=False).stdout.splitlines() if "=" in line)
        if show.get("ActiveState") in ("active", "activating", "deactivating") and show.get("SubState") not in ("exited", "dead"):
            started = show.get("ExecMainStartTimestamp", "")
            try:
                age = int(now() - time.mktime(time.strptime(started.split(" ", 1)[1].rsplit(" ", 1)[0], "%Y-%m-%d %H:%M:%S")))
            except (ValueError, IndexError):
                age = 0
            units.append({"name": name, "state": show.get("ActiveState"), "age_s": age, "stale": age > STALE_WORKER_AGE_S})
    return {"pods": pods, "jobs": jobs, "units": units}


def process_identity(pid):
    """Start-time field of /proc/<pid>/stat; a recycled pid will not match the recorded start."""
    try:
        return pathlib.Path("/proc/%d/stat" % pid).read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError, ValueError):
        return None


def gpu_client():
    sys.path.insert(0, str(GPU_CODE))
    from client import GPUClient  # noqa: PLC0415 - host-only module
    return GPUClient(GPU_SOCKET, timeout=300)


def owner_ended(status):
    """True when the recorded GPU owner is provably gone (mirrors the controller's own emergency check)."""
    owner = status.get("owner")
    if not owner:
        return False
    registry = json.loads((GPU_STATE / "worker.json").read_text())
    if registry.get("job") != owner:
        raise RuntimeError("owner identity does not match durable registry")
    if registry.get("kind") in ("router", "operator"):
        return process_identity(registry["pid"]) != registry["start"]
    state = run(["systemctl", "show", "llama-mesh-" + owner, "--property=ActiveState", "--value"], check=False).stdout.strip()
    return state not in ("active", "activating", "deactivating")


def deployment_spec_digest(obj):
    """Mirrors the GPU controller's own identity hash (g3h_service.ProductionActuator._get)."""
    spec = dict(obj["spec"])
    spec.pop("replicas", None)
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def identity_mismatches():
    """Deployments whose recorded identity no longer matches the live object: it was deleted and
    recreated (e.g. during a model decommission) instead of scaled, which otherwise wedges the
    controller permanently -- it can neither start (cutover-proof check) nor scale that name again
    (_get identity check)."""
    config = json.loads(GPU_CONTROLLER_CONFIG.read_text())
    stale = []
    for name, expected in config.get("deployment_identity", {}).items():
        try:
            obj = kub_json("-n", LLM_NS, "get", "deploy", name)
        except RuntimeError:
            stale.append(name)  # deployment no longer exists at all
            continue
        if obj["metadata"]["uid"] != expected.get("uid") or deployment_spec_digest(obj) != expected.get("spec_sha256"):
            stale.append(name)
    return stale


def repair_deployment_identity(names):
    """Drop stale deployment_identity records for recreated/removed deployments and refresh their
    Service URL, then restart the controller so it picks up the corrected config. Only removes the
    identity record (which the running config no longer needs to match); never touches urls/models
    entries beyond refreshing the ClusterIP, so the deployment stays usable."""
    if not names:
        return "no stale identity records"
    config = json.loads(GPU_CONTROLLER_CONFIG.read_text())
    for name in names:
        config["deployment_identity"].pop(name, None)
        try:
            svc = kub_json("-n", LLM_NS, "get", "svc", name)
            config["urls"][name] = "http://%s:%d" % (svc["spec"]["clusterIP"], svc["spec"]["ports"][0]["port"])
        except (RuntimeError, KeyError, IndexError):
            pass  # service gone too; leave the URL for an operator to remove the model entirely
    atomic_write(GPU_CONTROLLER_CONFIG, config, 0o600)
    run(["systemctl", "restart", GPU_CONTROLLER_UNIT], timeout=30)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if run(["systemctl", "is-active", GPU_CONTROLLER_UNIT], check=False).stdout.strip() == "active":
            return "reconciled identity for %s; controller restarted" % ", ".join(names)
        time.sleep(2)
    raise RuntimeError("controller did not come back active after identity reconciliation")


def gpu_state():
    status = gpu_client().call("status")
    leases = json.loads((GPU_STATE / "inference-leases.json").read_text()).get("leases", {})
    dead = [name[:12] for name, lease in leases.items() if process_identity(int(lease["pid"])) != str(lease["start"])]
    return {"owner": status.get("owner"), "phase": status.get("phase"), "uncertain": status.get("uncertain"),
            "generation": status.get("generation"), "primary": status.get("primary"),
            "owner_ended": owner_ended(status), "leases": len(leases), "dead_leases": dead,
            "stale_identity": identity_mismatches()}


def inference_state():
    router = kub_json("-n", LLM_NS, "get", "deploy", ROUTER_DEPLOY)["status"].get("readyReplicas", 0)
    selected = json.loads((GPU_STATE / "selected-model.json").read_text()).get("deployment")
    model_ready = kub_json("-n", LLM_NS, "get", "deploy", selected)["status"].get("readyReplicas", 0) if selected else 0
    return {"router_ready": router, "selected_model": selected, "selected_model_ready": model_ready}


def diagnose():
    report = {"time": now(), "app": safe(app_state), "database": safe(db_diagnose), "workers": safe(worker_state),
              "gpu": safe(gpu_state), "inference": safe(inference_state)}
    report["problems"] = problems(report)
    report["healthy"] = not report["problems"]
    report["live_claims"] = [c["id"] for c in report["database"].get("claims", []) if not c["orphan"]]
    return report


def problems(report):
    found = []
    live = 0
    for name in ("app", "database", "workers", "gpu", "inference"):
        if "error" in report[name]:
            found.append("%s could not be inspected: %s" % (name, report[name]["error"]))
    app, db, workers, gpu, inference = (report[k] for k in ("app", "database", "workers", "gpu", "inference"))
    if "error" not in app:
        if app["guard_file_present"]:
            found.append("Deployment guard is held (blocks all new work)")
        if app["ready"] < 1:
            found.append("App is not ready")
    if "error" not in db:
        orphans = [c for c in db["claims"] if c["orphan"]]
        live = len(db["claims"]) - len(orphans)  # a held claim whose owner is still active is a running job, not a wedge
        if orphans:
            found.append("%d orphaned execution claim(s) held" % len(orphans))
        for key, label in (("inbox", "queued session inputs"), ("running_jobs", "jobs marked running"), ("background_jobs", "background jobs marked running"),
                           ("unsettled_specialists", "unsettled specialist jobs"), ("uncertain_gpu_specialists", "specialist jobs with uncertain GPU ownership")):
            if db[key] and not live:  # with a live job, its own queue entries and running markers are expected
                found.append("%d %s" % (db[key], label))
    if "error" not in workers:
        stale = [p["name"] for p in workers["pods"] if p["stale"]] + [u["name"] for u in workers["units"] if u["stale"]]
        if stale:
            found.append("%d stale worker(s): %s" % (len(stale), ", ".join(stale[:4])))
    if "error" not in gpu:
        if gpu["owner"] and (gpu["owner_ended"] or not live):
            found.append("GPU owned by %s (%s)" % (gpu["owner"], "ended" if gpu["owner_ended"] else "still running"))
        if gpu["uncertain"]:
            found.append("GPU state uncertain")
        if gpu["phase"] != "qwen-ready":
            found.append("GPU phase is %s, not qwen-ready" % gpu["phase"])
        if gpu["dead_leases"]:
            found.append("%d inference lease(s) whose process is gone" % len(gpu["dead_leases"]))
        if gpu.get("stale_identity"):
            found.append("%d deployment(s) with a stale identity record (deleted/recreated instead of scaled): %s" % (len(gpu["stale_identity"]), ", ".join(gpu["stale_identity"][:4])))
    if "error" not in inference and (inference["router_ready"] < 1 or inference["selected_model_ready"] < 1):
        found.append("Inference not ready (router %s, model %s)" % (inference["router_ready"], inference["selected_model"]))
    return found


# ---------------------------------------------------------------- actions
class Run:
    def __init__(self, mode, directory):
        self.mode, self.dir, self.steps = mode, directory, []

    def step(self, name, fn, *args):
        started = now()
        try:
            detail = fn(*args)
            entry = {"step": name, "ok": True, "detail": detail, "seconds": round(now() - started, 1)}
        except Exception as error:  # noqa: BLE001 - the run continues; the report shows what failed
            entry = {"step": name, "ok": False, "detail": "%s: %s" % (type(error).__name__, str(error)[:300]), "seconds": round(now() - started, 1)}
        self.steps.append(entry)
        atomic_write(self.dir / "steps.json", self.steps, 0o600)
        return entry["ok"]


def clear_orphan_claims(run_dir, before):
    claims = [{k: c[k] for k in ("id", "parent_id", "time_suspended", "time_updated")} for c in before["database"]["claims"] if c["orphan"]]
    if not claims:
        return "no orphaned claims"
    expected = run_dir / "orphan-claims.json"
    atomic_write(expected, claims[:16], 0o600)
    result = run(["python3", str(ROOT / "tools/watoom-code/recover-orphan-claims.py"), "--claims", str(expected),
                  "--evidence", str(run_dir / "orphan-claims-evidence"), "--i-approve"], timeout=300)
    return "cleared %d orphaned claim(s)" % len(claims[:16])


def clean_workers(force):
    cleaned = []
    state = worker_state()
    if force:
        kub("-n", APP_NS, "delete", "jobs", "-l", WORKER_LABEL, "--wait=false", check=False)
        kub("-n", APP_NS, "delete", "pods", "-l", WORKER_LABEL, "--wait=false", check=False)
        cleaned += [p["name"] for p in state["pods"]] + [j["name"] for j in state["jobs"]]
        time.sleep(20)
        for pod in kub_json("-n", APP_NS, "get", "pods", "-l", WORKER_LABEL)["items"]:
            kub("-n", APP_NS, "delete", "pod", pod["metadata"]["name"], "--grace-period=0", "--force", check=False)
    else:
        for pod in state["pods"]:
            if pod["stale"]:
                kub("-n", APP_NS, "delete", "pod", pod["name"], "--wait=false", check=False)
                cleaned.append(pod["name"])
    for unit in state["units"]:
        if force or unit["stale"]:
            run(["systemctl", "stop", unit["name"]], check=False, timeout=90)
            cleaned.append(unit["name"])
    return "stopped/deleted: %s" % (", ".join(cleaned) if cleaned else "nothing to clean")


def recover_gpu(force):
    client = gpu_client()
    status = client.call("status")
    notes = []
    if status.get("owner") and (owner_ended(status) or force):
        if force:
            run(["systemctl", "stop", "llama-mesh-" + status["owner"]], check=False, timeout=90)
        client.call("recover", job=status["owner"], generation=status["generation"])
        notes.append("recovered owner %s" % status["owner"])
        status = client.call("status")
    if force and not status.get("owner") and not status.get("uncertain") and status.get("phase") == "model-ready":
        client.call("request-model", deployment=status["primary"], allow_switch=True)
        notes.append("restored primary model")
        status = client.call("status")
    if status.get("owner") or status.get("uncertain") or status.get("phase") != "qwen-ready":
        raise RuntimeError("GPU not back to qwen-ready (phase=%s owner=%s uncertain=%s): %s" % (status.get("phase"), status.get("owner"), status.get("uncertain"), "; ".join(notes)))
    return "; ".join(notes) or "GPU already qwen-ready"


MARKER = STATE / "app-scaled-down.json"


def scale_app(replicas):
    kub("-n", APP_NS, "scale", "deploy/" + APP_DEPLOY, "--replicas=%d" % replicas)
    if replicas == 0:
        deadline = time.monotonic() + 240
        while kub_json("-n", APP_NS, "get", "pods", "-l", "app=" + APP_DEPLOY)["items"]:
            if time.monotonic() > deadline:
                raise RuntimeError("App pod did not stop within 240s")
            time.sleep(3)
        return "app stopped"
    kub("-n", APP_NS, "rollout", "status", "deploy/" + APP_DEPLOY, "--timeout=300s", timeout=330)
    return "app running"


def force_database_and_guard(run_dir):
    counts = db_repair(DB, run_dir / "database-rows-cleared.json")
    guard = "no guard held"
    if GUARD_FILE.exists():
        (run_dir / "release-guard.before.json").write_bytes(GUARD_FILE.read_bytes())
        GUARD_FILE.unlink()
        guard = "removed held deployment guard"
    return "database %s; %s" % (counts, guard)


def restart_router():
    kub("-n", LLM_NS, "rollout", "restart", "deploy/" + ROUTER_DEPLOY)
    kub("-n", LLM_NS, "rollout", "status", "deploy/" + ROUTER_DEPLOY, "--timeout=300s", timeout=330)
    return "router restarted"


def verify_models():
    sys.path.insert(0, str(ROOT / "tools/watoom-code"))
    from maintenance_guard import Maintenance  # noqa: PLC0415 - host-only module
    import tempfile  # noqa: PLC0415
    m = Maintenance(APP_NS, APP_DEPLOY, pathlib.Path(tempfile.mkdtemp()), True, True)
    deadline = time.monotonic() + 120
    last = "no response"
    while time.monotonic() < deadline:
        try:
            guard = m.request("/api/session/deployment-guard")["data"]
            if guard.get("held") is not False:
                raise RuntimeError("deployment guard still held")
            if m.request("/api/session/active")["data"]:
                raise RuntimeError("executions still active")
            models = {x["id"] for x in m.request("/api/model")["data"] if x["providerID"] == "watoom" and x["enabled"]}
            if REQUIRED_MODELS <= models:
                return "app answers, guard released, %d models incl. required" % len(models)
            last = "missing models: %s" % sorted(REQUIRED_MODELS - models)
        except Exception as error:  # noqa: BLE001 - retry until deadline
            last = str(error)[:200]
        time.sleep(3)
    raise RuntimeError("app not healthy after restart: " + last)


def snapshot(run_dir):
    sys.path.insert(0, str(ROOT / "tools/watoom-code"))
    import release_guard  # noqa: PLC0415
    release_guard.snapshot_database(DB, run_dir / "application.before.sqlite")
    for name in ("state.json", "inference-leases.json", "worker.json", "selected-model.json"):
        if (GPU_STATE / name).exists():
            (run_dir / ("gpu-" + name)).write_bytes((GPU_STATE / name).read_bytes())
    return "database and GPU state snapshotted"


def prune_runs():
    runs = sorted(p for p in (STATE / "runs").glob("*") if p.is_dir())
    for old in runs[:-KEEP_RUNS]:
        for snapshot_file in old.glob("application.before.sqlite*"):
            snapshot_file.unlink()


def execute(mode):
    started = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    run_dir = STATE / "runs" / started
    run_dir.mkdir(parents=True, mode=0o700)
    r = Run(mode, run_dir)
    before = diagnose()
    atomic_write(run_dir / "before.json", before, 0o600)
    write_status(running=mode, started=started)
    r.step("snapshot", snapshot, run_dir)
    if mode == "stale":
        if "error" not in before["database"] and before["database"]["claims"]:
            r.step("clear orphaned claims", clear_orphan_claims, run_dir, before)
        r.step("clean stale workers", clean_workers, False)
        if "error" not in before["gpu"] and before["gpu"].get("stale_identity"):
            r.step("reconcile deployment identity", repair_deployment_identity, before["gpu"].get("stale_identity"))
        if "error" not in before["gpu"] and (before["gpu"]["owner_ended"] or before["gpu"]["owner"]):
            r.step("recover ended GPU owner", recover_gpu, False)
    else:
        atomic_write(MARKER, {"time": now(), "run": started}, 0o600)
        try:
            if r.step("stop app", scale_app, 0):
                r.step("repair database and guard", force_database_and_guard, run_dir)
            r.step("stop workers", clean_workers, True)
            if "error" not in before["gpu"] and before["gpu"].get("stale_identity"):
                r.step("reconcile deployment identity", repair_deployment_identity, before["gpu"].get("stale_identity"))
            r.step("recover GPU", recover_gpu, True)
            r.step("restart router", restart_router)
        finally:
            if r.step("start app", scale_app, 1):
                MARKER.unlink(missing_ok=True)
        r.step("verify health", verify_models)
    after = diagnose()
    verdict = "healthy" if after["healthy"] else "needs_attention"
    result = {"mode": mode, "started": started, "finished": now(), "verdict": verdict, "steps": r.steps,
              "remaining": after["problems"], "evidence": str(run_dir)}
    atomic_write(run_dir / "after.json", after, 0o600)
    atomic_write(run_dir / "result.json", result, 0o600)
    prune_runs()
    write_status(last_run=result, diagnosis=after)
    return result


# ---------------------------------------------------------------- requests, status, scan
def write_status(**extra):
    previous = {}
    with contextlib.suppress(OSError, ValueError):
        previous = json.loads((STATE / "status.json").read_text())
    status = {k: v for k, v in previous.items() if k in ("last_run",)}
    status.update(extra)
    if "diagnosis" not in status:
        status["diagnosis"] = diagnose()
    status["generated"] = now()
    atomic_write(STATE / "status.json", status)


def valid_request(raw, at):
    """A request must be recent, name a known mode and carry nothing else that matters."""
    if not isinstance(raw, dict) or raw.get("mode") not in MODES:
        return "invalid mode"
    try:
        age = at - float(raw.get("time", 0))
    except (TypeError, ValueError):
        return "invalid time"
    if age < -5 or age > MAX_REQUEST_AGE_S:
        return "request expired"
    return None


def heal_app_scale():
    """If an earlier force run died with the app scaled to zero, bring it back before anything else."""
    if not MARKER.exists():
        return None
    if safe(app_state).get("replicas") == 0:
        scale_app(1)
    MARKER.unlink(missing_ok=True)
    return "restored app after interrupted run"


def scan():
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "inbox").mkdir(exist_ok=True)
    with open(STATE / "lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        healed = safe(heal_app_scale)
        handled = []
        for path in sorted(glob.glob(str(STATE / "inbox" / "*.json"))):
            try:
                raw = json.loads(pathlib.Path(path).read_text())
            except (OSError, ValueError):
                raw = None
            os.unlink(path)
            problem = valid_request(raw, now())
            last = {}
            with contextlib.suppress(OSError, ValueError):
                last = json.loads((STATE / "status.json").read_text()).get("last_run", {})
            if not problem and now() - last.get("finished", 0) < COOLDOWN_S:
                problem = "cooldown: previous run finished moments ago"
            if problem:
                handled.append({"rejected": problem})
                continue
            handled.append(execute(raw["mode"]))
        if not handled:
            write_status()
        return {"healed": healed, "handled": handled}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("diagnose")
    sub.add_parser("scan")
    run_cmd = sub.add_parser("run")
    run_cmd.add_argument("--mode", choices=MODES, required=True)
    run_cmd.add_argument("--i-approve", action="store_true")
    args = parser.parse_args()
    if args.command == "diagnose":
        print(json.dumps(diagnose(), indent=2, default=str))
    elif os.geteuid() != 0:
        sys.exit("Root required")
    elif args.command == "scan":
        print(json.dumps(scan(), default=str))
    else:
        if not args.i_approve:
            sys.exit("--i-approve required; this interrupts or clears live state")
        STATE.mkdir(parents=True, exist_ok=True)
        with open(STATE / "lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            print(json.dumps(execute(args.mode), indent=2, default=str))


if __name__ == "__main__":
    main()
