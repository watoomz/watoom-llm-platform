#!/usr/bin/env python3
"""Authorised cutover through existing native admission, maintenance and Ansible owners."""

import argparse, pathlib, json, sys, os, subprocess, time, hashlib, secrets, fcntl, sqlite3

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from maintenance_guard import Maintenance
from release_guard import acquire, release, active_clear, durable_clearance, snapshot_database
from recover import atomic, published_health
from mcp_quiescence import quiesce, restore
from idle_streams import drain as drain_idle_streams
from native_readiness import wait as wait_native_skills

p = argparse.ArgumentParser()
p.add_argument("--evidence", required=True, type=pathlib.Path)
p.add_argument("--i-approve", action="store_true")
p.add_argument("--resume", action="store_true")
p.add_argument("--dry-run", action="store_true")
a = p.parse_args()
root = a.evidence.resolve()
out = root / "production"
plan = json.loads((out / "plan.json").read_text())
source = pathlib.Path(__file__).resolve().parent
repo = source.parents[2]
checkpoint = out / "recovery-state.json"
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def save(value):
    atomic(checkpoint, value)


def update(**fields):
    with checkpoint.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        s = json.loads(checkpoint.read_text())
        s.update(fields)
        save(s)
        if "phase" in fields:
            with (root / "journal.jsonl").open("a") as f:
                json.dump({"time": time.time(), "phase": fields["phase"], "component": "production-cutover"}, f)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
        return s


def ansible(play, values, timeout=900):
    env = {
        **os.environ,
        "ANSIBLE_CONFIG": str(repo / "ansible/ansible.cfg"),
        "ANSIBLE_ROLES_PATH": str(repo / "ansible/roles"),
    }
    logfile = out / (play + "-" + str(time.time_ns()) + ".log")
    with logfile.open("w") as log:
        r = subprocess.run(
            [
                "ansible-playbook",
                "-i",
                "inventories/homelab/hosts.yml",
                "playbooks/" + play + ".yml",
                "-c",
                "local",
                "-e",
                json.dumps(values),
            ],
            cwd=repo / "ansible",
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    os.chmod(logfile, 0o600)
    if r.returncode:
        raise RuntimeError("Ansible failed; inspect private " + str(logfile))


package_files = [
    "engine.mjs",
    "index.mjs",
    "package.json",
    "mock_provider.py",
    "worker_verifier.mjs",
    "optimisation.mjs",
]
package_digest = hashlib.sha256(
    "".join(sha(pathlib.Path(plan["source_package"]) / name) for name in package_files).encode()
).hexdigest()
if package_digest != plan["source_digest"]:
    raise RuntimeError("Immutable prepared package changed")
original_config = json.loads((out / "original-config.json").read_text())
final_config = json.loads((out / "final-config.json").read_text())
expected_plugins = list(original_config.get("plugins", []))
replacement = plan.get("update_existing_package")
if replacement:
    matches = [x for x in expected_plugins if isinstance(x, dict) and x.get("package") == replacement]
    if len(matches) != 1:
        raise RuntimeError("Exact approved prior learning package missing or ambiguous")
    expected_plugins.remove(matches[0])
if {k: v for k, v in original_config.items() if k != "plugins"} != {
    k: v for k, v in final_config.items() if k != "plugins"
} or final_config["plugins"][:-1] != expected_plugins:
    raise RuntimeError("Existing preferences, permissions, plugins or model routing changed")
if a.dry_run:
    print(
        json.dumps(
            {
                "status": plan["status"],
                "source_digest": plan["source_digest"],
                "phases": [
                    "fence",
                    "snapshot",
                    "validation deployment",
                    "native closed-loop acceptance",
                    "final deployment",
                    "service verification",
                ],
                "production_mutated": False,
            }
        )
    )
    raise SystemExit()
existing = json.loads(checkpoint.read_text()) if checkpoint.exists() else None
if not a.i_approve and not (a.resume and existing and existing.get("production_approved")):
    raise PermissionError("Separate explicit human production approval is required")
if plan["status"] != "CUTOVER_READY":
    raise RuntimeError("All staging gates must pass before approval can be used")
tests = json.loads((root / "test-results.json").read_text())
if tests.get("status") != "PASS" or tests.get("source_digest") != plan["source_digest"]:
    raise RuntimeError("Reviewed staging acceptance no longer matches candidate")
if (
    json.loads((root / "staging/prepared.json").read_text())["source_digest"] != plan["source_digest"]
    or tests.get("recovery_controller_sha256") != plan["controller_sha256"]
):
    raise RuntimeError("Latest staging candidate or tested recovery controller changed")
if (
    sha(out / "final-config.json") != plan["candidate_config_sha256"]
    or sha(out / "validation-config.json") != plan["validation_config_sha256"]
):
    raise RuntimeError("Prepared configuration changed")
if existing and existing["phase"] in ["CUTOVER_FAILED", "ROLLBACK_IN_PROGRESS", "ROLLED_BACK", "BLOCKED_RECOVERY"]:
    raise RuntimeError(
        "Prior cutover ended " + existing["phase"] + "; inspect preserved evidence and prepare a fresh reviewed release"
    )
m = Maintenance(plan["namespace"], plan["deployment"], out, True, True)
live = m.kub("get", "deploy", plan["deployment"])
if live["metadata"]["uid"] != plan["deployment_uid"]:
    raise RuntimeError("Baseline deployment identity changed")
if live["spec"]["template"]["spec"]["containers"][0]["image"] != plan["pinned_image"]:
    raise RuntimeError("Pinned application image changed")
if not existing:
    if sha(pathlib.Path(plan["config"])) != plan["baseline_config_sha256"]:
        raise RuntimeError("Production config changed since preparation")
    active_clear(m.request("/api/session/active"))
    durable_clearance(pathlib.Path("/data/ai/watoom-code/application.sqlite"))
    sys.path.insert(0, "/data/ai/helper-scripts/gpu-controller")
    from client import GPUClient

    gpu = GPUClient("/data/ai/helper-scripts/state/gpu-controller-private/worker.sock", timeout=10).call("status")
    from deployment_model import validate_idle_model

    gpu_config = json.loads(pathlib.Path("/data/ai/helper-scripts/config/gpu-controller.json").read_text())
    selected = (
        gpu_config["primary"]
        if gpu.get("phase") == "qwen-ready"
        else json.loads((pathlib.Path(gpu_config["state_root"]) / "selected-model.json").read_text())["deployment"]
    )
    model_live = json.loads(
        subprocess.check_output(
            ["kubectl", "-n", gpu_config["namespace"], "get", "deployment", plan["inference_deployment"], "-o", "json"],
            timeout=20,
        )
    )
    validate_idle_model(gpu, selected, plan["inference_deployment"], model_live)
    if plan["validation_model"].split("/", 1)[-1] not in original_config["providers"]["watoom"]["models"]:
        raise RuntimeError("Validation model is not registered")
    s = {
        **plan,
        "phase": "CUTOVER_READY",
        "production_approved": True,
        "grace_until": time.time() + 600,
        "health_failures": 0,
        "recovery_nonce": secrets.token_hex(16),
        "external_fence": False,
        "owned_sessions": [],
    }
    save(s)
if existing and existing["phase"] == "COMPLETE":
    print("PRODUCTION_ALREADY_VALIDATED")
    raise SystemExit()
# Re-arm after a crash between checkpoint creation and controller installation.
ansible(
    "watoom-code-self-learning-controller",
    {
        "watoom_learning_root": str(out),
        "watoom_learning_controller_script": plan["controller_script"],
        "watoom_learning_recovery_checkpoint": str(checkpoint),
    },
)
try:
    s = json.loads(checkpoint.read_text())
    if s["phase"] == "COMPLETE":
        print("PRODUCTION_ALREADY_VALIDATED")
        raise SystemExit()
    if s["phase"] == "PRODUCTION_VALIDATED" and not s.get("external_fence"):
        published = published_health(m)
        update(phase="COMPLETE", production_validated=True, published_service=published)
        print("PRODUCTION_VALIDATED_AFTER_RESUME")
        raise SystemExit()
    update(
        phase="CUTOVER_STARTED",
        grace_until=time.time() + 600,
        drain_started=time.time(),
        draining_until=time.time() + 90,
    )
    service_before = out / "maintenance-service-before.json"
    if service_before.exists():
        m.service = json.loads(service_before.read_text())
        m.held = True
        access = out / "maintenance-access-before.json"
        if access.exists():
            m.access = json.loads(access.read_text())
        m.verify_closed()
    else:
        update(external_fence=True)
        m.begin()
    guard = m.request("/api/session/deployment-guard")
    if not guard["data"]["held"]:
        acquire(
            lambda p: m.request(p),
            lambda p, b: m.request(p, b),
            lambda owner: update(owner=owner),
            lambda: durable_clearance(pathlib.Path("/data/ai/watoom-code/application.sqlite")),
        )
    s = json.loads(checkpoint.read_text())
    quiesce(m, s, lambda value: update(**{k: v for k, v in value.items() if k.startswith("mcp_")}))
    if not (out / "maintenance-access-before.json").exists():
        m.pause_access()
    drain_idle_streams(
        m,
        lambda: durable_clearance(pathlib.Path("/data/ai/watoom-code/application.sqlite")),
        lambda value: atomic(out / "idle-stream-drain.json", value),
    )
    update(draining_until=0)
    if not (out / "cutover-application.sqlite").exists():
        snapshot_database(pathlib.Path("/data/ai/watoom-code/application.sqlite"), out / "cutover-application.sqlite")
    if not (out / "cutover-memory-export.json").exists():
        code = "import os,urllib.request,json;h={'Authorization':'Bearer '+os.environ['AGENTMEMORY_SECRET']};r=urllib.request.urlopen(urllib.request.Request(os.environ['AGENTMEMORY_URL'].rstrip('/')+'/agentmemory/export',headers=h),timeout=20);v=json.load(r);assert 'version' in v and 'memories' in v;print(json.dumps(v))"
        raw = m.exec(code)
        (out / "cutover-memory-export.json").write_bytes(raw)
        os.chmod(out / "cutover-memory-export.json", 0o600)
    values = {
        "watoom_learning_production_approved": True,
        "watoom_learning_evidence": str(root),
        "watoom_learning_source_package": plan["source_package"],
        "watoom_learning_installed_package": plan["installed_package"],
        "watoom_learning_candidate_config": str(out / "validation-config.json"),
        "watoom_learning_candidate_deployment": plan["validation_deployment"],
    }
    if sha(pathlib.Path(plan["config"])) != plan["candidate_config_sha256"]:
        ansible("watoom-code-self-learning-cutover", values)
        s = json.loads(checkpoint.read_text())
        release(lambda p: m.request(p), lambda p, b: m.request(p, b), s["owner"])
        log = out / "native-production-validation.log"
        with log.open("w") as stream:
            r = subprocess.run(
                [
                    "python3",
                    str(source / "runtime_validation.py"),
                    "--evidence",
                    str(out),
                    "--namespace",
                    plan["namespace"],
                    "--deployment",
                    plan["deployment"],
                    "--agent",
                    "watoom-workflow",
                    "--model",
                    plan["validation_model"],
                    "--directory",
                    plan["validation_directory"],
                    "--database",
                    "/data/ai/watoom-code/application.sqlite",
                    "--learning-root",
                    plan["data_root"],
                    "--evaluations",
                    plan["evaluations"],
                    "--approved-state",
                    str(checkpoint),
                ],
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=1200,
            )
        os.chmod(log, 0o600)
        if r.returncode:
            raise RuntimeError("Production native learning validation failed; see " + str(log))
        validated = json.loads((out / "runtime-validation.json").read_text())
        # Disable the acceptance-only Skill without deleting its history or memory.
        request = secrets.token_hex(16)
        cmd = {"action": "disable", "id": validated["candidate"], "scope": validated["scope"], "request": request}
        action = pathlib.Path(plan["evaluations"]) / ("request-" + request + ".json")
        atomic(action, cmd)
        os.chmod(action, 0o644)
        deadline = time.monotonic() + 70
        while True:
            with sqlite3.connect("file:/data/ai/watoom-code/application.sqlite?mode=ro", uri=True) as db:
                states = [
                    json.loads(x[0]) for x in db.execute("select value from kv where key like ?", ("%learning/v1/%",))
                ]
            if any(s.get("operations", {}).get(request, {}).get("result") == "PASS" for s in states):
                break
            if time.monotonic() > deadline:
                raise RuntimeError("Acceptance Skill disable did not settle")
            time.sleep(1)
        active_clear(m.request("/api/session/active"))
        acquire(
            lambda p: m.request(p),
            lambda p, b: m.request(p, b),
            lambda owner: update(owner=owner),
            lambda: durable_clearance(pathlib.Path("/data/ai/watoom-code/application.sqlite")),
        )
        values.update(
            watoom_learning_candidate_config=str(out / "final-config.json"),
            watoom_learning_candidate_deployment=plan["final_deployment"],
        )
        ansible("watoom-code-self-learning-cutover", values)
    pod = m.pod()
    runtime_ids = [c.get("imageID", "") for c in pod.get("status", {}).get("containerStatuses", [])]
    if not runtime_ids or not all(x.endswith(plan["pinned_image"].split("@")[-1]) for x in runtime_ids):
        raise RuntimeError("Actual application image digest mismatch")
    if (
        hashlib.sha256(
            "".join(sha(pathlib.Path(plan["installed_package"]) / name) for name in package_files).encode()
        ).hexdigest()
        != plan["source_digest"]
    ):
        raise RuntimeError("Installed plugin bytes do not match staged package")
    code = "import os,urllib.request,json;h={'Authorization':'Bearer '+os.environ['AGENTMEMORY_SECRET']};r=urllib.request.urlopen(urllib.request.Request(os.environ['AGENTMEMORY_URL'].rstrip('/')+'/agentmemory/export',headers=h),timeout=20);print(json.dumps(json.load(r)))"
    exported = json.loads(m.exec(code))
    before = json.loads((out / "cutover-memory-export.json").read_text())
    old_records = {x["id"]: x["content"] for x in before["memories"]}
    new_records = {x["id"]: x["content"] for x in exported["memories"]}
    if any(new_records.get(key) != content for key, content in old_records.items()):
        raise RuntimeError("Existing AgentMemory records changed during cutover")
    atomic(
        out / "memory-preservation.json",
        {
            "status": "PASS",
            "original_records": len(old_records),
            "current_records": len(new_records),
            "new_verified_records": len(set(new_records) - set(old_records)),
        },
    )
    baseline_inference = json.loads((root / "baseline/inference.json").read_text())
    current_inference = json.loads(
        subprocess.check_output(
            ["kubectl", "-n", "llama-cpp", "get", "deploy", baseline_inference["metadata"]["name"], "-o", "json"],
            timeout=20,
        )
    )
    if (
        current_inference["spec"] != baseline_inference["spec"]
        or current_inference.get("status", {}).get("readyReplicas", 0) != baseline_inference["spec"]["replicas"]
    ):
        raise RuntimeError("Primary inference specification or readiness changed")
    atomic(
        out / "runtime-identities.json",
        {
            "status": "PASS",
            "pod_uid": pod["metadata"]["uid"],
            "image_ids": runtime_ids,
            "source_digest": plan["source_digest"],
            "primary_inference_unchanged": True,
        },
    )
    info, registered, readiness_attempts = wait_native_skills(m, plan["baseline_skills"])
    atomic(
        out / "native-readiness.json",
        {
            "status": "PASS",
            "attempts": readiness_attempts,
            "original_skills": len(plan["baseline_skills"]),
            "registered_skills": len(registered),
        },
    )
    code = "import os,urllib.request;assert urllib.request.urlopen(os.environ['AGENTMEMORY_URL'].rstrip('/')+'/agentmemory/livez',timeout=10).status==200;print('MEMORY_OK')"
    if b"MEMORY_OK" not in m.exec(code):
        raise RuntimeError("Persistent AgentMemory health failed")
    s = json.loads(checkpoint.read_text())
    restore(m, s, lambda value: update(**{k: v for k, v in value.items() if k.startswith("mcp_")}))
    update(phase="PRODUCTION_VALIDATED")
    guard = m.request("/api/session/deployment-guard")
    if guard["data"]["held"]:
        release(lambda p: m.request(p), lambda p, b: m.request(p, b), s["owner"])
    m.release()
    update(external_fence=False)
    published = published_health(m)
    update(phase="COMPLETE", external_fence=False, production_validated=True, published_service=published)
    atomic(
        root / "state.json", {"phase": "COMPLETE", "production_validated": True, "source_digest": plan["source_digest"]}
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "phase": "COMPLETE",
                "source_digest": plan["source_digest"],
                "learning_validation": str(out / "runtime-validation.json"),
            }
        )
    )
except Exception as error:
    update(phase="CUTOVER_FAILED", critical_failure=str(error)[:500], grace_until=0)
    print("CUTOVER_FAILED; independent recovery is armed. " + str(error))
    raise SystemExit(1)
