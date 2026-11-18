#!/usr/bin/env python3
"""Phases 3-4 of the learning loop: a deterministic, GPU-free memory curator (docs/proposals/learning-loop-design.md).

It keeps a *sidecar* lesson store, separate from the live AgentMemory semantic store, so curation can never
corrupt curated memory and can be reset on its own. Three lesson kinds are kept apart — semantic (facts),
episodic (incidents), procedural (how-to rules). The owner chose auto-improve with a way to roll back or
fix; this tool delivers that for the reversible lesson layer only:

- `curate` mines the owner's own corrections — human commits over paths the agent authored, within a window —
  and turns each into a procedural lesson (the diff is the evidence). Chat lines the owner marks with the lesson marker
  ("+ never do X") in the WatooM-Code chat become procedural lessons the same way (`--chat-db`, read-only). It also ingests verification-loop
  failures as episodic incidents. New lessons are auto-applied, but ONLY to this sidecar.
- Every write is wrapped in a journalled transaction; `rollback --txn <id>` reverts it exactly.
- A kill-switch file (`<root>/curator-disabled`) makes curate/apply a no-op.
- `recall` returns active lessons and bumps their usage counters; the staleness pass flags lessons that go
  unused or stop validating (they are retired, never hard-deleted, so they can be restored).

It never edits code, the harness, the coordinator guard, or AgentMemory itself; those stay owner-gated.
No LLM or GPU is used. Verdicts about whether a derived rule is safe come from the phase-2 graders
(verification_loop.py), never from a model's self-report.
"""
import argparse
import hashlib
import json
import os
import pathlib
import re
import secrets
import sqlite3
import subprocess
import time

# Identities that count as the agent/operator (the WatooM-Code models and Claude Code all commit as codex);
# an owner fix is a commit by the owner over a path one of these authored.
AGENT_EMAILS = ("codex@agent.example", "codex@agent.example", "codex@localhost")
OWNER_EMAILS = ("garthcordery@gmail.com",)
KINDS = ("semantic", "episodic", "procedural")
STALE_UNUSED_DAYS = 90
NOW = lambda: int(time.time())


def connect(store):
    store.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(store), isolation_level=None)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS lessons(
        id INTEGER PRIMARY KEY, kind TEXT NOT NULL, key TEXT UNIQUE NOT NULL, problem TEXT NOT NULL,
        fix TEXT NOT NULL, evidence_sha TEXT NOT NULL, source TEXT NOT NULL, status TEXT NOT NULL,
        times_helped INTEGER NOT NULL DEFAULT 0, created_utc INTEGER NOT NULL,
        last_validated_utc INTEGER, last_used_utc INTEGER)""")
    if "meta" not in [r[1] for r in db.execute("PRAGMA table_info(lessons)")]:
        db.execute("ALTER TABLE lessons ADD COLUMN meta TEXT")  # structured facts (engine, class, member) for recall
    db.execute("""CREATE TABLE IF NOT EXISTS journal(
        txn TEXT NOT NULL, utc INTEGER NOT NULL, op TEXT NOT NULL, lesson_key TEXT NOT NULL,
        before_json TEXT, after_json TEXT)""")
    return db


def disabled(root):
    return (root / "curator-disabled").exists()


def row(db, key):
    cur = db.execute("SELECT id,kind,key,problem,fix,evidence_sha,source,status,times_helped,created_utc,last_validated_utc,last_used_utc,meta FROM lessons WHERE key=?", (key,))
    cols = [c[0] for c in cur.description]
    r = cur.fetchone()
    return dict(zip(cols, r)) if r else None


def record(db, txn, op, key, before, after):
    db.execute("INSERT INTO journal(txn,utc,op,lesson_key,before_json,after_json) VALUES(?,?,?,?,?,?)",
               (txn, NOW(), op, key, json.dumps(before) if before else None, json.dumps(after) if after else None))


def upsert(db, txn, lesson):
    """Insert a new lesson, or refresh evidence on an existing key; journalled. Returns 'inserted'|'exists'."""
    before = row(db, lesson["key"])
    if before:
        return "exists"
    db.execute("INSERT INTO lessons(kind,key,problem,fix,evidence_sha,source,status,times_helped,created_utc,last_validated_utc,last_used_utc,meta) VALUES(?,?,?,?,?,?,?,0,?,?,NULL,?)",
               (lesson["kind"], lesson["key"], lesson["problem"], lesson["fix"], lesson["evidence_sha"],
                lesson["source"], lesson["status"], NOW(), lesson.get("last_validated_utc"),
                json.dumps(lesson["meta"], sort_keys=True) if lesson.get("meta") else None))
    record(db, txn, "insert", lesson["key"], None, lesson)
    return "inserted"


def set_status(db, txn, key, status):
    before = row(db, key)
    if not before or before["status"] == status:
        return False
    db.execute("UPDATE lessons SET status=? WHERE key=?", (status, key))
    after = dict(before, status=status)
    record(db, txn, "status", key, before, after)
    return True


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), "-c", "safe.directory=" + str(repo), *args],
                                   text=True, stderr=subprocess.DEVNULL)


def owner_fix_lessons(repo, owner_emails, agent_emails, since_days, max_commits=200, max_files=40):
    """Owner commits over agent-authored files in the window become procedural lessons; the diff is the evidence."""
    lessons = []
    since = "--since=%d.days.ago" % since_days
    log = git(repo, "log", since, "--no-merges", "--format=%H%x09%ae").strip().splitlines()
    for line in log[:max_commits]:
        sha, email = (line.split("\t", 1) + [""])[:2]
        if email not in owner_emails:
            continue  # only the owner's own hand-edits
        files = [f for f in git(repo, "show", "--name-only", "--format=", sha).splitlines() if f.strip()][:max_files]
        for path in files:
            # Was this path ever touched by an agent commit? If so, the owner revised the agent's work.
            authored = git(repo, "log", "--format=%ae", "--", path).splitlines()
            if not any(a in agent_emails for a in authored):
                continue
            try:
                diff = git(repo, "diff", sha + "~1", sha, "--", path)
            except subprocess.CalledProcessError:
                diff = git(repo, "show", "--format=", sha, "--", path)  # root commit has no parent
            if not diff.strip():
                continue
            evidence_sha = hashlib.sha256(diff.encode()).hexdigest()
            lessons.append({
                "kind": "procedural", "key": hashlib.sha256((path + "|" + evidence_sha).encode()).hexdigest()[:32],
                "problem": "owner revised agent-authored %s (commit %s)" % (path, sha[:12]),
                "fix": diff[:8000], "evidence_sha": evidence_sha, "source": "owner-fix:" + sha[:12],
                "status": "active", "last_validated_utc": NOW(),  # owner's own edit: trusted on ingest
            })
    return lessons


# An owner chat line becomes a lesson only when the owner marks it: a line that starts with the lesson marker
# (default "+", never used to start a line in the owner's chat history; "#" and "-" are markdown). Deliberate and
# deterministic: no wording heuristics, no LLM. Text that looks like a credential is skipped, never stored.
LESSON_MARKER = "+"
CHAT_SENSITIVE = re.compile(r"-----BEGIN.*PRIVATE KEY|bearer\s+\S+|(?:password|api[_-]?key|secret|token|authorization)\s*[:=]\s*\S+|"
                            r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,})", re.I)
CHAT_MIN_CHARS, CHAT_MAX_CHARS = 8, 4000


def marked_lines(text, marker):
    """Lines of a message that start with the marker, marker and surrounding space removed."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(marker) and not line.startswith(marker * 2):
            body = line[len(marker):].strip()
            if len(body) >= CHAT_MIN_CHARS:
                out.append(body[:CHAT_MAX_CHARS])
    return out


def owner_chat_lessons(app_db, since_days, marker=LESSON_MARKER, max_messages=2000):
    """Lessons the owner marks in the WatooM-Code chat (a line starting with the marker) become procedural lessons.

    Only messages the owner typed in the GUI count: they carry metadata.displayText. System notices, compaction
    summaries and coordinator-to-child dispatch text have no displayText and are ignored. The application database
    is opened read-only."""
    path = pathlib.Path(app_db)
    if not marker or not path.is_file():
        return []
    db = sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=5)
    try:
        cutoff = (NOW() - since_days * 86400) * 1000
        rows = db.execute("SELECT m.id,m.session_id,m.data,s.title,s.agent FROM session_message m "
                          "LEFT JOIN session_v2 s ON s.id=m.session_id "
                          "WHERE m.type='user' AND m.time_created>=? ORDER BY m.time_created DESC LIMIT ?",
                          (cutoff, max_messages)).fetchall()
    finally:
        db.close()
    lessons, seen = [], set()
    for msg_id, session_id, data, title, agent in rows:
        try:
            meta = (json.loads(data).get("metadata") or {})
        except ValueError:
            continue
        for text in marked_lines(meta.get("displayText") or "", marker):
            if CHAT_SENSITIVE.search(text):
                continue
            evidence_sha = hashlib.sha256(text.encode()).hexdigest()
            if evidence_sha in seen:
                continue
            seen.add(evidence_sha)
            lessons.append({
                "kind": "procedural", "key": hashlib.sha256(("chat|" + evidence_sha).encode()).hexdigest()[:32],
                "problem": "owner lesson to %s in \"%s\"" % (meta.get("agent") or agent or "agent", (title or session_id)[:80]),
                "fix": text, "evidence_sha": evidence_sha, "source": "owner-chat:" + str(msg_id)[:24],
                "status": "active", "last_validated_utc": NOW(),  # the owner's own words: trusted on ingest
            })
    return lessons


# Engine API facts. A worker receipt's `errors` carry the engine's own words, so "Godot 4.7.2 rejected
# Class.member" is ground truth, not an agent's guess. Only engine classes count: script-defined bases
# ("Node3D (player.gd)"), Nil and built-in containers are the project's own bugs and are skipped.
ENGINE_ERRORS = (
    ("call", re.compile(r"Invalid call\. Nonexistent function '([^']+)' in base '([^']+)'")),
    ("call", re.compile(r"Function \"([^\"(]+)\(\)\" not found in base ([A-Za-z0-9_]+)")),
    ("get", re.compile(r"Invalid access to property or key '([^']+)' on a base object of type '([^']+)'")),
    ("set", re.compile(r"Invalid assignment of property or key '([^']+)' with value of type '([^']*)' on a base object of type '([^']+)'")),
)
NOT_ENGINE_CLASS = {"Nil", "Dictionary", "Array", "String", "StringName", "Object", "Variant", "int", "float", "bool"}
ENGINE_CLASS = re.compile(r"^[A-Z][A-Za-z0-9]+$")
VERSION_DIR = re.compile(r"^\d+\.\d+(?:\.\d+)?$")


def toolchain_version(toolchain_dir):
    """Newest numeric version directory of an installed engine toolchain, or None."""
    path = pathlib.Path(toolchain_dir) if toolchain_dir else None
    if not path or not path.is_dir():
        return None
    versions = sorted((d.name for d in path.iterdir() if d.is_dir() and VERSION_DIR.match(d.name)),
                      key=lambda v: tuple(int(x) for x in v.split(".")))
    return versions[-1] if versions else None


def toolchain_installed(toolchain_dir):
    """Install time (epoch seconds) of the newest engine version directory, else 0."""
    version = toolchain_version(toolchain_dir)
    return int((pathlib.Path(toolchain_dir) / version).stat().st_mtime) if version else 0


def parse_engine_error(message):
    """(kind, class, member, value_type) for an engine API rejection, else None."""
    for kind, rx in ENGINE_ERRORS:
        m = rx.search(message)
        if not m:
            continue
        if kind == "set":
            member, value_type, cls = m.group(1), m.group(2), m.group(3)
        else:
            member, cls, value_type = m.group(1), m.group(2), ""
        if cls in NOT_ENGINE_CLASS or not ENGINE_CLASS.match(cls) or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", member):
            return None
        return kind, cls, member, value_type
    return None


def engine_error_lessons(receipts_dir, engine, version, since_days, max_files=1000, not_before=0):
    """Engine API rejections found in worker receipts become semantic lessons keyed by engine, version, class and member."""
    root = pathlib.Path(receipts_dir) if receipts_dir else None
    if not root or not root.is_dir() or not version:
        return []
    cutoff = max(NOW() - since_days * 86400, not_before)  # never attribute pre-install receipts to this engine version
    files = sorted((f for f in root.glob("*.operator.log") if f.stat().st_mtime >= cutoff),
                   key=lambda f: f.stat().st_mtime, reverse=True)[:max_files]
    lessons, seen = [], set()
    for f in files:
        try:
            receipt = json.loads(f.read_text(errors="replace").splitlines()[0])
        except (ValueError, OSError, IndexError):
            continue
        errors = receipt.get("errors") or []
        if isinstance(errors, str):
            try:
                errors = json.loads(errors)
            except ValueError:
                errors = [errors]
        for message in errors if isinstance(errors, list) else []:
            parsed = parse_engine_error(str(message))
            if not parsed:
                continue
            kind, cls, member, value_type = parsed
            key = hashlib.sha256("|".join((engine, version, kind, cls, member)).encode()).hexdigest()[:32]
            if key in seen:
                continue
            seen.add(key)
            what = {"call": "has no method", "get": "has no property", "set": "rejected assignment to"}[kind]
            note = {"call": "That method does not exist on %s in this version." % cls,
                    "get": "That property does not exist on %s in this version." % cls,
                    "set": "Either %s has no such property in this version, or the value type '%s' is wrong for it." % (cls, value_type)}[kind]
            lessons.append({
                "kind": "semantic", "key": key,
                "problem": "%s %s: %s %s '%s'" % (engine, version, cls, what, member),
                "fix": "The %s %s engine reported: %s %s Check the class reference for this exact version before using it; "
                       "do not move the same name to another class." % (engine, version, str(message)[:300], note),
                "evidence_sha": hashlib.sha256(str(message).encode()).hexdigest(), "source": "engine-error:" + f.name[:24],
                "status": "active", "last_validated_utc": NOW(),  # the engine said so itself
                "meta": {"engine": engine, "version": version, "kind": kind, "class": cls, "member": member, "value_type": value_type},
            })
    return lessons


def export_recall(db, path, max_engine=200, max_owner=40):
    """Compact JSON of active lessons for the coordinator guard to show agents. Atomic, world-readable."""
    engine, owner = [], []
    for source, problem, fix, meta in db.execute(
            "SELECT source,problem,fix,meta FROM lessons WHERE status='active' ORDER BY created_utc DESC").fetchall():
        if meta and source.startswith("engine-error:") and len(engine) < max_engine:
            engine.append(dict(json.loads(meta), problem=problem))
        elif source.startswith("owner-chat:") and len(owner) < max_owner:
            owner.append({"problem": problem, "rule": fix[:600]})
    payload = {"version": 1, "generated_utc": NOW(), "engine": engine, "owner": owner}
    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1, sort_keys=True))
    tmp.chmod(0o644)
    try:  # match the directory's owner so the app container user (not just root) owns what it reads
        parent = target.parent.stat()
        os.chown(tmp, parent.st_uid, parent.st_gid)
    except (PermissionError, OSError):
        pass
    tmp.replace(target)
    return {"engine": len(engine), "owner": len(owner)}


def verification_incidents(evidence_root, max_files=200):
    """Each FAILED grader in a verification_loop evidence file becomes an episodic incident (pending until re-seen)."""
    lessons = []
    root = pathlib.Path(evidence_root)
    if not root.is_dir():
        return lessons
    for report_path in sorted(root.rglob("verification.json"))[:max_files]:
        try:
            report = json.loads(report_path.read_text())
        except (ValueError, OSError):
            continue
        for file in report.get("files", []):
            for grader in file.get("graders", []):
                if grader.get("status") != "FAIL":
                    continue
                detail = (grader.get("detail") or "")[:4000]
                evidence_sha = hashlib.sha256((file["file"] + grader["grader"] + detail).encode()).hexdigest()
                lessons.append({
                    "kind": "episodic", "key": evidence_sha[:32],
                    "problem": "%s failed %s" % (file["file"], grader["grader"]),
                    "fix": detail, "evidence_sha": evidence_sha, "source": "verification:" + report_path.name,
                    "status": "pending",
                })
    return lessons


# A critic's own verdict is a model's judgement call, not owner-verified ground truth like a diff or a worker
# receipt -- so unlike owner_fix_lessons/owner_chat_lessons/engine_error_lessons it is never ingested as
# "active" on sight. It becomes a "pending" episodic incident, same tier as a verification_loop failure, and
# only reaches agents through the SAME recurrence mechanism pattern_lessons() already applies to those: a
# critic diagnosis that nobody has recurred on is not yet a lesson, it is one critic's opinion of one session.
CRITIC_FIELD = re.compile(r"^(DECISION|CRITICAL_FINDING|ONE_BEST_NEXT_ACTION)=(.*)$", re.M)


def critic_fix_lessons(app_db, since_days, max_sessions=500):
    """A watoom-critic session's final REVISE verdict becomes a pending episodic incident.

    Only a session's own last assistant turn counts (finish='stop': the critic's own words, not an
    intermediate tool-call message that happened to contain the marker text). PROCEED verdicts carry no fix
    and are not a lesson. The application database is opened read-only, same as owner_chat_lessons."""
    path = pathlib.Path(app_db)
    if not path.is_file():
        return []
    db = sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=5)
    try:
        cutoff = (NOW() - since_days * 86400) * 1000
        rows = db.execute(
            "SELECT m.id,m.session_id,m.data,s.title FROM session_message m "
            "JOIN session_v2 s ON s.id=m.session_id "
            "WHERE s.agent='watoom-critic' AND m.type='assistant' AND m.time_created>=? "
            "ORDER BY m.time_created DESC LIMIT ?", (cutoff, max_sessions * 20)).fetchall()
    finally:
        db.close()
    lessons, seen_session, seen_evidence = [], set(), set()
    for msg_id, session_id, data, title in rows:
        if session_id in seen_session or len(seen_session) >= max_sessions:
            continue
        seen_session.add(session_id)  # first row per session in DESC order is that session's last turn
        try:
            msg = json.loads(data)
        except ValueError:
            continue
        if msg.get("finish") != "stop":
            continue
        text = next((p.get("text") or "" for p in reversed(msg.get("content") or []) if p.get("type") == "text"), "")
        fields = dict(CRITIC_FIELD.findall(text))
        if fields.get("DECISION", "").strip().upper() != "REVISE":
            continue
        finding = (fields.get("CRITICAL_FINDING") or text)[:4000].strip()
        action = (fields.get("ONE_BEST_NEXT_ACTION") or "")[:2000].strip()
        if not finding:
            continue
        evidence_sha = hashlib.sha256((session_id + finding).encode()).hexdigest()
        if evidence_sha in seen_evidence:
            continue
        seen_evidence.add(evidence_sha)
        lessons.append({
            "kind": "episodic", "key": hashlib.sha256(("critic|" + evidence_sha).encode()).hexdigest()[:32],
            "problem": "watoom-critic found a real issue in \"%s\": %s" % ((title or session_id)[:80], finding[:300]),
            "fix": finding + ("\n\nNext action: " + action if action else ""),
            "evidence_sha": evidence_sha, "source": "critic:" + str(msg_id)[:24],
            "status": "pending",  # a model's own verdict, not owner-verified; promoted only by recurrence
        })
    return lessons


def pattern_lessons(db, min_occurrences=3, lookback_days=90, max_files_listed=10):
    """Mine the curator's OWN accumulated episodic incidents (not this run's fresh signal, the sidecar's whole
    history) for a grader that has failed on enough distinct files/sessions to be a pattern rather than a
    one-off, and turn that pattern into one new, auto-applied procedural lesson. Deterministic, no LLM: the
    grouping key is the exact grader name `verification_incidents()` already records, and the lesson's own key
    is a hash of that name, so re-running never duplicates it and a later rollback of the pattern lesson alone
    leaves every underlying episodic incident untouched."""
    cutoff = NOW() - lookback_days * 86400
    rows = db.execute(
        "SELECT key,problem,source,created_utc FROM lessons WHERE kind='episodic' AND source LIKE 'verification:%' AND created_utc>=?",
        (cutoff,)).fetchall()
    groups = {}
    for key, problem, source, created in rows:
        marker = " failed "
        idx = problem.rfind(marker)
        if idx < 0:
            continue
        grader = problem[idx + len(marker):].strip()  # grader name, after the last " failed "
        file = problem[:idx]
        if not grader:
            continue
        groups.setdefault(grader, []).append({"key": key, "file": file, "source": source})
    lessons = []
    for grader, incidents in sorted(groups.items()):
        if len(incidents) < min_occurrences:
            continue
        pattern_key = hashlib.sha256(("pattern|" + grader).encode()).hexdigest()[:32]
        files = sorted({i["file"] for i in incidents})
        lessons.append({
            "kind": "procedural", "key": pattern_key,
            "problem": "%s has failed %d separate time(s) across %d distinct file(s)" % (grader, len(incidents), len(files)),
            "fix": ("This is a recurring failure, not a one-off: the %s check has failed on %d different file(s) "
                    "(for example: %s). Before investigating a fresh failure from this same check from scratch, "
                    "check whether the same root cause applies again." %
                    (grader, len(files), ", ".join(files[:max_files_listed]))),
            "evidence_sha": hashlib.sha256("|".join(sorted(i["key"] for i in incidents)).encode()).hexdigest(),
            "source": "pattern:" + grader[:60],
            "status": "active", "last_validated_utc": NOW(),  # recurrence across real, already-recorded incidents is its own validation
            "meta": {"grader": grader, "occurrences": len(incidents), "files": files[:max_files_listed]},
        })
    return lessons


def curate(db, root, repo, evidence_root, owner_emails, agent_emails, since_days, apply, chat_db=None, marker=LESSON_MARKER,
          receipts_dir=None, engine_version=None, export_path=None, engine_installed=0, pattern_min_occurrences=3):
    if disabled(root):
        return {"status": "DISABLED", "applied": False, "reason": "curator-disabled flag present"}
    candidates = []
    if repo:
        candidates += owner_fix_lessons(repo, owner_emails, agent_emails, since_days)
    if evidence_root:
        candidates += verification_incidents(evidence_root)
    if chat_db:
        candidates += owner_chat_lessons(chat_db, since_days, marker)
        candidates += critic_fix_lessons(chat_db, since_days)  # same application.sqlite, read-only
    if receipts_dir and engine_version:
        candidates += engine_error_lessons(receipts_dir, "godot", engine_version, since_days, not_before=engine_installed)
    # Mine the curator's own accumulated memory, not just this run's fresh signals: an episodic incident that
    # has recurred often enough becomes one new, auto-applied procedural lesson (the design's "skillbook"
    # recurrence model, see docs/proposals/learning-loop-design.md §3.2).
    pattern_candidates = pattern_lessons(db, min_occurrences=pattern_min_occurrences)
    candidates += pattern_candidates
    # secrets.token_hex, not a hash of the current second: two curate() calls inside the same wall-clock second
    # (the timer firing twice quickly, or just a fast test) would otherwise produce the SAME txn id, silently
    # merging two unrelated batches so rolling back one would also undo the other.
    txn = "curate-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(4)
    inserted, existing = [], []
    if apply:
        db.execute("BEGIN")
        try:
            for lesson in candidates:
                (inserted if upsert(db, txn, lesson) == "inserted" else existing).append(lesson["key"])
            stale = stale_pass(db, txn)
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
    else:
        stale = []
    result = {"status": "PASS", "applied": bool(apply), "txn": txn,
              "candidates": len(candidates), "inserted": len(inserted),
              "already_present": len(existing), "retired_stale": len(stale),
              "pattern_candidates": len(pattern_candidates)}
    if apply and export_path:
        result["exported"] = export_recall(db, export_path)  # idempotent: rewritten every run, rollback shows next run
    return result


def stale_pass(db, txn):
    """Retire active lessons gone unused past the window; preserved for rollback, never deleted."""
    cutoff = NOW() - STALE_UNUSED_DAYS * 86400
    retired = []
    for (key,) in db.execute("SELECT key FROM lessons WHERE status='active' AND times_helped=0 AND created_utc<?", (cutoff,)).fetchall():
        if set_status(db, txn, key, "stale"):
            retired.append(key)
    return retired


def recall(db, query, limit):
    """Active lessons matching the query; bumps usage counters so unused lessons can be found and retired."""
    like = "%" + query + "%"
    rows = db.execute("SELECT key,kind,problem,fix,source FROM lessons WHERE status='active' AND (problem LIKE ? OR fix LIKE ?) ORDER BY times_helped DESC, created_utc DESC LIMIT ?",
                      (like, like, limit)).fetchall()
    out = []
    for key, kind, problem, fix, source in rows:
        db.execute("UPDATE lessons SET times_helped=times_helped+1, last_used_utc=? WHERE key=?", (NOW(), key))
        out.append({"kind": kind, "problem": problem, "fix": fix[:2000], "source": source})
    return out


def rollback(db, txn):
    entries = db.execute("SELECT op,lesson_key,before_json,after_json FROM journal WHERE txn=? ORDER BY rowid DESC", (txn,)).fetchall()
    if not entries:
        raise SystemExit("no journal entries for transaction " + txn)
    db.execute("BEGIN")
    for op, key, before_json, _ in entries:
        before = json.loads(before_json) if before_json else None
        if op == "insert":
            db.execute("DELETE FROM lessons WHERE key=?", (key,))
        elif op == "status" and before:
            db.execute("UPDATE lessons SET status=? WHERE key=?", (before["status"], key))
    db.execute("DELETE FROM journal WHERE txn=?", (txn,))
    db.execute("COMMIT")
    return {"status": "ROLLED_BACK", "txn": txn, "reverted": len(entries)}


def summary(db):
    counts = {k: 0 for k in KINDS}
    by_status = {}
    for kind, status, n in db.execute("SELECT kind,status,COUNT(*) FROM lessons GROUP BY kind,status").fetchall():
        counts[kind] = counts.get(kind, 0) + n
        by_status[status] = by_status.get(status, 0) + n
    return {"total": sum(counts.values()), "by_kind": counts, "by_status": by_status}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["curate", "recall", "rollback", "status"])
    p.add_argument("--store", type=pathlib.Path, required=True, help="sidecar lesson SQLite store")
    p.add_argument("--repo", type=pathlib.Path, help="repo to mine owner fixes from (curate)")
    p.add_argument("--evidence-root", help="directory of verification_loop evidence to ingest (curate)")
    p.add_argument("--chat-db", help="WatooM-Code application.sqlite to mine owner chat rules from (curate, read-only)")
    p.add_argument("--receipts-dir", help="game-worker receipts to mine engine API errors from (curate)")
    p.add_argument("--godot-toolchain", help="engine toolchain dir; its newest numeric subdirectory is the engine version")
    p.add_argument("--export-recall", help="write active lessons as JSON for the coordinator guard (curate --apply)")
    p.add_argument("--lesson-marker", default=LESSON_MARKER, help="chat lines starting with this become lessons (default %(default)s)")
    p.add_argument("--agent-email", action="append", default=list(AGENT_EMAILS))
    p.add_argument("--owner-email", action="append", default=list(OWNER_EMAILS))
    p.add_argument("--since-days", type=int, default=30)
    p.add_argument("--pattern-min-occurrences", type=int, default=3,
                   help="curate: a grader must fail on this many distinct files before its own recurring-failure lesson is written (default %(default)s)")
    p.add_argument("--apply", action="store_true", help="curate: write to the sidecar (otherwise dry-run)")
    p.add_argument("--query", default="")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--txn", help="transaction id to roll back")
    a = p.parse_args()
    root = a.store.resolve().parent
    db = connect(a.store.resolve())
    try:
        if a.mode == "curate":
            result = curate(db, root, a.repo, a.evidence_root, tuple(a.owner_email), tuple(a.agent_email), a.since_days, a.apply, a.chat_db, a.lesson_marker,
                            a.receipts_dir, toolchain_version(a.godot_toolchain), a.export_recall,
                            toolchain_installed(a.godot_toolchain), a.pattern_min_occurrences)
        elif a.mode == "recall":
            result = {"lessons": recall(db, a.query, a.limit)}
        elif a.mode == "rollback":
            if not a.txn:
                raise SystemExit("--txn is required for rollback")
            result = rollback(db, a.txn)
        else:
            result = summary(db)
    finally:
        db.close()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
