#!/usr/bin/env python3
"""Deliberately fail only the isolated app; independent host recovery must restore it."""

import argparse, pathlib, json, subprocess, hashlib, secrets, time, os, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from maintenance_guard import Maintenance
from release_guard import active_clear
from recover import atomic

p = argparse.ArgumentParser()
p.add_argument("--evidence", required=True, type=pathlib.Path)
p.add_argument("--namespace", required=True)
a = p.parse_args()
if not a.namespace.startswith("watoom-code-learning-"):
    raise ValueError("Staging-only exercise")
root = a.evidence.resolve()
stage = root / "staging"
statepath = stage / "recovery-state.json"
ns = a.namespace
if statepath.exists() and json.loads(statepath.read_text())["phase"] not in ["ROLLED_BACK", "COMPLETE"]:
    raise ValueError("Existing recovery exercise must settle first")
m = Maintenance(ns, "learning-app", root, True, True)
active_clear(m.request("/api/session/active"))
baseline = m.kub("get", "deploy", "learning-app")
uid = baseline["metadata"]["uid"]
replicas = baseline["spec"]["replicas"]
snapshot = stage / ("recovery-baseline-" + str(time.time_ns()))
snapshot.mkdir(mode=0o700)
manifest = {
    "apiVersion": "apps/v1",
    "kind": "Deployment",
    "metadata": {"name": "learning-app", "namespace": ns, "labels": baseline["metadata"].get("labels", {})},
    "spec": baseline["spec"],
}
deploy = snapshot / "deployment.json"
atomic(deploy, manifest)
os.chmod(deploy, 0o600)
config = stage / "config/opencode.json"
prior = snapshot / "config.json"
prior.write_bytes(config.read_bytes())
os.chmod(prior, 0o600)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
state = {
    "phase": "CUTOVER_STARTED",
    "namespace": ns,
    "deployment": "learning-app",
    "deployment_uid": uid,
    "replicas": replicas,
    "baseline_deployment": str(deploy),
    "baseline_deployment_sha256": sha(deploy),
    "baseline_config": str(prior),
    "baseline_config_sha256": sha(prior),
    "candidate_config_sha256": sha(config),
    "config": str(config),
    "directory": "/workspace",
    "grace_until": 0,
    "health_failures": 0,
    "recovery_nonce": secrets.token_hex(16),
    "production_approved": False,
    "exercise": "failed-app-startup",
}
atomic(statepath, state)
os.chmod(statepath, 0o600)
patch = {
    "spec": {
        "template": {
            "spec": {
                "containers": [
                    {
                        "name": "app",
                        "command": ["/usr/local/bin/opencode"],
                        "args": ["serve", "--unsupported-learning-recovery-fixture"],
                    }
                ]
            }
        }
    }
}
r = subprocess.run(
    ["kubectl", "-n", ns, "patch", "deploy", "learning-app", "--type=strategic", "-p", json.dumps(patch)],
    capture_output=True,
    text=True,
    timeout=20,
)
if r.returncode:
    raise RuntimeError(r.stderr)
start = time.monotonic()
deadline = start + 210
while time.monotonic() < deadline:
    s = json.loads(statepath.read_text())
    if s["phase"] == "ROLLED_BACK":
        active_clear(m.request("/api/session/active"))
        assert m.request("/api/info").get("version")
        report = {
            "status": "PASS",
            "exercise": "failed-app-startup",
            "independent_recovery": "systemd timer, no parent-process recovery calls",
            "seconds": time.monotonic() - start,
            "phase": s["phase"],
            "data_deleted": False,
            "baseline": str(snapshot),
            "production_modified": False,
        }
        atomic(root / "native-tests/recovery-exercise.json", report)
        print(json.dumps(report))
        raise SystemExit()
    if s["phase"] == "BLOCKED_RECOVERY":
        raise RuntimeError(s.get("blocker"))
    time.sleep(3)
raise RuntimeError("Independent rollback did not verify within 210s; checkpoint preserved: " + str(statepath))
