#!/usr/bin/env python3
"""Single resumable entry point. Production operations require explicit approval."""

import argparse, pathlib, json, subprocess, os, fcntl, sys, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from recover import atomic

p = argparse.ArgumentParser()
p.add_argument("--evidence", type=pathlib.Path, required=True)
p.add_argument("--namespace", default="watoom-code-learning-20261023")
p.add_argument("--update-existing-package")
for flag in ["dry-run", "stage-only", "i-approve", "resume", "status", "rollback"]:
    p.add_argument("--" + flag, action="store_true")
a = p.parse_args()
root = a.evidence.resolve()
source = pathlib.Path(__file__).resolve().parent
repo = source.parents[2]
if not str(root).startswith("/data/ai/helper-scripts/watoom-self-learning-") or not root.is_dir():
    raise ValueError("Existing private evidence root required")
if a.status:
    result = {}
    for name in ["state.json", "test-results.json", "production/recovery-state.json"]:
        file = root / name
        if file.exists():
            s = json.loads(file.read_text())
            result[name] = {
                k: s[k]
                for k in ["phase", "status", "source_digest", "production_validated", "critical_failure", "blocker"]
                if k in s
            }
    print(json.dumps(result, indent=2))
    raise SystemExit()
if a.dry_run:
    print(
        json.dumps(
            {
                "phases": [
                    "audit",
                    "prepare isolated stage",
                    "Ansible stage",
                    "serial acceptance",
                    "prepare pinned cutover",
                    "approved cutover or stop ready",
                ],
                "production_operations": bool(a.i_approve and not a.stage_only),
                "rollback": a.rollback,
                "mutations": False,
            }
        )
    )
    raise SystemExit()
with (root / "runner.lock").open("a") as lock:
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("Another runner owns this evidence directory")
        raise SystemExit(75)

    def journal(value):
        with (root / "journal.jsonl").open("a") as f:
            json.dump({"time": time.time(), **value}, f)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())

    def run(argv, timeout=1800):
        journal({"action": "before", "script": pathlib.Path(argv[1]).name})
        result = subprocess.run(argv, timeout=timeout)
        journal({"action": "after", "script": pathlib.Path(argv[1]).name, "exit": result.returncode})
        if result.returncode:
            raise SystemExit(result.returncode)

    def py(name, *args, timeout=1800):
        run(["python3", str(source / name), "--evidence", str(root), *args], timeout)

    if a.rollback:
        py("rollback.py", "--wait")
        raise SystemExit()
    state = json.loads((root / "state.json").read_text()) if (root / "state.json").exists() else {}
    if (
        a.resume
        and a.i_approve
        and not a.stage_only
        and state.get("phase") == "CUTOVER_READY"
        and not (root / "production/recovery-state.json").exists()
    ):
        py(
            "prepare_cutover.py",
            *(["--update-existing-package", a.update_existing_package] if a.update_existing_package else [])
        )
        py("deploy.py", "--i-approve", timeout=2400)
        raise SystemExit()
    if a.resume and (root / "production/recovery-state.json").exists() and not a.stage_only:
        py("deploy.py", "--resume", *(["--i-approve"] if a.i_approve else []))
        raise SystemExit()
    py("audit.py", "--namespace", a.namespace, "--allow-absent-staging")
    py("stage.py", "--namespace", a.namespace)
    env = {
        **os.environ,
        "ANSIBLE_CONFIG": str(repo / "ansible/ansible.cfg"),
        "ANSIBLE_ROLES_PATH": str(repo / "ansible/roles"),
    }
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
        timeout=600,
    )
    if result.returncode:
        raise SystemExit(result.returncode)
    py("validate.py", "--namespace", a.namespace, timeout=1800)
    py(
        "prepare_cutover.py",
        *(["--update-existing-package", a.update_existing_package] if a.update_existing_package else [])
    )
    atomic(
        root / "state.json",
        {
            "phase": "CUTOVER_READY",
            "production_cutover": False,
            "source_digest": json.loads((root / "staging/prepared.json").read_text())["source_digest"],
        },
    )
    if a.stage_only or not a.i_approve:
        print("CUTOVER_READY; production unchanged")
        raise SystemExit()
    py("deploy.py", "--i-approve", timeout=2400)
