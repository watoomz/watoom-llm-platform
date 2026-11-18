"""Tickets board tests (stdlib unittest, same style as tools/skill-editor/test_skill_editor.py). Run from tools/tickets/board:
python3 -m unittest test_board"""
import hashlib
import json
import os
import pathlib
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import broker as bk
from broker import Board, Error, respond, tk
from server import Application, BrokerError, Tokens

AGENTS = {"agents": [
    {"id": "owner", "label": "Owner", "role": "owner", "lane": False, "aliases": ["root"]},
    {"id": "claude-sonnet", "label": "Sonnet", "role": "agent", "lane": True, "aliases": ["claude-sonnet-3a"]},
    {"id": "claude-sabre", "label": "Sabre", "role": "agent", "lane": True, "aliases": ["claude-sabre-fd"]}]}
ORIGIN = "https://glance.example"


class Fixture:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.store = self.root / "tickets"
        self.store.mkdir()
        self.agents = self.root / "agents.json"
        self.agents.write_text(json.dumps(AGENTS))
        os.environ["WATOOM_TICKETS_DIR"] = str(self.store)
        os.environ["WATOOM_TICKET_AGENTS_FILE"] = str(self.agents)
        os.environ["WATOOM_TICKET_WEBHOOK_FILE"] = str(self.root / "none")
        self.synced = []
        self.board = Board(self.store, self.agents, lambda tid, h: self.synced.append((tid, h)))

    def seed(self, *tickets):
        with tk.Store(self.store) as s:
            for kw in tickets:
                kw = dict(kw)
                status, queue, owner, shared = kw.pop("status", "open"), kw.pop("queue", None), kw.pop("owner", ""), kw.pop("shared", False)
                t = s.add(kw.pop("title", "t"), owner=owner, shared=shared, **kw)
                t["status"] = status
                if queue:
                    t["queue"] = queue
                else:
                    t.pop("queue")  # a legacy ticket: no board fields
                    t.pop("shared")


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()
        self.b = self.f.board

    def tearDown(self):
        self.f.tmp.cleanup()
        os.environ.pop("WATOOM_TICKET_AGENTS_FILE", None)

    def card(self, tid, actor="owner", role="owner"):
        return next(c for c in self.b.board(actor, role)["tickets"] if c["id"] == tid)

    def test_board_on_a_fresh_store(self):
        b = self.b.board("owner", "owner")
        self.assertEqual(b["tickets"], [])
        self.assertEqual([q["id"] for q in b["queues"]], list(tk.QUEUES))
        self.assertEqual([l["id"] for l in b["lanes"]], ["claude-sonnet", "claude-sabre", ""])
        self.assertFalse((self.f.store / "tickets.json").exists())  # reads never create or rewrite the store

    def test_legacy_tickets_land_in_default_columns_and_lanes(self):
        self.f.seed({"title": "open one"}, {"title": "doing unowned", "status": "doing"}, {"title": "qwen", "status": "blocked", "owner": "model:Swift-Qwen-coder"},
                    {"title": "done", "status": "done"}, {"title": "dropped", "status": "dropped"})
        b = self.b.board("owner", "owner")
        self.assertEqual([c["queue"] for c in b["tickets"]], ["backlog", "wip", "wip", "completed", "cancelled"])
        self.assertEqual([c["lane"] for c in b["tickets"][:3]], [None, "", "model:Swift-Qwen-coder"])
        self.assertEqual([l["label"] for l in b["lanes"]], ["Sonnet", "Sabre", "Swift Qwen coder", "Unassigned"])
        self.assertNotIn("body", b["tickets"][0])
        self.assertNotIn("notes", b["tickets"][0])

    def test_etag_changes_with_the_store_and_the_actor(self):
        self.f.seed({"title": "a"})
        tag = self.b.board("owner", "owner")["etag"]
        self.assertTrue(self.b.board("owner", "owner", tag)["not_modified"])
        self.assertNotEqual(self.b.board("claude-sonnet", "agent")["etag"], tag)
        self.b.note("owner", "owner", "T-0001", {"text": "x"})
        self.assertNotIn("not_modified", self.b.board("owner", "owner", tag))

    def test_summary_is_counts_only(self):
        self.f.seed({"title": "secret title", "priority": "high"}, {"title": "b", "status": "blocked", "owner": "claude-sonnet-3a"})
        with tk.Store(self.f.store) as s:
            s.change_request("T-0002", "please", "claude-sabre")
        out = self.b.summary()
        self.assertNotIn("secret", json.dumps(out))
        self.assertEqual((out["queues"]["backlog"], out["queues"]["wip"], out["blocked"], out["high_open"], out["pending_change_requests"]), (1, 1, 1, 1, 1))
        self.assertEqual(out["lanes"][0], {"label": "Sonnet", "count": 1})

    def test_create_defaults_owner_and_queue(self):
        r = self.b.create("claude-sabre", "agent", {"title": "Agent made", "shared": True})
        self.assertEqual(r, {"ticket": "T-0001", "duplicate": False})
        r = self.b.create("owner", "owner", {"title": "Human made", "queue": "issues"})
        t1, t2 = tk.load(self.f.store)["tickets"]
        self.assertEqual((t1["owner"], t1["queue"], t1["shared"], t2["owner"], t2["queue"]), ("claude-sabre", "requests", True, "", "issues"))
        self.assertEqual(self.f.synced[0], ("T-0001", "New ticket"))
        with self.assertRaises(Error):
            self.b.create("owner", "owner", {"title": "x", "queue": "wip"})
        with self.assertRaises(Error):
            self.b.create("owner", "owner", {"title": "x" * 201})
        self.assertTrue(self.b.create("owner", "owner", {"title": "Agent made"})["duplicate"])

    def test_owner_moves_anything_and_assigns_by_lane(self):
        self.f.seed({"title": "a"})
        r = self.b.move("owner", "owner", "T-0001", {"queue": "wip", "lane": "claude-sabre"})
        self.assertEqual((r["card"]["status"], r["card"]["lane"], r["card"]["owner"]), ("doing", "claude-sabre", "claude-sabre"))
        self.assertEqual(self.f.synced[-1], ("T-0001", "open -> doing (owner)"))
        r = self.b.move("owner", "owner", "T-0001", {"queue": "wip", "lane": "", "blocked": True})
        self.assertEqual((r["card"]["status"], r["card"]["owner"]), ("blocked", ""))
        r = self.b.move("owner", "owner", "T-0001", {"queue": "obsolete", "note": "superseded"})
        self.assertEqual((r["card"]["status"], r["card"]["queue"]), ("dropped", "obsolete"))

    def test_agent_rules_on_moves(self):
        self.f.seed({"title": "unowned"}, {"title": "sabre's", "owner": "claude-sabre-fd", "status": "doing"}, {"title": "shared", "owner": "claude-sabre", "shared": True, "queue": "backlog"})
        with self.assertRaises(Error) as e:
            self.b.move("claude-sonnet", "agent", "T-0002", {"queue": "completed"})
        self.assertEqual(e.exception.code, "forbidden")
        self.assertIn("change_request", str(e.exception))
        with self.assertRaises(Error):
            self.b.move("claude-sonnet", "agent", "T-0001", {"queue": "wip", "lane": "claude-sabre"})  # not its lane
        with self.assertRaises(Error):
            self.b.move("claude-sonnet", "agent", "T-0001", {"queue": "cancelled"})
        r = self.b.move("claude-sonnet", "agent", "T-0001", {"queue": "wip", "lane": "claude-sonnet"})
        self.assertEqual(r["card"]["owner"], "claude-sonnet")  # claimed
        r = self.b.move("claude-sabre", "agent", "T-0002", {"queue": "completed", "note": "tested"})  # alias owner
        self.assertEqual(r["card"]["status"], "done")
        r = self.b.move("claude-sonnet", "agent", "T-0003", {"queue": "wip"})
        self.assertEqual(r["card"]["owner"], "claude-sonnet")
        self.assertTrue(any(n["text"] == "owner changed: claude-sabre -> claude-sonnet (shared ticket)" for n in r["ticket"]["notes"]))

    def test_if_updated_conflict_and_failed_write_leaves_store_unchanged(self):
        self.f.seed({"title": "a"})
        before = (self.f.store / "tickets.json").read_text()
        with self.assertRaises(Error) as e:
            self.b.move("owner", "owner", "T-0001", {"queue": "issues", "if_updated": "1999-01-01T00:00:00Z"})
        self.assertEqual(e.exception.code, "conflict")
        with self.assertRaises(Error) as e:
            self.b.note("claude-sonnet", "agent", "T-0001", {"text": "x"})  # claim before note
        self.assertEqual(e.exception.code, "forbidden")
        self.assertEqual((self.f.store / "tickets.json").read_text(), before)
        self.assertEqual(self.f.synced, [])
        with self.assertRaises(Error) as e:
            self.b.note("owner", "owner", "T-0099", {"text": "x"})
        self.assertEqual(e.exception.code, "notfound")

    def test_edit_share_owner_and_permissions(self):
        self.f.seed({"title": "a", "owner": "claude-sabre"})
        t = self.b.ticket("claude-sabre", "agent", "T-0001")
        self.assertEqual(t["can"], {"move": True, "note": True, "edit": True, "share": False, "assign": False, "drop": False, "change_request": False, "decide": False})
        r = self.b.edit("claude-sabre", "agent", "T-0001", {"title": "b", "priority": "high", "if_updated": t["updated"]})
        self.assertEqual(r["ticket"]["notes"][-1]["text"], "title, priority changed")
        with self.assertRaises(Error):
            self.b.edit("claude-sabre", "agent", "T-0001", {"shared": True})
        with self.assertRaises(Error):
            self.b.edit("claude-sonnet", "agent", "T-0001", {"title": "mine now"})
        r = self.b.edit("owner", "owner", "T-0001", {"shared": True, "owner": "claude-sonnet-3a"})
        self.assertEqual((r["ticket"]["shared"], r["ticket"]["owner"]), (True, "claude-sonnet"))
        r = self.b.edit("claude-sabre", "agent", "T-0001", {"body": "shared now, so allowed"})
        self.assertEqual(r["ticket"]["body"], "shared now, so allowed")

    def test_change_requests_and_decisions(self):
        self.f.seed({"title": "a", "owner": "claude-sabre"})
        with self.assertRaises(Error):
            self.b.change_request("claude-sabre", "agent", "T-0001", {"text": "x"})  # owns it
        self.b.change_request("claude-sonnet", "agent", "T-0001", {"text": "let me"})
        with self.assertRaises(Error):
            self.b.decide("claude-sonnet", "agent", "T-0001", {"index": 0, "decision": "assign"})
        r = self.b.decide("owner", "owner", "T-0001", {"index": 0, "decision": "assign"})
        self.assertEqual((r["ticket"]["owner"], r["ticket"]["change_requests"][0]["state"]), ("claude-sonnet", "approved"))
        self.assertEqual(r["ticket"]["change_requests"][0]["by_label"], "Sonnet")

    def test_identity_checks(self):
        for actor, role in (("owner", "agent"), ("claude-sonnet", "owner"), ("../x", "agent"), ("root", "agent"), ("x", "admin")):
            with self.assertRaises(Error):
                self.b.board(actor, role)
        self.assertEqual(self.b.board("model:Brand-New", "agent")["tickets"], [])  # any model name, no registry change

    def test_respond_wraps_errors(self):
        self.assertEqual(respond(self.b, b'{"op":"nope"}')["code"], "invalid")
        self.assertEqual(respond(self.b, b"not json")["code"], "invalid")
        self.assertIn("result", respond(self.b, b'{"op":"summary"}'))


class ServerTests(unittest.TestCase):
    """The HTTP layer against a real Board through an in-process stand-in for the socket."""

    def setUp(self):
        self.f = Fixture()
        self.f.seed({"title": "unowned"}, {"title": "sabre's", "owner": "claude-sabre", "status": "doing"})
        self.requests = []

        def bridge(req):
            self.requests.append(req)
            resp = respond(self.f.board, json.dumps(req).encode())
            if "error" in resp:
                raise BrokerError(resp["error"], resp["code"])
            return resp["result"]
        self.token = "agent-token-for-tests"
        tokens = self.f.root / "tokens.json"
        tokens.write_text(json.dumps({hashlib.sha256(self.token.encode()).hexdigest(): "claude-sonnet",
                                      hashlib.sha256(b"owner-token").hexdigest(): "owner"}))
        self.app = Application("p" * 30, ORIGIN, bridge, "/tickets", Tokens(tokens))
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), self.app.handler())
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d/tickets" % self.srv.server_port

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.f.tmp.cleanup()
        os.environ.pop("WATOOM_TICKET_AGENTS_FILE", None)

    def http(self, method, path, body=None, headers=None, raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(self.url + path, data=data, method=method, headers=headers or {})

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a):
                return None
        try:
            r = urllib.request.build_opener(NoRedirect).open(req, timeout=5)
            return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def login(self):
        code, h, _ = self.http("POST", "/login", raw=b"password=" + b"p" * 30, headers={"Origin": ORIGIN})
        self.assertEqual(code, 303)
        self.assertIn("HttpOnly; SameSite=Strict; Path=/tickets/", h["Set-Cookie"])
        cookie = h["Set-Cookie"].split(";")[0]
        code, _, body = self.http("GET", "/api/session", headers={"Cookie": cookie})
        return cookie, json.loads(body)["csrf"]

    def test_summary_needs_no_login_and_board_does(self):
        code, _, body = self.http("GET", "/api/summary")
        self.assertEqual((code, json.loads(body)["queues"]["backlog"]), (200, 1))
        self.assertEqual(self.http("GET", "/api/board")[0], 401)
        self.assertEqual(self.http("GET", "/")[0], 303)
        self.assertEqual(self.http("GET", "/login")[0], 200)

    def test_owner_login_csrf_origin_and_etag(self):
        self.assertEqual(self.http("POST", "/login", raw=b"password=wrong-password", headers={"Origin": ORIGIN})[0], 401)
        cookie, csrf = self.login()
        code, h, body = self.http("GET", "/api/board", headers={"Cookie": cookie})
        self.assertEqual(code, 200)
        self.assertEqual(self.http("GET", "/api/board", headers={"Cookie": cookie, "If-None-Match": h["ETag"]})[0], 304)
        move = {"queue": "issues"}
        self.assertEqual(self.http("POST", "/api/tickets/T-0001/move", move, {"Cookie": cookie, "Origin": ORIGIN})[0], 403)  # no CSRF
        self.assertEqual(self.http("POST", "/api/tickets/T-0001/move", move, {"Cookie": cookie, "Origin": "https://evil", "X-CSRF-Token": csrf})[0], 403)
        code, _, body = self.http("POST", "/api/tickets/T-0001/move", dict(move, by="claude-sabre"), {"Cookie": cookie, "Origin": ORIGIN, "X-CSRF-Token": csrf})
        self.assertEqual((code, json.loads(body)["card"]["queue"]), (200, "issues"))
        self.assertEqual(self.requests[-1]["actor"], "owner")  # a client "by" is ignored
        self.assertNotIn("by", self.requests[-1]["args"])
        code, _, body = self.http("GET", "/", headers={"Cookie": cookie})
        self.assertIn(b'src="/tickets/app.js"', body)

    def test_bearer_agent_identity_and_rules(self):
        auth = {"Authorization": "Bearer " + self.token}
        code, _, body = self.http("GET", "/api/session", headers=auth)
        self.assertEqual(json.loads(body)["actor"], "claude-sonnet")
        self.assertEqual(json.loads(body)["role"], "agent")
        code, _, body = self.http("POST", "/api/tickets/T-0002/note", {"text": "hi"}, auth)  # sabre's ticket
        self.assertEqual(code, 403)
        self.assertIn("change_request", json.loads(body)["error"])
        self.assertEqual(self.http("POST", "/api/tickets/T-0002/change-request", {"text": "may I"}, auth)[0], 200)
        self.assertEqual(self.http("POST", "/api/tickets/T-0002/change-request/0", {"decision": "assign"}, auth)[0], 403)
        self.assertEqual(self.http("POST", "/api/tickets/T-0001/move", {"queue": "wip"}, auth)[0], 200)  # claims
        self.assertEqual(self.http("POST", "/api/tickets", {"title": "from an agent"}, auth)[0], 201)
        self.assertEqual(self.http("GET", "/api/board", headers={"Authorization": "Bearer owner-token"})[0], 401)  # never the owner
        self.assertEqual(self.http("GET", "/api/board", headers={"Authorization": "Bearer nope"})[0], 401)
        self.assertEqual(self.http("GET", "/api/board", headers=dict(auth, Cookie="tb_session=x"))[0], 400)

    def test_bad_requests(self):
        auth = {"Authorization": "Bearer " + self.token}
        self.assertEqual(self.http("POST", "/api/tickets/T-0001/move", raw=b"[1]", headers=auth)[0], 400)
        self.assertEqual(self.http("POST", "/api/tickets/T-0001/move", raw=b"x" * 20000, headers=auth)[0], 400)
        self.assertEqual(self.http("POST", "/api/tickets/T-0001/explode", {}, auth)[0], 404)
        self.assertEqual(self.http("GET", "/api/tickets/T-0404", headers=auth)[0], 404)
        self.assertEqual(self.http("GET", "/elsewhere")[0], 401)  # unknown paths stay behind the login
        self.assertEqual(self.http("GET", "/elsewhere", headers=auth)[0], 404)


class SocketTests(unittest.TestCase):
    """The real Unix-socket protocol: server.Broker talking to broker.main's handler (peer uid check included)."""

    def test_round_trip_over_the_socket(self):
        if os.geteuid() != 0:
            self.skipTest("broker.main requires root")
        import subprocess
        import sys
        import time
        from server import Broker
        f = Fixture()
        self.addCleanup(f.tmp.cleanup)
        f.seed({"title": "over the socket"})
        sock = f.root / "broker.sock"
        cfg = f.root / "config.json"
        cfg.write_text(json.dumps({"socket": str(sock), "ui_uid": 0, "ui_gid": 0, "store_dir": str(f.store), "agents_file": str(f.agents),
                                   "webhook_file": str(f.root / "none")}))
        p = subprocess.Popen([sys.executable, str(pathlib.Path(bk.__file__)), "--config", str(cfg)])
        self.addCleanup(p.kill)
        for _ in range(50):
            if sock.exists():
                break
            time.sleep(0.1)
        b = Broker(str(sock))
        self.assertEqual(b({"op": "summary"})["queues"]["backlog"], 1)
        r = b({"op": "move", "actor": "owner", "role": "owner", "ticket": "T-0001", "args": {"queue": "issues"}})
        self.assertEqual(r["card"]["queue"], "issues")
        with self.assertRaises(BrokerError) as e:
            b({"op": "note", "actor": "claude-sonnet", "role": "agent", "ticket": "T-0001", "args": {"text": "x"}})
        self.assertEqual(e.exception.code, "forbidden")
        self.assertEqual(oct(sock.stat().st_mode & 0o777), "0o660")


if __name__ == "__main__":
    unittest.main()
