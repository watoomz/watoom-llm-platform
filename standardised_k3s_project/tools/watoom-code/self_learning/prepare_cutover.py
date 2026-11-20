#!/usr/bin/env python3
"""Prepare a private, checksum-pinned cutover; never changes production."""

import argparse, pathlib, json, hashlib, subprocess, shutil, os, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from maintenance_guard import Maintenance
from recover import atomic

p = argparse.ArgumentParser()
p.add_argument("--evidence", type=pathlib.Path, required=True)
p.add_argument("--update-existing-package")
p.add_argument("--validation-model", default="watoom/swift-qwen38-coder")
p.add_argument("--validation-deployment", default="llama-cpp-swift-qwen38-coder")
a = p.parse_args()
root = a.evidence.resolve()
source = pathlib.Path(__file__).resolve().parent
stage = root / "staging"
out = root / "production"
out.mkdir(exist_ok=True, mode=0o700)
os.chmod(out, 0o700)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
files = ["engine.mjs", "index.mjs", "package.json", "mock_provider.py", "worker_verifier.mjs", "optimisation.mjs"]
identity = hashlib.sha256("".join(sha(source / n) for n in files).encode()).hexdigest()
prepared = json.loads((stage / "prepared.json").read_text())
if prepared["source_digest"] != identity:
    raise ValueError("Current executable source has not been staged")
m = Maintenance("watoom-code", "watoom-code", out, True, True)
live = m.kub("get", "deploy", "watoom-code")
configpath = pathlib.Path("/data/ai/watoom-code/config/opencode.json")
original = configpath.read_bytes()
config = json.loads(original)
if live["spec"]["template"]["spec"]["containers"][0]["image"] != prepared["appimage"]:
    raise ValueError("Staging and production images differ")
guard = next(
    (
        x if isinstance(x, str) else x["package"]
        for x in config.get("plugins", [])
        if "coordinator-guard" in (x if isinstance(x, str) else x.get("package", ""))
    ),
    None,
)
if not guard or not guard.startswith("/config/watoom-tools/coordinator-guard"):
    raise ValueError("Verified native guard package not found")
guardhost = pathlib.Path("/data/ai/watoom-code/config") / pathlib.Path(guard).relative_to("/config")
if "export async function gameSourceFingerprint" not in (guardhost / "index.js").read_text():
    raise ValueError("Installed guard fingerprint interface not present")
package = out / ("package-" + identity)
package.mkdir(exist_ok=True, mode=0o755)
for name in files:
    target = package / name
    if target.exists() and sha(target) != sha(source / name):
        raise ValueError("Immutable prepared source collision")
    if not target.exists():
        shutil.copy2(source / name, target)
        os.chmod(target, 0o644)
dest = pathlib.Path("/data/ai/watoom-code/config/watoom-tools") / ("self-learning-" + identity)
runtime = "/config/watoom-tools/" + dest.name
policies = json.loads((source / "production-policies.json").read_text())
for policy in policies:
    policy["environment"] = {
        "application_image": prepared["appimage"],
        "native_worker_guard_sha256": sha(guardhost / "index.js"),
        "contract": "native-cpu-worker-v1",
    }
fixture = json.loads((stage / "config/opencode.json").read_text())["plugins"][0]["options"]["policies"][0]
existing_ids = [k["id"] for k in m.request("/api/skill?location%5Bdirectory%5D=%2Fworkspace")["data"]]
options = {
    "existingSkillIDs": existing_ids,
    "root": "/state/self-learning",
    "agent": "watoom-workflow",
    "workerGuardPackage": guard,
    "policies": policies,
    "metadataBytes": 1024,
    "curatorMs": 900000,
    "evaluations": "/config/watoom-tools/self-learning-evaluations",
    "autoPromote": True,
    "agentMemoryVersion": "0.9.29",
    "fixture": False,
}
existing = [
    x for x in config.get("plugins", []) if "self-learning-" in (x if isinstance(x, str) else x.get("package", ""))
]
if existing:
    if len(existing) != 1 or not isinstance(existing[0], dict) or existing[0]["package"] != a.update_existing_package:
        raise ValueError("Exact existing immutable package approval required")
    preserved = existing[0]["options"]
    options = {**preserved, **options, "optimisationRevisions": preserved.get("optimisationRevisions", [])}
final = json.loads(original)
if existing:
    final["plugins"] = (
        [x for x in final["plugins"] if x.get("package") != a.update_existing_package]
        if all(isinstance(x, dict) for x in final["plugins"])
        else [x for x in final["plugins"] if not isinstance(x, dict) or x.get("package") != a.update_existing_package]
    )
final.setdefault("plugins", []).append({"package": runtime, "options": options})
validation = json.loads(json.dumps(final))
validation["plugins"][-1]["options"].update({"fixture": True, "curatorMs": 30000, "policies": policies + [fixture]})
(out / "original-config.json").write_bytes(original)
os.chmod(out / "original-config.json", 0o600)
atomic(out / "final-config.json", final)
atomic(out / "validation-config.json", validation)
baseline = {
    "apiVersion": "apps/v1",
    "kind": "Deployment",
    "metadata": {"name": "watoom-code", "namespace": "watoom-code", "labels": live["metadata"].get("labels", {})},
    "spec": live["spec"],
}
atomic(out / "original-deployment.json", baseline)
for phase, cfg in [("validation", "validation-config.json"), ("final", "final-config.json")]:
    manifest = json.loads(json.dumps(baseline))
    manifest["spec"]["template"]["metadata"].setdefault("annotations", {})["watoom-self-learning-config-sha256"] = sha(
        out / cfg
    )
    manifest["spec"]["template"]["metadata"]["annotations"]["watoom-self-learning-source-sha256"] = identity
    atomic(out / (phase + "-deployment.json"), manifest)
controller_files = [
    source / "recover.py",
    source / "mcp_quiescence.py",
    source.parent / "maintenance_guard.py",
    source.parent / "release_guard.py",
]
controller_id = hashlib.sha256("".join(sha(p) for p in controller_files).encode()).hexdigest()
controller = out / ("controller-" + controller_id)
controller.mkdir(exist_ok=True, mode=0o755)
for item in controller_files:
    target = controller / item.name
    if target.exists() and sha(target) != sha(item):
        raise ValueError("Pinned controller changed")
    if not target.exists():
        shutil.copy2(item, target)
        os.chmod(target, 0o644)
baseline_skills = [k["id"] for k in m.request("/api/skill?location%5Bdirectory%5D=%2Fworkspace")["data"]]
testfile = root / "test-results.json"
tests = json.loads(testfile.read_text()) if testfile.exists() else {}
lifecycle = (
    json.loads((root / "lifecycle-contract-tests.json").read_text())
    if (root / "lifecycle-contract-tests.json").exists()
    else {}
)
lifecycle_ok = lifecycle.get("status") == "PASS" and all(
    lifecycle.get("sources", {}).get(n) == sha(source / n)
    for n in [
        "mcp_quiescence.py",
        "idle_streams.py",
        "recover.py",
        "deploy.py",
        "optimise.py",
        "test_mcp_quiescence.py",
        "test_idle_streams.py",
        "native_readiness.py",
        "test_native_readiness.py",
        "deployment_model.py",
        "test_deployment_model.py",
    ]
)
idle_proof = (
    json.loads((root / "native-tests/idle-stream-drain.json").read_text())
    if (root / "native-tests/idle-stream-drain.json").exists()
    else {}
)
readiness_proof = (
    json.loads((root / "native-tests/native-readiness.json").read_text())
    if (root / "native-tests/native-readiness.json").exists()
    else {}
)
ready = (
    readiness_proof.get("status") == "PASS"
    and readiness_proof.get("source_sha256") == sha(source / "native_readiness.py")
    and idle_proof.get("status") == "PASS"
    and idle_proof.get("source_sha256") == sha(source / "idle_streams.py")
    and lifecycle_ok
    and tests.get("status") == "PASS"
    and tests.get("source_digest") == identity
    and tests.get("recovery_controller_sha256") == sha(source / "recover.py")
)
plan = {
    "validation_model": a.validation_model,
    "inference_deployment": a.validation_deployment,
    "update_existing_package": a.update_existing_package,
    "learning_agent": "watoom-workflow",
    "status": "CUTOVER_READY" if ready else "STAGING_VALIDATION_PENDING",
    "production_approved": False,
    "namespace": "watoom-code",
    "deployment": "watoom-code",
    "deployment_uid": live["metadata"]["uid"],
    "replicas": live["spec"]["replicas"],
    "source_digest": identity,
    "pinned_image": prepared["appimage"],
    "source_package": str(package),
    "installed_package": str(dest),
    "config": str(configpath),
    "data_root": "/data/ai/watoom-code/self-learning",
    "evaluations": "/data/ai/watoom-code/config/watoom-tools/self-learning-evaluations",
    "baseline_skills": baseline_skills,
    "directory": "/workspace",
    "validation_directory": "/state/self-learning/acceptance-project",
    "baseline_deployment": str(out / "original-deployment.json"),
    "baseline_deployment_sha256": sha(out / "original-deployment.json"),
    "baseline_config": str(out / "original-config.json"),
    "baseline_config_sha256": sha(out / "original-config.json"),
    "validation_config_sha256": sha(out / "validation-config.json"),
    "candidate_config_sha256": sha(out / "final-config.json"),
    "validation_deployment": str(out / "validation-deployment.json"),
    "final_deployment": str(out / "final-deployment.json"),
    "migration": "Existing native plugin KV namespace only; no schema or AgentMemory migration",
    "rollback_policy": "Restore exact original config and deployment references; preserve old/new databases and generated data",
    "grace_seconds": 600,
    "controller_script": str(controller / "recover.py"),
    "controller_sha256": sha(controller / "recover.py"),
}
atomic(out / "plan.json", plan)
atomic(root / "cutover-plan.json", plan)
atomic(
    root / "rollback-plan.json",
    {
        k: plan[k]
        for k in [
            "namespace",
            "deployment",
            "deployment_uid",
            "baseline_deployment",
            "baseline_deployment_sha256",
            "baseline_config",
            "baseline_config_sha256",
            "rollback_policy",
        ]
    },
)
print(
    json.dumps(
        {
            "status": plan["status"],
            "source_digest": identity,
            "plan": str(out / "plan.json"),
            "production_mutated": False,
        }
    )
)
