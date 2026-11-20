import json, os, pathlib, sys, tempfile, time, unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import game_session_watchdog as watchdog


class Undispatched(unittest.TestCase):
    def test_undispatched_request_prompts_coordinator_once(self):
        # T-0133: a request the worker never picked up left the session waiting on QUEUED forever.
        with tempfile.TemporaryDirectory() as games:
            d = pathlib.Path(games) / "demo/.opencode/worker-requests"
            d.mkdir(parents=True)
            req = d / ("a" * 64 + ".json")
            req.write_text(json.dumps({"session_id": "ses_child", "job": "verify-3", "operation": "godot-game"}))
            old = time.time() - 3600
            os.utime(req, (old, old))
            m = MagicMock()
            m.request.side_effect = lambda path, body=None: (
                {"data": {"parentID": "ses_coord"}} if path == "/api/session/ses_child" else {"data": {}}
            )
            argv = ["watchdog"]
            with patch.object(watchdog, "GAMES", pathlib.Path(games)), patch.object(
                watchdog, "Maintenance", return_value=m
            ), patch.object(sys, "argv", argv), patch("builtins.print"):
                with self.assertRaises(SystemExit):
                    watchdog.main()
                prompts = [c for c in m.request.call_args_list if c.args[0].endswith("/prompt")]
                self.assertEqual([c.args[0] for c in prompts], ["/api/session/ses_coord/prompt"])
                self.assertIn("never picked up", prompts[0].args[1]["text"])
                self.assertTrue((d / ("a" * 64 + ".undispatched")).exists())
                m.request.reset_mock()
                with self.assertRaises(SystemExit):
                    watchdog.main()
                self.assertFalse([c for c in m.request.call_args_list if c.args[0].endswith("/prompt")])


if __name__ == "__main__":
    unittest.main()
