#!/usr/bin/env python3
"""Audited, human-approved host change requests for models.

Models write <queue>/<id>.json; `scan` (timer) validates it against policy.json and publishes <id>.status.json with the
exact diff. Only an operator running `approve` on the host applies it: fixed policy checks, then a one-path commit/push.
Models never run host commands, choose checks, set paths outside the allowlist, or approve themselves.
"""

import argparse, difflib, hashlib, json, os, pathlib, re, secrets, stat, subprocess, sys, tempfile, time

POLICY = pathlib.Path(os.environ.get("WATOOM_CHANGE_POLICY", pathlib.Path(__file__).with_name("policy.json")))
ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")


def policy():
    return json.loads(POLICY.read_text())


def read_regular(directory, name, limit):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_size > limit:
            raise ValueError("Request must be a regular file within the size limit")
        return os.read(fd, limit + 1)
    finally:
        os.close(fd)


def write_status(queue, rid, value):
    d = os.open(queue, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        tmp = "." + rid + ".status.tmp"
        fd = os.open(tmp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY | os.O_NOFOLLOW, 0o644, dir_fd=d)
        with os.fdopen(fd, "w") as f:
            json.dump(value, f, indent=2)
        os.replace(tmp, rid + ".status.json", src_dir_fd=d, dst_dir_fd=d)
    finally:
        os.close(d)


def audit(p, event, **extra):
    path = pathlib.Path(p["audit"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(
            json.dumps(
                {"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": event, **extra}, sort_keys=True
            )
            + "\n"
        )


def sha(b):
    return hashlib.sha256(b).hexdigest()


def evaluate(p, raw, rid):
    """Return (request, target_path, old_bytes, new_bytes) or raise ValueError with the reason shown to the model."""
    lim = p["limits"]
    v = json.loads(raw)
    if not isinstance(v, dict) or set(v) != {"schema", "id", "file", "old", "new", "reason"} or v["schema"] != 1:
        raise ValueError("Exact fields required: schema,id,file,old,new,reason (schema 1)")
    if v["id"] != rid or not ID.fullmatch(rid):
        raise ValueError("id must equal the file name and match [a-z0-9-]{1,64}")
    if (
        isinstance(v["file"], str)
        and v["file"] not in p["targets"]
        and "standardised_k3s_project/" + v["file"] in p["targets"]
    ):
        v["file"] = "standardised_k3s_project/" + v["file"]
    if v["file"] not in p["targets"]:
        raise ValueError(
            "File is not in the change-request allowlist: %s (allowed: %s)"
            % (v["file"], ", ".join(sorted(p["targets"])))
        )
    if (
        not all(isinstance(v[k], str) for k in ("old", "new", "reason"))
        or not v["old"]
        or not 1 <= len(v["reason"]) <= 1000
    ):
        raise ValueError("old/new/reason must be strings; old non-empty; reason 1-1000 chars")
    if max(len(v["old"]), len(v["new"])) > lim["max_text_bytes"] or v["old"] == v["new"]:
        raise ValueError("old/new size limit or no-op change")
    path = pathlib.Path(p["repo"]) / v["file"]
    if path.is_symlink() or not path.is_file() or path.resolve() != path:
        raise ValueError("Target must be a regular in-repo file")
    base = path.read_bytes()
    text = base.decode()
    if text.count(v["old"]) != 1:
        n = text.count(v["old"])
        hint = ""
        if n == 0 and v["old"].strip() and text.count(v["old"].strip()) == 1:
            hint = " Whitespace differs: the text matches once without its leading/trailing whitespace; copy the line exactly, including indentation."
        raise ValueError("old must match exactly once in the current file (matches: %d).%s" % (n, hint))
    new = text.replace(v["old"], v["new"], 1)
    changed = sum(
        1
        for l in difflib.unified_diff(text.splitlines(), new.splitlines(), lineterm="", n=0)
        if l[:1] in "+-" and l[:3] not in ("+++", "---")
    )
    if changed > lim["max_changed_lines"]:
        raise ValueError("Too many changed lines (%d > %d)" % (changed, lim["max_changed_lines"]))
    return v, path, base, new.encode()


def diff(v, base, new):
    return "".join(
        difflib.unified_diff(
            base.decode().splitlines(True), new.decode().splitlines(True), "a/" + v["file"], "b/" + v["file"]
        )
    )


def queues(p):
    """Explicit queues plus every project's .opencode/change-requests found by the policy globs (symlink-free paths only)."""
    seen = []
    for q in list(p.get("queues", [])) + [
        str(x) for g in p.get("queue_globs", []) for x in sorted(pathlib.Path("/").glob(g.lstrip("/")))
    ]:
        q = pathlib.Path(q)
        root = pathlib.Path(p.get("queue_root", "/data/ai/projects"))
        try:
            ok = q.is_dir() and q.resolve() == q and q.is_relative_to(root)
        except OSError:
            ok = False
        if ok and q not in seen:
            seen.append(q)
    return seen


def queue_items(p):
    for q in queues(p):
        for f in sorted(q.glob("*.json")):
            if not f.name.endswith(".status.json") and not f.name.startswith("."):
                yield q, f.stem


def load(p, queue, rid):
    d = os.open(queue, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        return read_regular(d, rid + ".json", p["limits"]["max_request_bytes"])
    finally:
        os.close(d)


def scan(p):
    n = 0
    for q, rid in queue_items(p):
        status = q / (rid + ".status.json")
        if status.exists():
            continue
        try:
            raw = load(p, q, rid)
            v, path, base, new = evaluate(p, raw, rid)
            write_status(
                q,
                rid,
                {
                    "status": "PENDING_APPROVAL",
                    "request_sha256": sha(raw),
                    "base_sha256": sha(base),
                    "diff": diff(v, base, new),
                    "next": "An operator must approve on the host: change_request.py approve " + rid,
                },
            )
            audit(p, "pending", id=rid, queue=str(q), file=v["file"], request_sha256=sha(raw))
        except (ValueError, json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
            write_status(q, rid, {"status": "REJECTED", "reason": str(e)[:400]})
            audit(p, "rejected", id=rid, reason=str(e)[:200])
        n += 1
    return n


def find(p, rid, project=None):
    hits = [q for q, i in queue_items(p) if i == rid and (project is None or project in str(q))]
    if project and len(hits) > 1:
        hits = [q for q in hits if q.parent.parent.name == project] or hits
    if len(hits) != 1:
        raise SystemExit(
            (
                "Unknown request "
                if not hits
                else "Ambiguous id; pass --project NAME. Candidates: " + ", ".join(map(str, hits))
            )
            + rid
        )
    return hits[0]


def git(p, *a, check=True):
    try:
        return _git(p, *a, check=check)
    except subprocess.CalledProcessError as e:
        raise SystemExit("git %s failed: %s" % (a[0], (e.stderr or e.stdout or str(e.returncode)).strip()[-200:]))


def _git(p, *a, check=True):
    return subprocess.run(
        [
            "git",
            "-C",
            p["repo"],
            "-c",
            "safe.directory=" + p["repo"],
            "-c",
            "user.name=WatooM Change Requests",
            "-c",
            "user.email=change-requests@agent.example",
            *a,
        ],
        capture_output=True,
        text=True,
        check=check,
    )


def approve(p, rid, push, project=None):
    q = find(p, rid, project)
    st = json.loads((q / (rid + ".status.json")).read_text())
    if st.get("status") != "PENDING_APPROVAL":
        raise SystemExit("Not pending: " + str(st.get("status")))
    raw = load(p, q, rid)
    if sha(raw) != st["request_sha256"]:
        raise SystemExit("Request changed after review; resubmit with a new id")
    v, path, base, new = evaluate(p, raw, rid)
    if sha(base) != st["base_sha256"]:
        raise SystemExit("Target changed since review (STALE); resubmit")
    if git(p, "status", "--porcelain", "--", v["file"]).stdout.strip():
        raise SystemExit("Target has uncommitted changes; refusing to mix them into a commit")
    target = p["targets"][v["file"]]
    cwd = pathlib.Path(p["repo"]) / target.get("cwd", ".")
    path.write_bytes(new)
    try:
        for argv in target["checks"]:
            r = subprocess.run(
                [a.replace("{file}", str(path)) for a in argv], cwd=cwd, capture_output=True, text=True, timeout=300
            )
            if r.returncode:
                raise RuntimeError(" ".join(argv)[:80] + " failed: " + (r.stderr or r.stdout)[-300:])
    except BaseException as e:
        path.write_bytes(base)
        write_status(q, rid, {**st, "status": "CHECK_FAILED", "reason": str(e)[:400]})
        audit(p, "check_failed", id=rid, reason=str(e)[:200])
        raise SystemExit("Checks failed; file restored: " + str(e)[:200])
    git(p, "add", "--", v["file"])
    msg = "change-request %s: %s\n\nApproved by operator on the host. Model reason: %s" % (rid, v["file"], v["reason"])
    git(p, "commit", "-q", "-m", msg, "--", v["file"])
    commit = git(p, "rev-parse", "HEAD").stdout.strip()
    pushed = False
    if push and p.get("push"):
        pushed = git(p, "push", "-q", "origin", "HEAD", check=False).returncode == 0
    write_status(q, rid, {**st, "status": "APPLIED", "commit": commit, "pushed": pushed})
    audit(p, "applied", id=rid, queue=str(q), file=v["file"], commit=commit, pushed=pushed)
    print("APPLIED", rid, commit, "pushed" if pushed else "NOT pushed")


STATE_DEFAULT = "/data/ai/helper-scripts/state/change-requests"


def state_dir(p):
    return pathlib.Path(p.get("state_dir", STATE_DEFAULT))


def atomic_write(path, text, mode=0o644):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    fd = os.open(tmp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def keep_errors(p, new):
    """Decision failures stay in the feed for 30 minutes so the page can still show them after the next scan."""
    try:
        old = json.loads((state_dir(p) / "requests.json").read_text()).get("errors", [])
    except (OSError, ValueError):
        old = []
    now = time.time()
    seen = {(e.get("id"), e.get("error")) for e in new}
    keep = [
        e
        for e in old
        if isinstance(e, dict) and now - float(e.get("time", 0)) < 1800 and (e.get("id"), e.get("error")) not in seen
    ]
    return (keep + new)[-10:]


def publish(p, errors=None):
    """Write the page feed (read-only copy of every request's status and diff) for the Glance change-request page."""
    rows = []
    for q, rid in queue_items(p):
        f = q / (rid + ".status.json")
        try:
            st = json.loads(f.read_text()) if f.exists() else {"status": "UNSCANNED"}
            when = f.stat().st_mtime if f.exists() else 0
        except (OSError, ValueError):
            continue
        try:
            req = json.loads(load(p, q, rid))
            target = str(req.get("file", ""))[:200]
            reason = str(req.get("reason", ""))[:1000]
        except (OSError, ValueError):
            target = reason = ""
        rows.append(
            {
                "project": q.parent.parent.name,
                "id": rid,
                "status": st.get("status"),
                "file": target,
                "reason": reason,
                "diff": str(st.get("diff", ""))[:20000],
                "request_sha256": st.get("request_sha256"),
                "base_sha256": st.get("base_sha256"),
                "commit": st.get("commit"),
                "pushed": st.get("pushed"),
                "detail": str(st.get("reason", ""))[:400],
                "time": when,
            }
        )
    rows.sort(key=lambda r: (r["status"] != "PENDING_APPROVAL", -r["time"]))
    atomic_write(
        state_dir(p) / "requests.json",
        json.dumps(
            {
                "schema": 1,
                "generated": time.time(),
                "pending": sum(r["status"] == "PENDING_APPROVAL" for r in rows),
                "requests": rows[:40],
                "errors": keep_errors(p, errors or []),
            }
        ),
    )


def decisions(p):
    """Apply decisions dropped by the Glance helper after a correct operator PIN. Each is re-verified against the live request hash."""
    inbox = state_dir(p) / "decisions"
    errors = []
    done = 0
    if not inbox.is_dir():
        return errors
    for f in sorted(inbox.glob("*.json"))[:20]:
        try:
            raw = f.read_bytes()
            if len(raw) > 4096 or f.is_symlink():
                raise ValueError("bad decision file")
            d = json.loads(raw)
            if (
                not isinstance(d, dict)
                or d.get("action") not in ("approve", "reject")
                or not all(isinstance(d.get(k), str) for k in ("id", "project", "request_sha256"))
                or not ID.fullmatch(d["id"])
            ):
                raise ValueError("malformed decision")
            q = find(p, d["id"], d["project"])
            st = json.loads((q / (d["id"] + ".status.json")).read_text())
            if st.get("status") != "PENDING_APPROVAL" or st.get("request_sha256") != d["request_sha256"]:
                raise ValueError("request is no longer the reviewed pending version")
            audit(p, d["action"] + "_via_glance", id=d["id"], queue=str(q), client=str(d.get("client", ""))[:64])
            if d["action"] == "approve":
                approve(p, d["id"], True, d["project"])
            else:
                write_status(
                    q,
                    d["id"],
                    {"status": "REJECTED", "reason": str(d.get("reason") or "Rejected by operator in Glance")[:400]},
                )
                audit(p, "rejected_by_operator", id=d["id"])
            done += 1
        except SystemExit as e:
            errors.append(
                {
                    "id": str(d.get("id", "?")) if isinstance(d, dict) else "?",
                    "error": str(e)[:300],
                    "time": time.time(),
                }
            )
        except Exception as e:
            errors.append(
                {
                    "id": str(d.get("id", "?")) if isinstance(d, dict) else "?",
                    "error": (type(e).__name__ + ": " + str(e))[:300],
                    "time": time.time(),
                }
            )
        finally:
            try:
                f.unlink()
            except OSError:
                pass
    return errors


def main():
    a = argparse.ArgumentParser()
    s = a.add_subparsers(dest="cmd", required=True)
    s.add_parser("scan")
    s.add_parser("list")
    sp = s.add_parser("set-pin")
    sp.add_argument(
        "--env",
        action="store_true",
        help="print CHANGE_REQUEST_PIN / GLANCE_CHANGE_APPROVAL_PIN_HASH lines for piping into the vault (never to a terminal)",
    )
    sh = s.add_parser("show")
    sh.add_argument("id")
    sh.add_argument("--project")
    ap = s.add_parser("approve")
    ap.add_argument("id")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--project")
    rj = s.add_parser("reject")
    rj.add_argument("id")
    rj.add_argument("--reason", default="Rejected by operator")
    rj.add_argument("--project")
    x = a.parse_args()
    p = policy()
    if x.cmd == "scan":
        n = scan(p)
        errs = decisions(p)
        publish(p, errs)
        print("processed", n, "errors", len(errs))
    elif x.cmd == "set-pin":
        pin = secrets.token_urlsafe(15)
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), 200000).hex()
        atomic_write("/root/.watoom-change-request-pin", pin + "\n", 0o600)
        if x.env:
            print("CHANGE_REQUEST_PIN=" + pin)
            print("GLANCE_CHANGE_APPROVAL_PIN_HASH=" + salt + ":" + digest)
        else:
            print(
                "PIN written to /root/.watoom-change-request-pin (root only). Hash for the glance-change-approval secret:"
            )
            print(salt + ":" + digest)
    elif x.cmd == "list":
        for q, rid in queue_items(p):
            f = q / (rid + ".status.json")
            print(q.parent.parent.name, rid, json.loads(f.read_text()).get("status") if f.exists() else "UNSCANNED")
    elif x.cmd == "show":
        q = find(p, x.id, x.project)
        print(json.dumps(json.loads((q / (x.id + ".status.json")).read_text()), indent=2))
        print(json.loads((q / (x.id + ".status.json")).read_text()).get("diff", ""))
    elif x.cmd == "approve":
        approve(p, x.id, not x.no_push, x.project)
    elif x.cmd == "reject":
        q = find(p, x.id, x.project)
        write_status(q, x.id, {"status": "REJECTED", "reason": x.reason})
        audit(p, "rejected_by_operator", id=x.id)


if __name__ == "__main__":
    main()
