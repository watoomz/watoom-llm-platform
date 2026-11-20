import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from g3h_service import Runtime, atomic
from controller import State, Conflict, Unsafe
from durable_store import DurableStore
from inference_leases import leases, prune


class API:
    def get(self, name):
        return {
            "metadata": {"uid": name, "generation": 1},
            "spec": {"replicas": 1 if name == "qwen" else 0},
            "status": {},
        }


class Leases(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.r = Runtime(
            {
                "state_root": str(self.root),
                "models": ["qwen", "other", "mesh"],
                "primary": "qwen",
                "mesh": "mesh",
                "urls": {},
                "stop_timeout": 1,
                "startup_timeout": 1,
            },
            api=API(),
            probe=lambda *a: True,
            identity=lambda p: "alive",
        )
        DurableStore(self.root / "state.json").save(State())

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, action, **data):
        return self.r.handle(dict(action=action, **data), private=False, pid=123, uid=0)

    def test_lease_blocks_swap_and_stop(self):
        self.call("begin-inference", deployment="qwen", allow_switch=False)
        with self.assertRaises(Conflict):
            self.call("request-model", deployment="other", allow_switch=True)
        with self.r.store.exclusive(), self.assertRaises(Unsafe):
            self.r.actuator.scale("qwen", 0, 1)

    def test_uncertain_end_persists_then_idle_prunes(self):
        token = self.call("begin-inference", deployment="qwen", allow_switch=False)["lease"]
        with patch("inference_leases.idle", return_value=False):
            self.assertFalse(self.call("end-inference", lease=token)["released"])
        with patch("inference_leases.idle", return_value=True), self.r.store.exclusive():
            self.assertEqual(prune(self.r, atomic), {})

    def test_wrong_process_cannot_release(self):
        token = self.call("begin-inference", deployment="qwen", allow_switch=False)["lease"]
        with self.assertRaises(Unsafe):
            self.r.handle({"action": "end-inference", "lease": token}, private=False, pid=456, uid=0)

    def test_restart_preserves_accounting(self):
        self.call("begin-inference", deployment="qwen", allow_switch=False)
        self.assertEqual(len(leases(self.root)), 1)

    def test_alive_request_not_pruned_by_idle_snapshot(self):
        self.call("begin-inference", deployment="qwen", allow_switch=False)
        with patch("inference_leases.idle", return_value=True), self.r.store.exclusive():
            self.assertEqual(len(prune(self.r, atomic)), 1)


if __name__ == "__main__":
    unittest.main()


class CompletedAccounting(unittest.TestCase):
    setUp = Leases.setUp
    tearDown = Leases.tearDown
    call = Leases.call

    def seed(self, completed=True, name="other"):
        atomic(
            self.root / "inference-leases.json",
            {
                "version": 1,
                "leases": {"fixture": {"deployment": name, "pid": 123, "start": "alive", "completed": completed}},
            },
        )

    def test_completed_stopped_backend_pruned_without_http_or_scaling(self):
        self.seed()
        with patch(
            "inference_leases.idle", side_effect=AssertionError("stopped endpoint must not be queried")
        ), patch.object(self.r.actuator, "scale", side_effect=AssertionError("must not scale")):
            self.assertEqual(self.call("status")["active_requests"], 0)

    def test_live_uncompleted_stopped_lease_preserved(self):
        self.seed(completed=False)
        with patch("inference_leases.idle", return_value=False):
            self.assertEqual(self.call("status")["active_requests"], 1)

    def test_terminating_or_unproven_pods_preserve_completed(self):
        self.seed()
        with patch.object(self.r.actuator, "probe", return_value=False), patch(
            "inference_leases.idle", return_value=False
        ):
            self.assertEqual(self.call("status")["active_requests"], 1)

    def test_identity_lookup_failure_preserves_completed(self):
        self.seed()
        with patch.object(self.r.actuator, "_get", side_effect=Unsafe("identity changed")), patch(
            "inference_leases.idle", return_value=False
        ):
            self.assertEqual(self.call("status")["active_requests"], 1)

    def test_current_completed_idle_lease_pruned(self):
        self.seed(name="qwen")
        with patch("inference_leases.idle", return_value=True):
            self.assertEqual(self.call("status")["active_requests"], 0)

    def test_uncertain_state_does_not_prune(self):
        self.seed()
        with self.r.store.exclusive():
            self.r.store.save(State("recovery-required", None, 0, True))
        with patch("inference_leases.prune", side_effect=AssertionError("must preserve uncertain state")):
            self.assertTrue(self.call("status")["uncertain"])
