import unittest, sys, pathlib, copy, tempfile, json
from unittest.mock import patch, Mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import game_worker_bridge as bridge
from game_worker_bridge import native_proof, request_identity, read_request, project_safe


class Bridge(unittest.TestCase):
    def setUp(self):
        self.v = {
            "project": "/data/ai/projects/games/test",
            "operation": "regression",
            "source_fingerprint": "a" * 64,
            "session_id": "ses_test",
            "message_id": "msg_test",
            "call_id": "call_test",
            "job": "stable",
            "agent": "watoom-builder",
        }
        self.v["request_id"] = request_identity(self.v)
        self.part = {
            "type": "tool",
            "name": "watoom_game_worker",
            "id": "call_test",
            "state": {
                "status": "completed",
                "input": {"action": "request", "operation": "regression", "job": "stable"},
                "metadata": {k: self.v[k] for k in ["request_id", "project", "operation", "source_fingerprint", "job"]},
            },
        }

    def proof(self, p):
        return native_proof({"content": [p]}, self.v)

    def test_failure_signals_are_structured_and_command_repr_is_not_a_reason(self):
        import subprocess

        self.assertEqual(("run", "timeout"), bridge.failure_metadata({"timed_out": True}))
        self.assertEqual(
            ("reconcile", "source_changed"), bridge.failure_metadata({"source_changes_by_import": {"created": ["x"]}})
        )
        self.assertEqual(("stage", "unreachable"), bridge.failure_metadata(returncode=255))
        self.assertEqual(("run", "oom"), bridge.failure_metadata({"failure_reason": "memory limit exceeded"}))
        self.assertEqual(
            "Worker command failed (timeout).",
            bridge.human_failure(
                "Command '['/usr/bin/python3', 'secret-arg']' timed out after 1000 seconds", "timeout"
            ),
        )
        self.assertEqual(
            ("run", "timeout"), bridge.failure_metadata(error=subprocess.TimeoutExpired(["private-argv"], 100))
        )
        self.assertEqual(
            ("stage", "unreachable"),
            bridge.failure_metadata(error=subprocess.CalledProcessError(255, ["private-argv"])),
        )

    def test_low_ram_active_session_never_parks(self):
        m = Mock()
        m.request.return_value = {"data": {"ses_active": {"type": "running"}}}
        with patch.object(bridge.pathlib.Path, "read_text", return_value="MemAvailable: 1024 kB"), patch.object(
            bridge, "cpu_client"
        ) as client:
            with bridge.reserve_headroom(m) as ready:
                self.assertFalse(ready)
            client.assert_not_called()

    def test_cpu_restored_even_when_worker_fails(self):
        m = Mock()
        m.request.return_value = {"data": {}}
        client = Mock()
        client.call.return_value = {"generation": 3}
        with patch.object(
            bridge.pathlib.Path, "read_text", side_effect=["MemAvailable: 1024 kB", "MemAvailable: 9000000 kB"]
        ), patch.object(bridge, "cpu_client", return_value=client):
            with self.assertRaises(RuntimeError):
                with bridge.reserve_headroom(m) as ready:
                    self.assertTrue(ready)
                    raise RuntimeError("worker failed")
        self.assertEqual([x.args[0] for x in client.call.call_args_list], ["begin", "park-cpu", "restore"])

    def test_native_call_required(self):
        self.assertTrue(self.proof(self.part))

    def test_fake_and_running_denied(self):
        for name in ["shell", "read", "question"]:
            p = copy.deepcopy(self.part)
            p["name"] = name
            self.assertFalse(self.proof(p))
        p = copy.deepcopy(self.part)
        p["state"]["status"] = "running"
        self.assertFalse(self.proof(p))

    def test_identity_and_operation_binding(self):
        for key in ["request_id", "project", "operation", "source_fingerprint", "job"]:
            p = copy.deepcopy(self.part)
            p["state"]["metadata"][key] = "different"
            self.assertFalse(self.proof(p))
        p = copy.deepcopy(self.part)
        p["id"] = "other"
        self.assertFalse(self.proof(p))

    def test_no_arbitrary_commands(self):
        p = copy.deepcopy(self.part)
        p["state"]["input"]["command"] = "id"
        self.assertFalse(self.proof(p))

    def test_invalid_request_file_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / ("a" * 64 + ".json")
            p.write_text("{bad")
            self.assertIsNone(read_request(p, pathlib.Path(d)))
            p.write_text(json.dumps({"project": d}))
            self.assertIsNone(read_request(p, pathlib.Path(d)))

    def test_worker_agents_equal_guard_worker_roles(self):
        # T-0133: the guard grants the worker tool to workerRoles; the bridge must accept exactly those agents.
        import re
        from asset_capture_contract import WORKER_AGENTS

        guard = pathlib.Path(__file__).resolve().parents[3] / "ansible/roles/watoom-code/files/coordinator-guard/index.js"
        match = re.search(r"const workerRoles=new Set\(\[([^\]]*)\]\)", guard.read_text())
        self.assertIsNotNone(match, "workerRoles not found in coordinator-guard/index.js")
        self.assertEqual(set(re.findall(r'"([^"]+)"', match.group(1))), set(WORKER_AGENTS))

    def write_request(self, folder, agent):
        v = dict(self.v, project=str(folder), agent=agent)
        v["request_id"] = request_identity(v)
        p = folder / (v["request_id"] + ".json")
        p.write_text(json.dumps(v))
        return p, v

    def test_developer_request_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            p, v = self.write_request(pathlib.Path(d), "watoom-developer")
            self.assertEqual(read_request(p, pathlib.Path(d)), v)
            self.assertFalse(bridge.refuse_disallowed_agent(v))

    def test_disallowed_agent_fails_once_instead_of_silent_queue(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as private:
            project = pathlib.Path(d)
            (project / ".opencode/worker-requests").mkdir(parents=True)
            p, v = self.write_request(project, "watoom-reviewer")
            self.assertIsNone(read_request(p, project))
            self.assertEqual(read_request(p, project, any_agent=True), v)
            with patch.object(bridge, "PRIVATE", pathlib.Path(private)):
                self.assertTrue(bridge.refuse_disallowed_agent(v))
                status = project / ".opencode/worker-requests" / (v["request_id"] + ".status.json")
                result = json.loads(status.read_text())
                self.assertEqual((result["status"], result["failure_code"]), ("FAILED", "agent_not_allowed"))
                status.unlink()
                self.assertTrue(bridge.refuse_disallowed_agent(v))
                self.assertFalse(status.exists(), "refusal must be published once")

    def test_outside_project_refused(self):
        self.assertFalse(project_safe("/tmp"))

    def capture_project(self, root, output):
        project = pathlib.Path(root)
        job = project / ".opencode/capture-jobs/dirt"
        job.mkdir(parents=True)
        (job / "arena.tscn").write_text("[gd_scene]")
        (job / "request.json").write_text(
            json.dumps(
                {
                    "schema": 1,
                    "scene": ".opencode/capture-jobs/dirt/arena.tscn",
                    "inputs": [".opencode/capture-jobs/dirt/arena.tscn"],
                    "output_directory": output,
                    "images": ["ground.png"],
                }
            )
        )
        return project, {**self.v, "operation": "capture-scene", "job": "dirt", "project": str(project)}

    def test_bad_capture_manifest_fails_its_request_with_a_reason(self):
        # A trailing slash once crashed the dispatcher on every run, blocking every queued request behind it.
        with tempfile.TemporaryDirectory() as d:
            project, v = self.capture_project(d, ".opencode/captures/dirt/")
            with patch.object(bridge, "fingerprint", return_value="f" * 64):
                current, reason = bridge.checked_fingerprint(project, v)
            self.assertIsNone(current)
            self.assertIn(".opencode/capture-jobs/dirt/request.json", reason)
            self.assertIn("output_directory", reason)
            self.assertIn("trailing slash", reason)

    def test_valid_capture_manifest_still_fingerprints(self):
        with tempfile.TemporaryDirectory() as d:
            project, v = self.capture_project(d, ".opencode/captures/dirt")
            with patch.object(bridge, "fingerprint", return_value="f" * 64):
                current, reason = bridge.checked_fingerprint(project, v)
            self.assertIsNone(reason)
            self.assertRegex(current, "^[0-9a-f]{64}$")

    def test_restart_recovers_finished_evidence_instead_of_discarding_it(self):
        # A dispatcher restart while a request was RUNNING must adopt a real finished receipt already on disk
        # (the operator finished before the dispatcher itself died), not blanket-discard it as unreconciled.
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as private:
            project = pathlib.Path(d)
            (project / ".opencode/worker-requests").mkdir(parents=True)
            v = dict(self.v, operation="godot-game", project=str(project))
            out = pathlib.Path(d) / "out"
            out.mkdir()
            (out / "result.json").write_text(json.dumps({"status": "PASS", "summary": "ok"}))
            with patch.object(bridge, "PRIVATE", pathlib.Path(private)), patch.object(
                bridge, "request_fingerprint", return_value=v["source_fingerprint"]
            ):
                result = bridge.finalize_receipt(v, v["request_id"], out, project, 0, "unused", None)
            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual(result["worker_result"]["status"], "PASS")

    def test_restart_recovery_falls_back_to_reconciliation_when_evidence_unusable(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as private:
            project = pathlib.Path(d)
            (project / ".opencode/worker-requests").mkdir(parents=True)
            v = dict(self.v, operation="lmb-qualify", project=str(project))
            out = pathlib.Path(d) / "out"
            out.mkdir()
            (out / "result.json").write_text(json.dumps({"status": "PASS", "project": "/different/project"}))
            with patch.object(bridge, "PRIVATE", pathlib.Path(private)):
                with self.assertRaises(ValueError):
                    bridge.finalize_receipt(v, v["request_id"], out, project, 0, "unused", None)


if __name__ == "__main__":
    unittest.main()
