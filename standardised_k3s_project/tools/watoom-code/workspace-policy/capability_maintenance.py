#!/usr/bin/env python3
"""Bounded read-only health refresh over existing native catalogue and learning stores.
No model calls, engine jobs, source updates, package promotion or cleanup.
"""

import argparse, pathlib, json, sqlite3, hashlib, fcntl, os, tempfile, sys, datetime


def summary(catalog, app):
    tables = {x[0] for x in catalog.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    review = "_watoom_skill_review" in tables
    counts = dict(
        zip(
            ["discovered", "structurally_valid"],
            catalog.execute("SELECT count(*),coalesce(sum(validation='valid'),0) FROM skills").fetchone(),
        )
    )
    counts["enabled"] = catalog.execute("SELECT count(*) FROM approvals").fetchone()[0]
    joins = (
        "LEFT JOIN _watoom_skill_review r ON r.skill_id=s.id"
        if review
        else "LEFT JOIN (SELECT NULL skill_id,NULL content_sha,NULL revision,NULL state) r ON 1=0"
    )
    stale = catalog.execute(
        "SELECT s.id FROM skills s JOIN approvals a ON a.skill_id=s.id LEFT JOIN sources src ON src.repo=s.repo LEFT JOIN approval_context ac ON ac.skill_id=s.id "
        + joins
        + " WHERE a.approved_sha<>COALESCE(r.content_sha,s.sha256) OR src.commit_sha IS NULL OR ac.commit_sha IS NULL OR ac.commit_sha<>COALESCE(r.revision,src.commit_sha) OR (r.state IS NOT NULL AND r.state<>'ENABLED') LIMIT 64"
    ).fetchall()
    duplicates = catalog.execute(
        "SELECT sha256,count(*) FROM skills GROUP BY sha256 HAVING count(*)>1 ORDER BY count(*) DESC LIMIT 32"
    ).fetchall()
    learning = {
        "scopes": 0,
        "verified_events": 0,
        "rejected_events": 0,
        "delivered_memories": 0,
        "candidates": 0,
        "active_recipes": 0,
        "uncertain_deliveries": 0,
    }
    for key, raw in app.execute("SELECT key,value FROM kv WHERE key LIKE '%:learning/v1/%'"):
        state = json.loads(raw)
        learning["scopes"] += 1
        learning["verified_events"] += sum(x.get("status") == "VERIFIED" for x in state.get("events", {}).values())
        learning["rejected_events"] += sum(x.get("status") == "REJECTED" for x in state.get("events", {}).values())
        learning["delivered_memories"] += sum(x.get("state") == "delivered" for x in state.get("outbox", {}).values())
        learning["uncertain_deliveries"] += sum(
            x.get("state") in ["sending", "uncertain"] for x in state.get("outbox", {}).values()
        )
        learning["candidates"] += sum(x.get("state") == "candidate" for x in state.get("skills", {}).values())
        learning["active_recipes"] += sum(x.get("state") == "active" for x in state.get("skills", {}).values())
    return {
        "skills": counts,
        "staleApprovalReferences": [x[0] for x in stale],
        "duplicateContentGroups": [{"sha256": x[0], "entries": x[1]} for x in duplicates],
        "learning": learning,
        "classification": "metadata and structural evidence only; native receipts/evaluators establish execution success",
        "actions": {
            "updates": "versioned candidate only; existing owner review and evaluation required",
            "cleanup": "DEFERRED by owner; no artifacts or records removed",
            "promotion": "unchanged; existing self-learning validation and native idle gates remain authoritative",
        },
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--iac-root", required=True, type=pathlib.Path)
    p.add_argument("--output", type=pathlib.Path, default=pathlib.Path("/data/ai/watoom-code/capability-maintenance"))
    a = p.parse_args()
    a.output.mkdir(exist_ok=True, mode=0o755)
    with (a.output / "refresh.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        catalog = sqlite3.connect("file:/data/ai/watoom-code/catalog.sqlite?mode=ro", uri=True, timeout=3)
        app = sqlite3.connect("file:/data/ai/watoom-code/application.sqlite?mode=ro", uri=True, timeout=3)
        result = summary(catalog, app)
        catalog.close()
        app.close()
        trusted = pathlib.Path(__file__).parent / "native"
        assert trusted.stat().st_uid == 0 and not trusted.stat().st_mode & 0o022
        sys.path.insert(0, str(trusted))
        from maintenance_guard import Maintenance

        m = Maintenance("watoom-code", "watoom-code", a.output, True, True)
        native = m.request("/api/skill/index?location%5Bdirectory%5D=/data/ai/projects/homelab/homelab-llm")["data"]
        memory = m.request("/api/memory/status?location%5Bdirectory%5D=/data/ai/projects/homelab/homelab-llm")["data"]
        from lesson_audit import audit

        config = json.loads(pathlib.Path("/data/ai/watoom-code/config/opencode.json").read_text())
        policies = []
        for entry in config.get("plugins", []):
            if isinstance(entry, dict) and "self-learning-" in entry.get("package", ""):
                policies.extend(entry.get("options", {}).get("policies", []))
        result["lessonAudit"] = audit(policies)
        result.update(
            {
                "schema": 1,
                "sampledAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "nativeSkills": native["catalogueSize"],
                "pipelines": sum(x["kind"] == "pipeline" for x in native["entries"]),
                "memoryEnabled": memory["memory"]["enabled"],
                "memoryRequired": memory["memory"]["required"],
                "ownershipAvailable": memory["ownership"]["available"],
                "sources": [
                    "native /api/skill/index",
                    "native /api/memory/status",
                    "existing catalog.sqlite",
                    "existing native learning KV",
                ],
                "selectionInterface": "existing authenticated Skills UI and watoom_skill_search; this report is not another catalogue or execution authority",
            }
        )
        raw = (json.dumps(result, indent=2) + "\n").encode()
        fd, tmp = tempfile.mkstemp(dir=a.output, prefix=".health-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
                os.fchmod(f.fileno(), 0o644)
            os.replace(tmp, a.output / "health.json")
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "nativeSkills": result["nativeSkills"],
                    "pipelines": result["pipelines"],
                    "learning": result["learning"],
                    "staleApprovalReferences": len(result["staleApprovalReferences"]),
                }
            )
        )


if __name__ == "__main__":
    main()
