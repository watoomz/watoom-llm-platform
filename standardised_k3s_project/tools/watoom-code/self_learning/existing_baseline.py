#!/usr/bin/env python3
"""Read-only census and privacy-preserving historical usage baseline. No task execution."""

import argparse, pathlib, json, sqlite3, hashlib, sys, time, subprocess, os

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from maintenance_guard import Maintenance
from recover import atomic

p = argparse.ArgumentParser()
p.add_argument("--evidence", type=pathlib.Path, required=True)
p.add_argument("--namespace", default="watoom-code")
p.add_argument("--deployment", default="watoom-code")
p.add_argument("--database", type=pathlib.Path, default=pathlib.Path("/data/ai/watoom-code/application.sqlite"))
p.add_argument("--directory", default="/workspace")
a = p.parse_args()
import urllib.parse

out = a.evidence / "existing-skills"
out.mkdir(exist_ok=True, mode=0o700)
os.chmod(out, 0o700)
m = Maintenance(a.namespace, a.deployment, out, True, True)
inventory = m.request("/api/skill?" + urllib.parse.urlencode({"location[directory]": a.directory}))
atomic(out / "native-inventory.json", inventory)
skills = {
    k["id"]: {
        "id": k["id"],
        "path": k["path"],
        "sha256": hashlib.sha256(k["content"].encode()).hexdigest(),
        "bytes": len(k["content"].encode()),
        "loads": 0,
        "failedLoads": 0,
        "attempts": 0,
        "failedAttempts": 0,
        "repeatedCommands": 0,
        "sessionInputTokens": 0,
        "sessionOutputTokens": 0,
        "cacheReadTokens": 0,
        "reportedCost": 0,
        "verifiedCorrections": 0,
        "workflowBaseline": "TASK_TESTS_REQUIRED",
        "costAttribution": "Shared loaded-session totals; overlapping Skills are not additive; reported zero cost does not prove free inference",
    }
    for k in inventory["data"]
}
c = sqlite3.connect("file:" + str(a.database) + "?mode=ro", uri=True)
c.execute("pragma query_only=ON")
sessions = {}
seen = set()
for mid, sid, data in c.execute(
    "select id,session_id,data from session_message where type='assistant' order by session_id,seq"
):
    msg = json.loads(data)
    session = sessions.setdefault(sid, {"loaded": set(), "calls": set()})
    for t in msg.get("content", []):
        if t.get("type") != "tool":
            continue
        state = t.get("state", {})
        args = t.get("input", state.get("input", {}))
        name = t.get("name")
        eid = (mid, t.get("id"))
        if eid in seen:
            continue
        seen.add(eid)
        ok = state.get("status") == "completed"
        result = state.get("result", state)
        ok = ok and result.get("isError") is not True and not result.get("metadata", {}).get("exit", 0)
        if name == "skill":
            k = skills.get(args.get("id"))
            if k:
                k["loads" if ok else "failedLoads"] += 1
                session["loaded"].add(k["id"]) if ok else None
            continue
        sig = hashlib.sha256(json.dumps([name, args], sort_keys=True).encode()).hexdigest()
        for kid in session["loaded"]:
            k = skills[kid]
            k["attempts"] += 1
            k["failedAttempts"] += int(not ok)
            k["repeatedCommands"] += int(sig in session["calls"])
        session["calls"].add(sig)
for sid, data in sessions.items():
    if not data["loaded"]:
        continue
    row = c.execute(
        "select tokens_input,tokens_output,tokens_cache_read,cost from session_v2 where id=?", (sid,)
    ).fetchone()
    if row:
        for kid in data["loaded"]:
            for key, value in zip(
                ["sessionInputTokens", "sessionOutputTokens", "cacheReadTokens", "reportedCost"], row
            ):
                skills[kid][key] += value or 0
c.close()
for k in skills.values():
    k["priority"] = k["loads"] + 5 * k["failedAttempts"] + 2 * k["repeatedCommands"] + k["sessionInputTokens"] / 1000
report = {
    "time": time.time(),
    "status": "INVENTORY_COMPLETE_WORKFLOW_BASELINES_PENDING",
    "count": len(skills),
    "namespace": a.namespace,
    "directory": a.directory,
    "skills": sorted(skills.values(), key=lambda k: (-k["priority"], k["id"])),
    "verifiedCorrectionPolicy": "Only independent verifier receipts may label successful corrections; historical tool completion is insufficient",
    "sessionAccounting": "Full session totals shared with all loaded Skills; not marginal or causal Skill token cost",
    "sources": ["authenticated native Skill API", "read-only native application.sqlite"],
}
atomic(out / "baseline.json", report)
print(
    json.dumps(
        {
            "count": len(skills),
            "loaded": sum(k["loads"] > 0 for k in skills.values()),
            "top": [
                {
                    "id": k["id"],
                    "loads": k["loads"],
                    "failedAttempts": k["failedAttempts"],
                    "repeatedCommands": k["repeatedCommands"],
                    "sharedInputTokens": k["sessionInputTokens"],
                }
                for k in report["skills"][:8]
            ],
            "status": report["status"],
        }
    )
)
