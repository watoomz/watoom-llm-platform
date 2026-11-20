#!/usr/bin/env python3
"""Isolated revision-control exercise. Synthetic numbers are NOT performance evidence."""

import argparse, pathlib, json, sqlite3, sys, hashlib, time, os, secrets, subprocess, fcntl

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from maintenance_guard import Maintenance
from release_guard import acquire, active_clear
from recover import atomic

p = argparse.ArgumentParser()
p.add_argument("--evidence", type=pathlib.Path, required=True)
p.add_argument("--namespace", required=True)
a = p.parse_args()
if not a.namespace.startswith("watoom-code-learning-"):
    raise ValueError("Staging only")
root = a.evidence
stage = root / "staging"
source = pathlib.Path(__file__).resolve().parent
repo = source.parents[2]
database = stage / "state/application.sqlite"
checkpoint = stage / "recovery-state.json"
m = Maintenance(a.namespace, "learning-app", root, True, True)
active_clear(m.request("/api/session/active"))


def states(part):
    with sqlite3.connect("file:" + str(database) + "?mode=ro", uri=True) as db:
        return [json.loads(v) for v, in db.execute("select value from kv where key like ?", ("%" + part + "/v1/%",))]


state = next(s for s in states("optimisation") if s.get("scope", {}).get("repository") == "/workspace")
r = next(
    (
        r
        for r in state["revisions"].values()
        if r["state"] in ["candidate", "evaluated", "selected-next-start", "rollback-pending"]
        and r["skill"] not in ["report", "opencode"]
        and state["skills"][r["skill"]].get("active") in [None, r["id"]]
        and r["previous"] == state["skills"][r["skill"]]["baseline"]
    ),
    None,
)
if not r:
    raise RuntimeError("Expected conservative existing Skill candidate missing")
original = state["revisions"][r["previous"]]
scope = state["scope"]
skill = r["skill"]
# Container paths refer to owned host artifacts.
body = lambda record: (stage / "state/skills" / pathlib.Path(record["path"]).name).read_bytes()
assert (
    hashlib.sha256(body(original)).hexdigest() == original["sha256"]
    and hashlib.sha256(body(r)).hexdigest() == r["sha256"]
)
assert [l for l in body(original).decode().splitlines() if l.strip()] == [
    l for l in body(r).decode().splitlines() if l.strip()
]
out = stage / ("overlay-proof-" + str(time.time_ns()))
out.mkdir(mode=0o700)
config = stage / "config/opencode.json"
prior = out / "config.json"
prior.write_bytes(config.read_bytes())
prior.chmod(0o600)
live = m.kub("get", "deploy", "learning-app")
baseline = {
    "apiVersion": "apps/v1",
    "kind": "Deployment",
    "metadata": {"name": "learning-app", "namespace": a.namespace, "labels": live["metadata"].get("labels", {})},
    "spec": live["spec"],
}
manifest = out / "deployment.json"
atomic(manifest, baseline)
original_manifests = (stage / "manifests.json").read_bytes()
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
candidate = json.loads(config.read_text())
candidate["plugins"][0]["options"]["optimisationRevisions"] = [r["id"]]
candidatefile = out / "candidate.json"
atomic(candidatefile, candidate)
s = {
    "phase": "CUTOVER_STARTED",
    "namespace": a.namespace,
    "deployment": "learning-app",
    "deployment_uid": live["metadata"]["uid"],
    "replicas": 1,
    "baseline_deployment": str(manifest),
    "baseline_deployment_sha256": sha(manifest),
    "baseline_config": str(prior),
    "baseline_config_sha256": sha(prior),
    "candidate_config_sha256": sha(candidatefile),
    "config": str(config),
    "directory": "/workspace",
    "grace_until": time.time() + 45,
    "health_failures": 0,
    "recovery_nonce": secrets.token_hex(16),
    "production_approved": False,
    "baseline_skills": [k["id"] for k in m.request("/api/skill?location%5Bdirectory%5D=%2Fworkspace")["data"]],
}
atomic(checkpoint, s)


def update(**values):
    with checkpoint.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        s = json.loads(checkpoint.read_text())
        s.update(values)
        atomic(checkpoint, s)


def command(kind, id, report=None):
    nonce = secrets.token_hex(16)
    e = {
        "kind": "existing-skill-" + kind,
        "id": id,
        "scope": scope,
        "request": nonce,
        "report": report,
        "evaluator": "synthetic-control-only",
    }
    file = stage / "evaluations" / ("existing-" + nonce + ".json")
    if kind == "regression":
        e["receipt"] = "owned-control-reset-" + nonce
    atomic(file, e)
    file.chmod(0o644)
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        op = next(
            (s.get("operations", {}).get(nonce) for s in states("learning") if nonce in s.get("operations", {})), None
        )
        if op:
            if op["result"] != "PASS":
                raise RuntimeError(kind + " rejected: " + op.get("reason", ""))
            return
        time.sleep(0.2)
    raise RuntimeError("Native protected operation timed out")


def native():
    return next(k for k in m.request("/api/skill?location%5Bdirectory%5D=%2Fworkspace")["data"] if k["id"] == skill)


start = time.monotonic()
error = None
selected = False
try:
    acquire(lambda p: m.request(p), lambda p, b: m.request(p, b), lambda owner: update(owner=owner), lambda: None)
    if state["skills"][skill].get("active") == r["id"]:
        command("regression", r["id"])
        command("rollback", skill)
    marker = out / "expiry.json"
    atomic(marker, {"checkpoint": str(checkpoint), "nonce": s["recovery_nonce"]})
    subprocess.run(
        [
            "systemd-run",
            "--quiet",
            "--unit=watoom-skill-overlay-expiry-" + str(time.time_ns()),
            "--on-active=75s",
            "/usr/bin/python3",
            "-I",
            str(source / "expire_fixture.py"),
            "--input",
            str(marker),
        ],
        check=True,
        timeout=10,
    )
    cases = []
    baseline_cases = []
    for i, cid in enumerate(["read-procedure", "preserve-code", "references-and-safety"]):
        common = {
            "id": cid,
            "task": "Owned revision control fixture " + cid,
            "regression": "Preserve original instructions",
            "coverage": ["original-instructions"],
        }
        baseline_cases.append(
            {**common, "receipt": "synthetic-baseline-" + str(i), "correctness": True, "safety": True}
        )
        cases.append(
            {k: v for k, v in common.items() if k != "coverage"}
            | {
                "original": {
                    "receipt": "synthetic-old-" + str(i),
                    "correctness": True,
                    "safety": True,
                    "coverage": ["original-instructions"],
                    "tokens": 100,
                },
                "candidate": {
                    "receipt": "synthetic-new-" + str(i),
                    "correctness": True,
                    "safety": True,
                    "coverage": ["original-instructions"],
                    "tokens": 90,
                },
            }
        )
    command("baseline", skill, {"hash": original["sha256"], "cases": baseline_cases, "scope": "synthetic-control-only"})
    report = {
        "baselineHash": original["sha256"],
        "candidateHash": r["sha256"],
        "environment": "isolated-staging-control-fixture",
        "cases": cases,
        "measurementOrigin": "synthetic-test-fixture",
        "measurementProtocol": {
            "registeredSuite": "synthetic-control-only",
            "domainRepresentative": False,
            "pairedRepetitions": 3,
            "sameEnvironment": True,
            "regressionChecks": True,
            "verifierReceipts": ["fixture1", "fixture2", "fixture3"],
        },
    }
    from optimise import qualified

    fake = json.loads(json.dumps(state))
    fake["revisions"][r["id"]]["state"] = "evaluated"
    fake["comparisons"][r["id"]] = report
    assert not qualified(fake, r["id"]), "Synthetic evidence must never qualify for production"
    command("compare", r["id"], report)
    before = hashlib.sha256(native()["content"].encode()).hexdigest()
    command("select", r["id"])
    assert hashlib.sha256(native()["content"].encode()).hexdigest() == before, "Selection hot-replaced an active Skill"
    selected = True
    # A new immutable configuration and a fresh idle pod are required for activation.
    atomic(config, candidate)
    os.chown(config, 1001, 1001)
    os.chmod(config, 0o600)
    prepared = json.loads(original_manifests)
    next(d for d in prepared["items"] if d.get("kind") == "Deployment" and d["metadata"]["name"] == "learning-app")[
        "spec"
    ]["template"]["metadata"]["annotations"]["watoom-learning-config-sha256"] = sha(config)
    atomic(stage / "manifests.json", prepared)
    env = {
        **os.environ,
        "ANSIBLE_CONFIG": str(repo / "ansible/ansible.cfg"),
        "ANSIBLE_ROLES_PATH": str(repo / "ansible/roles"),
    }
    with (out / "apply.log").open("w") as log:
        result = subprocess.run(
            [
                "ansible-playbook",
                "-i",
                str(repo / "ansible/inventories/homelab/hosts.yml"),
                str(repo / "ansible/playbooks/watoom-code-self-learning-stage.yml"),
                "-c",
                "local",
                "-e",
                json.dumps({"watoom_learning_root": str(root / "staging"), "watoom_learning_namespace": a.namespace}),
            ],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=90,
        )
    if result.returncode:
        raise RuntimeError("Owned staging overlay rollout failed")
    deadline = time.monotonic() + 40
    while hashlib.sha256(native()["content"].encode()).hexdigest() != r["sha256"]:
        if time.monotonic() > deadline:
            raise RuntimeError("Pinned existing Skill overlay did not activate")
        time.sleep(0.3)
except Exception as e:
    error = str(e)
finally:
    (stage / "manifests.json").write_bytes(original_manifests)
    os.chmod(stage / "manifests.json", 0o600)
    update(
        phase="CUTOVER_FAILED",
        critical_failure="Owned overlay fixture complete; verify automatic baseline restoration"
        + (": " + error if error else ""),
        grace_until=0,
    )
deadline = time.monotonic() + 180
while time.monotonic() < deadline:
    s = json.loads(checkpoint.read_text())
    if s["phase"] == "ROLLED_BACK":
        assert sha(config) == sha(prior), "Exact config not restored"
        assert (
            hashlib.sha256(native()["content"].encode()).hexdigest() == original["sha256"]
        ), "Previous Skill version not restored"
        assert not m.request("/api/session/deployment-guard")["data"]["held"]
        report = {
            "status": "FAIL" if error else "PASS",
            "skill": skill,
            "revision": r["id"],
            "selection_does_not_hot_replace": selected,
            "native_overlay_activated": not error,
            "automatic_rollback": "verified original config, Skill body and admission restored by independent timer",
            "versions_preserved": True,
            "synthetic_measurements_rejected_for_production": True,
            "measurementOrigin": "synthetic-control-fixture",
            "performance_improvement": "NOT_CLAIMED",
            "seconds": time.monotonic() - start,
            "evidence": str(out),
            "error": error,
        }
        atomic(root / "native-tests/existing-overlay.json", report)
        print(json.dumps(report))
        raise SystemExit(1 if error else 0)
    if s["phase"] == "BLOCKED_RECOVERY":
        raise RuntimeError(s.get("blocker"))
    time.sleep(1)
raise RuntimeError("Owned overlay automatic restoration did not verify; checkpoint retained")
