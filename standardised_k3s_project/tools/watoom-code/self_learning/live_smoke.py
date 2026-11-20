#!/usr/bin/env python3
"""One idle-gated safe request through the existing primary model router; no GPU lifecycle commands."""

import argparse, pathlib, sys, subprocess, json, sqlite3, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from maintenance_guard import Maintenance
from release_guard import active_clear
from recover import atomic

p = argparse.ArgumentParser()
p.add_argument("--evidence", required=True, type=pathlib.Path)
p.add_argument("--namespace", required=True)
a = p.parse_args()
if not a.namespace.startswith("watoom-code-learning-"):
    raise ValueError("Staging-only smoke")
root = a.evidence
stage = root / "staging"
prod = Maintenance("watoom-code", "watoom-code", root, True, True)
m = Maintenance(a.namespace, "learning-app", root, True, True)
active_clear(prod.request("/api/session/active"))
active_clear(m.request("/api/session/active"))
sys.path.insert(0, "/data/ai/helper-scripts/gpu-controller")
from client import GPUClient

controller = GPUClient("/data/ai/helper-scripts/state/gpu-controller-private/worker.sock", timeout=10)
status = controller.call("status")
if status.get("owner") is not None or status.get("phase") != "qwen-ready":
    raise RuntimeError("Existing controller does not admit an idle primary-Qwen smoke")
before = prod.kub("get", "deploy", "watoom-code")["spec"]
skills = m.request("/api/skill?location%5Bdirectory%5D=%2Fworkspace")["data"]
if not any(x["id"].startswith("learned-") for x in skills):
    raise RuntimeError("Native learned Skill not ready")
session = m.request(
    "/api/session",
    {
        "title": "Live primary-model learning smoke",
        "agent": "learning-fixture",
        "model": {"providerID": "watoom", "id": "swift-qwen38-coder"},
        "location": {"directory": "/workspace"},
    },
)["data"]
sid = session["id"]
start = time.monotonic()
m.request(
    "/api/session/" + sid + "/prompt",
    {
        "text": "Load the matching learned native Skill for sorting fixture development data. Apply it by calling watoom_learning_fixture exactly once, then report its verified result in one sentence. Do not use any other tools except skill and watoom_learning_fixture. This is an isolated CPU fixture; do not request infrastructure changes."
    },
)
deadline = time.monotonic() + 180
while sid in m.request("/api/session/active")["data"]:
    if time.monotonic() > deadline:
        raise RuntimeError("Live smoke timed out; leave existing session intact and inspect evidence")
    time.sleep(1)
elapsed = time.monotonic() - start
with sqlite3.connect("file:" + str(stage / "state/application.sqlite") + "?mode=ro", uri=True) as c:
    row = c.execute(
        "select idle_outcome,tokens_input,tokens_output,tokens_reasoning,tokens_cache_read,tokens_cache_write from session_v2 where id=?",
        (sid,),
    ).fetchone()
    messages = [
        json.loads(x[0])
        for x in c.execute("select data from session_message where session_id=? and type=?", (sid, "assistant"))
    ]
    tools = [x for msg in messages for x in msg.get("content", []) if x.get("type") == "tool"]
successful = (
    row[0] == "succeeded"
    and any(t["name"] == "skill" and t["state"]["status"] == "completed" for t in tools)
    and sum(t["name"] == "watoom_learning_fixture" and t["state"]["status"] == "completed" for t in tools) == 1
    and not any(t["state"]["status"] == "error" for t in tools)
)
after = controller.call("status")
report = {
    "status": "PASS" if successful else "FAIL",
    "session": sid,
    "model": "watoom/swift-qwen38-coder",
    "seconds": elapsed,
    "native_usage": dict(zip(["outcome", "input", "output", "reasoning", "cache_read", "cache_write"], row)),
    "tools": [{"name": t["name"], "status": t["state"]["status"]} for t in tools],
    "controller_owner_before": status.get("owner"),
    "controller_owner_after": after.get("owner"),
    "controller_generation_unchanged": status.get("generation") == after.get("generation"),
    "production_deployment_unchanged": before == prod.kub("get", "deploy", "watoom-code")["spec"],
    "model_swaps": 0,
    "efficiency_improvement": "NOT_CLAIMED",
}
atomic(root / "native-tests/live-model-smoke.json", report)
print(json.dumps(report))
if not successful:
    print(json.dumps(messages[-2:])[:5000])
    raise SystemExit(1)
