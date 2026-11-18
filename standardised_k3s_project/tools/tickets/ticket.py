#!/usr/bin/env python3
"""WatooM to-do tickets with Discord notifications (stdlib only).

Purpose: log items to do so neither the owner nor a model forgets them. Every ticket has an id (T-0001), title, status
(open, doing, blocked, done, dropped), priority, project, optional PR/commit link and a note history. Each change is posted
to a Discord channel when a webhook file exists; Discord problems never block or fail a ticket change.

  ticket.py add "title" [--body T] [--project P] [--priority low|normal|high] [--pr URL] [--by NAME]
  ticket.py list [--status S ...] [--project P] [--all]        open work by default (open, doing, blocked)
  ticket.py show T-0001
  ticket.py status T-0001 doing|blocked|done|dropped|open [--note T] [--pr URL] [--by NAME]
  ticket.py note T-0001 "text" [--by NAME]
  ticket.py ingest            read model requests from the project queues, create tickets (run by a timer)
  ticket.py digest            post the open list to Discord (for a daily timer)
  ticket.py repost [--skip T-0001 ...]   post every ticket again into the channel for its status
  ticket.py add ... [--queue requests|issues|backlog] [--shared]    board column (default requests); shared = any agent may work it
  ticket.py move T-0001 requests|issues|backlog|wip|completed|cancelled|obsolete [--lane NAME|-] [--blocked|--unblocked] [--note T] [--pr URL] [--by NAME]
  ticket.py migrate           optional: write queue/shared/owner/change_requests into every ticket once (no status change, no Discord)

Models cannot run commands: they write <project>/.opencode/tickets/<id>.json (the id equals the file name):
  {"schema":1,"id":"x","title":"...","body":"...","priority":"normal","project":"..."}           creates a ticket
  {"schema":1,"id":"y","action":"status","ticket":"T-0003","status":"doing|blocked|done|open","note":"...","pr":"..."}
  {"schema":1,"id":"z","action":"note","ticket":"T-0003","text":"..."}
  {"schema":1,"id":"c","action":"change_request","ticket":"T-0003","text":"what to change and why"}
  {"schema":1,"id":"m","action":"move","ticket":"T-0003","queue":"requests|issues|backlog|wip|completed","note":"..."}   board column
A create request may also carry "queue" (requests, issues or backlog; default requests) and "shared": true (any model may work it).
Every request should carry "model":"<your model name>". A ticket has ONE owner model: its creator, or the first model to set an unowned ticket
to doing. Another model's status or note on it is rejected; it files a change_request instead, which is posted to Discord and recorded on the
ticket, and the owner approves it with `ticket.py assign T-0003 <model>` (the new owner may then work the ticket).
`ingest` applies each request once, writes <id>.status.json next to it (state created/updated/rejected) and refreshes
OPEN-TICKETS.md in the same folder, a read-only list of active tickets. Models cannot set "dropped" (owner only). Environment: WATOOM_TICKETS_DIR (default /data/ai/tickets), WATOOM_TICKET_WEBHOOK_FILE
(default /data/ai/secrets/discord_tickets_webhook; the URL is never printed or stored in the tickets file). Per-status Discord channels: put one
webhook URL in <that file>_new, _progress, _closed and _cancelled; a post goes to the channel for the ticket's status (created/reopened -> new,
doing/blocked -> progress, done -> closed, dropped -> cancelled) and falls back to the base file when a channel file is missing,
WATOOM_TICKET_QUEUE_GLOBS (default /data/ai/projects/*/*/.opencode/tickets).
"""
import argparse
import fcntl
import glob
import hashlib
import json
import os
import pathlib
import re
import stat
import sys
import time
import urllib.error
import urllib.request

STATUSES = ("open", "doing", "blocked", "done", "dropped")
ACTIVE = ("open", "doing", "blocked")
PRIORITIES = ("low", "normal", "high")
COLOURS = {"open": 0x3B82F6, "doing": 0xF59E0B, "blocked": 0xEF4444, "done": 0x22C55E, "dropped": 0x6B7280}
ICONS = {"open": "🆕", "doing": "🔧", "blocked": "⛔", "done": "✅", "dropped": "🗑️"}
REQUEST_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
MAX_REQUEST_BYTES = 16384

# Board columns (kanban-design.md 2.3). `status` stays the authority; `queue` only refines it, so every reader that knows
# just `status` still sees a valid value, and a stored queue that no longer fits the status is ignored on read.
QUEUES = ("requests", "issues", "backlog", "wip", "completed", "cancelled", "obsolete")
QUEUE_STATUS = {"requests": ("open",), "issues": ("open",), "backlog": ("open",), "wip": ("doing", "blocked"),
                "completed": ("done",), "cancelled": ("dropped",), "obsolete": ("dropped",)}
DEFAULT_QUEUE = {"open": "backlog", "doing": "wip", "blocked": "wip", "done": "completed", "dropped": "cancelled"}
INTAKE_QUEUES = ("requests", "issues", "backlog")  # where a new ticket may start
MODEL_QUEUES = ("requests", "issues", "backlog", "wip", "completed")  # cancelled/obsolete are owner-only (status dropped)
NEW_TICKET_QUEUE = "requests"
OWNER_ID = "owner"


def tickets_dir():
    return pathlib.Path(os.environ.get("WATOOM_TICKETS_DIR", "/data/ai/tickets"))


def queue_of(t):
    """The board column of a ticket: its stored queue when that fits its status, else the default for the status."""
    q = t.get("queue")
    return q if q in QUEUE_STATUS and t["status"] in QUEUE_STATUS[q] else DEFAULT_QUEUE[t["status"]]


def load(directory=None):
    """Read-only snapshot without the lock (writers replace the file atomically, so a reader sees one whole version)."""
    p = (pathlib.Path(directory) if directory else tickets_dir()) / "tickets.json"
    return json.loads(p.read_text()) if p.exists() else {"next": 1, "tickets": []}


# Agent registry (kanban-design.md 3.1): /data/ai/tickets/agents.json, no secrets. It only seeds ids, labels and aliases;
# any other name (a new local model "model:<name>") works without a config change and gets a WIP lane once it owns a ticket.
BUILTIN_AGENTS = [{"id": OWNER_ID, "label": "Owner", "role": "owner", "lane": False, "aliases": []}]


def agents_file():
    return pathlib.Path(os.environ.get("WATOOM_TICKET_AGENTS_FILE") or (tickets_dir() / "agents.json"))


def load_agents(path=None):
    """Registry entries; a missing or broken file gives just the built-in owner entry (never an error)."""
    try:
        raw = json.loads(pathlib.Path(path or agents_file()).read_text())
        rows = raw.get("agents") if isinstance(raw, dict) else None
    except (OSError, ValueError):
        rows = None
    out = []
    for a in rows if isinstance(rows, list) else []:
        if isinstance(a, dict) and isinstance(a.get("id"), str) and a["id"].strip():
            out.append({"id": a["id"].strip()[:60], "label": str(a.get("label") or a["id"])[:60], "role": "owner" if a.get("role") == "owner" else "agent",
                        "lane": bool(a.get("lane")), "aliases": [str(x)[:60] for x in a.get("aliases") or [] if isinstance(x, str)]})
    if not any(a["role"] == "owner" for a in out):
        out = BUILTIN_AGENTS + out
    return out


def canonical(name, agents=None):
    """Registry id for a name or one of its aliases; any other name is returned unchanged (history is never rewritten)."""
    name = (name or "").strip()
    for a in load_agents() if agents is None else agents:
        if name == a["id"] or name in a["aliases"]:
            return a["id"]
    return name


def label_of(name, agents=None):
    """Display label: the registry label, or for an unregistered "model:<name>" the name with dashes as spaces."""
    cid = canonical(name, agents)
    for a in load_agents() if agents is None else agents:
        if a["id"] == cid:
            return a["label"]
    return cid[6:].replace("-", " ") if cid.startswith("model:") else cid


def may(actor, role, action, t, agents=None):
    """True when actor may do action on ticket t. Actions: note, status, move, edit, share, assign, drop, change_request."""
    if role == "owner":
        return True
    if action in ("share", "assign", "drop"):  # drop = move to cancelled or obsolete, or status dropped
        return False
    if action == "change_request":
        return True
    owner = canonical(t.get("owner", ""), agents)
    if t.get("shared") or owner == canonical(actor, agents):
        return True
    return not owner and action in ("status", "move")  # unowned: the first agent to start it claims it


class Refused(ValueError):
    """may() said no. A ValueError, so the queue path reports it as a rejected request, as before."""


def refusal(actor, action, t):
    """The reason text for a refused action (same wording as the queue rejections)."""
    if action in ("drop", "share", "assign"):
        return "only the owner may %s %s; file a change_request (what you want changed and why) instead" % (
            {"drop": "cancel or obsolete", "share": "change sharing on", "assign": "reassign"}[action], t["id"])
    if t.get("owner"):
        return "%s is owned by %s; write a change_request (action change_request, text = what you want to change and why) and the owner will approve it" % (t["id"], t["owner"])
    return "%s has no owner yet: start it (status doing) to claim it, or file a change_request" % t["id"]


def plan_move(actor, role, t, queue, lane=None, agents=None):
    """Check a board move with may() and return the owner the ticket gets (None = unchanged). Raises Refused or ValueError.
    lane applies to wip only: None keeps the owner (an agent's move into wip goes to its own lane), "" is Unassigned."""
    if queue not in QUEUE_STATUS:
        raise ValueError("queue must be one of %s" % ", ".join(QUEUES))
    if lane is not None and queue != "wip":
        raise ValueError("a lane applies to the wip queue only")
    owner = canonical(t.get("owner", ""), agents)
    me = canonical(actor, agents)
    target = None
    if queue in ("cancelled", "obsolete"):
        action = "drop"
    elif role == "owner":
        action = "move"
        target = None if lane is None else canonical(lane, agents)
    elif queue == "wip" and lane is not None and canonical(lane, agents) != me:
        action = "assign"  # an agent may only use its own lane
    else:
        action = "move"
        target = me if owner != me and (queue == "wip" or not owner) else None  # claim an unowned ticket, take a shared one into its lane
    if not may(actor, role, action, t, agents):
        raise Refused(refusal(actor, action, t))
    return None if target is None or target == owner else target


def lanes(data, agents=None):
    """WIP lanes: registry agents with lane true, then every other owner of a wip ticket (generic: any model), then Unassigned."""
    agents = load_agents() if agents is None else agents
    out, seen = [], set()
    for a in agents:
        if a["lane"] and a["id"] not in seen:
            out.append({"id": a["id"], "label": a["label"]})
            seen.add(a["id"])
    for t in data["tickets"]:
        o = canonical(t.get("owner", ""), agents)
        if o and o not in seen and queue_of(t) == "wip":
            out.append({"id": o, "label": label_of(o, agents)})
            seen.add(o)
    out.append({"id": "", "label": "Unassigned"})
    return out


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


_STOP = {"a", "an", "the", "to", "of", "and", "in", "on", "for", "with", "at", "game"}


def _words(text):
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP}


def _jaccard(a, b):
    return len(a & b) / len(a | b) if a | b else 0.0


class Store:
    """One JSON file, replaced atomically, with an advisory lock held for the whole read-modify-write."""

    def __init__(self, directory=None):
        self.dir = pathlib.Path(directory) if directory else tickets_dir()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "tickets.json"
        self._lock = None

    def __enter__(self):
        self._lock = open(self.dir / ".lock", "w")
        fcntl.flock(self._lock, fcntl.LOCK_EX)
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {"next": 1, "tickets": []}
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=1, ensure_ascii=False) + "\n")
            os.replace(tmp, self.path)
        fcntl.flock(self._lock, fcntl.LOCK_UN)
        self._lock.close()

    def find(self, tid):
        tid = tid.upper() if tid[:1].lower() == "t" else "T-%04d" % int(tid)
        for t in self.data["tickets"]:
            if t["id"] == tid:
                return t
        raise SystemExit("no such ticket: %s" % tid)

    def add(self, title, body="", project="", priority="normal", by="", pr="", source="", owner="", queue=NEW_TICKET_QUEUE, shared=False):
        if not title.strip():
            raise ValueError("title is required")
        if priority not in PRIORITIES:
            raise ValueError("priority must be one of %s" % ", ".join(PRIORITIES))
        if queue not in INTAKE_QUEUES:
            raise ValueError("a new ticket's queue must be one of %s" % ", ".join(INTAKE_QUEUES))
        t = {"id": "T-%04d" % self.data["next"], "title": title.strip()[:200], "body": body.strip()[:4000], "status": "open",
             "priority": priority, "project": project.strip()[:80], "pr": pr.strip()[:300], "by": by[:60], "owner": owner[:60], "change_requests": [], "source": source[:200],
             "created": now(), "updated": now(), "notes": [], "queue": queue, "shared": bool(shared)}
        self.data["next"] += 1
        self.data["tickets"].append(t)
        return t

    def find_duplicate(self, title):
        """An ACTIVE ticket whose title is the same request (word overlap >= 0.7), or None. Closed tickets do not count: a new request may reopen old work."""
        a = _words(title)
        for t in self.data["tickets"]:
            if t["status"] in ACTIVE and a and _jaccard(a, _words(t["title"])) >= 0.7:
                return t
        return None

    def add_or_duplicate(self, title, body="", project="", priority="normal", by="", pr="", source="", owner="", queue=NEW_TICKET_QUEUE, shared=False):
        """(ticket, is_duplicate). A request that matches an active ticket adds a note to that ticket instead of creating a second one."""
        if queue not in INTAKE_QUEUES:
            raise ValueError("a new ticket's queue must be one of %s" % ", ".join(INTAKE_QUEUES))
        dup = self.find_duplicate(title)
        if dup:
            dup["notes"].append({"time": now(), "by": by[:60], "text": ("duplicate request: " + title.strip() + (" - " + body.strip() if body.strip() else ""))[:1000]})
            dup["updated"] = now()
            return dup, True
        return self.add(title, body, project, priority, by, pr, source, owner, queue, shared), False

    def set_status(self, tid, status, note="", pr="", by=""):
        if status not in STATUSES:
            raise ValueError("status must be one of %s" % ", ".join(STATUSES))
        t = self.find(tid)
        old = t["status"]
        t["status"] = status
        if "queue" in t and status not in QUEUE_STATUS.get(t["queue"], ()):
            t["queue"] = DEFAULT_QUEUE[status]  # the stored column no longer fits: e.g. issues -> doing -> open lands in backlog
        t["updated"] = now()
        if pr:
            t["pr"] = pr.strip()[:300]
        if note:
            t["notes"].append({"time": now(), "by": by[:60], "text": note.strip()[:1000]})
        return t, old

    def move(self, tid, queue, blocked=None, note="", by="", pr="", owner=None, shared_take=False):
        """Put a ticket in a board column; returns (ticket, old_status). The status follows the queue (wip: doing, or blocked when
        blocked is true; blocked=None keeps an already blocked ticket blocked). owner (not None) reassigns it like `assign`.
        Authorisation is the caller's job (plan_move)."""
        if queue not in QUEUE_STATUS:
            raise ValueError("queue must be one of %s" % ", ".join(QUEUES))
        t = self.find(tid)
        old_queue = queue_of(t)
        if queue == "wip":
            status = "blocked" if blocked or (blocked is None and t["status"] == "blocked") else "doing"
        else:
            status = QUEUE_STATUS[queue][0]
        if owner is not None and owner != t.get("owner", ""):
            t, _ = self.assign(tid, owner, by)
            if shared_take:
                t["notes"][-1]["text"] += " (shared ticket)"
        t["queue"] = queue
        t, old = self.set_status(tid, status, note, pr, by)
        if old == status and old_queue != queue:
            t["notes"].append({"time": now(), "by": by[:60], "text": "queue: %s -> %s" % (old_queue, queue)})
        return t, old

    def set_shared(self, tid, shared, by=""):
        """Owner action (after creation): let any agent work the ticket, or go back to single-owner rules. Owner is unchanged."""
        t = self.find(tid)
        old = bool(t.get("shared"))
        if old != bool(shared):
            t["shared"] = bool(shared)
            t["notes"].append({"time": now(), "by": by[:60], "text": "shared: %s -> %s" % ("on" if old else "off", "on" if shared else "off")})
            t["updated"] = now()
        return t

    EDITABLE = {"title": 200, "body": 4000, "project": 80, "pr": 300}

    def edit(self, tid, fields, by=""):
        """Change title, body, priority, project or pr; each change appends a note such as "title changed". Returns the ticket."""
        t = self.find(tid)
        changed = []
        for k, v in fields.items():
            if k == "priority":
                if v not in PRIORITIES:
                    raise ValueError("priority must be one of %s" % ", ".join(PRIORITIES))
            elif k in self.EDITABLE:
                v = str(v).strip()[: self.EDITABLE[k]]
                if k == "title" and not v:
                    raise ValueError("title is required")
            else:
                raise ValueError("cannot edit %s" % k)
            if t.get(k, "") != v:
                t[k] = v
                changed.append(k)
        if changed:
            t["notes"].append({"time": now(), "by": by[:60], "text": ", ".join(changed) + " changed"})
            t["updated"] = now()
        return t

    def decide_change_request(self, tid, index, decision, note="", by=""):
        """Owner action on one pending change request: assign (give the ticket to the requester), share, or reject."""
        t = self.find(tid)
        crs = t.get("change_requests") or []
        if not isinstance(index, int) or not 0 <= index < len(crs):
            raise ValueError("no such change request")
        c = crs[index]
        if c.get("state") != "pending":
            raise ValueError("that change request is already %s" % c.get("state"))
        if decision == "assign":
            t, _ = self.assign(tid, c["by"], by)
        elif decision == "share":
            t = self.set_shared(tid, True, by)
        elif decision != "reject":
            raise ValueError("decision must be assign, share or reject")
        c["state"] = "rejected" if decision == "reject" else "approved"
        text = "change request from %s %s" % (c["by"] or "-", c["state"]) + (": " + note.strip() if note.strip() else "")
        t["notes"].append({"time": now(), "by": by[:60], "text": text[:1000]})
        t["updated"] = now()
        return t

    def migrate(self):
        """Optional one-off: write queue, shared, owner and change_requests into every ticket. Changes no status. Returns the count changed."""
        n = 0
        for t in self.data["tickets"]:
            before = dict(t)
            t["queue"] = queue_of(t)
            t.setdefault("shared", False)
            t.setdefault("owner", "")
            t.setdefault("change_requests", [])
            n += t != before
        return n

    def assign(self, tid, owner, by=""):
        """Owner action: give the ticket to one model (or "" to leave it unowned); pending change requests from that model are closed."""
        t = self.find(tid)
        old = t.get("owner", "")
        t["owner"] = owner.strip()[:60]
        for c in t.get("change_requests", []):
            if c["state"] == "pending" and c["by"] == t["owner"]:
                c["state"] = "approved"
        t["notes"].append({"time": now(), "by": by[:60], "text": "owner changed: %s -> %s" % (old or "-", t["owner"] or "-")})
        t["updated"] = now()
        return t, old

    def change_request(self, tid, text, by=""):
        t = self.find(tid)
        t.setdefault("change_requests", []).append({"time": now(), "by": by[:60], "text": text.strip()[:1000], "state": "pending"})
        t["updated"] = now()
        return t

    def note(self, tid, text, by=""):
        t = self.find(tid)
        t["notes"].append({"time": now(), "by": by[:60], "text": text.strip()[:1000]})
        t["updated"] = now()
        return t


CHANNELS = {"open": "new", "doing": "progress", "blocked": "progress", "done": "closed", "dropped": "cancelled"}


def channel_for(t, headline=""):
    """Discord channel for a ticket post: new (created or reopened), progress (doing, blocked), closed (done), cancelled (dropped)."""
    if headline.startswith("New ticket"):
        return "new"
    return CHANNELS.get(t["status"], "new")


def webhook_url(channel=""):
    """Webhook for a channel: <base>_<channel> (new, progress, closed, cancelled) when that file exists, else the base file (one channel for everything)."""
    base = os.environ.get("WATOOM_TICKET_WEBHOOK_FILE", "/data/ai/secrets/discord_tickets_webhook")
    for path in ((base + "_" + channel,) if channel else ()) + (base,):
        try:
            url = pathlib.Path(path).read_text().strip()
        except OSError:
            continue
        if url.startswith("https://") or url.startswith("http://127.0.0.1"):
            return url
    return ""


def post(payload, channel=""):
    """Send one Discord message; return True when sent. Never raises and never prints the URL."""
    url = webhook_url(channel)
    if not url:
        return False
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "User-Agent": "watoom-tickets/1"})
        urllib.request.urlopen(req, timeout=10).read()
        return True
    except Exception as exc:  # network, rate limit, bad webhook: report the type only
        print("discord: not sent (%s)" % type(exc).__name__, file=sys.stderr)
        return False


def _hook_id(url):
    return hashlib.sha1(url.encode()).hexdigest()[:12]  # identifies the webhook without storing it


def _message_url(url, mid):
    base, _, q = url.partition("?")
    return base + "/messages/" + mid + ("?" + q if q else "")


def _call(method, url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json", "User-Agent": "watoom-tickets/1"})
    body = urllib.request.urlopen(req, timeout=10).read()
    return json.loads(body) if body else {}


def sync(tid, headline, store_dir=None):
    """Keep exactly ONE Discord message per ticket: edit it when the ticket changes, and when its status moves it to another channel delete the old
    message and post it there. The message id is saved on the ticket (never the webhook URL). Returns True when Discord has the current state;
    never raises."""
    try:
        with Store(store_dir) as s:
            t = s.find(tid)
            ch = channel_for(t, headline)
            url = webhook_url(ch)
            if not url:
                return False
            h, d, payload = _hook_id(url), t.get("discord") or {}, embed(t, headline)
            if d.get("id") and d.get("hook") == h:
                try:
                    _call("PATCH", _message_url(url, d["id"]), payload)
                    return True
                except urllib.error.HTTPError as exc:
                    if exc.code != 404:
                        raise  # message gone (404): post a fresh one below; anything else is a real failure
            elif d.get("id"):
                old = webhook_url(d.get("channel", ""))
                if old:
                    try:
                        _call("DELETE", _message_url(old, d["id"]))
                    except Exception:
                        pass  # the old message may already be deleted by hand
            r = _call("POST", url + ("&" if "?" in url else "?") + "wait=true", payload)
            t["discord"] = {"channel": ch, "hook": h, "id": str(r.get("id", ""))} if r.get("id") else {}
            return True
    except Exception as exc:
        print("discord: not synced (%s)" % type(exc).__name__, file=sys.stderr)
        return False


def embed(t, headline):
    fields = [{"name": "Priority", "value": t["priority"], "inline": True}, {"name": "Status", "value": t["status"], "inline": True}]
    if t["project"]:
        fields.append({"name": "Project", "value": t["project"], "inline": True})
    if t.get("owner"):
        fields.append({"name": "Owner", "value": t["owner"], "inline": True})
    if queue_of(t) != DEFAULT_QUEUE[t["status"]]:
        fields.append({"name": "Queue", "value": queue_of(t), "inline": True})
    if t.get("shared"):
        fields.append({"name": "Shared", "value": "any agent may work this", "inline": True})
    if t["pr"]:
        fields.append({"name": "PR / commit", "value": t["pr"][:1000], "inline": False})
    if t["notes"]:
        n = t["notes"][-1]
        fields.append({"name": "Latest note", "value": ((n["by"] + ": ") if n["by"] else "") + n["text"][:900], "inline": False})
    return {"embeds": [{"title": ("%s %s %s" % (ICONS[t["status"]], t["id"], t["title"]))[:250], "description": (headline + ("\n\n" + t["body"] if t["body"] and headline.startswith("New") else ""))[:1800],
                        "color": COLOURS[t["status"]], "fields": fields, "timestamp": t["updated"]}]}


def line(t):
    extra = ("  queue: " + queue_of(t) if queue_of(t) != DEFAULT_QUEUE[t["status"]] else "") + ("  shared" if t.get("shared") else "")  # empty for tickets without the new fields
    return "%s [%-7s] %-6s %s%s%s%s%s" % (t["id"], t["status"], t["priority"], t["title"], "  (%s)" % t["project"] if t["project"] else "", "  owner: " + t["owner"] if t.get("owner") else "", "  PR: " + t["pr"] if t["pr"] else "", extra)


def safe_regular(path):
    """Read a request file only if it is a plain regular file inside the size limit (no symlinks, no devices)."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_REQUEST_BYTES:
            raise ValueError("request must be a regular file under %d bytes" % MAX_REQUEST_BYTES)
        return os.read(fd, MAX_REQUEST_BYTES + 1)
    finally:
        os.close(fd)


MODEL_STATUSES = ("open", "doing", "blocked", "done")  # "dropped" is owner-only


MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,39}")


def apply_request(s, v, rid, qp, source):
    """Apply one validated model request to an open Store; return (status_record, ticket, headline).
    A request names its model in "model" (default: the project folder name). A ticket has one owner (its creator, or the first model to
    start an unowned ticket); any other model's status/note is rejected and must go through a change_request that the owner approves with
    `ticket.py assign`."""
    action = v.get("action", "create")
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", str(v.get("model") or "")).strip("-._")[:40] or qp.parent.parent.name  # "Swift Qwen coder" -> "Swift-Qwen-coder", never a rejection
    if not MODEL_NAME.fullmatch(name):
        raise ValueError("model must be 1-40 characters of letters, digits, . _ -")
    by = "model:" + name
    if action == "create":
        t, dup = s.add_or_duplicate(str(v.get("title", "")), str(v.get("body", "")), str(v.get("project", "")) or qp.parent.parent.name,
                                    str(v.get("priority", "normal")), by=by, source=source, owner=by,
                                    queue=str(v.get("queue") or NEW_TICKET_QUEUE), shared=v.get("shared") is True)
        if dup:
            return {"state": "duplicate", "ticket": t["id"], "owner": t.get("owner", ""), "reason": "an active ticket already tracks this; your text was added to it as a note"}, t, "Note added (duplicate request from %s)" % by
        return {"state": "created", "ticket": t["id"], "owner": by}, t, "New ticket from a model"
    if action not in ("status", "note", "change_request", "move"):
        raise ValueError("action must be create, status, note, change_request or move")
    t = s.find(str(v.get("ticket", "")))
    owner = t.get("owner", "")
    if action == "change_request":
        if owner and canonical(owner) == canonical(by):
            raise ValueError("you own this ticket; change it directly with status or note")
        s.change_request(t["id"], str(v.get("text", "")), by)
        return {"state": "change_requested", "ticket": t["id"], "owner": owner}, t, "Change request from %s (owner: %s); approve with: ticket.py assign %s %s" % (by, owner or "none", t["id"], by)
    if action == "move":
        q = str(v.get("queue", ""))
        if q not in MODEL_QUEUES:
            raise ValueError("models may move a ticket to %s (cancelled and obsolete are owner-only; file a change_request)" % ", ".join(MODEL_QUEUES))
        new_owner = plan_move(by, "agent", t, q)
        take = bool(t.get("shared") and owner and new_owner)
        blocked = v.get("blocked") if isinstance(v.get("blocked"), bool) else None
        t, old = s.move(t["id"], q, blocked, str(v.get("note", "")), by, str(v.get("pr", "")), owner=new_owner, shared_take=take)
        return {"state": "updated", "ticket": t["id"], "status": t["status"], "queue": q, "owner": t.get("owner", "")}, t, "%s -> %s (%s)" % (old, t["status"], by) if old != t["status"] else "queue -> %s (%s)" % (q, by)
    if not may(by, "agent", action, t):
        raise Refused(refusal(by, action, t))
    if action == "status":
        st = str(v.get("status", ""))
        if st not in MODEL_STATUSES:
            raise ValueError("models may set status %s (dropping is owner-only)" % ", ".join(MODEL_STATUSES))
        if not owner:
            t["owner"] = by  # first model to work an unowned ticket claims it
        t, old = s.set_status(t["id"], st, str(v.get("note", "")), str(v.get("pr", "")), by)
        return {"state": "updated", "ticket": t["id"], "status": st, "owner": t["owner"]}, t, "%s -> %s (%s)" % (old, st, by)
    t = s.note(t["id"], str(v.get("text", "")), by)  # may() above: own or shared ticket (an unowned one must be claimed first)
    return {"state": "updated", "ticket": t["id"]}, t, "Note added (%s)" % by


def write_open_list(qp, store_dir=None):
    """Read-only list of active tickets next to the requests, so a sandboxed model can see what exists."""
    with Store(store_dir) as s:
        rows = [t for t in s.data["tickets"] if t["status"] in ACTIVE]
    order = {"high": 0, "normal": 1, "low": 2}
    rows.sort(key=lambda x: (order[x["priority"]], x["id"]))
    text = ["# Open tickets (generated %s; do not edit, write request files instead)\n" % now()]
    text += ["- %s [%s] %s %s%s%s" % (t["id"], t["status"], t["priority"], t["title"], " (%s)" % t["project"] if t["project"] else "", " owner: %s" % t["owner"] if t.get("owner") else "") for t in rows]
    if not rows:
        text.append("Nothing open.")
    tmp = qp / ".OPEN-TICKETS.md.tmp"
    tmp.write_text("\n".join(text) + "\n")
    os.replace(tmp, qp / "OPEN-TICKETS.md")


def ensure_queues(globs):
    """Create the tickets queue folder in every project that has a .opencode folder, owned like it, so a sandboxed model can see
    OPEN-TICKETS.md and write requests even in a project that never had a ticket (ingest only reads folders that already exist)."""
    for pattern in globs:
        if not pattern.endswith("/.opencode/tickets"):
            continue
        for parent in sorted(glob.glob(pattern[: -len("/tickets")])):
            pp = pathlib.Path(parent)
            q = pp / "tickets"
            if pp.is_symlink() or not pp.is_dir() or pp.resolve() != pp or q.exists() or q.is_symlink():
                continue
            try:
                st = pp.stat()
                q.mkdir()
                os.chown(q, st.st_uid, st.st_gid)
                os.chmod(q, st.st_mode & 0o7777)
            except OSError as exc:
                print("could not create the queue %s: %s" % (q, exc), file=sys.stderr)


def ingest(store_dir=None):
    done = []
    globs = os.environ.get("WATOOM_TICKET_QUEUE_GLOBS", "/data/ai/projects/*/*/.opencode/tickets").split(":")
    ensure_queues(globs)
    for pattern in globs:
        for q in sorted(glob.glob(pattern)):
            qp = pathlib.Path(q)
            if qp.is_symlink() or not qp.is_dir() or qp.resolve() != qp:
                continue
            for f in sorted(qp.glob("*.json"), key=lambda x: (x.lstat().st_mtime_ns, x.name)):  # oldest first: a later "done" must win
                if f.name.endswith(".status.json") or f.with_name(f.name[:-5] + ".status.json").exists():
                    continue
                rid = f.name[:-5]
                status = {"schema": 1, "id": rid}
                try:
                    v = json.loads(safe_regular(f))
                    if not isinstance(v, dict) or v.get("schema") != 1 or v.get("id") != rid or not REQUEST_ID.fullmatch(rid):
                        raise ValueError("needs schema 1 and an id equal to the file name ([a-z0-9-]{1,64})")
                    with Store(store_dir) as s:
                        rec, t, headline = apply_request(s, v, rid, qp, str(f))
                    status.update(rec)
                    done.append((t, headline))
                except (ValueError, OSError, json.JSONDecodeError, SystemExit) as exc:
                    status.update(state="rejected", reason=str(exc)[:300])
                try:
                    f.with_name(rid + ".status.json").write_text(json.dumps(status, indent=1))
                except OSError as exc:
                    print("could not write status for %s: %s" % (f, exc), file=sys.stderr)
            try:
                write_open_list(qp, store_dir)
            except OSError as exc:
                print("could not write the open list in %s: %s" % (qp, exc), file=sys.stderr)
    for t, headline in done:
        sync(t["id"], headline, store_dir)
    return [t for t, _ in done]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("title")
    a.add_argument("--body", default="")
    a.add_argument("--project", default="")
    a.add_argument("--priority", default="normal", choices=PRIORITIES)
    a.add_argument("--pr", default="")
    a.add_argument("--by", default=os.environ.get("USER", ""))
    a.add_argument("--queue", default=NEW_TICKET_QUEUE, choices=INTAKE_QUEUES, help="board column (default %s)" % NEW_TICKET_QUEUE)
    a.add_argument("--shared", action="store_true", help="global ticket: any agent may work it")
    ls = sub.add_parser("list")
    ls.add_argument("--status", nargs="*", choices=STATUSES)
    ls.add_argument("--project", default="")
    ls.add_argument("--all", action="store_true")
    ls.add_argument("--queue", nargs="*", choices=QUEUES, help="only these board columns")
    mv = sub.add_parser("move", help="put a ticket in a board column; the status follows (wip: doing, completed: done, cancelled/obsolete: dropped)")
    mv.add_argument("id")
    mv.add_argument("queue", choices=QUEUES)
    mv.add_argument("--lane", default=None, help="wip only: the agent whose lane it goes in (sets the owner); '-' = Unassigned")
    bl = mv.add_mutually_exclusive_group()
    bl.add_argument("--blocked", dest="blocked", action="store_true", default=None)
    bl.add_argument("--unblocked", dest="blocked", action="store_false")
    mv.add_argument("--note", default="")
    mv.add_argument("--pr", default="")
    mv.add_argument("--by", default=os.environ.get("USER", ""))
    sub.add_parser("migrate", help="optional: write the board fields into every ticket once (no status change, no Discord)")
    sh = sub.add_parser("show")
    sh.add_argument("id")
    st = sub.add_parser("status")
    st.add_argument("id")
    st.add_argument("status", choices=STATUSES)
    st.add_argument("--note", default="")
    st.add_argument("--pr", default="")
    st.add_argument("--by", default=os.environ.get("USER", ""))
    nt = sub.add_parser("note")
    nt.add_argument("id")
    nt.add_argument("text")
    nt.add_argument("--by", default=os.environ.get("USER", ""))
    asg = sub.add_parser("assign", help="owner only: give a ticket to one model (approves its change request); '-' clears the owner")
    asg.add_argument("id")
    asg.add_argument("owner")
    asg.add_argument("--by", default=os.environ.get("USER", ""))
    rp = sub.add_parser("repost", help="make Discord match the store: edit each ticket's one message (or post it once if it has none, e.g. after the channels were cleared)")
    rp.add_argument("--skip", nargs="*", default=[], help="ticket ids to leave out")
    sub.add_parser("ingest")
    sub.add_parser("digest")
    args = ap.parse_args(argv)

    if args.cmd == "add":
        with Store() as s:
            t, dup = s.add_or_duplicate(args.title, args.body, args.project, args.priority, args.by, args.pr, queue=args.queue, shared=args.shared)
        sent = sync(t["id"], "Note added (duplicate request)" if dup else "New ticket")
        print("%s %s%s" % (t["id"], "already tracks this; note added instead of a new ticket" if dup else "created", "" if sent else " (not posted to Discord)"))
    elif args.cmd == "list":
        with Store() as s:
            want = set(args.status or (STATUSES if args.all else ACTIVE))
            rows = [t for t in s.data["tickets"] if t["status"] in want and (not args.project or t["project"] == args.project)]
            if args.queue:
                rows = [t for t in s.data["tickets"] if queue_of(t) in args.queue and (not args.project or t["project"] == args.project) and (not args.status or t["status"] in want)]
        order = {"high": 0, "normal": 1, "low": 2}
        for t in sorted(rows, key=lambda x: (order[x["priority"]], x["id"])):
            print(line(t))
        print("%d ticket(s)" % len(rows))
    elif args.cmd == "show":
        with Store() as s:
            t = s.find(args.id)
        print(line(t))
        for k in ("body", "by", "owner", "source", "created", "updated"):
            if t.get(k):
                print("%s: %s" % (k, t[k]))
        if "queue" in t or t.get("shared"):  # board fields: only tickets that use them print these lines
            print("queue: %s%s" % (queue_of(t), "  (shared: any agent may work it)" if t.get("shared") else ""))
        for c in t.get("change_requests", []):
            print("  change request (%s) %s %s: %s" % (c["state"], c["time"], c["by"], c["text"]))
        for n in t["notes"]:
            print("  - %s %s%s" % (n["time"], (n["by"] + ": ") if n["by"] else "", n["text"]))
    elif args.cmd == "status":
        with Store() as s:
            t, old = s.set_status(args.id, args.status, args.note, args.pr, args.by)
        sent = sync(t["id"], "%s -> %s" % (old, t["status"]))
        print("%s %s -> %s%s" % (t["id"], old, t["status"], "" if sent else " (not posted to Discord)"))
    elif args.cmd == "note":
        with Store() as s:
            t = s.note(args.id, args.text, args.by)
        sync(t["id"], "Note added")
        print("%s noted" % t["id"])
    elif args.cmd == "assign":
        with Store() as s:
            t, old = s.assign(args.id, "" if args.owner == "-" else args.owner, args.by)
        sync(t["id"], "Owner changed: %s -> %s" % (old or "-", t["owner"] or "-"))
        print("%s owner %s -> %s" % (t["id"], old or "-", t["owner"] or "-"))
    elif args.cmd == "move":
        # Operator path, unenforced like status/note/assign (owner decision 3). --lane sets the owner like assign.
        with Store() as s:
            t = s.find(args.id)
            owner = None if args.lane is None else ("" if args.lane == "-" else canonical(args.lane))
            if owner is not None and args.queue != "wip":
                raise SystemExit("--lane applies to the wip queue only")
            t, old = s.move(t["id"], args.queue, args.blocked, args.note, args.by, args.pr, owner=owner)
        headline = "%s -> %s (%s)" % (old, t["status"], args.by) if old != t["status"] else "queue -> %s (%s)" % (args.queue, args.by)
        sent = sync(t["id"], headline)
        print("%s %s -> %s [%s]%s" % (t["id"], old, t["status"], args.queue, "" if sent else " (not posted to Discord)"))
    elif args.cmd == "migrate":
        with Store() as s:
            n = s.migrate()
        print("migrated %d ticket(s)" % n)
    elif args.cmd == "repost":
        with Store() as s:
            rows = [t for t in s.data["tickets"] if t["id"] not in {x.upper() for x in args.skip}]
        sent = 0
        for t in rows:
            if sync(t["id"], "Moved to the %s channel" % channel_for(t)):
                sent += 1
            time.sleep(0.8)  # Discord webhooks allow about 5 posts per 2 seconds
        print("reposted %d of %d ticket(s) into their status channels" % (sent, len(rows)))
    elif args.cmd == "ingest":
        created = ingest()
        print("ingested %d request(s): %s" % (len(created), ", ".join(t["id"] for t in created) or "none"))
    elif args.cmd == "digest":
        with Store() as s:
            rows = [t for t in s.data["tickets"] if t["status"] in ACTIVE]
        order = {"high": 0, "normal": 1, "low": 2}
        rows.sort(key=lambda x: (order[x["priority"]], x["id"]))
        text = "\n".join("%s %s **%s** %s" % (ICONS[t["status"]], t["id"], t["priority"], t["title"][:90]) for t in rows) or "Nothing open."
        sent = post({"embeds": [{"title": "Open tickets (%d)" % len(rows), "description": text[:3900], "color": 0x3B82F6, "timestamp": now()}]})
        print("digest: %d open%s" % (len(rows), "" if sent else " (not posted to Discord)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
