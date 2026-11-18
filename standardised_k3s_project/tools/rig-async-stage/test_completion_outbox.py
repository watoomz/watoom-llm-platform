import importlib.util, json, pathlib, tempfile, unittest
spec = importlib.util.spec_from_file_location("completion_outbox", pathlib.Path(__file__).parent / "worker-source/completion_outbox.py")
outbox = importlib.util.module_from_spec(spec); spec.loader.exec_module(outbox)
APP = {"namespace": "watoom-code-rig-jobs", "name": "watoom-code"}
REQ = {"request_id": "4" * 64, "job": "rig-stage-import"}

class CompletionOutboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); outbox.ROOT = pathlib.Path(self.tmp.name) / "outbox"
    def tearDown(self):
        self.tmp.cleanup()
    def entry(self):
        return json.loads(next(outbox.ROOT.glob("*.json")).read_text())
    def test_status_change_after_delivery_neither_renotifies_nor_raises(self):
        outbox.enqueue(REQ, "ses_coord", "finished with status COMPLETED.", kind="godot", application=APP)
        path = next(outbox.ROOT.glob("*.json")); d = json.loads(path.read_text()); d["state"] = "DELIVERED"; path.write_text(json.dumps(d))
        # The reconciliation loop: the same request later reports a different status.
        outbox.enqueue(REQ, "ses_coord", "finished with status RECONCILIATION_REQUIRED.", kind="godot", application=APP)
        self.assertEqual(self.entry()["state"], "DELIVERED")
        self.assertIn("COMPLETED", self.entry()["body"]["text"])
        self.assertEqual(len(list(outbox.ROOT.glob("*.json"))), 1)
    def test_different_session_or_application_is_still_a_conflict(self):
        outbox.enqueue(REQ, "ses_coord", "t", kind="godot", application=APP)
        with self.assertRaises(ValueError):
            outbox.enqueue(REQ, "ses_other", "t", kind="godot", application=APP)
        path = next(outbox.ROOT.glob("*.json")); d = json.loads(path.read_text()); d["application"] = {"namespace": "x", "name": "y"}; path.write_text(json.dumps(d))
        with self.assertRaises(ValueError):
            outbox.enqueue(REQ, "ses_coord", "t", kind="godot", application=APP)

if __name__ == "__main__":
    unittest.main()
