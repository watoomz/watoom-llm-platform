#!/usr/bin/env python3
"""Actual native staging SSE + admission/ingress fences; independent recovery armed."""

import argparse, pathlib, sys, json, os, time, secrets, hashlib, subprocess, urllib.request, base64

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from maintenance_guard import Maintenance
from release_guard import acquire, release, active_clear, durable_clearance
from recover import atomic
from idle_streams import drain

p = argparse.ArgumentParser()
p.add_argument("--evidence", required=True, type=pathlib.Path)
a = p.parse_args()
root = a.evidence.resolve()
stage = root / "staging"
source = pathlib.Path(__file__).resolve().parent
repo = source.parents[2]
checkpoint = stage / "recovery-state.json"
prior = json.loads(checkpoint.read_text())
assert prior["phase"] in ["ROLLED_BACK", "COMPLETE"]
atomic(stage / ("prior-recovery-state-" + str(time.time_ns()) + ".json"), prior)


class FixtureMaintenance(Maintenance):
    def transport(self):
        value = super().transport()
        # The isolated CPU provider is a permanent fixture dependency, not a task worker.
        code = "import pathlib,json;print(json.dumps([int(p.name) for p in pathlib.Path('/proc').iterdir() if p.name.isdigit() and (p/'cmdline').exists() and (p/'cmdline').read_bytes().split(bytes([0]))[:2]==[b'python3',b'/learning/source/mock_provider.py']]))"
        providers = json.loads(self.exec(code))
        assert len(providers) == 1, "Expected the single inspected CPU mock fixture"
        value["processes"] = [x for x in value["processes"] if x["pid"] not in providers]
        return value


m = FixtureMaintenance(
    json.loads((stage / "prepared.json").read_text())["namespace"], "learning-app", stage, True, True
)
active_clear(m.request("/api/session/active"))
live = m.kub("get", "deploy", "learning-app")
snapshot = stage / ("idle-stream-baseline-" + str(time.time_ns()))
snapshot.mkdir(mode=0o700)
config = stage / "config/opencode.json"
backup = snapshot / "config.json"
backup.write_bytes(config.read_bytes())
os.chmod(backup, 0o600)
manifest = snapshot / "deployment.json"
atomic(
    manifest,
    {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": m.name, "namespace": m.ns, "labels": live["metadata"].get("labels", {})},
        "spec": live["spec"],
    },
)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
state = {
    "phase": "CUTOVER_READY",
    "namespace": m.ns,
    "deployment": m.name,
    "deployment_uid": live["metadata"]["uid"],
    "replicas": 1,
    "baseline_deployment": str(manifest),
    "baseline_deployment_sha256": sha(manifest),
    "baseline_config": str(backup),
    "baseline_config_sha256": sha(backup),
    "candidate_config_sha256": sha(config),
    "config": str(config),
    "directory": "/workspace",
    "grace_until": time.time() + 600,
    "health_failures": 0,
    "recovery_nonce": secrets.token_hex(16),
    "production_approved": False,
    "external_fence": False,
}
atomic(checkpoint, state)
env = {
    **os.environ,
    "ANSIBLE_CONFIG": str(repo / "ansible/ansible.cfg"),
    "ANSIBLE_ROLES_PATH": str(repo / "ansible/roles"),
}
with (snapshot / "arm-controller.log").open("w") as log:
    r = subprocess.run(
        [
            "ansible-playbook",
            "-i",
            "inventories/homelab/hosts.yml",
            "playbooks/watoom-code-self-learning-controller.yml",
            "-c",
            "local",
            "-e",
            json.dumps(
                {
                    "watoom_learning_root": str(stage),
                    "watoom_learning_controller_script": str(source / "recover.py"),
                    "watoom_learning_recovery_checkpoint": str(checkpoint),
                }
            ),
        ],
        cwd=repo / "ansible",
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        timeout=120,
    )
assert r.returncode == 0
stream = None
try:
    ip = m.pod()["status"]["podIP"]
    request = urllib.request.Request(
        "http://" + ip + ":4096/api/event",
        headers={"Authorization": "Basic " + base64.b64encode(("opencode:" + m.password).encode()).decode()},
    )
    stream = urllib.request.urlopen(request, timeout=10)
    assert stream.status == 200 and stream.headers.get_content_type() == "text/event-stream"
    state.update(
        phase="CUTOVER_STARTED", external_fence=True, drain_started=time.time(), draining_until=time.time() + 90
    )
    atomic(checkpoint, state)
    acquire(
        lambda p: m.request(p),
        lambda p, b: m.request(p, b),
        lambda owner: (state.update(owner=owner), atomic(checkpoint, state)),
        lambda: durable_clearance(stage / "state/application.sqlite"),
    )
    m.begin()
    time.sleep(2)
    start = time.monotonic()
    proof = []
    drain(m, lambda: durable_clearance(stage / "state/application.sqlite"), lambda value: proof.append(value))
    assert proof[0]["idle_streams"], "Expected actual native event connection"
    assert stream.status == 200
    release(lambda p: m.request(p), lambda p, b: m.request(p, b), state["owner"])
    m.release()
    state.update(phase="COMPLETE", external_fence=False, draining_until=0)
    atomic(checkpoint, state)
    report = {
        "status": "PASS",
        "seconds": time.monotonic() - start,
        "native_event_response": "text/event-stream",
        "guard_and_external_fence": True,
        "proof": proof[0],
        "production_modified": False,
        "fixture_exclusion": "single exact python3 /learning/source/mock_provider.py PID; production rejects all children",
        "snapshot": str(snapshot),
        "source_sha256": sha(source / "idle_streams.py"),
    }
    atomic(root / "native-tests/idle-stream-drain.json", report)
    print(json.dumps(report))
except Exception as error:
    state.update(phase="CUTOVER_FAILED", critical_failure=str(error)[:300], draining_until=0, grace_until=0)
    atomic(checkpoint, state)
    raise
finally:
    if stream is not None:
        stream.close()
