#!/usr/bin/env python3
"""Operator actions consumed by the existing native plugin; never edits its database."""

import argparse, pathlib, sqlite3, json, secrets, os

p = argparse.ArgumentParser()
p.add_argument("--evidence", type=pathlib.Path, required=True)
p.add_argument("--action", choices=["list", "enable", "disable", "rollback"], default="list")
p.add_argument("--id")
p.add_argument("--runtime", choices=["staging", "production"], default="staging")
a = p.parse_args()
root = a.evidence.resolve()
stage = root / "staging"
plan = json.loads((root / "production/plan.json").read_text()) if a.runtime == "production" else None
database = pathlib.Path("/data/ai/watoom-code/application.sqlite") if plan else stage / "state/application.sqlite"
evaluations = pathlib.Path(plan["evaluations"]) if plan else stage / "evaluations"
if not str(root).startswith("/data/ai/helper-scripts/watoom-self-learning-"):
    raise ValueError("Dedicated evidence root required")
with sqlite3.connect("file:" + str(database) + "?mode=ro", uri=True) as db:
    states = [json.loads(x[0]) for x in db.execute("select value from kv where key like ?", ("%learning/v1/%",))]
skills = [k for s in states for k in s["skills"].values()]
if a.action == "list":
    print(
        json.dumps(
            {
                "skills": skills,
                "operations": [op for s in states for op in s.get("operations", {}).values()],
                "archives": [entry for s in states for entry in s.get("archives", [])],
            },
            indent=2,
        )
    )
    raise SystemExit()
if os.geteuid() != 0:
    raise PermissionError("Operator-owned action files require administrative execution")
k = next((k for k in skills if k["id"] == a.id), None)
if not k:
    raise ValueError("Exact existing Skill ID required")
request = secrets.token_hex(16)
out = evaluations / ("request-" + request + ".json")
value = {"action": a.action, "id": a.id, "scope": k["scope"], "request": request}
with out.open("x") as f:
    json.dump(value, f, indent=2)
    f.flush()
    os.fsync(f.fileno())
os.chmod(out, 0o644)
print(
    json.dumps(
        {
            "queued": a.action,
            "id": a.id,
            "request": request,
            "mechanism": "native deterministic curator, maximum 30s in acceptance staging",
        }
    )
)
