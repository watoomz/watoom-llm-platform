#!/usr/bin/env python3
"""Additive project-local canary activation, checksum guarded reversible rollback."""

import pathlib, argparse, json, hashlib, datetime, shutil, sys

p = argparse.ArgumentParser()
p.add_argument("--root", required=True)
p.add_argument("--audit-report", required=True)
p.add_argument("--dry-run", action="store_true")
p.add_argument("--rollback", action="store_true")
p.add_argument("--snapshot")
p.add_argument("--i-approve", action="store_true")
p.add_argument("--test-failure", action="store_true")
a = p.parse_args()
r = pathlib.Path(a.root).resolve()
audit = json.loads(pathlib.Path(a.audit_report).read_text())
if not r.is_relative_to(pathlib.Path("/data/ai/assets/generated/blender-asset-builder")):
    p.error("target outside versioned builder project")
if a.test_failure and r.name != "rollback-fixture":
    p.error("failure injection is restricted to disposable rollback-fixture")
if not any(x["id"] in ["CANARY-SKILL", "BLENDER-VERSION"] for x in audit["checks"]):
    p.error("no relevant runtime audit check IDs")
dest = r / "opencode.json"
content = json.dumps({"skills": ["./.opencode/skills"]}, indent=2) + "\n"
if a.dry_run:
    print(
        json.dumps(
            {
                "action": "rollback" if a.rollback else "project-local activation",
                "target": str(dest),
                "no_production_cutover": True,
            }
        )
    )
    sys.exit(0)
if a.rollback:
    if not a.i_approve:
        sys.exit("RISK: rollback replaces project-local configuration; refusing without --i-approve")
    s = pathlib.Path(a.snapshot).resolve()
    m = json.loads((s / "snapshot.json").read_text())
    assert m["target"] == str(dest)
    assert hashlib.sha256(dest.read_bytes()).hexdigest() == m["installed_sha256"], "configuration changed; preserve it"
    dest.rename(s / "displaced.json")
    if m["prior_exists"]:
        shutil.copy2(s / "prior.json", dest)
    print("PASS rollback; displaced configuration retained")
    sys.exit(0)
if dest.exists() and json.loads(dest.read_text()) == {"skills": ["./.opencode/skills"]}:
    print("PASS already activated (idempotent)")
    sys.exit(0)
if dest.exists():
    sys.exit("BLOCKED: existing project configuration differs; preserve it")
s = r / "reports" / ("canary-snapshot-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
s.mkdir()
m = {"target": str(dest), "prior_exists": False, "installed_sha256": hashlib.sha256(content.encode()).hexdigest()}
try:
    dest.write_text(content)
    if a.test_failure:
        raise RuntimeError("intentional disposable validation failure")
    assert json.loads(dest.read_text())["skills"] == ["./.opencode/skills"]
    (s / "snapshot.json").write_text(json.dumps(m, indent=2))
    print("PASS snapshot=" + str(s))
except Exception:
    if dest.exists():
        dest.rename(s / "failed.json")
    raise
