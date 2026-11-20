#!/usr/bin/env python3
"""Re-pin the GPU controller's approved spec digest for the primary model Deployment.

The controller refuses all GPU actions (incl. recovery) when a pinned Deployment's
UID/spec digest differs from live. After a reviewed primary Deployment change, run
--apply (via the llm-model-lab role with gpu_controller_repin_primary=true).
Only deployment_identity[primary].spec_sha256 may change; UID must match; the
controller must be qwen-ready, unowned and certain. A timestamped backup is kept.
Exit 0 = unchanged/updated, 2 = blocked. Same digest formula as g3h_service.py.

--name DEPLOYMENT re-pins another pinned model the same way (2026-11-19: the model-lab manifest added a chat
template to llama-cpp-qwen35-defiant-fable-9b, the pin was not updated, and every model switch failed with
"deployment identity or model configuration changed"). A non-primary model must also be fully stopped (spec and
status replicas 0): its new spec is only trusted before it ever runs under the new pin. Check that the live spec is
the reviewed manifest first (kubectl diff -f <manifest> must be empty).

--recovery: the drift has already sent the controller to recovery-required (a switch hit the stale pin). Allowed only
in that phase with an authenticated router owner (router-*), per tools/llm/watoom-gpu-controller/README.md (a running
non-primary is then allowed: it is the failed switch's target): re-pin,
restart watoom-gpu-controller.service, then the same router reconciles with POST /models/load of the primary model.
"""

import argparse, copy, hashlib, json, os, pathlib, subprocess, sys, time

BASE = pathlib.Path("/data/ai/helper-scripts")
CONFIG = BASE / "config/gpu-controller.json"
STATE = BASE / "state/gpu-controller/state.json"


def digest(obj):
    spec = copy.deepcopy(obj["spec"])
    spec.pop("replicas", None)
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write; default is read-only check")
    ap.add_argument("--config", default=str(CONFIG))
    ap.add_argument("--state", default=str(STATE))
    ap.add_argument(
        "--recovery", action="store_true", help="allow phase recovery-required owned by the router (see docstring)"
    )
    ap.add_argument("--name", default=None, help="a pinned Deployment other than the primary (must be stopped)")
    a = ap.parse_args()
    cfgp = pathlib.Path(a.config)
    cfg = json.loads(cfgp.read_text())
    name, ns = a.name or cfg["primary"], cfg["namespace"]
    if name not in cfg.get("deployment_identity", {}):
        sys.exit("BLOCKED: %s is not a pinned Deployment; enrol it, do not re-pin" % name)
    live = json.loads(subprocess.check_output(["kubectl", "-n", ns, "get", "deployment", name, "-o", "json"]))
    pinned = cfg["deployment_identity"][name]
    if live["metadata"]["uid"] != pinned["uid"]:
        sys.exit("BLOCKED: %s Deployment UID changed; re-enrol, do not re-pin" % name)
    if (
        name != cfg["primary"]
        and not a.recovery
        and (live["spec"].get("replicas", 1) != 0 or live.get("status", {}).get("replicas", 0) != 0)
    ):
        sys.exit("BLOCKED: %s is not stopped; re-pin a non-primary model only while it has 0 replicas" % name)
    new = digest(live)
    if new == pinned["spec_sha256"]:
        print("UNCHANGED")
        return
    st = json.loads(pathlib.Path(a.state).read_text())
    recovering = (
        a.recovery and st.get("phase") == "recovery-required" and str(st.get("owner") or "").startswith("router-")
    )
    if not recovering and (st.get("phase"), st.get("owner"), st.get("uncertain")) != ("qwen-ready", None, False):
        sys.exit("BLOCKED: controller not qwen-ready/unowned/certain: " + json.dumps(st))
    if not a.apply:
        print("DRIFT %s -> %s (run with --apply)" % (pinned["spec_sha256"][:12], new[:12]))
        sys.exit(2)
    backup = cfgp.with_name(cfgp.name + ".bak-" + time.strftime("%Y%m%dT%H%M%S"))
    backup.write_bytes(cfgp.read_bytes())
    os.chmod(backup, 0o600)
    old = pinned["spec_sha256"]  # pinned IS cfg's dict: read it before the update below
    cfg["deployment_identity"][name]["spec_sha256"] = new
    raw = cfgp.read_text()
    indent = 2 if '\n  "' in raw else None
    tmp = cfgp.with_name(cfgp.name + ".tmp")
    tmp.write_text(json.dumps(cfg, indent=indent) + "\n")
    os.chmod(tmp, 0o600)
    tmp.replace(cfgp)
    print("REPINNED %s %s -> %s (backup %s)" % (name, old[:12], new[:12], backup.name))


if __name__ == "__main__":
    main()
