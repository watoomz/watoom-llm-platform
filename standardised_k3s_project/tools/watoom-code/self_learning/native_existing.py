#!/usr/bin/env python3
"""Native discovery/load baseline for every existing Skill; no workflow execution."""

import pathlib, argparse, json, sys, time, sqlite3, hashlib, urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from maintenance_guard import Maintenance
from recover import atomic

p = argparse.ArgumentParser()
p.add_argument("--evidence", required=True, type=pathlib.Path)
p.add_argument("--namespace", required=True)
a = p.parse_args()
if not a.namespace.startswith("watoom-code-learning-"):
    raise ValueError("Isolated baseline only")
root = a.evidence
inventory = json.loads((root / "existing-skills/native-inventory.json").read_text())["data"]
database = root / "staging/state/application.sqlite"
m = Maintenance(a.namespace, "learning-app", root, True, True)
deadline = time.monotonic() + 45
while True:
    registered = {
        k["id"]: k
        for k in m.request("/api/skill?" + urllib.parse.urlencode({"location[directory]": "/workspace"}))["data"]
    }
    if {k["id"] for k in inventory} <= set(registered):
        break
    if time.monotonic() > deadline:
        raise RuntimeError("Native corpus registration did not settle")
    time.sleep(1)
checks = []


def procedure(k):
    return (
        k["content"].split("## Runtime Diagnostics Snapshot", 1)[0].strip()
        if k["id"] == "report"
        else k["content"].strip()
    )


for original in inventory:
    k = registered.get(original["id"])
    assert k is not None, original["id"] + " missing from native registry"
    assert procedure(k) == procedure(original), "Baseline instructions changed: " + k["id"]
    start = time.monotonic()
    sid = m.request(
        "/api/session",
        {
            "title": "Existing Skill load baseline " + k["id"],
            "agent": "learning-fixture",
            "model": {"providerID": "fixture", "id": "cpu-fixture"},
            "location": {"directory": "/workspace"},
            "permissions": [
                {"action": "*", "resource": "*", "effect": "deny"},
                {"action": "skill", "resource": k["id"], "effect": "allow"},
            ],
        },
    )["data"]["id"]
    m.request(
        "/api/session/" + sid + "/prompt",
        {
            "text": "LOAD_EXISTING:"
            + k["id"]
            + " Load only this native Skill. Do not execute its instructions or any commands."
        },
    )
    deadline = time.monotonic() + 30
    while sid in m.request("/api/session/active")["data"]:
        if time.monotonic() > deadline:
            raise RuntimeError("Native Skill load timed out: " + k["id"])
        time.sleep(0.15)
    with sqlite3.connect("file:" + str(database) + "?mode=ro", uri=True) as c:
        messages = [
            json.loads(x[0])
            for x in c.execute("select data from session_message where session_id=? and type='assistant'", (sid,))
        ]
    tools = [t for msg in messages for t in msg.get("content", []) if t.get("type") == "tool"]
    assert len(tools) == 1 and tools[0]["name"] == "skill" and tools[0]["state"]["status"] == "completed", (
        k["id"] + " did not load correctly"
    )
    content = "\n".join(x.get("text", "") for x in tools[0]["state"].get("content", []) if x.get("type") == "text")
    assert k["content"].strip() in content, "Loaded Skill body mismatch: " + k["id"]
    checks.append(
        {
            "id": k["id"],
            "sha256": hashlib.sha256(k["content"].encode()).hexdigest(),
            "session": sid,
            "seconds": time.monotonic() - start,
            "nativeDiscovery": "PASS",
            "nativeLoad": "PASS",
            "instructionRetention": "PASS",
            "permissionBoundary": "PASS",
            "workflowExecution": "NOT_TESTED",
            "volatileRuntimeDiagnostics": k["id"] == "report",
            "tokens": "UNAVAILABLE_CPU_MOCK",
        }
    )
    if len(checks) % 10 == 0:
        atomic(root / "existing-skills/native-load-progress.json", {"completed": len(checks), "total": len(inventory)})
with sqlite3.connect("file:" + str(database) + "?mode=ro", uri=True) as db:
    states = [json.loads(v) for v, in db.execute("select value from kv where key like ?", ("%optimisation/v1/%",))]
assert any(
    s.get("scope", {}).get("repository") == "/workspace" and {k["id"] for k in inventory} <= set(s["skills"])
    for s in states
), "Native optimiser inventory missed filesystem Skills"
tracked = next(
    s
    for s in states
    if s.get("scope", {}).get("repository") == "/workspace" and s.get("scope", {}).get("agent") == "learning-fixture"
)
assert all(
    tracked["skills"][k["id"]].get("metrics", {}).get("loads", 0) >= 1 for k in inventory
), "Every native Skill load must retain its usage counter"
report = {
    "status": "PASS",
    "scope": "Native discovery, parsing, load, body preservation and execute-denied permission baseline; not Skill-specific workflow effectiveness",
    "count": len(checks),
    "checks": checks,
    "existingRevisionsPromoted": 0,
}
atomic(root / "existing-skills/native-load-baseline.json", report)
print(json.dumps({"status": "PASS", "count": len(checks), "scope": report["scope"]}))
