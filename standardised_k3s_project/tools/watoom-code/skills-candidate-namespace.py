#!/usr/bin/env python3
"""Move only the owned, idle candidate into the existing Kali-authorized test namespace."""

import argparse, copy, hashlib, json, os, pathlib, shutil, subprocess, time
from maintenance_guard import Maintenance
import release_guard


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evidence", required=True, type=pathlib.Path)
    a = p.parse_args()
    root = a.evidence.resolve()
    out = root / "candidate"
    identity = json.loads((out / "identity.json").read_text())
    name = identity["name"]
    assert (
        name == "watoom-code-skills-candidate-20261017"
        and identity["owner"] == root.name
        and identity["namespace"] == "watoom-code"
    )
    m = Maintenance(identity["namespace"], name, out, True, True)
    before = m.kub("get", "deploy", name)
    assert before["metadata"]["labels"]["watoom-test-owner"] == root.name
    assert m.request("/api/session/active")["data"] == {}
    release_guard.durable_clearance(out / "state/application.sqlite")
    assert m.request("/api/session/deployment-guard")["data"] == {
        "version": 1,
        "supported": True,
        "held": True,
        "leases": 0,
    }
    (out / "stage-candidate-before-namespace.private.json").write_text(json.dumps(before, indent=2))
    (out / "stage-candidate-before-namespace.private.json").chmod(0o600)
    source = pathlib.Path("/data/ai/watoom-code/config/.watoom")
    target = out / "config/.watoom"
    assert not target.exists()
    files = [path for path in source.rglob("*") if path.is_file()]
    assert len(files) <= 128 and sum(path.stat().st_size for path in files) <= 8 * 1024 * 1024
    shutil.copytree(source, target, symlinks=True)
    for path in [target, *target.rglob("*")]:
        os.chown(path, 1001, 1009, follow_symlinks=False)
    deployment = copy.deepcopy(before)
    deployment.pop("status", None)
    for key in ["uid", "resourceVersion", "creationTimestamp", "generation", "managedFields"]:
        deployment["metadata"].pop(key, None)
    deployment["metadata"].get("annotations", {}).pop("kubectl.kubernetes.io/last-applied-configuration", None)
    deployment["metadata"]["namespace"] = "opencode"
    deployment["spec"]["template"]["spec"]["serviceAccountName"] = "default"
    assert deployment["spec"]["template"]["spec"].get("automountServiceAccountToken") is False
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert not container.get("envFrom"), "Explicit secret references required"
    manifests = []
    references = {}
    for env in container["env"]:
        ref = env.get("valueFrom", {}).get("secretKeyRef")
        if ref:
            references.setdefault(ref["name"], set()).add(ref["key"])
    for old, keys in references.items():
        source_secret = m.kub("get", "secret", old)
        new = name + "-" + hashlib.sha256(old.encode()).hexdigest()[:8]
        existing = subprocess.check_output(
            ["kubectl", "-n", "opencode", "get", "secret", new, "--ignore-not-found", "-o", "json"]
        )
        assert not existing.strip(), "Do not overwrite an existing namespace secret"
        manifests.append(
            {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {"name": new, "namespace": "opencode", "labels": {"watoom-test-owner": root.name}},
                "type": "Opaque",
                "data": {key: source_secret["data"][key] for key in keys},
            }
        )
        for env in container["env"]:
            ref = env.get("valueFrom", {}).get("secretKeyRef")
            if ref and ref["name"] == old:
                ref["name"] = new
    labels = deployment["spec"]["template"]["metadata"]["labels"]
    services = json.loads(subprocess.check_output(["kubectl", "-n", "opencode", "get", "svc", "-o", "json"]))["items"]
    for service in services:
        selector = service.get("spec", {}).get("selector", {})
        assert not selector or not all(
            labels.get(key) == value for key, value in selector.items()
        ), "Candidate collides with an existing Service selector"
    existing = subprocess.check_output(
        ["kubectl", "-n", "opencode", "get", "deploy", name, "--ignore-not-found", "-o", "json"]
    )
    assert not existing.strip(), "Do not overwrite an existing deployment"
    service = json.loads((out / "service.json").read_text())
    service["metadata"]["namespace"] = "opencode"
    for manifest in [*manifests, service, deployment]:
        check = subprocess.run(
            ["kubectl", "apply", "--dry-run=server", "-f", "-"],
            input=json.dumps(manifest).encode(),
            capture_output=True,
        )
        if check.returncode:
            raise RuntimeError(check.stderr.decode()[-500:])
    # Stop just this idle, fenced owned process before the same SQLite state is mounted elsewhere.
    subprocess.run(
        ["kubectl", "-n", identity["namespace"], "scale", "deploy/" + name, "--replicas=0"],
        check=True,
        capture_output=True,
    )
    deadline = time.monotonic() + 60
    while m.kub("get", "pods", "-l", "app=" + name)["items"]:
        if time.monotonic() > deadline:
            raise RuntimeError("Owned old candidate has not stopped; do not start another process")
        time.sleep(1)
    for manifest in [*manifests, service, deployment]:
        subprocess.run(
            ["kubectl", "apply", "-f", "-"], input=json.dumps(manifest).encode(), check=True, capture_output=True
        )
    identity.update(
        namespace="opencode", previous_namespace="watoom-code", status="MOVED_TO_EXISTING_AUTHORIZED_NAMESPACE_FENCED"
    )
    (out / "identity.json").write_text(json.dumps(identity, indent=2))
    (out / "namespace-move.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "old_candidate_stopped": True,
                "namespace": "opencode",
                "network_policy_changed": False,
                "same_image": identity["image"],
                "same_persistent_state": True,
                "native_profile_files_copied": len(files),
                "service_selector_collision": "NONE",
            },
            indent=2,
        )
    )
    print("PASS owned candidate moved with no duplicate process, policy change or Service collision")


if __name__ == "__main__":
    main()
