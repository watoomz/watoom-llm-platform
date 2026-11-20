#!/usr/bin/env python3
"""Apply a changed manifest to a STOPPED (replicas 0) GPU-controller model deployment and re-approve its identity.

The controller refuses a deployment whose uid/spec digest differs from config deployment_identity, so a settings
change needs the same transaction as scripts/watoom-qwen-maintenance.py (which only edits the running Swift args):
controller stopped -> manifest applied (uid kept, replicas stay 0) -> identity recorded in the live config AND the
repo copy Ansible installs -> controller restarted only when identity matches the live object. Any failure before the
identity is recorded restores the previous deployment object.

  gpu-controller-reconfigure.py --deployment NAME --manifest FILE            # check: predicted digest, no changes
  gpu-controller-reconfigure.py --deployment NAME --manifest FILE --apply    # transaction (needs no in-flight requests)
"""
import argparse, copy, datetime, hashlib, json, os, pathlib, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIVE_CONFIG = pathlib.Path("/data/ai/helper-scripts/config/gpu-controller.json")
REPO_CONFIG = ROOT / "ansible/roles/llm-model-lab/files/gpu-controller.json"
STATE = pathlib.Path("/data/ai/helper-scripts/state/gpu-controller")
UNIT = "watoom-gpu-controller.service"
NS = "llama-cpp"
OUT = pathlib.Path("/data/ai/helper-scripts/reports")


class Blocked(RuntimeError):
    pass


def run(args, stdin=None, timeout=60, ok=True):
    p = subprocess.run(args, input=stdin, capture_output=True, text=True, timeout=timeout)
    if ok and p.returncode:
        raise Blocked("%s failed: %s" % (" ".join(args[:4]), p.stderr.strip()[-600:]))
    return p


def digest(obj):
    spec = copy.deepcopy(obj["spec"])
    spec.pop("replicas", None)
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def live(name):
    return json.loads(run(["kubectl", "-n", NS, "get", "deployment", name, "-o", "json"]).stdout)


def atomic_json(path, obj, indent=2):
    raw = json.dumps(obj, indent=indent) + "\n"
    temp = path.with_name(path.name + ".reconfigure-tmp")
    mode = path.stat().st_mode & 0o777
    temp.write_text(raw)
    os.chmod(temp, mode)
    os.replace(temp, path)


def quiet(name):
    """The controller must be certain, not switching, not owning or selecting this deployment, with no requests."""
    state = json.loads((STATE / "state.json").read_text())
    if state.get("uncertain") or str(state.get("phase", "")).startswith("switching"):
        raise Blocked("controller busy or uncertain: %s" % state)
    selected = json.loads((STATE / "selected-model.json").read_text()).get("deployment")
    if selected == name:
        raise Blocked("deployment is the selected model")
    leases = json.loads((STATE / "inference-leases.json").read_text()).get("leases")
    if leases:
        raise Blocked("in-flight inference requests")
    for p in (STATE / "intents").glob("*.json"):
        if json.loads(p.read_text()).get("status") != "acknowledged":
            raise Blocked("pending controller intent " + p.name)
    return state


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--deployment", required=True)
    a.add_argument("--manifest", required=True, type=pathlib.Path)
    a.add_argument("--apply", action="store_true")
    a = a.parse_args()
    if os.geteuid():
        raise Blocked("operator (root) only")
    cfg = json.loads(LIVE_CONFIG.read_text())
    known = cfg["deployment_identity"].get(a.deployment)
    before = live(a.deployment)
    if known != {"uid": before["metadata"]["uid"], "spec_sha256": digest(before)}:
        raise Blocked("live deployment already differs from its approved identity; reconcile first")
    if before["spec"].get("replicas", 0) != 0:
        raise Blocked("deployment must be stopped (replicas 0)")
    manifest = a.manifest.read_text()
    dry = json.loads(run(["kubectl", "apply", "--dry-run=server", "-o", "json", "-f", "-"], stdin=manifest).stdout)
    items = dry.get("items", [dry])
    predicted = [i for i in items if i["kind"] == "Deployment" and i["metadata"]["name"] == a.deployment]
    if len(predicted) != 1:
        raise Blocked("manifest must contain the deployment exactly once")
    predicted = predicted[0]
    if predicted["metadata"]["uid"] != before["metadata"]["uid"] or predicted["spec"].get("replicas", 0) != 0:
        raise Blocked("apply would recreate or start the deployment")
    new = {"uid": before["metadata"]["uid"], "spec_sha256": digest(predicted)}
    print(json.dumps({"deployment": a.deployment, "approved": known, "predicted": new, "changed": new != known}))
    if not a.apply or new == known:
        return
    folder = OUT / ("gpu-reconfigure-%s-%s" % (a.deployment, datetime.datetime.now().strftime("%Y%m%d-%H%M%S")))
    folder.mkdir(parents=True)
    (folder / "deployment.before.json").write_text(json.dumps(before))
    (folder / "controller-config.before.json").write_text(json.dumps(cfg))
    state = quiet(a.deployment)
    stopped = recorded = applied = False
    try:
        run(["systemctl", "stop", UNIT], timeout=60)
        stopped = True
        if json.loads((STATE / "state.json").read_text()) != state or json.loads((STATE / "inference-leases.json").read_text()).get("leases"):
            raise Blocked("controller state or leases changed while stopping")
        applied = True
        run(["kubectl", "apply", "-f", "-"], stdin=manifest, timeout=120)
        after = live(a.deployment)
        if {"uid": after["metadata"]["uid"], "spec_sha256": digest(after)} != new or after["spec"].get("replicas", 0) != 0:
            raise Blocked("applied deployment does not match the prediction")
        for path in (LIVE_CONFIG, REPO_CONFIG):
            c = json.loads(path.read_text())
            if path == LIVE_CONFIG and c != cfg:
                raise Blocked("controller config changed during the transaction")
            c["deployment_identity"][a.deployment] = new
            atomic_json(path, c)
        recorded = True
        (folder / "deployment.after.json").write_text(json.dumps(after))
    except BaseException as e:
        print("APPLY_ERROR=" + str(e), file=sys.stderr)
        if applied and not recorded:
            old = {k: before[k] for k in ("apiVersion", "kind", "metadata", "spec")}
            old["metadata"] = {k: before["metadata"][k] for k in ("name", "namespace", "labels", "annotations") if k in before["metadata"]}
            run(["kubectl", "replace", "-f", "-"], stdin=json.dumps(old), timeout=120, ok=False)
            print("ROLLBACK=" + ("PASS" if digest(live(a.deployment)) == known["spec_sha256"] else "FAILED (manual recovery)"), file=sys.stderr)
        raise
    finally:
        if stopped:
            now = live(a.deployment)
            identity = json.loads(LIVE_CONFIG.read_text())["deployment_identity"][a.deployment]
            if identity == {"uid": now["metadata"]["uid"], "spec_sha256": digest(now)}:
                run(["systemctl", "start", UNIT], timeout=60)
                time.sleep(3)
                print("GPU_CONTROLLER_RESTARTED=" + run(["systemctl", "is-active", UNIT], ok=False).stdout.strip())
            else:
                print("GPU_CONTROLLER_RESTARTED=NO identity mismatch; evidence " + str(folder), file=sys.stderr)
    print("RESULT=APPLIED evidence " + str(folder))


if __name__ == "__main__":
    try:
        main()
    except Blocked as e:
        print("BLOCKED: " + str(e), file=sys.stderr)
        sys.exit(2)
