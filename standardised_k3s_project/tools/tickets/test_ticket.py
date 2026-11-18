import importlib.util
import json
import os
import pathlib
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

spec = importlib.util.spec_from_file_location("ticket", pathlib.Path(__file__).with_name("ticket.py"))
tk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tk)


class Sink(BaseHTTPRequestHandler):
    got = []      # json payloads of POST and PATCH
    calls = []    # (method, path)
    gone = set()  # message ids that answer 404 to PATCH
    n = 0

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n)) if n else None

    def _reply(self, code, obj=None):
        data = json.dumps(obj).encode() if obj is not None else b""
        self.send_response(code)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        Sink.got.append(self._body())
        Sink.calls.append(("POST", self.path))
        Sink.n += 1
        self._reply(200, {"id": "m%d" % Sink.n})

    def do_PATCH(self):
        Sink.calls.append(("PATCH", self.path))
        if self.path.split("?")[0].rsplit("/", 1)[-1] in Sink.gone:
            self._reply(404, {"message": "Unknown Message"})
            return
        Sink.got.append(self._body())
        self._reply(200, {})

    def do_DELETE(self):
        Sink.calls.append(("DELETE", self.path))
        self._reply(204)

    def log_message(self, *a):
        pass


class Tickets(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        os.environ["WATOOM_TICKETS_DIR"] = str(self.root / "t")
        os.environ["WATOOM_TICKET_WEBHOOK_FILE"] = str(self.root / "none")
        os.environ["WATOOM_TICKET_QUEUE_GLOBS"] = str(self.root / "proj/*/.opencode/tickets")
        Sink.got, Sink.calls, Sink.gone, Sink.n = [], [], set(), 0

    def tearDown(self):
        self.tmp.cleanup()

    def hook(self):
        srv = HTTPServer(("127.0.0.1", 0), Sink)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        (self.root / "hook").write_text("http://127.0.0.1:%d/x\n" % srv.server_port)
        os.environ["WATOOM_TICKET_WEBHOOK_FILE"] = str(self.root / "hook")

    def test_ids_status_and_notes(self):
        with tk.Store() as s:
            a = s.add("one", priority="high")
            b = s.add("two")
        self.assertEqual((a["id"], b["id"]), ("T-0001", "T-0002"))
        with tk.Store() as s:
            t, old = s.set_status("2", "done", note="fixed", pr="abc123", by="me")
        self.assertEqual((old, t["status"], t["pr"], t["notes"][0]["text"]), ("open", "done", "abc123", "fixed"))
        with tk.Store() as s:
            self.assertEqual(s.data["next"], 3)
            with self.assertRaises(ValueError):
                s.add("bad", priority="urgent")
            with self.assertRaises(ValueError):
                s.set_status("T-0001", "nope")

    def test_failed_change_does_not_save(self):
        with self.assertRaises(ValueError):
            with tk.Store() as s:
                s.add("kept?")
                raise ValueError("boom")
        with tk.Store() as s:
            self.assertEqual(s.data["tickets"], [])

    def test_no_webhook_is_not_an_error(self):
        self.assertFalse(tk.post({"content": "x"}))
        self.assertEqual(tk.main(["add", "hello"]), 0)

    def test_discord_posts_and_never_leaks_url(self):
        self.hook()
        tk.main(["add", "ship it", "--priority", "high", "--project", "demo"])
        tk.main(["status", "T-0001", "done", "--pr", "https://example/pr/1", "--note", "merged"])
        self.assertEqual(len(Sink.got), 2)
        e = Sink.got[1]["embeds"][0]
        self.assertIn("T-0001", e["title"])
        self.assertEqual(e["color"], tk.COLOURS["done"])
        self.assertTrue(any(f["name"] == "PR / commit" for f in e["fields"]))
        self.assertNotIn("127.0.0.1", (self.root / "t" / "tickets.json").read_text())

    def test_https_only_webhook(self):
        (self.root / "h").write_text("ftp://example/x")
        os.environ["WATOOM_TICKET_WEBHOOK_FILE"] = str(self.root / "h")
        self.assertEqual(tk.webhook_url(), "")

    def test_ingest_model_requests(self):
        q = self.root / "proj" / "game" / ".opencode" / "tickets"
        q.mkdir(parents=True)
        (q / "fix-water.json").write_text(json.dumps({"schema": 1, "id": "fix-water", "title": "Creek 2 still buried", "priority": "high"}))
        (q / "bad-id.json").write_text(json.dumps({"schema": 1, "id": "other", "title": "x"}))
        (q / "huge.json").write_text("x" * 20000)
        made = tk.ingest()
        self.assertEqual([t["title"] for t in made], ["Creek 2 still buried"])
        self.assertEqual(made[0]["project"], "game")
        self.assertEqual(json.loads((q / "fix-water.status.json").read_text())["ticket"], "T-0001")
        self.assertEqual(json.loads((q / "bad-id.status.json").read_text())["state"], "rejected")
        self.assertEqual(json.loads((q / "huge.status.json").read_text())["state"], "rejected")
        self.assertEqual(tk.ingest(), [])  # already processed: no duplicates

    def test_ingest_creates_the_queue_and_open_list_in_a_project_without_one(self):
        (self.root / "proj" / "game" / ".opencode").mkdir(parents=True)
        (self.root / "proj" / "plain").mkdir(parents=True)  # no .opencode: left alone
        tk.ingest()
        q = self.root / "proj" / "game" / ".opencode" / "tickets"
        self.assertTrue((q / "OPEN-TICKETS.md").is_file())
        self.assertFalse((self.root / "proj" / "plain" / ".opencode").exists())

    def test_ingest_skips_symlinked_queue(self):
        real = self.root / "elsewhere"
        real.mkdir()
        (real / "a.json").write_text(json.dumps({"schema": 1, "id": "a", "title": "x"}))
        link_parent = self.root / "proj" / "p" / ".opencode"
        link_parent.mkdir(parents=True)
        (link_parent / "tickets").symlink_to(real)
        self.assertEqual(tk.ingest(), [])

    def queue(self):
        q = self.root / "proj" / "game" / ".opencode" / "tickets"
        q.mkdir(parents=True, exist_ok=True)
        return q

    clock = [1_700_000_000]

    def req(self, q, rid, **kw):
        f = q / (rid + ".json")
        f.write_text(json.dumps({"schema": 1, "id": rid, **kw}))
        Tickets.clock[0] += 10
        os.utime(f, (Tickets.clock[0], Tickets.clock[0]))

    def test_model_name_with_spaces_is_cleaned_not_rejected(self):
        q = self.queue()
        self.req(q, "spacey", model="Swift Qwen coder", title="Needs a clean model name")
        made = tk.ingest()
        self.assertEqual(len(made), 1)
        self.assertEqual(json.loads((q / "spacey.status.json").read_text())["state"], "created")
        self.assertEqual(made[0]["owner"], "model:Swift-Qwen-coder")

    def test_model_updates_and_open_list(self):
        self.hook()
        q = self.queue()
        self.req(q, "first", title="Water gap")
        tk.ingest()
        self.req(q, "start-it", action="status", ticket="T-0001", status="doing", note="looking now")
        self.req(q, "say-more", action="note", ticket="T-0001", text="buried at 17-23")
        self.req(q, "finish", action="status", ticket="T-0001", status="done", pr="abc123")
        made = tk.ingest()
        self.assertEqual(len(made), 3)
        with tk.Store() as s:
            t = s.find("T-0001")
        self.assertEqual((t["status"], t["pr"], len(t["notes"])), ("done", "abc123", 2))
        self.assertEqual(json.loads((q / "start-it.status.json").read_text())["state"], "updated")
        self.assertEqual(len(Sink.got), 4)  # create + 3 updates
        self.assertIn("Nothing open", (q / "OPEN-TICKETS.md").read_text())

    def test_open_list_shows_active_tickets(self):
        q = self.queue()
        self.req(q, "a", title="Alpha", priority="high")
        self.req(q, "b", title="Beta")
        tk.ingest()
        text = (q / "OPEN-TICKETS.md").read_text()
        self.assertLess(text.index("Alpha"), text.index("Beta"))  # high priority first
        self.assertIn("T-0001", text)

    def test_models_cannot_drop_and_unknown_ticket_is_rejected(self):
        q = self.queue()
        self.req(q, "a", title="Alpha")
        tk.ingest()
        self.req(q, "drop-it", action="status", ticket="T-0001", status="dropped")
        self.req(q, "ghost", action="note", ticket="T-0099", text="x")
        self.req(q, "weird", action="delete", ticket="T-0001")
        self.assertEqual(tk.ingest(), [])
        for rid in ("drop-it", "ghost", "weird"):
            self.assertEqual(json.loads((q / (rid + ".status.json")).read_text())["state"], "rejected")
        with tk.Store() as s:
            self.assertEqual(s.find("T-0001")["status"], "open")

    def _req(self, name, body):
        q = self.root / "proj/game/.opencode/tickets"
        q.mkdir(parents=True, exist_ok=True)
        (q / (name + ".json")).write_text(json.dumps(dict(schema=1, id=name, **body)))
        tk.ingest()
        return json.loads((q / (name + ".status.json")).read_text())

    def test_ticket_has_one_owner_and_other_models_need_a_change_request(self):
        r = self._req("make", {"title": "Dungeon", "model": "alpha"})
        self.assertEqual((r["state"], r["owner"]), ("created", "model:alpha"))
        r = self._req("b-start", {"action": "status", "ticket": r["ticket"], "status": "doing", "model": "beta"})
        self.assertEqual(r["state"], "rejected")
        self.assertIn("change_request", r["reason"])
        r = self._req("b-note", {"action": "note", "ticket": "T-0001", "text": "hi", "model": "beta"})
        self.assertEqual(r["state"], "rejected")
        r = self._req("b-cr", {"action": "change_request", "ticket": "T-0001", "text": "owner is busy, I will take it", "model": "beta"})
        self.assertEqual(r["state"], "change_requested")
        r = self._req("a-cr", {"action": "change_request", "ticket": "T-0001", "text": "x", "model": "alpha"})
        self.assertEqual(r["state"], "rejected")  # the owner just edits its own ticket
        with tk.Store() as s:
            t = s.find("T-0001")
            self.assertEqual(t["change_requests"][0]["state"], "pending")
            s.assign("T-0001", "model:beta", "owner")
            self.assertEqual(s.find("T-0001")["change_requests"][0]["state"], "approved")
        r = self._req("b-start2", {"action": "status", "ticket": "T-0001", "status": "doing", "model": "beta"})
        self.assertEqual(r["state"], "updated")

    def test_unowned_ticket_is_claimed_by_the_first_model_that_starts_it(self):
        with tk.Store() as s:
            s.add("owner made this", project="game", by="claude")
        r = self._req("note-first", {"action": "note", "ticket": "T-0001", "text": "x", "model": "alpha"})
        self.assertEqual(r["state"], "rejected")
        r = self._req("claim", {"action": "status", "ticket": "T-0001", "status": "doing", "model": "alpha"})
        self.assertEqual((r["state"], r["owner"]), ("updated", "model:alpha"))
        r = self._req("other", {"action": "status", "ticket": "T-0001", "status": "done", "model": "beta"})
        self.assertEqual(r["state"], "rejected")

    def test_posts_go_to_the_channel_for_the_status_and_fall_back_to_the_base_webhook(self):
        for n in ("new", "closed"):
            (self.root / ("hook_" + n)).write_text("http://127.0.0.1:1/" + n)
        (self.root / "hook").write_text("http://127.0.0.1:1/base")
        os.environ["WATOOM_TICKET_WEBHOOK_FILE"] = str(self.root / "hook")
        self.assertTrue(tk.webhook_url("new").endswith("/new"))
        self.assertTrue(tk.webhook_url("closed").endswith("/closed"))
        self.assertTrue(tk.webhook_url("progress").endswith("/base"))  # no progress file: base channel
        t = {"status": "done"}
        self.assertEqual(tk.channel_for(t), "closed")
        self.assertEqual(tk.channel_for({"status": "doing"}), "progress")
        self.assertEqual(tk.channel_for({"status": "dropped"}), "cancelled")
        self.assertEqual(tk.channel_for({"status": "open"}, "New ticket from a model"), "new")
        self.assertEqual(tk.channel_for({"status": "blocked"}), "progress")

    def two_hooks(self):
        srv = HTTPServer(("127.0.0.1", 0), Sink)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        base = str(self.root / "hook")
        (self.root / "hook_new").write_text("http://127.0.0.1:%d/new\n" % srv.server_port)
        (self.root / "hook_closed").write_text("http://127.0.0.1:%d/closed\n" % srv.server_port)
        os.environ["WATOOM_TICKET_WEBHOOK_FILE"] = base

    def test_one_discord_message_per_ticket_is_edited_not_reposted(self):
        self.hook()
        tk.main(["add", "single message"])
        tk.main(["note", "T-0001", "first"])
        tk.main(["note", "T-0001", "second"])
        tk.main(["status", "T-0001", "doing"])
        self.assertEqual([m for m, _ in Sink.calls], ["POST", "PATCH", "PATCH", "PATCH"])
        self.assertIn("/messages/m1", Sink.calls[1][1])
        self.assertEqual(Sink.got[-1]["embeds"][0]["fields"][-1]["value"].split(": ")[-1], "second")

    def test_changing_channel_deletes_the_old_message_and_posts_the_new_one(self):
        self.two_hooks()
        tk.main(["add", "moves channel"])
        tk.main(["status", "T-0001", "done"])
        self.assertEqual(Sink.calls, [("POST", "/new?wait=true"), ("DELETE", "/new/messages/m1"), ("POST", "/closed?wait=true")])
        tk.main(["note", "T-0001", "after"])
        self.assertEqual(Sink.calls[-1], ("PATCH", "/closed/messages/m2"))

    def test_a_message_deleted_by_hand_is_reposted_once(self):
        self.hook()
        tk.main(["add", "cleared channel"])
        Sink.gone.add("m1")
        tk.main(["note", "T-0001", "x"])
        self.assertEqual([m for m, _ in Sink.calls], ["POST", "PATCH", "POST"])
        tk.main(["note", "T-0001", "y"])
        self.assertEqual(Sink.calls[-1][0], "PATCH")

    def test_a_similar_active_request_is_a_note_not_a_second_ticket(self):
        self.hook()
        tk.main(["add", "Game: less pale tree leaves"])
        tk.main(["add", "less pale tree leaves (game)"])
        with tk.Store() as s:
            self.assertEqual(len(s.data["tickets"]), 1)
            self.assertIn("duplicate request", s.data["tickets"][0]["notes"][-1]["text"])
        self.assertEqual([m for m, _ in Sink.calls], ["POST", "PATCH"])
        tk.main(["status", "T-0001", "done"])
        tk.main(["add", "less pale tree leaves again"])  # closed ticket: a new request is allowed
        with tk.Store() as s:
            self.assertEqual(len(s.data["tickets"]), 2)

    def test_model_duplicate_request_is_reported_not_created(self):
        d = self.root / "proj" / "game" / ".opencode" / "tickets"
        d.mkdir(parents=True)
        for rid in ("a-1", "a-2"):
            (d / (rid + ".json")).write_text(json.dumps({"schema": 1, "id": rid, "action": "create", "title": "Fix creek mouth shallows"}))
        tk.ingest()
        self.assertEqual(json.loads((d / "a-2.status.json").read_text())["state"], "duplicate")
        with tk.Store() as s:
            self.assertEqual(len(s.data["tickets"]), 1)


class Board(unittest.TestCase):
    """Kanban additions (kanban-design.md): queue, shared, registry, may(), move, edit, change-request decisions."""

    AGENTS = {"agents": [
        {"id": "owner", "label": "Owner", "role": "owner", "lane": False, "aliases": ["root"]},
        {"id": "claude-sonnet", "label": "Sonnet", "role": "agent", "lane": True, "aliases": ["claude-sonnet-3a"]},
        {"id": "claude-sabre", "label": "Sabre", "role": "agent", "lane": True, "aliases": ["claude-sabre-fd"]}]}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        os.environ["WATOOM_TICKETS_DIR"] = str(self.root / "t")
        os.environ["WATOOM_TICKET_WEBHOOK_FILE"] = str(self.root / "none")
        os.environ["WATOOM_TICKET_QUEUE_GLOBS"] = str(self.root / "proj/*/.opencode/tickets")
        os.environ.pop("WATOOM_TICKET_AGENTS_FILE", None)
        (self.root / "t").mkdir()
        (self.root / "t" / "agents.json").write_text(json.dumps(self.AGENTS))

    def tearDown(self):
        self.tmp.cleanup()

    def legacy(self, **kw):
        """A ticket as written before owner/change_requests/queue/shared existed."""
        t = {"id": "T-0001", "title": "old", "body": "", "status": "open", "priority": "normal", "project": "", "pr": "", "by": "claude",
             "source": "", "created": "2026-11-01T00:00:00Z", "updated": "2026-11-01T00:00:00Z", "notes": []}
        t.update(kw)
        (self.root / "t" / "tickets.json").write_text(json.dumps({"next": 2, "tickets": [t]}))

    def req(self, rid, body):
        q = self.root / "proj/game/.opencode/tickets"
        q.mkdir(parents=True, exist_ok=True)
        (q / (rid + ".json")).write_text(json.dumps(dict(schema=1, id=rid, **body)))
        tk.ingest()
        return json.loads((q / (rid + ".status.json")).read_text())

    def test_queue_of_defaults_and_mismatch(self):
        self.assertEqual(tk.queue_of({"status": "open"}), "backlog")
        self.assertEqual(tk.queue_of({"status": "blocked"}), "wip")
        self.assertEqual(tk.queue_of({"status": "dropped", "queue": "obsolete"}), "obsolete")
        self.assertEqual(tk.queue_of({"status": "done", "queue": "issues"}), "completed")  # an old writer changed the status
        self.assertEqual(tk.queue_of({"status": "open", "queue": "bogus"}), "backlog")

    def test_load_is_lock_free_and_handles_a_missing_store(self):
        self.assertEqual(tk.load(self.root / "nowhere"), {"next": 1, "tickets": []})
        self.legacy()
        before = (self.root / "t" / "tickets.json").read_bytes()
        self.assertEqual(tk.load()["tickets"][0]["id"], "T-0001")
        self.assertEqual((self.root / "t" / "tickets.json").read_bytes(), before)  # not rewritten

    def test_new_tickets_default_to_requests_and_accept_shared(self):
        tk.main(["add", "fresh one", "--shared"])
        tk.main(["add", "an issue", "--queue", "issues"])
        with tk.Store() as s:
            a, b = s.data["tickets"]
            self.assertEqual((a["queue"], a["shared"], b["queue"], b["shared"]), ("requests", True, "issues", False))
            with self.assertRaises(ValueError):
                s.add("x", queue="wip")

    def test_set_status_fixes_a_stale_queue_and_leaves_legacy_tickets_alone(self):
        with tk.Store() as s:
            t = s.add("x", queue="issues")
            s.set_status(t["id"], "doing")
            self.assertEqual(t["queue"], "wip")
            s.set_status(t["id"], "open")
            self.assertEqual(t["queue"], "backlog")
        self.legacy()
        with tk.Store() as s:
            s.set_status("T-0001", "done")
            self.assertNotIn("queue", s.find("T-0001"))

    def test_move_sets_status_and_notes_same_status_moves(self):
        with tk.Store() as s:
            t = s.add("x")
            t, old = s.move(t["id"], "issues", by="owner")
            self.assertEqual((old, t["status"], t["queue"], t["notes"][-1]["text"]), ("open", "open", "issues", "queue: requests -> issues"))
            t, old = s.move(t["id"], "wip", blocked=True, by="owner")
            self.assertEqual(t["status"], "blocked")
            t, _ = s.move(t["id"], "wip", owner="claude-sabre", by="owner")  # another lane: stays blocked
            self.assertEqual((t["status"], t["owner"]), ("blocked", "claude-sabre"))
            self.assertIn("owner changed: - -> claude-sabre", t["notes"][-1]["text"])
            t, _ = s.move(t["id"], "obsolete", by="owner")
            self.assertEqual((t["status"], tk.queue_of(t)), ("dropped", "obsolete"))

    def test_registry_aliases_and_generic_model_lanes(self):
        self.assertEqual(tk.canonical("claude-sabre-fd"), "claude-sabre")
        self.assertEqual(tk.canonical("claude"), "claude")  # historical name maps to nothing
        self.assertEqual(tk.label_of("model:Any-New-model"), "Any New model")
        data = {"tickets": [{"status": "doing", "owner": "model:Some-Local"}, {"status": "doing", "owner": "claude-sonnet-3a"},
                            {"status": "open", "owner": "model:Not-In-Wip"}]}
        self.assertEqual([x["id"] for x in tk.lanes(data)], ["claude-sonnet", "claude-sabre", "model:Some-Local", ""])

    def test_missing_registry_still_works(self):
        (self.root / "t" / "agents.json").unlink()
        self.assertEqual([a["id"] for a in tk.load_agents()], ["owner"])
        self.assertEqual(tk.lanes({"tickets": []}), [{"id": "", "label": "Unassigned"}])

    def test_may_rules(self):
        own = {"owner": "claude-sabre-fd"}
        self.assertTrue(tk.may("claude-sabre", "agent", "note", own))  # alias of the owner
        self.assertFalse(tk.may("claude-sonnet", "agent", "note", own))
        self.assertTrue(tk.may("claude-sonnet", "agent", "note", dict(own, shared=True)))
        self.assertFalse(tk.may("claude-sonnet", "agent", "share", dict(own, shared=True)))
        self.assertFalse(tk.may("claude-sabre", "agent", "drop", own))
        self.assertTrue(tk.may("claude-sonnet", "agent", "change_request", own))
        self.assertTrue(tk.may("claude-sonnet", "agent", "move", {}))
        self.assertFalse(tk.may("claude-sonnet", "agent", "note", {}))  # claim before note (owner decision 10)
        self.assertTrue(tk.may("owner", "owner", "drop", own))

    def test_plan_move(self):
        t = {"id": "T-0009", "owner": "", "status": "open"}
        self.assertEqual(tk.plan_move("claude-sonnet", "agent", t, "wip"), "claude-sonnet")  # claims
        with self.assertRaises(tk.Refused):
            tk.plan_move("claude-sonnet", "agent", t, "wip", lane="claude-sabre")
        with self.assertRaises(tk.Refused):
            tk.plan_move("claude-sonnet", "agent", t, "cancelled")
        shared = {"id": "T-0009", "owner": "claude-sabre", "status": "open", "shared": True}
        self.assertEqual(tk.plan_move("claude-sonnet", "agent", shared, "wip"), "claude-sonnet")  # takes it into its lane
        self.assertIsNone(tk.plan_move("claude-sonnet", "agent", shared, "issues"))  # no lane change: owner kept
        self.assertEqual(tk.plan_move("owner", "owner", shared, "wip", lane=""), "")
        with self.assertRaises(ValueError):
            tk.plan_move("owner", "owner", shared, "backlog", lane="x")

    def test_queue_move_create_and_shared(self):
        r = self.req("mk", {"title": "Global thing", "model": "alpha", "shared": True, "queue": "issues"})
        self.assertEqual(r["state"], "created")
        with tk.Store() as s:
            t = s.find("T-0001")
            self.assertEqual((t["queue"], t["shared"], t["owner"]), ("issues", True, "model:alpha"))
        r = self.req("b-note", {"action": "note", "ticket": "T-0001", "text": "I can help", "model": "beta"})
        self.assertEqual(r["state"], "updated")  # shared: another model may note
        r = self.req("b-move", {"action": "move", "ticket": "T-0001", "queue": "wip", "model": "beta"})
        self.assertEqual((r["state"], r["owner"], r["status"]), ("updated", "model:beta", "doing"))
        with tk.Store() as s:
            self.assertTrue(s.find("T-0001")["notes"][-1]["text"].endswith("(shared ticket)") or
                            any("(shared ticket)" in n["text"] for n in s.find("T-0001")["notes"]))
        r = self.req("b-drop", {"action": "move", "ticket": "T-0001", "queue": "obsolete", "model": "beta"})
        self.assertEqual(r["state"], "rejected")
        r = self.req("bad-q", {"action": "create", "title": "Wrong queue", "queue": "wip"})
        self.assertEqual(r["state"], "rejected")

    def test_queue_move_respects_ownership(self):
        self.req("mk", {"title": "Alpha's", "model": "alpha"})
        r = self.req("b-move", {"action": "move", "ticket": "T-0001", "queue": "wip", "model": "beta"})
        self.assertEqual(r["state"], "rejected")
        self.assertIn("owned by model:alpha", r["reason"])
        r = self.req("a-move", {"action": "move", "ticket": "T-0001", "queue": "completed", "model": "alpha", "note": "verified"})
        self.assertEqual((r["state"], r["status"]), ("updated", "done"))

    def test_edit_share_and_change_request_decisions(self):
        with tk.Store() as s:
            t = s.add("x", owner="model:alpha")
            s.edit(t["id"], {"title": "y", "priority": "high", "project": "p"}, by="owner")
            self.assertEqual(t["notes"][-1]["text"], "title, priority, project changed")
            with self.assertRaises(ValueError):
                s.edit(t["id"], {"status": "done"})
            s.set_shared(t["id"], True, by="owner")
            self.assertEqual(t["notes"][-1]["text"], "shared: off -> on")
            s.set_shared(t["id"], False, by="owner")
            for who in ("model:beta", "model:gamma", "model:delta"):
                s.change_request(t["id"], "please", who)
            s.decide_change_request(t["id"], 0, "assign", by="owner")
            s.decide_change_request(t["id"], 1, "share", by="owner")
            s.decide_change_request(t["id"], 2, "reject", "not now", by="owner")
            self.assertEqual([c["state"] for c in t["change_requests"]], ["approved", "approved", "rejected"])
            self.assertEqual((t["owner"], t["shared"]), ("model:beta", True))
            with self.assertRaises(ValueError):
                s.decide_change_request(t["id"], 2, "assign")

    def test_legacy_ticket_survives_every_path_and_migrate(self):
        self.legacy()
        self.assertEqual(tk.main(["show", "T-0001"]), 0)
        self.assertEqual(tk.main(["note", "T-0001", "x"]), 0)
        self.assertEqual(tk.main(["move", "T-0001", "wip", "--lane", "claude-sabre-fd", "--by", "owner"]), 0)
        with tk.Store() as s:
            t = s.find("T-0001")
            self.assertEqual((t["status"], t["owner"], t["queue"]), ("doing", "claude-sabre", "wip"))
        self.legacy()
        with tk.Store() as s:
            self.assertEqual(s.migrate(), 1)
            t = s.find("T-0001")
            self.assertEqual((t["queue"], t["shared"], t["owner"], t["change_requests"], t["status"]), ("backlog", False, "", [], "open"))
            self.assertEqual(s.migrate(), 0)

    def test_embed_only_shows_board_fields_when_used(self):
        legacy = {"id": "T-0001", "title": "t", "body": "", "status": "open", "priority": "normal", "project": "", "pr": "", "notes": [], "updated": "x"}
        names = [f["name"] for f in tk.embed(legacy, "h")["embeds"][0]["fields"]]
        self.assertEqual(names, ["Priority", "Status"])
        names = [f["name"] for f in tk.embed(dict(legacy, queue="issues", shared=True), "h")["embeds"][0]["fields"]]
        self.assertEqual(names, ["Priority", "Status", "Queue", "Shared"])


if __name__ == "__main__":
    unittest.main()
