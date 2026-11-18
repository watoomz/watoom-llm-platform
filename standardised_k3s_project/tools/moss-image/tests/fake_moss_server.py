#!/usr/bin/env python3
"""Minimal stand-in for mossimage.cpp's moss-server (protocol 2) for offline tests. Records every request."""
import base64, json, os, sys, threading, time

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
LOG = os.environ.get("FAKE_MOSS_LOG")
cancelled = set()
out_lock = threading.Lock()


def send(obj):
    with out_lock:
        sys.stdout.write(json.dumps(obj) + "\n")
        sys.stdout.flush()


def generate(rid, p):
    send({"id": rid, "result": {"accepted": True}})
    send({"event": "plan", "id": rid, "explanation": "fake", "plan": {}})
    slow = "SLOW" in p["prompt"]
    steps = 1000 if slow else 3
    for i in range(steps + 1):
        if rid in cancelled:
            send({"event": "done", "id": rid, "status": "cancelled", "steps_run": i, "warnings": [], "report": None})
            return
        send({"event": "progress", "id": rid, "phase": "denoise" if i else "text_encoder", "step": i, "total_steps": steps,
              "fraction": 0.9 * i / steps, "eta_seconds": 1.0})
        time.sleep(0.05)
    if "FAIL" in p["prompt"]:
        send({"event": "done", "id": rid, "status": "error", "error": {"code": "out_of_memory", "message": "fake oom"}, "warnings": []})
        return
    with open(p["output"], "wb") as f:
        f.write(PNG)
    send({"event": "done", "id": rid, "status": "ok", "image": p["output"], "warnings": ["fake warning"], "report": {}})


for line in sys.stdin:
    try:
        req = json.loads(line)
    except ValueError:
        continue
    if LOG:
        with open(LOG, "a") as f:
            f.write(json.dumps(req) + "\n")
    m, rid, p = req.get("method"), req.get("id"), req.get("params") or {}
    if m == "hello":
        send({"id": rid, "result": {"protocol_version": 2, "abi_version": 1}})
    elif m == "load":
        send({"id": rid, "result": {"model": p.get("model"), "mode": p.get("mode"), "device": 0}})
    elif m == "generate":
        threading.Thread(target=generate, args=(rid, p), daemon=True).start()
    elif m == "cancel":
        cancelled.add(p.get("id"))
        send({"id": rid, "result": {"cancelled": True}})
    elif m in ("release", "unload"):
        send({"id": rid, "result": {}})
    elif m == "shutdown":
        send({"id": rid, "result": {}})
        break
