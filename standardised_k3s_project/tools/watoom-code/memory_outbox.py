#!/usr/bin/env python3
"""Operator reconciliation of stranded native AgentMemory outbox items.

The native client marks an item `uncertain` after an ambiguous acknowledgment and only
ever re-checks the first 32 by rowid; it has no path back to `pending`. This tool applies
the client's own verification (search AgentMemory by id, accept only a narrative that is
the exact stored envelope) to every stranded item:

  found          -> observed, with a receipt in the client's format
  absent (twice) -> pending, so native delivery re-sends it

Absence is proven by two independent searches (id and digest) before an item is
re-queued, so a re-send cannot duplicate a stored memory. Read-only unless --apply.
"""
import argparse, base64, json, pathlib, re, sqlite3, subprocess, sys, time, urllib.request

DB = pathlib.Path("/data/ai/watoom-code/application.sqlite")
NS = "watoom-code"
MEMORY_ID = re.compile(r"^[A-Za-z0-9._:-]{1,512}$")

def canonical_scope(scope):
    return json.dumps([scope["project"], scope["repository"], scope["agent"]], separators=(",", ":"))

def envelope(row):
    body = json.loads(row["body"])
    if body.get("version") != 2 or body.get("id") != row["id"] or body.get("digest") != row["digest"] \
            or canonical_scope(body["scope"]) != row["scope"] or body.get("job") != row["job"] or body.get("seq") != row["seq"]:
        raise ValueError("outbox integrity failure: " + row["id"])
    return body

def match(body, results):
    """The receipt for the stored envelope among search results, else None (client's reconcile rule)."""
    for result in (results or [])[:16]:
        try:
            obs = result["observation"]
            narrative, memory_id = obs["narrative"], obs["id"]
            if not isinstance(narrative, str) or len(narrative.encode()) > 12288 or not isinstance(memory_id, str) or not MEMORY_ID.match(memory_id):
                continue
            if json.loads(narrative) != body:
                continue
            return {"id": body["id"], "digest": body["digest"], "scope": body["scope"], "memoryId": memory_id, "durability": "observed"}
        except (KeyError, TypeError, ValueError):
            continue
    return None

def classify(body, search):
    scope = body["scope"]
    for query in (body["id"], body["digest"]):
        response = search({"query": query, "project": scope["project"], "agentId": scope["agent"], "limit": 16, "format": "full"})
        if not isinstance(response.get("results"), list):
            raise ValueError("invalid search response")
        receipt = match(body, response["results"])
        if receipt:
            return "found", receipt
    return "absent", None

def candidates(db, sending_older_ms, now_ms):
    db.row_factory = sqlite3.Row
    return db.execute("SELECT * FROM _watoom_outbox WHERE state='uncertain' OR (state='sending' AND time_attempted<?) ORDER BY rowid",
                      (now_ms - sending_older_ms,)).fetchall()

def apply(db, row, outcome, receipt, now_ms):
    """One guarded transaction per item; a row the client changed meanwhile is left alone."""
    with db:
        db.execute("BEGIN IMMEDIATE")
        if outcome == "found":
            cur = db.execute("UPDATE _watoom_outbox SET state='observed',receipt=?,last_error=NULL,time_observed=? WHERE id=? AND state=? AND digest=?",
                             (json.dumps(receipt, separators=(",", ":")), now_ms, row["id"], row["state"], row["digest"]))
        else:
            cur = db.execute("UPDATE _watoom_outbox SET state='pending',last_error=NULL WHERE id=? AND state=? AND digest=?",
                             (row["id"], row["state"], row["digest"]))
        return cur.rowcount == 1

def http_search():
    def kub(*args):
        return json.loads(subprocess.check_output(["kubectl", "-n", NS, *args, "-o", "json"]))
    env = next(c for c in kub("get", "deploy", "watoom-code")["spec"]["template"]["spec"]["containers"] if c["name"] == "app")["env"]
    ref = next(x for x in env if x["name"] == "AGENTMEMORY_SECRET")["valueFrom"]["secretKeyRef"]
    secret = base64.b64decode(kub("get", "secret", ref["name"])["data"][ref["key"]]).decode()
    url = "http://%s:3111/agentmemory/search" % kub("get", "svc", "agentmemory")["spec"]["clusterIP"]
    def search(body):
        req = urllib.request.Request(url, data=json.dumps({**body, "token_budget": 4096}).encode(),
                                     headers={"content-type": "application/json", "authorization": "Bearer " + secret})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)
    return search

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--evidence", required=True, type=pathlib.Path)
    p.add_argument("--sending-older-than-hours", type=float, default=24)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--i-approve", action="store_true")
    a = p.parse_args()
    if a.apply and not a.i_approve:
        sys.exit("BLOCKED: --apply requires --i-approve")
    import release_guard
    out = a.evidence.resolve(); out.mkdir(mode=0o700, parents=True, exist_ok=False)
    search, now = http_search(), int(time.time() * 1000)
    with sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=5) as ro:
        rows = candidates(ro, int(a.sending_older_than_hours * 3600_000), now)
    plan, errors = [], []
    for row in rows:
        try:
            outcome, receipt = classify(envelope(row), search)
            plan.append((row, outcome, receipt))
        except Exception as error:
            errors.append({"id": row["id"], "error": str(error)[:200]})
    report = {"candidates": len(rows), "found": sum(o == "found" for _, o, _ in plan),
              "absent": sum(o == "absent" for _, o, _ in plan), "errors": errors,
              "items": [{"id": r["id"], "state": r["state"], "job": r["job"], "seq": r["seq"], "outcome": o} for r, o, _ in plan]}
    if a.apply:
        if errors:
            sys.exit("BLOCKED: %d items could not be verified; nothing changed" % len(errors))
        release_guard.snapshot_database(DB, out / "application-before.private.sqlite")
        (out / "application-before.private.sqlite").chmod(0o600)
        with sqlite3.connect(DB, timeout=10, isolation_level=None) as db:
            db.row_factory = sqlite3.Row
            report["applied"] = sum(apply(db, r, o, rc, int(time.time() * 1000)) for r, o, rc in plan)
        report["skipped_concurrent"] = len(plan) - report["applied"]
    (out / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "items"}, indent=2))

if __name__ == "__main__":
    main()
