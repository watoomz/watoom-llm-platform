"""Explicitly approved controller/router integration; never changes replica policy."""

import argparse, copy, hashlib, json, os, secrets, shutil, subprocess, sys, time, tempfile
from pathlib import Path
from manage import ROOT, run, write, snapshot, preflight, validate
from broker import rpc

CONTROLLER = Path("/data/ai/helper-scripts/gpu-controller")
CONFIG = Path("/data/ai/helper-scripts/config/gpu-controller.json")
SOCKET = "/data/ai/helper-scripts/state/gpu-controller-private/worker.sock"
MODULES = ["g3h_service.py", "model_lifecycle.py", "inference_leases.py", "kubernetes_api.py"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def get(ns, kind, name):
    return json.loads(run(["kubectl", "-n", ns, "get", kind, name, "-o", "json"]))


def wait_status():
    deadline = time.monotonic() + 30
    while True:
        try:
            return rpc(SOCKET, {"action": "status"})
        except (FileNotFoundError, ConnectionRefusedError):
            if time.monotonic() > deadline:
                raise
            time.sleep(0.2)


def patch(ns, kind, name, current, changes):
    ops = [
        {"op": "test", "path": "/metadata/uid", "value": current["metadata"]["uid"]},
        {"op": "test", "path": "/metadata/resourceVersion", "value": current["metadata"]["resourceVersion"]},
        *changes,
    ]
    # ConfigMaps can exceed the kernel per-argument limit. Keep private JSON off argv.
    descriptor, filename = tempfile.mkstemp(prefix="model-manager-patch-", suffix=".json")
    try:
        with os.fdopen(descriptor, "w") as file:
            json.dump(ops, file, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        return json.loads(
            run(["kubectl", "-n", ns, "patch", kind, name, "--type=json", "--patch-file", filename, "-o", "json"])
        )
    finally:
        os.unlink(filename)


def journal(out):
    path = out / "transaction.json"
    return json.loads(path.read_text()) if path.exists() else {"patches": [], "manager_started": False}


def transactional_patch(out, ns, kind, name, current, field, value):
    transaction = journal(out)
    before = current["data"] if field == "/data" else current["spec"]["template"]
    entry = {
        "namespace": ns,
        "kind": kind,
        "name": name,
        "uid": current["metadata"]["uid"],
        "field": field,
        "before": before,
        "after": value,
    }
    if entry not in transaction["patches"]:
        transaction["patches"].append(entry)
    write(out / "transaction.json", transaction)  # durable intent BEFORE Kubernetes mutation
    return patch(ns, kind, name, current, [{"op": "replace", "path": field, "value": value}])


def restore_patches(out, apply=False):
    transaction = journal(out)
    prepared = []
    seen = set()
    # All preconditions checked before the first restore; reject unrelated edits.
    for entry in reversed(transaction["patches"]):
        fingerprint = json.dumps(entry, sort_keys=True)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        current = get(entry["namespace"], entry["kind"], entry["name"])
        if current["metadata"]["uid"] != entry["uid"]:
            raise RuntimeError("Replacement resource protected")
        value = current["data"] if entry["field"] == "/data" else current["spec"]["template"]
        if value not in (entry["before"], entry["after"]):
            raise RuntimeError("Independent edit blocks rollback")
        if value == entry["after"]:
            prepared.append((entry, current))
    if apply:
        for entry, current in prepared:
            patch(
                entry["namespace"],
                entry["kind"],
                entry["name"],
                current,
                [{"op": "replace", "path": entry["field"], "value": entry["before"]}],
            )
    return prepared


def resource_identity(obj):
    meta = obj["metadata"]
    return {
        "uid": meta["uid"],
        "spec": obj.get("spec"),
        "labels": meta.get("labels", {}),
        "annotations": {
            k: v
            for k, v in meta.get("annotations", {}).items()
            if k != "kubectl.kubernetes.io/last-applied-configuration"
        },
    }


def rollback_plan(out):
    plan = json.loads((out / "cutover-plan.json").read_text())
    release = out / "rollback-release.json"
    if release.exists():
        snapshot = json.loads(release.read_text())
        plan.update(
            commit=snapshot["commit"],
            candidate_files=snapshot["candidate_files"],
            controller_files=snapshot["controller_files"],
        )
    return plan


def owned_resources(out):
    result = []
    release = out / "rollback-release.json"
    snapshot = json.loads(release.read_text()) if release.exists() else None
    for kind in ("deployment", "service", "ingressroute"):
        raw = run(["kubectl", "-n", "glance", "get", kind, "model-manager", "--ignore-not-found", "-o", "json"])
        if not raw.strip():
            continue
        obj = json.loads(raw)
        meta = obj["metadata"]
        if meta.get("labels", {}).get("watoom.io/owner") != "model-manager":
            raise RuntimeError("Foreign manager resource protected")
        if snapshot:
            if resource_identity(obj) != snapshot["resources"].get(kind):
                raise RuntimeError("Manager changed since rollback preparation")
        elif meta.get("annotations", {}).get("watoom.io/model-manager-release") != rollback_plan(out)["commit"]:
            raise RuntimeError("Foreign or replaced manager resource protected")
        result.append(obj)
    return result


def prepare_rollback(out):
    # Capture exact approved maintenance releases without modifying original backups.
    plan = json.loads((out / "cutover-plan.json").read_text())
    candidate = {}
    baseline = {}
    resources = {}
    for name in MODULES:
        actual = CONTROLLER / name
        source = ROOT / "tools/llm/watoom-gpu-controller" / name
        if not actual.exists() or sha(actual) != sha(source):
            raise RuntimeError("Installed controller differs from maintained source")
        candidate[name] = sha(actual)
        before = out / "before" / name
        baseline[name] = sha(before) if before.exists() else None
        if name in plan["controller_files"] and baseline[name] != plan["controller_files"][name]:
            raise RuntimeError("Original controller backup changed")
    for kind in ("deployment", "service", "ingressroute"):
        obj = json.loads(run(["kubectl", "-n", "glance", "get", kind, "model-manager", "-o", "json"]))
        if obj["metadata"].get("labels", {}).get("watoom.io/owner") != "model-manager":
            raise RuntimeError("Foreign manager resource protected")
        resources[kind] = resource_identity(obj)
    snapshot = {
        "commit": run(["git", "rev-parse", "HEAD"], cwd=ROOT).strip(),
        "candidate_files": candidate,
        "controller_files": baseline,
        "resources": resources,
        "original_backups": "before",
        "precondition": "Unregister managed models, preserve files, and obtain administrative quiet",
    }
    write(out / "rollback-release.json", snapshot)
    return {"state": "PREPARED_NOT_EXECUTED", "commit": snapshot["commit"], "managed_models_must_be_retired": True}


def delete_owned(obj):
    kind = obj["kind"]
    meta = obj["metadata"]
    prefix = (
        "/apis/apps/v1"
        if kind == "Deployment"
        else "/apis/traefik.io/v1alpha1" if kind == "IngressRoute" else "/api/v1"
    )
    plural = {"Deployment": "deployments", "Service": "services", "IngressRoute": "ingressroutes"}[kind]
    options = {
        "apiVersion": "v1",
        "kind": "DeleteOptions",
        "preconditions": {"uid": meta["uid"], "resourceVersion": meta["resourceVersion"]},
    }
    run(
        ["kubectl", "delete", "--raw", prefix + "/namespaces/glance/" + plural + "/" + meta["name"], "-f", "-"],
        input=json.dumps(options),
    )


def router_plan(cm, deployment, code):
    cm = copy.deepcopy(cm)
    deployment = copy.deepcopy(deployment)
    cm["data"]["router.py"] = code
    spec = deployment["spec"]["template"]["spec"]
    volumes = {
        "managed-models": {
            "name": "managed-models",
            "hostPath": {"path": "/data/ai/helper-scripts/state/model-manager-router", "type": "Directory"},
        },
        "managed-key": {
            "name": "managed-key",
            "hostPath": {"path": "/data/ai/private/model-manager/backend-key", "type": "File"},
        },
    }
    for name, desired in volumes.items():
        existing = next((x for x in spec.get("volumes", []) if x["name"] == name), None)
        if existing and existing != desired:
            raise ValueError("Foreign router volume collision")
        if not existing:
            spec.setdefault("volumes", []).append(desired)
    container = next(c for c in spec["containers"] if c["name"] == "router")
    mounts = [
        {"name": "managed-models", "mountPath": "/managed-models", "readOnly": True},
        {"name": "managed-key", "mountPath": "/private/backend-key", "readOnly": True},
    ]
    for mount in mounts:
        old = next((x for x in container.get("volumeMounts", []) if x["name"] == mount["name"]), None)
        if old and old != mount:
            raise ValueError("Foreign mount collision")
        if not old:
            container.setdefault("volumeMounts", []).append(mount)
    for name, value in {
        "WATOOM_MANAGED_CATALOG": "/managed-models/catalog.json",
        "WATOOM_MANAGED_KEY": "/private/backend-key",
    }.items():
        previous = next((x for x in container.get("env", []) if x["name"] == name), None)
        if previous and previous != {"name": name, "value": value}:
            raise ValueError("Foreign environment collision")
        if not previous:
            container.setdefault("env", []).append({"name": name, "value": value})
    return cm, deployment


def glance_plan(current):
    import yaml

    desired = copy.deepcopy(current)
    document = yaml.safe_load(desired["data"]["glance.yml"])
    page = next(p for p in document["pages"] if p["name"] == "LLM Lab")
    url = "https://glance.internal.homelab.example/model-manager/"
    if url not in json.dumps(page):
        widget = {
            "type": "bookmarks",
            "title": "Model management",
            "groups": [{"links": [{"title": "Model Manager", "url": url, "icon": "mdi:download-network"}]}],
        }
        page["columns"][0]["widgets"].insert(0, widget)
    desired["data"]["glance.yml"] = yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=1000)
    return desired


def prepare(out):
    preflight()
    before = snapshot(out)
    # Complete private snapshots, including absent-file records, before mutation.
    for name in MODULES:
        source = CONTROLLER / name
        if source.exists():
            destination = out / "before" / name
            if not destination.exists():
                shutil.copy2(source, destination)
        else:
            write(out / "before" / (name + ".absent.json"), {"absent": True})
    if not (out / "before/controller-config.json").exists():
        write(out / "before/controller-config.json", json.loads(CONFIG.read_text()))
    commit = run(["git", "rev-parse", "HEAD"], cwd=ROOT).strip()
    result = {
        "commit": commit,
        "controller_files": {
            name: sha(CONTROLLER / name) if (CONTROLLER / name).exists() else None for name in MODULES
        },
        "candidate_files": {name: sha(ROOT / "tools/llm/watoom-gpu-controller" / name) for name in MODULES},
        "approval_required": "Production controller restart, router rollout and authenticated model-manager publication; no model activation or weight deletion",
    }
    write(out / "cutover-plan.json", result)
    return result


def fence_runtime(out):
    # Reuse the installed production Runtime and its existing lock/owner protocol.
    sys.path.insert(0, str(CONTROLLER))
    from g3h_service import Runtime, atomic, process_identity
    from controller import State

    config = json.loads(CONFIG.read_text())
    runtime = Runtime(config)
    with runtime.store.exclusive():
        state = runtime.store.load()
        if state.phase != "qwen-ready" or state.owner or state.uncertain or runtime.journal.pending():
            raise RuntimeError("Production ownership is not idle")
        from urllib.request import urlopen

        def idle():
            with urlopen(config["urls"][config["primary"]] + "/slots", timeout=10) as response:
                slots = json.load(response)
            if not isinstance(slots, list) or not slots or not all(x.get("is_processing") is False for x in slots):
                raise RuntimeError("Actual inference is active")

        idle()
        owner = "operator-" + str(os.getpid()) + "-" + str(process_identity(os.getpid()))
        generation = state.generation + 1
        atomic(
            runtime.owner_path,
            {"kind": "operator", "job": owner, "pid": os.getpid(), "start": process_identity(os.getpid())},
        )
        runtime.store.save(State("acquiring", owner, generation))
        runtime.actuator.generation = generation
        write(out / "gpu-owner.json", {"owner": owner, "generation": generation})
        # Deny new router grants, then drain any pre-claim request; never stop its work.
        deadline = time.monotonic() + 120
        try:
            for check in range(3):
                while True:
                    try:
                        idle()
                        break
                    except RuntimeError:
                        if time.monotonic() > deadline:
                            raise
                        time.sleep(2)
                if check < 2:
                    time.sleep(2)
        except BaseException:
            runtime.controller._restore(owner, generation)
            raise
    return runtime, owner, generation


def restore_owner(runtime, owner, generation):
    # After code replacement, the caller's imported Runtime is stale. Restore using
    # the CURRENT installed code in a fresh interpreter, with exact live-owner proof.
    code = """import sys,json,os
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from g3h_service import Runtime,process_identity
config=json.loads(Path(sys.argv[2]).read_text());runtime=Runtime(config)
owner=sys.argv[3];generation=int(sys.argv[4]);parent=int(sys.argv[5])
with runtime.store.exclusive():
 state=runtime.store.load();identity=json.loads(runtime.owner_path.read_text())
 if (state.owner,state.generation)!=(owner,generation) or identity.get("kind")!="operator" or identity.get("pid")!=parent or process_identity(parent)!=identity.get("start"):
  raise RuntimeError("Live operator identity or ownership changed; restoration refused")
 runtime.actuator.generation=generation
 runtime.actuator.unknown=bool(runtime.journal.pending())
 runtime.controller._restore(owner,generation)
"""
    run(
        [sys.executable, "-c", code, str(CONTROLLER), str(CONFIG), owner, str(generation), str(os.getpid())],
        timeout=600,
    )
    state = rpc(SOCKET, {"action": "status"})
    if state["owner"] or state["uncertain"] or state["phase"] != "qwen-ready":
        raise RuntimeError("Primary restoration not verified")


def activate(out, approve, admin_quiet):
    plan = json.loads((out / "cutover-plan.json").read_text())
    if not admin_quiet or approve != plan["commit"] or run(["git", "rev-parse", "HEAD"], cwd=ROOT).strip() != approve:
        raise RuntimeError("Exact prepared commit approval and administrative quiet are required")
    if not (out / "stage-validation.json").exists() or not (out / "sdxl-artifact.json").exists():
        raise RuntimeError("CPU staging and SDXL image artifact required")
    for name, expected in plan["candidate_files"].items():
        if sha(ROOT / "tools/llm/watoom-gpu-controller" / name) != expected:
            raise RuntimeError("Candidate source changed")
    for name, expected in plan["controller_files"].items():
        actual = sha(CONTROLLER / name) if (CONTROLLER / name).exists() else None
        if actual != expected:
            raise RuntimeError("Installed controller changed; prepare a new snapshot")
    for kind in ("deployment", "service", "ingressroute"):
        if run(["kubectl", "-n", "glance", "get", kind, "model-manager", "--ignore-not-found", "-o", "name"]).strip():
            raise RuntimeError("Production manager name already exists; reconcile prior transaction")
    if (out / "transaction.json").exists():
        raise RuntimeError("Existing transaction requires rollback/reconciliation before another activation")
    write(out / "transaction.json", {"patches": [], "manager_started": False})
    sys.path.insert(0, str(ROOT / "tools/watoom-code"))
    from native_admission import hold

    def quiet():
        state = rpc(SOCKET, {"action": "status"})
        if state["owner"] or state["uncertain"] or state.get("active_requests", 0):
            raise RuntimeError("Active GPU work blocks cutover")

    with hold(out / "native-cutover", quiet):
        runtime, owner, generation = fence_runtime(out)
        try:
            private = Path("/data/ai/private/model-manager")
            private.mkdir(parents=True, exist_ok=True, mode=0o700)
            for name in ("password", "backend-key"):
                path = private / name
                if not path.exists():
                    path.write_text(secrets.token_urlsafe(36))
                    path.chmod(0o640)
                    os.chown(path, 0, 1009)
            routes = Path("/data/ai/helper-scripts/state/model-manager-router")
            routes.mkdir(parents=True, exist_ok=True, mode=0o755)
            if not (routes / "catalog.json").exists():
                (routes / "catalog.json").write_text('{"version":1,"models":{}}')
            for name in MODULES:
                destination = CONTROLLER / name
                shutil.copy2(ROOT / "tools/llm/watoom-gpu-controller" / name, destination)
                destination.chmod(0o600)
            config = json.loads(CONFIG.read_text())
            config["managed_auth_file"] = "/data/ai/private/model-manager/backend-key"
            write(CONFIG, config)
            run(["systemctl", "restart", "watoom-gpu-controller.service"])
            status = wait_status()
            if status.get("managed_enrollment_version") != 1 or status["owner"] != owner:
                raise RuntimeError("New runtime did not retain fenced ownership")
            cm = get("llama-cpp", "cm", "llm-router-app")
            deployment = get("llama-cpp", "deployment", "llm-router")
            before_cm = json.loads((out / "before/llama-cpp-cm-llm-router-app.json").read_text())
            before_deploy = json.loads((out / "before/llama-cpp-deployment-llm-router.json").read_text())
            if cm["data"] != before_cm["data"] or deployment["spec"] != before_deploy["spec"]:
                raise RuntimeError("Router changed independently")
            desired_cm, desired_deploy = router_plan(
                cm, deployment, (ROOT / "ansible/roles/llm-model-lab/files/gpu-controller-router.py").read_text()
            )
            transactional_patch(out, "llama-cpp", "cm", "llm-router-app", cm, "/data", desired_cm["data"])
            transactional_patch(
                out,
                "llama-cpp",
                "deployment",
                "llm-router",
                deployment,
                "/spec/template",
                desired_deploy["spec"]["template"],
            )
            run(
                ["kubectl", "-n", "llama-cpp", "rollout", "status", "deployment/llm-router", "--timeout=180s"],
                timeout=190,
            )
            write(
                out / "router-after.json",
                {"cm_data": desired_cm["data"], "template": desired_deploy["spec"]["template"]},
            )
            artifact = json.loads((out / "artifact.json").read_text())
            sdxl = json.loads((out / "sdxl-artifact.json").read_text())
            variables = {
                "model_manager_enabled": True,
                "model_manager_stage_only": False,
                "model_manager_controller_verified": True,
                "model_manager_publish_route": False,
                "model_manager_image": artifact["image"],
                "model_manager_sdxl_image": sdxl["image"],
                "model_manager_release": approve,
            }
            transaction = journal(out)
            transaction["manager_started"] = True
            write(out / "transaction.json", transaction)
            write(out / "production-vars.json", variables)
            env = dict(
                os.environ,
                ANSIBLE_CONFIG=str(ROOT / "ansible/ansible.cfg"),
                ANSIBLE_ROLES_PATH=str(ROOT / "ansible/roles"),
            )
            run(
                [
                    "ansible-playbook",
                    "-i",
                    str(ROOT / "ansible/inventories/homelab/hosts.yml"),
                    str(ROOT / "ansible/playbooks/model-manager.yml"),
                    "--connection",
                    "local",
                    "--limit",
                    "homelab-host",
                    "-e",
                    "@" + str(out / "production-vars.json"),
                ],
                cwd=ROOT,
                env=env,
                timeout=300,
            )
            run(
                ["kubectl", "-n", "glance", "rollout", "status", "deployment/model-manager", "--timeout=120s"],
                timeout=130,
            )
            validate(out, namespace="glance")
            variables["model_manager_publish_route"] = True
            write(out / "production-vars.json", variables)
            run(
                [
                    "ansible-playbook",
                    "-i",
                    str(ROOT / "ansible/inventories/homelab/hosts.yml"),
                    str(ROOT / "ansible/playbooks/model-manager.yml"),
                    "--connection",
                    "local",
                    "--limit",
                    "homelab-host",
                    "-e",
                    "@" + str(out / "production-vars.json"),
                ],
                cwd=ROOT,
                env=env,
                timeout=300,
            )
            finish_publication(out, approve)
        finally:
            restore_owner(runtime, owner, generation)
    return json.loads((out / "activation.json").read_text())


def finish_publication(out, approve):
    current_glance = get("glance", "cm", "glance-config")
    desired_glance = glance_plan(current_glance)
    write(out / "glance-after.json", desired_glance["data"])
    transactional_patch(out, "glance", "cm", "glance-config", current_glance, "/data", desired_glance["data"])
    glance = get("glance", "deployment", "glance")
    template = copy.deepcopy(glance["spec"]["template"])
    template["metadata"].setdefault("annotations", {})["watoom.io/model-manager-config"] = hashlib.sha256(
        desired_glance["data"]["glance.yml"].encode()
    ).hexdigest()
    transactional_patch(out, "glance", "deployment", "glance", glance, "/spec/template", template)
    run(["kubectl", "-n", "glance", "rollout", "status", "deployment/glance", "--timeout=120s"], timeout=130)
    resources = [get("glance", kind, "model-manager") for kind in ("deployment", "service", "ingressroute")]
    write(
        out / "production-resources.json",
        [{"kind": x["kind"], "name": x["metadata"]["name"], "uid": x["metadata"]["uid"]} for x in resources],
    )
    write(
        out / "activation.json",
        {
            "state": "DEPLOYED_GENERATION_NOT_TESTED",
            "url": "https://glance.internal.homelab.example/model-manager/",
            "commit": approve,
        },
    )


def resume_publication(out, approve, admin_quiet):
    plan = json.loads((out / "cutover-plan.json").read_text())
    if approve != plan["commit"] or not admin_quiet:
        raise RuntimeError("Exact prepared source approval required")
    if not (out / "production-validation.json").exists():
        raise RuntimeError("Prior real production API validation required")
    for name, expected in plan["candidate_files"].items():
        if sha(CONTROLLER / name) != expected:
            raise RuntimeError("Controller changed independently")
    restore_patches(out)  # all recorded mutations must still be their exact before/after values
    resources = owned_resources(out)
    if {x["kind"] for x in resources} != {"Deployment", "Service", "IngressRoute"}:
        raise RuntimeError("Incomplete production manager resources")
    sys.path.insert(0, str(ROOT / "tools/watoom-code"))
    from native_admission import hold

    def quiet():
        state = rpc(SOCKET, {"action": "status"})
        if state["owner"] or state["uncertain"] or state.get("active_requests", 0):
            raise RuntimeError("Active work blocks publication resume")

    with hold(out / "native-publication-resume", quiet):
        runtime, owner, generation = fence_runtime(out)
        try:
            validate(out, namespace="glance")
            finish_publication(out, approve)
        finally:
            restore_owner(runtime, owner, generation)
    return json.loads((out / "activation.json").read_text())


def rollback(out, approve, admin_quiet):
    plan = rollback_plan(out)
    if approve != plan["commit"] or not admin_quiet:
        raise RuntimeError("Exact rollback approval and administrative quiet required")
    ledger = Path("/data/ai/helper-scripts/state/gpu-controller/managed-models.json")
    if ledger.exists() and json.loads(ledger.read_text())["models"]:
        raise RuntimeError("Unregister managed models before rollback; weights may be kept")
    manager_root = Path("/data/ai/helper-scripts/state/model-manager-broker")
    marker = manager_root / "maintenance.json"
    if marker.exists():
        raise RuntimeError("Existing manager maintenance owner requires reconciliation")
    write(marker, {"operation": "rollback", "commit": approve})
    os.chown(marker, 0, 1009)
    os.chmod(marker, 0o640)
    from file_lock import lock_file
    import sqlite3

    operation_lock = None
    try:
        catalog = Path("/data/ai/model-manager/catalog.sqlite")
        if catalog.exists():
            lock_path = catalog.parent / "operations.lock"
            if not lock_path.exists():
                lock_path.touch(mode=0o640)
                os.chown(lock_path, 1009, 1009)
            operation_lock = lock_path.open("a")
            lock_file(operation_lock)
            with sqlite3.connect("file:" + str(catalog) + "?mode=ro", uri=True) as db:
                busy = db.execute(
                    "SELECT count(*) FROM jobs WHERE state IN ('QUEUED','DOWNLOADING','GENERATING','REMOVING','CANCEL_REQUESTED')"
                ).fetchone()[0]
            if busy:
                raise RuntimeError("Queued or active manager work blocks rollback; work is preserved")
        original = json.loads((out / "before/controller-config.json").read_text())
        current = json.loads(CONFIG.read_text())
        expected = {**original, "managed_auth_file": "/data/ai/private/model-manager/backend-key"}
        if current not in (original, expected):
            raise RuntimeError("Controller config changed independently")
        for name in MODULES:
            actual = sha(CONTROLLER / name) if (CONTROLLER / name).exists() else None
            if actual not in (plan["candidate_files"][name], plan["controller_files"][name]):
                raise RuntimeError("Controller source changed independently")
        restore_patches(out)  # prove ALL Kubernetes restore preconditions before any mutation
        resources = owned_resources(out) if journal(out)["manager_started"] else []
        sys.path.insert(0, str(ROOT / "tools/watoom-code"))
        from native_admission import hold

        def quiet():
            state = rpc(SOCKET, {"action": "status"})
            if state["owner"] or state["uncertain"] or state.get("active_requests", 0):
                raise RuntimeError("Active work blocks rollback")

        with hold(out / "native-rollback", quiet):
            runtime, owner, generation = fence_runtime(out)
            try:
                restore_patches(out, apply=True)
                for resource in reversed(resources):
                    delete_owned(resource)
                if journal(out)["manager_started"]:
                    run(["systemctl", "stop", "watoom-model-manager-broker.service"])
                for name in MODULES:
                    destination = CONTROLLER / name
                    if plan["controller_files"][name] is not None:
                        shutil.copy2(out / "before" / name, destination)
                    elif destination.exists():
                        destination.unlink()
                write(CONFIG, original)
                run(["systemctl", "restart", "watoom-gpu-controller.service"])
                wait_status()
                for namespace, deployment in (("llama-cpp", "llm-router"), ("glance", "glance")):
                    run(
                        ["kubectl", "-n", namespace, "rollout", "status", "deployment/" + deployment, "--timeout=180s"],
                        timeout=190,
                    )
            finally:
                restore_owner(runtime, owner, generation)
        write(
            out / "rollback.json",
            {"state": "CONTROLLER_ROUTER_RESTORED", "model_files": "untouched", "manager": "OWNED_RESOURCES_REMOVED"},
        )
        return json.loads((out / "rollback.json").read_text())
    finally:
        if operation_lock:
            operation_lock.close()
        # If resources remain, KEEP admission closed for explicit reconciliation.
        try:
            remaining = owned_resources(out) if journal(out)["manager_started"] else []
        except Exception:
            remaining = [True]
        if not remaining and marker.exists():
            marker.unlink()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["prepare", "activate", "resume-publication", "prepare-rollback", "rollback"])
    p.add_argument("--evidence", required=True)
    p.add_argument("--approve")
    p.add_argument("--i-approve", action="store_true")
    p.add_argument("--administrative-quiet", action="store_true")
    a = p.parse_args()
    out = Path(a.evidence)
    if not out.is_absolute() or not out.is_relative_to("/data/ai/helper-scripts"):
        raise RuntimeError("Private evidence path required")
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    if a.action not in ("prepare", "prepare-rollback"):
        if not a.i_approve:
            raise RuntimeError("Standing approval gate requires --i-approve after reviewing this exact change")
        print(
            "RISK: production controller/router replacement, GPU admission maintenance and model-manager publication/removal. Active work is never killed; model files are retained.",
            file=sys.stderr,
        )
    result = (
        prepare(out)
        if a.action == "prepare"
        else (
            prepare_rollback(out)
            if a.action == "prepare-rollback"
            else {"activate": activate, "resume-publication": resume_publication, "rollback": rollback}[a.action](
                out, a.approve, a.administrative_quiet
            )
        )
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
