import unittest, tempfile, pathlib, threading, urllib.request, urllib.error, json, sys
from http.server import ThreadingHTTPServer
import agent, job_admission


class AdmissionHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.before = (agent.STATE, agent.WORKSPACE, agent.TOKEN, agent.make_command)
        agent.STATE = pathlib.Path(self.tmp.name) / "state"
        agent.WORKSPACE = pathlib.Path(self.tmp.name)
        agent.TOKEN = "owned-test-token-" + "a" * 48
        agent.make_command = lambda payload, jobdir: [sys.executable, "-c", "print('admission-positive-control')"]
        self.owner = "a" * 64
        self.start()

    def start(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), agent.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def tearDown(self):
        self.stop()
        agent.STATE, agent.WORKSPACE, agent.TOKEN, agent.make_command = self.before

    def call(self, path, body=None, auth=True):
        req = urllib.request.Request(
            "http://127.0.0.1:" + str(self.server.server_port) + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": "Bearer " + agent.TOKEN} if auth else {},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.load(e)

    def test_authenticated_fence_persists_and_blocks_real_execution(self):
        self.assertEqual(self.call("/api/maintenance", auth=False)[0], 401)
        code, positive = self.call("/api/jobs", {"task": "probe", "timeout": 5})
        self.assertEqual((code, positive.get("status")), (200, "PASS"), positive)
        self.assertEqual(self.call("/api/maintenance", {"action": "acquire", "owner": self.owner})[0], 200)
        before = len(list((agent.STATE / "jobs").iterdir()))
        self.assertEqual(self.call("/api/jobs", {"task": "probe"})[0], 503)
        self.assertEqual(len(list((agent.STATE / "jobs").iterdir())), before)
        self.stop()
        self.start()
        self.assertTrue(self.call("/api/maintenance")[1]["held"])
        self.assertEqual(self.call("/api/maintenance", {"action": "release", "owner": "b" * 64})[0], 409)
        self.assertEqual(self.call("/api/maintenance", {"action": "release", "owner": self.owner})[0], 200)
        code, positive = self.call("/api/jobs", {"task": "probe", "timeout": 5})
        self.assertEqual((code, positive.get("status")), (200, "PASS"), positive)

    def test_native_cancellation_before_dispatch_survives_restart(self):
        operation = "c" * 64
        self.assertEqual(self.call("/api/jobs/cancel", {"operation_id": operation})[0], 200)
        self.stop()
        self.start()
        code, result = self.call(
            "/api/jobs",
            {"task": "3d-creative", "operation": "world", "asset_id": "ast_" + "a" * 24, "operation_id": operation},
        )
        self.assertEqual((code, result.get("status")), (200, "CANCELLED"))
        self.assertFalse(any(p.is_dir() for p in (agent.STATE / "jobs").iterdir()))

    def test_cancellation_during_preparation_never_launches_command(self):
        entered = threading.Event()
        resume = threading.Event()
        operation = "f" * 64
        marker = pathlib.Path(self.tmp.name) / "unexpected-execution"

        def prepare(payload, jobdir):
            entered.set()
            if not resume.wait(5):
                raise RuntimeError("test preparation barrier timed out")
            return [sys.executable, "-c", "from pathlib import Path;Path(" + repr(str(marker)) + ").touch()"]

        agent.make_command = prepare
        results = []
        worker = threading.Thread(
            target=lambda: results.append(
                self.call("/api/jobs", {"task": "probe", "operation_id": operation, "timeout": 5})
            )
        )
        worker.start()
        try:
            self.assertTrue(entered.wait(5))
            self.assertEqual(self.call("/api/jobs/cancel", {"operation_id": operation})[0], 200)
        finally:
            resume.set()
            worker.join(8)
        self.assertFalse(worker.is_alive())
        self.assertEqual((results[0][0], results[0][1].get("status")), (200, "CANCELLED"), results)
        self.assertFalse(marker.exists())
        receipt = next((agent.STATE / "jobs").glob("*/result.json"))
        self.assertEqual(json.loads(receipt.read_text())["status"], "CANCELLED")

    def test_cancel_operation_targets_only_its_existing_job(self):
        operation = "d" * 64
        job = "1" * 16
        other = "2" * 16
        for ident, op in [(job, operation), (other, "e" * 64)]:
            p = agent.STATE / "jobs" / ident
            p.mkdir(parents=True)
            (p / "request.json").write_text(json.dumps({"task": "3d-creative", "operation_id": op}))
        code, result = self.call("/api/jobs/cancel", {"operation_id": operation})
        self.assertEqual((code, result.get("id")), (200, job))
        self.assertTrue((agent.STATE / "jobs" / job / "cancel.requested").is_file())
        self.assertFalse((agent.STATE / "jobs" / other / "cancel.requested").exists())
        self.assertEqual(self.call("/api/jobs/cancel", {"operation_id": "../escape"})[0], 400)

    def test_active_job_refuses_maintenance(self):
        with job_admission.start(agent.STATE):
            self.assertEqual(self.call("/api/maintenance", {"action": "acquire", "owner": self.owner})[0], 409)


if __name__ == "__main__":
    unittest.main()
