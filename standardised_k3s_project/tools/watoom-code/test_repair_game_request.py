import unittest, tempfile, pathlib, sqlite3, json, shutil
from repair_game_request import _restore
from game_worker_bridge import fingerprint, request_identity


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.p = pathlib.Path(tempfile.mkdtemp(prefix=".request-repair-test-", dir="/data/ai/projects/games"))
        (self.p / "scripts").mkdir()
        (self.p / "project.godot").write_text("[application]")
        (self.p / "scripts/test.gd").write_text("extends Node")
        self.tmp = tempfile.TemporaryDirectory()
        self.out = pathlib.Path(self.tmp.name)
        self.db = self.out / "app.sqlite"
        self.req = dict(
            schema=1,
            project=str(self.p),
            operation="capture",
            job="same-job",
            source_fingerprint=fingerprint(self.p),
            session_id="ses_real",
            message_id="msg_real",
            call_id="call_real",
            agent="watoom-builder",
            created_at=1,
        )
        self.req["request_id"] = request_identity(self.req)
        self.path = self.p / ".opencode/worker-requests" / (self.req["request_id"] + ".json")
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({**self.req, "message_id": "msg_fake"}))
        self.call = dict(
            type="tool",
            name="watoom_game_worker",
            id="call_real",
            time={"created": 1, "ran": 2},
            state={
                "status": "completed",
                "input": {"action": "request", "operation": "capture", "job": "same-job"},
                "metadata": self.req,
            },
        )
        with sqlite3.connect(self.db) as d:
            d.executescript(
                "create table session_v2(id text,agent text,directory text);create table session_message(session_id text,id text,data text);"
            )
            d.execute("insert into session_v2 values(?,?,?)", ("ses_real", "watoom-builder", str(self.p)))

    def record(self, call=None):
        with sqlite3.connect(self.db) as d:
            d.execute(
                "insert into session_message values(?,?,?)",
                ("ses_real", "msg_real", json.dumps({"content": [call or self.call]})),
            )

    def repair(self):
        return _restore(self.p, self.req["request_id"], self.db, self.out / "evidence")

    def test_same_identity_repair(self):
        self.record()
        r = self.repair()
        self.assertTrue(r["same_native_identity"])
        self.assertEqual(json.loads(self.path.read_text())["message_id"], "msg_real")
        self.assertEqual(json.loads(pathlib.Path(r["backup"]).read_text())["message_id"], "msg_fake")

    def test_no_native_evidence_no_repair(self):
        with self.assertRaisesRegex(ValueError, "Exactly one"):
            self.repair()

    def test_changed_source_no_repair(self):
        self.record()
        (self.p / "scripts/test.gd").write_text("changed")
        with self.assertRaisesRegex(ValueError, "Source changed"):
            self.repair()

    def test_failed_native_call_no_repair(self):
        self.call["state"]["status"] = "error"
        self.record()
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.repair()

    def tearDown(self):
        assert self.p.parent == pathlib.Path("/data/ai/projects/games") and self.p.name.startswith(
            ".request-repair-test-"
        )
        shutil.rmtree(self.p)
        self.tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
