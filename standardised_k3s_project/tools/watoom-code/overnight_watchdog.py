#!/usr/bin/env python3
"""Overnight health watchdog for the watoom-code stack (report-only by default).

Purpose
-------
Give an unattended operator/model a single, safe probe of whether the
watoom-code job pipeline is healthy, idle on a *designed* gate, or genuinely
hung -- WITHOUT firing any fenced recovery action or switching GPU leases.

It is deliberately conservative:
  * It never runs the fenced recover-*.py scripts (those require an explicit
    operator --i-approve + idle fence by design).
  * It never switches a model lease (that must go through the GPU ownership
    controller with rollback).
  * It never writes a visual-review receipt (forbidden by VISUAL_RECEIPT_CONTRACT).

It only READS state and classifies it, so a supervisor loop (a human, Claude
Code, or a Codex run) can decide what to do. Safe actions (restarting a crashed
stateless service) are gated behind --restart-crashed and still logged.

Classification (printed as JSON, and encoded in the exit code):
  0  HEALTHY            stack up, recent progress
  10 IDLE_REVIEW_GATE   parked on a vision review (needs a vision lease / GUI)
  20 IDLE               quiet, nothing claimed, no gate -- normal between jobs
  30 HANG               a stateless service is down or a claim looks stuck
  40 PROBE_ERROR        the watchdog itself could not read state

Usage
-----
  overnight_watchdog.py                 # probe + JSON report, no actions
  overnight_watchdog.py --report DIR    # also append a timestamped line to DIR/watchdog.log
  overnight_watchdog.py --restart-crashed   # restart a crashed router/opencode (logged)

Reusable by the owner's models; see README stanza in this directory.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

STAGE_DB = Path("/data/ai/watoom-code/application.sqlite")
WORKER_REPORTS = Path("/data/ai/helper-scripts/reports/game-worker")
ROUTER_URL = "http://10.243.133.2:8000"            # llm-router ClusterIP svc
REVIEW_GATE_STATUS = "CAPTURED_VISUAL_REVIEW_PENDING"
# Models the coordinator-guard accepts as image presenters (opencode.json.j2
# `verifiedVisionModels`). These are vision-capable despite "-coder" names —
# do NOT infer vision capability from the deployment string.
VERIFIED_VISION = {
    "swift-qwen38-coder", "qwen38-uncensored-mtp", "tiel-coder-35b-a3b-mtp",
}
# How long a pending review / no-progress window is "just idle" vs worth flagging.
IDLE_FLAG_SEC = 45 * 60


def _procs():
    """Return a dict of expected long-lived processes -> count seen."""
    try:
        out = subprocess.run(["ps", "-eo", "cmd"], capture_output=True, text=True,
                             timeout=10).stdout
    except Exception as e:  # noqa: BLE001
        return {"_error": str(e)}
    return {
        "opencode_serve": len(re.findall(r"opencode serve", out)),
        "router": len(re.findall(r"\brouter\.py\b", out)),
    }


def _router_health():
    try:
        with urllib.request.urlopen(ROUTER_URL + "/health", timeout=5) as r:
            return json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def _latest_worker_report():
    """Newest game-worker operator.log: (age_sec, status, scene) or None."""
    try:
        logs = sorted(WORKER_REPORTS.glob("*.operator.log"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:  # noqa: BLE001
        return None
    if not logs:
        return None
    newest = logs[0]
    age = time.time() - newest.stat().st_mtime
    status = scene = None
    try:
        doc = json.loads(newest.read_text())
        status = doc.get("status")
        scene = doc.get("scene")
    except Exception:  # noqa: BLE001
        pass
    return {"age_sec": round(age), "status": status, "scene": scene,
            "report": newest.name}


def classify(snap):
    procs = snap["processes"]
    if procs.get("_error"):
        return "PROBE_ERROR", 40, "could not enumerate processes"
    # A stateless service we expect up has crashed -> genuine hang class.
    if procs.get("router", 0) < 1:
        return "HANG", 30, "router.py not running"
    if procs.get("opencode_serve", 0) < 1:
        return "HANG", 30, "no opencode serve process"

    wr = snap["worker_report"]
    if wr and wr.get("status") == REVIEW_GATE_STATUS:
        active = (snap["router_health"] or {}).get("active_deployment", "")
        model = active.removeprefix("llama-cpp-")
        vision_capable = model in VERIFIED_VISION
        if not vision_capable:
            return ("IDLE_REVIEW_GATE", 10,
                    f"capture parked on vision review ({wr.get('scene')}); active "
                    f"model '{model}' is NOT in the guard's verifiedVisionModels -- "
                    f"lease a verified vision model (GPU controller) or resume in GUI")
        # Active model CAN present the image; the review just is not being driven.
        return ("IDLE_REVIEW_GATE", 10,
                f"capture parked on vision review ({wr.get('scene')}); active model "
                f"'{model}' IS vision-capable, so no lease change needed -- the agent "
                f"session must run/resume the review (GUI)")

    if wr and wr.get("age_sec", 0) <= IDLE_FLAG_SEC:
        return "HEALTHY", 0, "recent worker activity"
    return "IDLE", 20, "no active claim or gate; quiet between jobs"


def restart_crashed(snap, report_dir):
    """Only restarts a crashed STATELESS service (router via its k8s deploy)."""
    acted = []
    procs = snap["processes"]
    if procs.get("router", 0) < 1:
        # router runs in-cluster; bounce its deployment rather than the bare proc.
        try:
            subprocess.run(["kubectl", "-n", "llama-cpp", "rollout", "restart",
                            "deployment/llm-router"], check=True, timeout=60,
                           capture_output=True, text=True)
            acted.append("rolled out llm-router")
        except Exception as e:  # noqa: BLE001
            acted.append(f"router restart FAILED: {e}")
    # opencode serve is session-stateful; do NOT auto-restart it here.
    return acted


def main():
    ap = argparse.ArgumentParser(description="watoom-code overnight health watchdog (report-only).")
    ap.add_argument("--report", type=Path, help="dir to append a watchdog.log line to")
    ap.add_argument("--restart-crashed", action="store_true",
                    help="restart a crashed stateless service (router); logged")
    args = ap.parse_args()

    snap = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "processes": _procs(),
        "router_health": _router_health(),
        "worker_report": _latest_worker_report(),
    }
    state, code, reason = classify(snap)
    snap.update({"state": state, "reason": reason})

    actions = []
    if args.restart_crashed and state == "HANG":
        actions = restart_crashed(snap, args.report)
        snap["actions"] = actions

    print(json.dumps(snap, indent=2))

    if args.report:
        try:
            args.report.mkdir(parents=True, exist_ok=True)
            line = json.dumps({"ts": snap["ts"], "state": state,
                               "reason": reason, "actions": actions})
            with (args.report / "watchdog.log").open("a") as f:
                f.write(line + "\n")
        except Exception as e:  # noqa: BLE001
            print(f"[watchdog] could not write report: {e}", file=sys.stderr)

    sys.exit(code)


if __name__ == "__main__":
    main()
