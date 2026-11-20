#!/usr/bin/env python3
"""Reviewable, identity-fenced production cutover through Ansible; data never rolled back."""

import argparse, datetime, hashlib, json, pathlib, subprocess, os

REPO = pathlib.Path(__file__).resolve().parents[2]
p = argparse.ArgumentParser()
p.add_argument("mode", choices=["prepare", "apply", "rollback"])
p.add_argument("--snapshot")
p.add_argument("--candidate-sha256")
p.add_argument("--acceptance")
p.add_argument("--i-approve", action="store_true")
a = p.parse_args()
os.umask(0o077)


def kub(*args):
    return subprocess.check_output(["kubectl", "-n", "opencode", *args])


def clean(o):
    o = json.loads(json.dumps(o))
    o.pop("status", None)
    for key in ["uid", "resourceVersion", "generation", "creationTimestamp", "managedFields"]:
        o["metadata"].pop(key, None)
    return o


if a.mode == "prepare":
    out = pathlib.Path("/data/ai/helper-scripts/reports") / (
        "watoom-code-cutover-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    out.mkdir()
    live = json.loads(kub("get", "deployment", "opencode-v2-canary", "-o", "json"))
    if live["metadata"].get("ownerReferences"):
        raise SystemExit("Unexpected Deployment controller ownership")
    (out / "original.json").write_text(json.dumps(live, indent=2))
    candidate = clean(live)
    containers = candidate["spec"]["template"]["spec"]["containers"]
    if len(containers) != 1:
        raise SystemExit("Expected single verified application container")
    containers[0][
        "image"
    ] = "127.0.0.1:5000/watoom-code@sha256:7aab2c83a85ba9443fb8e4c91a40f8e66f074d80328135d80d5f992a7d75a7b4"
    containers[0].pop("command", None)
    containers[0]["args"] = ["serve", "--hostname", "0.0.0.0", "--port", "4096"]
    (out / "candidate.json").write_text(json.dumps(candidate, indent=2))
    print(out)
    print("CANDIDATE_SHA256=" + hashlib.sha256((out / "candidate.json").read_bytes()).hexdigest())
    raise SystemExit(0)
if not a.i_approve:
    raise SystemExit("Production changes require explicit --i-approve")
if not a.snapshot:
    raise SystemExit("--snapshot required")
out = pathlib.Path(a.snapshot).resolve()
original = json.loads((out / "original.json").read_text())
live = json.loads(kub("get", "deployment", "opencode-v2-canary", "-o", "json"))
if live["metadata"]["uid"] != original["metadata"]["uid"]:
    raise SystemExit("Deployment identity changed")
if a.mode == "apply":
    if not a.acceptance:
        raise SystemExit("A reviewed production-candidate acceptance report is required")
    gates = json.loads(pathlib.Path(a.acceptance).read_text())
    for key in [
        "candidate_runtime",
        "configuration",
        "native_agents",
        "skills",
        "agentmemory",
        "toolkit",
        "cpu_specialist",
        "gpu_boundary",
    ]:
        if gates.get(key) != "PASS":
            raise SystemExit("Missing production-candidate acceptance: " + key)
    candidate = out / "candidate.json"
    if hashlib.sha256(candidate.read_bytes()).hexdigest() != a.candidate_sha256:
        raise SystemExit("Reviewed candidate checksum mismatch")
else:
    candidate = out / "restore.json"
    candidate.write_text(json.dumps(clean(original)))
env = dict(os.environ, ANSIBLE_CONFIG=str(REPO / "ansible/ansible.cfg"), ANSIBLE_ROLES_PATH=str(REPO / "ansible/roles"))
cmd = [
    "ansible-playbook",
    "-i",
    "inventories/homelab/hosts.yml",
    "playbooks/watoom-code-cutover.yml",
    "-c",
    "local",
    "-e",
    json.dumps({"watoom_code_reviewed_manifest": str(candidate), "watoom_code_cutover_approved": True}),
]
result = subprocess.run(cmd, cwd=REPO / "ansible", env=env)
if result.returncode and a.mode == "apply":
    restore = out / "automatic-restore.json"
    restore.write_text(json.dumps(clean(original)))
    cmd[-1] = json.dumps({"watoom_code_reviewed_manifest": str(restore), "watoom_code_cutover_approved": True})
    subprocess.run(cmd, cwd=REPO / "ansible", env=env)
raise SystemExit(result.returncode)
