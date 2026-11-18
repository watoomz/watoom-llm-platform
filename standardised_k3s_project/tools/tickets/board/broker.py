#!/usr/bin/env python3
"""Root ticket-board broker (stdlib only): every board read and write goes through ticket.py.

The UI pod (server.py) authenticates people and agents and forwards one JSON line per request over a Unix socket; only the
configured UI uid may connect (SO_PEERCRED). The pod decides "actor" and "role" from the credential; this broker trusts those
two values and nothing else beyond the documented inputs. Writes use ticket.Store (one exclusive flock for the whole
read-modify-write, atomic replace), the access rule is ticket.may()/plan_move(), and Discord is updated by ticket.sync() on one
background thread after the store is written, so a slow Discord call never holds a browser request (kanban-design.md 4.3, 4.4).
Reads use ticket.load() and never take the lock or rewrite the file.
"""
import argparse
import copy
import errno
import hashlib
import json
import os
import pathlib
import queue as queue_mod
import re
import socket
import socketserver
import struct
import sys
import threading

HERE = pathlib.Path(__file__).resolve().parent
for _d in (HERE, HERE.parent):  # installed: ticket.py next to this file; source tree: tools/tickets/ticket.py
    if (_d / "ticket.py").is_file():
        sys.path.insert(0, str(_d))
        break
import ticket as tk  # noqa: E402

TICKET_ID = re.compile(r"T-\d{1,6}")
ACTOR = re.compile(r"[A-Za-z0-9][A-Za-z0-9:._-]{0,59}")
LIMITS = {"title": 200, "body": 4000, "note": 1000, "text": 1000, "project": 80, "pr": 300}
MAX_LINE = 64 * 1024
QUEUE_LABELS = {"requests": "Requests", "issues": "Issues", "backlog": "Backlog", "wip": "Work in progress",
                "completed": "Completed", "cancelled": "Cancelled", "obsolete": "Obsolete"}
CARD_DROP = ("body", "notes", "change_requests", "source", "discord")


class Error(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def text(value, field, required=False):
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise Error("invalid", "%s must be text" % field)
    if len(value) > LIMITS[field]:
        raise Error("invalid", "%s is longer than %d characters" % (field, LIMITS[field]))
    if required and not value.strip():
        raise Error("invalid", "%s is required" % field)
    return value


class Board:
    def __init__(self, store_dir, agents_file, syncer=None):
        self.dir = pathlib.Path(store_dir)
        self.agents_file = pathlib.Path(agents_file)
        self.syncer = syncer or (lambda tid, headline: None)

    # ---- identity -------------------------------------------------------------------------------------------------
    def agents(self):
        return tk.load_agents(self.agents_file)

    def owner_id(self, agents):
        return next(a["id"] for a in agents if a["role"] == "owner")

    def check_actor(self, actor, role, agents):
        if role not in ("owner", "agent") or not isinstance(actor, str) or not ACTOR.fullmatch(actor):
            raise Error("invalid", "bad actor")
        if (role == "owner") != (tk.canonical(actor, agents) == self.owner_id(agents)):
            raise Error("forbidden", "actor and role do not match the registry")

    # ---- reads (lock-free) ----------------------------------------------------------------------------------------
    def etag(self, actor, role):
        parts = [actor, role]
        for p in (self.dir / "tickets.json", self.agents_file):
            try:
                st = p.stat()
                parts += [str(st.st_mtime_ns), str(st.st_size)]
            except OSError:
                parts.append("-")
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:20]

    def can(self, t, actor, role, agents):
        c = {a: tk.may(actor, role, a, t, agents) for a in ("move", "note", "edit", "share", "assign", "drop")}
        own = tk.canonical(t.get("owner", ""), agents) == tk.canonical(actor, agents)
        c["change_request"] = role != "owner" and not own
        c["decide"] = role == "owner"
        return c

    def lane_of(self, t, agents):
        return tk.canonical(t.get("owner", ""), agents) if tk.queue_of(t) == "wip" else None

    def card(self, t, actor, role, agents):
        c = {k: v for k, v in t.items() if k not in CARD_DROP}
        c.setdefault("owner", "")
        c["shared"] = bool(t.get("shared"))
        c["queue"] = tk.queue_of(t)
        c["lane"] = self.lane_of(t, agents)
        c["owner_label"] = tk.label_of(t["owner"], agents) if t.get("owner") else ""
        c["note_count"] = len(t.get("notes") or [])
        c["pending_requests"] = sum(1 for x in t.get("change_requests") or [] if x.get("state") == "pending")
        c["last_note"] = (t.get("notes") or [{}])[-1].get("time", "")
        c["can"] = self.can(t, actor, role, agents)
        return c

    def view(self, t, actor, role, agents):
        v = copy.deepcopy(t)
        v.setdefault("owner", "")
        v.setdefault("change_requests", [])
        v.pop("discord", None)
        v["shared"] = bool(t.get("shared"))
        v["queue"] = tk.queue_of(t)
        v["lane"] = self.lane_of(t, agents)
        v["owner_label"] = tk.label_of(t["owner"], agents) if t.get("owner") else ""
        v["by_label"] = tk.label_of(t.get("by", ""), agents) if t.get("by") else ""
        for n in v.get("notes", []) + v["change_requests"]:
            n["by_label"] = tk.label_of(n.get("by", ""), agents) if n.get("by") else ""
        v["can"] = self.can(t, actor, role, agents)
        return v

    def board(self, actor, role, etag=None):
        agents = self.agents()
        self.check_actor(actor, role, agents)
        tag = self.etag(actor, role)
        if etag and etag == tag:
            return {"not_modified": True, "etag": tag}
        data = tk.load(self.dir)
        tickets = data["tickets"]
        known = [{"id": a["id"], "label": a["label"]} for a in agents]
        seen = {a["id"] for a in agents}
        for t in tickets:  # every owner ever used, so the owner select offers new models too
            o = tk.canonical(t.get("owner", ""), agents)
            if o and o not in seen:
                known.append({"id": o, "label": tk.label_of(o, agents)})
                seen.add(o)
        return {"etag": tag, "queues": [{"id": q, "label": QUEUE_LABELS[q]} for q in tk.QUEUES], "lanes": tk.lanes(data, agents),
                "agents": known, "projects": sorted({t["project"] for t in tickets if t.get("project")}),
                "tickets": [self.card(t, actor, role, agents) for t in tickets]}

    def find(self, tickets, tid):
        if not isinstance(tid, str) or not TICKET_ID.fullmatch(tid):
            raise Error("invalid", "bad ticket id")
        for t in tickets:
            if t["id"] == tid:
                return t
        raise Error("notfound", "no such ticket: %s" % tid)

    def ticket(self, actor, role, tid):
        agents = self.agents()
        self.check_actor(actor, role, agents)
        return self.view(self.find(tk.load(self.dir)["tickets"], tid), actor, role, agents)

    def summary(self):
        """Counts and lane labels only: no titles, no text (served without login to the Glance widget)."""
        agents = self.agents()
        data = tk.load(self.dir)
        counts = {q: 0 for q in tk.QUEUES}
        lane_counts = {}
        for t in data["tickets"]:
            q = tk.queue_of(t)
            counts[q] += 1
            if q == "wip":
                lane = tk.canonical(t.get("owner", ""), agents)
                lane_counts[lane] = lane_counts.get(lane, 0) + 1
        tickets = data["tickets"]
        return {"queues": counts, "blocked": sum(t["status"] == "blocked" for t in tickets),
                "high_open": sum(t["status"] in tk.ACTIVE and t.get("priority") == "high" for t in tickets),
                "pending_change_requests": sum(c.get("state") == "pending" for t in tickets for c in t.get("change_requests") or []),
                "lanes": [{"label": l["label"], "count": lane_counts.get(l["id"], 0)} for l in tk.lanes(data, agents)],
                "total": len(tickets), "updated": max((t.get("updated", "") for t in tickets), default="")}

    # ---- writes (Store + flock) ------------------------------------------------------------------------------------
    def _write(self, actor, role, tid, if_updated, change):
        """Run change(store, ticket, agents) -> headline under the store lock; return the view and queue the Discord sync."""
        agents = self.agents()
        self.check_actor(actor, role, agents)
        if if_updated is not None and not isinstance(if_updated, str):
            raise Error("invalid", "if_updated must be a time string")
        with tk.Store(self.dir) as s:
            t = self.find(s.data["tickets"], tid)
            if if_updated and t.get("updated") != if_updated:
                raise Error("conflict", "%s changed since you loaded it (updated %s); reload it" % (tid, t.get("updated")))
            try:
                headline = change(s, t, agents)
            except tk.Refused as e:
                raise Error("forbidden", str(e))
            except SystemExit as e:
                raise Error("notfound", str(e))
            except Error:
                raise
            except ValueError as e:
                raise Error("invalid", str(e))
            t = s.find(tid)
            result = {"ticket": self.view(t, actor, role, agents), "card": self.card(t, actor, role, agents)}
        if headline:
            self.syncer(tid, headline)
        return result

    def refuse_unless(self, actor, role, action, t, agents):
        if not tk.may(actor, role, action, t, agents):
            raise tk.Refused(tk.refusal(actor, action, t))

    def create(self, actor, role, req):
        agents = self.agents()
        self.check_actor(actor, role, agents)
        title = text(req.get("title"), "title", True)
        body = text(req.get("body"), "body")
        project = text(req.get("project"), "project")
        priority = req.get("priority") or "normal"
        q = req.get("queue") or tk.NEW_TICKET_QUEUE
        shared = req.get("shared", False)
        if priority not in tk.PRIORITIES or q not in tk.INTAKE_QUEUES or not isinstance(shared, bool):
            raise Error("invalid", "priority must be low/normal/high, queue requests/issues/backlog, shared true/false")
        with tk.Store(self.dir) as s:
            t, dup = s.add_or_duplicate(title, body, project, priority, by=actor, source="board",
                                        owner=actor if role == "agent" else "", queue=q, shared=shared)
        self.syncer(t["id"], "Note added (duplicate request from %s)" % actor if dup else "New ticket")
        return {"ticket": t["id"], "duplicate": dup}

    def move(self, actor, role, tid, req):
        q = req.get("queue")
        lane = req.get("lane")
        blocked = req.get("blocked")
        note = text(req.get("note"), "note")
        pr = text(req.get("pr"), "pr")
        if lane is not None and not isinstance(lane, str) or blocked is not None and not isinstance(blocked, bool):
            raise Error("invalid", "lane must be text, blocked true/false")

        def change(s, t, agents):
            take = bool(t.get("shared") and t.get("owner"))
            new_owner = tk.plan_move(actor, role, t, q, lane, agents)
            t2, old = s.move(tid, q, blocked, note, actor, pr, owner=new_owner, shared_take=take and new_owner is not None and role != "owner")
            return "%s -> %s (%s)" % (old, t2["status"], actor) if old != t2["status"] else "queue -> %s (%s)" % (q, actor)
        return self._write(actor, role, tid, req.get("if_updated"), change)

    def note(self, actor, role, tid, req):
        body = text(req.get("text"), "text", True)

        def change(s, t, agents):
            self.refuse_unless(actor, role, "note", t, agents)
            s.note(tid, body, actor)
            return "Note added (%s)" % actor
        return self._write(actor, role, tid, req.get("if_updated"), change)

    def edit(self, actor, role, tid, req):
        fields = {k: req[k] for k in ("title", "body", "priority", "project", "pr") if k in req}
        for k in fields:
            if k != "priority":
                text(fields[k], k, k == "title")
        shared, owner = req.get("shared"), req.get("owner")
        if shared is not None and not isinstance(shared, bool) or owner is not None and not isinstance(owner, str):
            raise Error("invalid", "shared must be true/false and owner text")
        if not fields and shared is None and owner is None:
            raise Error("invalid", "nothing to change")

        def change(s, t, agents):
            done = []
            if fields:
                self.refuse_unless(actor, role, "edit", t, agents)
            if shared is not None and shared != bool(t.get("shared")):
                self.refuse_unless(actor, role, "share", t, agents)
            if owner is not None and tk.canonical(owner, agents) != tk.canonical(t.get("owner", ""), agents):
                self.refuse_unless(actor, role, "assign", t, agents)
                if owner and not ACTOR.fullmatch(owner):
                    raise Error("invalid", "bad owner name")
                s.assign(tid, tk.canonical(owner, agents) if owner else "", actor)
                done.append("Owner changed: %s" % (owner or "-"))
            if fields:
                before = len(t["notes"])
                s.edit(tid, fields, actor)
                if len(t["notes"]) > before:
                    done.append("Edited")
            if shared is not None:
                before = len(t["notes"])
                s.set_shared(tid, shared, actor)
                if len(t["notes"]) > before:
                    done.append("Shared: %s" % ("on" if shared else "off"))
            return "; ".join(done) + " (%s)" % actor if done else ""
        return self._write(actor, role, tid, req.get("if_updated"), change)

    def change_request(self, actor, role, tid, req):
        body = text(req.get("text"), "text", True)

        def change(s, t, agents):
            if role == "agent" and tk.canonical(t.get("owner", ""), agents) == tk.canonical(actor, agents):
                raise Error("invalid", "you own this ticket; change it directly")
            s.change_request(tid, body, actor)
            return "Change request from %s (owner: %s)" % (actor, t.get("owner") or "none")
        return self._write(actor, role, tid, req.get("if_updated"), change)

    def decide(self, actor, role, tid, req):
        index, decision = req.get("index"), req.get("decision")
        note = text(req.get("note"), "note")
        if role != "owner":
            raise Error("forbidden", "only the owner decides change requests")
        if not isinstance(index, int) or isinstance(index, bool) or decision not in ("assign", "share", "reject"):
            raise Error("invalid", "index must be a number and decision assign, share or reject")

        def change(s, t, agents):
            s.decide_change_request(tid, index, decision, note, actor)
            return "Change request %s (%s)" % ({"assign": "approved: owner changed", "share": "approved: ticket shared", "reject": "rejected"}[decision], actor)
        return self._write(actor, role, tid, None, change)

    def handle(self, req):
        if not isinstance(req, dict):
            raise Error("invalid", "request must be an object")
        op, actor, role, tid = req.get("op"), req.get("actor"), req.get("role"), req.get("ticket")
        args = req.get("args") or {}
        if not isinstance(args, dict):
            raise Error("invalid", "args must be an object")
        if op == "summary":
            return self.summary()
        if op == "board":
            return self.board(actor, role, req.get("etag"))
        if op == "ticket":
            return self.ticket(actor, role, tid)
        if op == "create":
            return self.create(actor, role, args)
        writes = {"move": self.move, "note": self.note, "edit": self.edit, "change_request": self.change_request, "decide": self.decide}
        if op in writes:
            return writes[op](actor, role, tid, args)
        raise Error("invalid", "unsupported operation")


class Syncer:
    """One background thread that runs ticket.sync() in order, so the browser never waits for Discord."""

    def __init__(self, store_dir):
        self.store_dir = str(store_dir)
        self.q = queue_mod.Queue()
        threading.Thread(target=self.run, daemon=True).start()

    def __call__(self, tid, headline):
        self.q.put((tid, headline))

    def run(self):
        while True:
            tid, headline = self.q.get()
            try:
                tk.sync(tid, headline, self.store_dir)
            except Exception as exc:  # sync() never raises; this is only a guard so the thread survives
                print("discord: sync failed (%s)" % type(exc).__name__, file=sys.stderr)


def respond(board, raw):
    try:
        if len(raw) > MAX_LINE:
            raise Error("invalid", "oversized request")
        return {"result": board.handle(json.loads(raw))}
    except Error as e:
        return {"error": str(e)[:400], "code": e.code}
    except (ValueError, KeyError, TypeError, UnicodeDecodeError) as e:
        return {"error": str(e)[:300], "code": "invalid"}
    except Exception as e:
        return {"error": type(e).__name__ + ": " + str(e)[:200], "code": "failed"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    a = p.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("ticket broker requires root")
    config = json.loads(pathlib.Path(a.config).read_text())
    # ticket.py reads these for sync() and webhooks; set them once so the CLI, the timers and the broker share one store.
    os.environ["WATOOM_TICKETS_DIR"] = config["store_dir"]
    os.environ["WATOOM_TICKET_AGENTS_FILE"] = config["agents_file"]
    if config.get("webhook_file"):
        os.environ["WATOOM_TICKET_WEBHOOK_FILE"] = config["webhook_file"]
    board = Board(config["store_dir"], config["agents_file"], Syncer(config["store_dir"]))

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            uid = struct.unpack("3i", self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))[1]
            if uid != config["ui_uid"]:
                response = {"error": "unauthorized peer", "code": "forbidden"}
            else:
                response = respond(board, self.rfile.readline(MAX_LINE + 1))
            try:
                self.wfile.write(json.dumps(response).encode() + b"\n")
            except OSError:
                pass

    path = pathlib.Path(config["socket"])
    if path.exists() or path.is_symlink():
        if not path.is_socket() or path.lstat().st_uid != 0:
            raise SystemExit("refuse foreign socket path")
        path.unlink()

    class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
        daemon_threads = True

    with Server(str(path), Handler) as server:
        try:
            os.removexattr(path, "system.posix_acl_access")
        except OSError as error:
            if error.errno not in (errno.ENODATA, errno.ENOTSUP):
                raise
        os.chown(path, 0, config["ui_gid"])
        os.chmod(path, 0o660)
        try:
            server.serve_forever()
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
