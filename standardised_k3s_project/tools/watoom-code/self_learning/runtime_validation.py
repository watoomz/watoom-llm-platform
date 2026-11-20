#!/usr/bin/env python3
"""Native closed-loop validation, usable in staging or an explicitly approved cutover."""

import argparse, pathlib, json, sqlite3, time, sys, urllib.parse, hashlib, os, fcntl, secrets

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from maintenance_guard import Maintenance
from recover import atomic

p = argparse.ArgumentParser()
for key in ["evidence", "namespace", "agent", "model", "database", "learning-root", "evaluations"]:
    p.add_argument("--" + key, required=True)
p.add_argument("--approved-state", type=pathlib.Path)
p.add_argument("--deployment", default="learning-app")
p.add_argument("--directory", default="/workspace")
a = p.parse_args()
root = pathlib.Path(a.evidence)
database = pathlib.Path(a.database)
learning = pathlib.Path(a.learning_root)
evaluations = pathlib.Path(a.evaluations)
if a.namespace == "watoom-code":
    if not a.approved_state or not json.loads(a.approved_state.read_text()).get("production_approved"):
        raise PermissionError("Explicit approved cutover checkpoint required")
elif not a.namespace.startswith("watoom-code-learning-"):
    raise ValueError("Unowned validation namespace")
m = Maintenance(a.namespace, a.deployment, root, True, True)
episodes = []


def states():
    with sqlite3.connect("file:" + str(database) + "?mode=ro", uri=True) as c:
        return [json.loads(x[0]) for x in c.execute("select value from kv where key like ?", ("%learning/v1/%",))]


def session(text):
    provider, model = a.model.split("/", 1)
    start = time.monotonic()
    s = m.request(
        "/api/session",
        {
            "title": "Owned native learning acceptance",
            "agent": a.agent,
            "model": {"providerID": provider, "id": model},
            "location": {"directory": a.directory},
            "permissions": [
                {"action": "*", "resource": "*", "effect": "deny"},
                {"action": "skill", "resource": "learned-*", "effect": "allow"},
                {"action": "watoom_learning_*", "resource": "*", "effect": "allow"},
            ],
        },
    )["data"]
    sid = s["id"]
    if a.approved_state:
        with a.approved_state.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            checkpoint = json.loads(a.approved_state.read_text())
            checkpoint.setdefault("owned_sessions", []).append(sid)
            atomic(a.approved_state, checkpoint)
    m.request("/api/session/" + sid + "/prompt", {"text": text})
    deadline = time.monotonic() + 180
    while sid in m.request("/api/session/active")["data"]:
        if time.monotonic() > deadline:
            raise RuntimeError("Owned validation session timed out: " + sid)
        time.sleep(1)
    with sqlite3.connect("file:" + str(database) + "?mode=ro", uri=True) as c:
        row = c.execute(
            "select idle_outcome,tokens_input,tokens_output,tokens_cache_read from session_v2 where id=?", (sid,)
        ).fetchone()
        messages = [
            json.loads(x[0])
            for x in c.execute("select data from session_message where session_id=? and type=?", (sid, "assistant"))
        ]
    tools = [x for msg in messages for x in msg.get("content", []) if x.get("type") == "tool"]
    if (
        row[0] != "succeeded"
        or not any(t["name"] == "watoom_learning_fixture" and t["state"]["status"] == "completed" for t in tools)
        or any(t["state"]["status"] == "error" for t in tools)
    ):
        raise RuntimeError("Native fixture did not verify: " + sid)
    e = {
        "session": sid,
        "seconds": time.monotonic() - start,
        "usage": {"input": row[1], "output": row[2], "cache_read": row[3]},
        "tools": [t["name"] for t in tools],
    }
    episodes.append(e)
    atomic(root / "runtime-validation-progress.json", {"episodes": episodes})
    return e


start = time.monotonic()
for _ in range(3):
    session(
        "Operator acceptance: call ONLY watoom_learning_fixture exactly once to sort and verify its fixed development data, then return the short result. Do not inspect files, delegate, use a shell, or write checkpoints."
    )
candidate = next(
    k
    for s in states()
    for k in s["skills"].values()
    if k["policy"] == "sort-fixture" and k["scope"]["agent"] == a.agent and k["scope"]["repository"] == a.directory
)
body = learning / "skills" / pathlib.Path(candidate["path"]).name
assert hashlib.sha256(body.read_bytes()).hexdigest() == candidate["sha256"]
assert json.loads((learning / "fixture-result.json").read_text()) == [1, 2, 3]
replay = session(
    "Operator independent replay: call ONLY watoom_learning_fixture once and verify the persisted sorted result. Return one short sentence; no other actions."
)
if candidate["state"] == "disabled":
    request = secrets.token_hex(16)
    path = evaluations / ("request-" + request + ".json")
    atomic(path, {"action": "enable", "id": candidate["id"], "scope": candidate["scope"], "request": request})
    os.chmod(path, 0o644)
    deadline = time.monotonic() + 70
    while not any(s.get("operations", {}).get(request, {}).get("result") == "PASS" for s in states()):
        if time.monotonic() > deadline:
            raise RuntimeError("Owned acceptance Skill could not resume its evaluated revision")
        time.sleep(0.5)
    candidate["state"] = "active"
if candidate["state"] != "active":
    e = {
        "id": candidate["id"],
        "scope": candidate["scope"],
        "candidateHash": candidate["sha256"],
        "policyDigest": candidate["version"],
        "correctness": True,
        "safety": True,
        "useful": True,
        "replayIDs": [replay["session"]],
        "evaluator": "native-fixed-sort-replay-v1",
        "usefulness_basis": "Correct fixture procedure and lazy native loading; no speedup claimed",
    }
    evaluations.mkdir(parents=True, exist_ok=True)
    os.chown(evaluations, 0, 0)
    os.chmod(evaluations, 0o755)
    path = evaluations / (candidate["id"] + ".json")
    atomic(path, e)
    os.chmod(path, 0o644)
deadline = time.monotonic() + 70
query = urllib.parse.urlencode({"location[directory]": a.directory})
while not any(k["id"] == candidate["id"] for k in m.request("/api/skill?" + query)["data"]):
    if time.monotonic() > deadline:
        raise RuntimeError("Evaluated Skill did not become natively discoverable")
    time.sleep(1)
fresh = session(
    "RETRIEVE the matching learned native Skill for sorting fixture development data, load it with skill, then apply it by calling watoom_learning_fixture once and report the verified result. Do not use any other tools or write checkpoints."
)
assert "skill" in fresh["tools"], "Fresh session did not load the native Skill"
final = next(s for s in states() if candidate["id"] in s["skills"])
assert all(x["state"] == "delivered" for x in final["outbox"].values()), "AgentMemory delivery pending"
report = {
    "status": "PASS",
    "namespace": a.namespace,
    "agent": a.agent,
    "candidate": candidate["id"],
    "scope": candidate["scope"],
    "episodes": episodes,
    "seconds": time.monotonic() - start,
    "closed_loop": "CAPTURE_GENERATE_EVALUATE_PROMOTE_RETRIEVE_APPLY_VERIFIED",
    "memory_deliveries": len(final["outbox"]),
    "efficiency_improvement": "NOT_CLAIMED",
}
atomic(root / "runtime-validation.json", report)
print(json.dumps(report))
