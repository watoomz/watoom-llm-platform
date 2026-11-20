#!/usr/bin/env python3
"""One bounded independent recovery tick. Healthy services are never rolled back for agent loss."""

import argparse, pathlib, json, subprocess, time, os, fcntl, hashlib, sys, secrets

_here = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_here if (_here / "maintenance_guard.py").exists() else _here.parent))
from maintenance_guard import Maintenance

sys.path.insert(0, str(_here))
from mcp_quiescence import restore as restore_mcp


def atomic(path, value):
    temp = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(value, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    os.fsync(fd)
    os.close(fd)


def decide(state, healthy, now):
    if state["phase"] not in ["CUTOVER_STARTED", "CUTOVER_FAILED", "ROLLBACK_IN_PROGRESS"]:
        return "NO_ACTION"
    if state["phase"] == "ROLLBACK_IN_PROGRESS":
        return "VERIFY_ROLLBACK" if healthy else "RESTORE"
    if state["phase"] == "CUTOVER_FAILED":
        return "RESTORE"
    if healthy:
        return "KEEP_HEALTHY"
    if now < state.get("grace_until", 0):
        return "WAIT_STARTUP"
    if state.get("health_failures", 0) + 1 < 3 and state["phase"] != "CUTOVER_FAILED":
        return "RECHECK"
    return "RESTORE"


def published_health(m):
    import urllib.request, base64

    service = m.kub("get", "svc", m.name)
    ip = service["spec"]["clusterIP"]
    port = service["spec"]["ports"][0]["port"]
    token = base64.b64encode(("opencode:" + m.password).encode()).decode()
    request = urllib.request.Request(
        "http://" + ip + ":" + str(port) + "/api/info", headers={"Authorization": "Basic " + token}
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.load(response)
    if not data.get("version"):
        raise RuntimeError("Published Service health failed")
    return {"status": "PASS", "service": m.name, "version": data["version"]}


def normalized(spec):
    spec = json.loads(json.dumps(spec))
    spec["template"]["metadata"].get("annotations", {}).pop("watoom-learning-recovery", None)
    if not spec["template"]["metadata"].get("annotations"):
        spec["template"]["metadata"].pop("annotations", None)
    return spec


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def tick(path):
    if not path.exists():
        return {"action": "NO_STATE"}
    st = path.lstat()
    if st.st_uid != 0 or st.st_mode & 0o022 or path.is_symlink():
        raise PermissionError("Root-owned non-writable recovery checkpoint required")
    with path.with_suffix(".lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"action": "BUSY"}
        state = json.loads(path.read_text())
        ns = state["namespace"]
        name = state["deployment"]
        if state.get("controller_sha256") and digest(pathlib.Path(__file__)) != state["controller_sha256"]:
            raise ValueError("Pinned recovery controller checksum changed")
        if not (ns.startswith("watoom-code-learning-") and name == "learning-app") and not (
            ns == "watoom-code" and name == "watoom-code" and state.get("production_approved") is True
        ):
            raise ValueError("Recovery target not authorised")
        if state["phase"] not in ["CUTOVER_STARTED", "CUTOVER_FAILED", "ROLLBACK_IN_PROGRESS"]:
            return {"action": "NO_ACTION", "phase": state["phase"]}
        if state["phase"] == "ROLLBACK_IN_PROGRESS" and time.time() - state.get("rollback_started", time.time()) > 900:
            state["phase"] = "BLOCKED_RECOVERY"
            state["blocker"] = "Baseline restoration could not be verified within 900 seconds"
            atomic(path, state)
            return {"action": "BLOCKED_RECOVERY"}
        if (
            state["phase"] == "CUTOVER_STARTED"
            and time.time() < state.get("draining_until", 0)
            and 0 < state.get("draining_until", 0) - state.get("drain_started", 0) <= 90
        ):
            return {"action": "WAIT_BOUNDED_DRAIN"}
        out = path.parent
        healthy = False
        active = None
        error = ""
        try:
            m = Maintenance(ns, name, out, True, True)
            d = m.kub("get", "deploy", name)
            if d["metadata"]["uid"] != state["deployment_uid"]:
                state["phase"] = "BLOCKED_RECOVERY"
                state["blocker"] = "Deployment identity changed"
                atomic(path, state)
                return {"action": "BLOCKED_RECOVERY"}
            if d.get("status", {}).get("readyReplicas", 0) != state["replicas"]:
                raise RuntimeError("Workload not ready")
            info = m.request("/api/info")
            if not isinstance(info.get("version"), str):
                raise RuntimeError("Application health contract failed")
            registered = m.request("/api/skill?location%5Bdirectory%5D=" + state.get("directory", "/workspace"))
            if not set(state.get("baseline_skills", [])) <= {k["id"] for k in registered["data"]}:
                raise RuntimeError("Baseline native Skills missing")
            if state.get("production_approved"):
                code = "import os,urllib.request;u=os.environ['AGENTMEMORY_URL'].rstrip('/')+'/agentmemory/livez';r=urllib.request.urlopen(u,timeout=8);assert r.status==200;print('MEMORY_OK')"
                if b"MEMORY_OK" not in m.exec(code):
                    raise RuntimeError("AgentMemory endpoint not ready")
            active = m.request("/api/session/active")
            healthy = True
        except Exception as e:
            error = type(e).__name__ + ": " + str(e)[:200]
        action = decide(state, healthy, time.time())
        state["last_health"] = {"healthy": healthy, "time": time.time(), "error": error}
        if action == "KEEP_HEALTHY":
            state["health_failures"] = 0
            state["recovery_observation"] = "Healthy; retain candidate while awaiting full operator validation"
        elif action == "RECHECK":
            state["health_failures"] = state.get("health_failures", 0) + 1
        elif action == "RESTORE":
            if active and active.get("data"):
                owned = set(state.get("owned_sessions", []))
                running = set(active["data"])
                if running <= owned:
                    for sid in running:
                        m.request("/api/session/" + sid + "/interrupt?resume=false", {})
                    atomic(path, state)
                    return {"action": "WAIT_OWNED_VALIDATION_INTERRUPT"}
                state["phase"] = "BLOCKED_RECOVERY"
                state["blocker"] = "Unowned active sessions prevent automatic restoration"
                atomic(path, state)
                return {"action": "BLOCKED_RECOVERY"}
            specfile = pathlib.Path(state["baseline_deployment"])
            config = pathlib.Path(state["config"])
            prior = pathlib.Path(state["baseline_config"])
            if (
                digest(specfile) != state["baseline_deployment_sha256"]
                or digest(prior) != state["baseline_config_sha256"]
            ):
                state["phase"] = "BLOCKED_RECOVERY"
                state["blocker"] = "Recovery input checksum failed"
                atomic(path, state)
                return {"action": "BLOCKED_RECOVERY"}
            allowed = (
                "/data/ai/watoom-code/config/opencode.json"
                if state.get("production_approved")
                else str(path.parent / "config/opencode.json")
            )
            if str(config) != allowed or config.is_symlink():
                raise ValueError("Unexpected recovery config path")
            current = digest(config)
            if current not in [
                state["candidate_config_sha256"],
                state.get("validation_config_sha256"),
                state["baseline_config_sha256"],
            ]:
                state["phase"] = "BLOCKED_RECOVERY"
                state["blocker"] = "Configuration changed outside this release; preserve it"
                atomic(path, state)
                return {"action": "BLOCKED_RECOVERY"}
            state["phase"] = "ROLLBACK_IN_PROGRESS"
            state.setdefault("rollback_started", time.time())
            if time.time() - state["rollback_started"] > 900:
                state["phase"] = "BLOCKED_RECOVERY"
                state["blocker"] = "Baseline restoration health could not be verified within900s"
                atomic(path, state)
                return {"action": "BLOCKED_RECOVERY"}
            atomic(path, state)
            if current != state["baseline_config_sha256"]:
                # Preserve failed configuration separately before atomic restoration.
                failed = path.parent / ("failed-config-" + str(time.time_ns()) + ".json")
                failed.write_bytes(config.read_bytes())
                os.chmod(failed, 0o600)
                temp = config.with_suffix(".recovery.tmp")
                temp.write_bytes(prior.read_bytes())
                os.chown(temp, 1001, 1001)
                os.chmod(temp, 0o600)
                os.replace(temp, config)
            if (
                healthy
                and digest(config) == state["baseline_config_sha256"]
                and normalized(d["spec"]) == normalized(json.loads(specfile.read_text())["spec"])
            ):
                state["restore_applied"] = True
                state["recovery_observation"] = (
                    "Verified baseline already running; preserve its process and release only owned fences"
                )
                atomic(path, state)
                return {"action": "BASELINE_ALREADY_RUNNING", "phase": state["phase"], "healthy": True}
            restored = json.loads(specfile.read_text())
            restored["spec"]["template"]["metadata"].setdefault("annotations", {})["watoom-learning-recovery"] = state[
                "recovery_nonce"
            ]
            restore_manifest = path.parent / "rollback-apply.json"
            atomic(restore_manifest, restored)
            r = subprocess.run(
                ["kubectl", "--request-timeout=15s", "apply", "-f", str(restore_manifest)],
                capture_output=True,
                timeout=25,
            )
            if r.returncode:
                state["restore_error"] = r.stderr.decode()[-300:]
            state["restore_applied"] = r.returncode == 0
        elif action == "VERIFY_ROLLBACK":
            baseline = json.loads(pathlib.Path(state["baseline_deployment"]).read_text())
            current = m.kub("get", "deploy", name)
            if (
                normalized(current["spec"]) != normalized(baseline["spec"])
                or digest(pathlib.Path(state["config"])) != state["baseline_config_sha256"]
            ):
                state["phase"] = "CUTOVER_FAILED"
                atomic(path, state)
                return {"action": "BASELINE_NOT_YET_RESTORED"}
            restore_mcp(m, state, lambda value: atomic(path, value))
            if state.get("owner"):
                guard = m.request("/api/session/deployment-guard")
                if guard.get("data", {}).get("held"):
                    m.request("/api/session/deployment-guard", {"action": "release", "owner": state["owner"]})
            if state.get("external_fence"):
                service = path.parent / "maintenance-service-before.json"
                if not service.exists():
                    raise RuntimeError("Maintenance restoration input missing")
                m.service = json.loads(service.read_text())
                m.held = True
                access = path.parent / "maintenance-access-before.json"
                if access.exists():
                    m.access = json.loads(access.read_text())
                m.release()
                state["external_fence"] = False
            atomic(path, state)
            if state.get("production_approved"):
                state["published_service"] = published_health(m)
            state["phase"] = "ROLLED_BACK"
            state["rollback_verified_at"] = time.time()
            state["recovery_observation"] = (
                "Baseline readiness and authenticated endpoints verified; data stores preserved"
            )
        atomic(path, state)
        return {"action": action, "phase": state["phase"], "healthy": healthy}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--state", required=True, type=pathlib.Path)
    a = p.parse_args()
    try:
        print(json.dumps(tick(a.state.resolve())))
    except Exception as e:
        # Retain the exact checkpoint; host timer retries transient health/API failures.
        print(json.dumps({"action": "RECOVERY_ERROR", "error": str(e)[:300]}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
