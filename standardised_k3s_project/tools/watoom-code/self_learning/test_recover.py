import unittest, tempfile, pathlib, os, json
from unittest.mock import patch
import recover


class RecoveryTests(unittest.TestCase):
    def test_healthy_candidate_survives_agent_loss(self):
        self.assertEqual(
            recover.decide(
                {"phase": "CUTOVER_STARTED", "health_failures": 20, "grace_until": 0, "agent_last_seen": 0},
                True,
                999999,
            ),
            "KEEP_HEALTHY",
        )

    def test_explicit_critical_failure_rolls_back_even_when_http_is_healthy(self):
        self.assertEqual(recover.decide({"phase": "CUTOVER_FAILED"}, True, 0), "RESTORE")

    def test_startup_has_bounded_grace(self):
        self.assertEqual(recover.decide({"phase": "CUTOVER_STARTED", "grace_until": 600}, False, 599), "WAIT_STARTUP")

    def test_three_health_failures_restore(self):
        for count, expected in [(0, "RECHECK"), (1, "RECHECK"), (2, "RESTORE")]:
            self.assertEqual(
                recover.decide({"phase": "CUTOVER_STARTED", "grace_until": 0, "health_failures": count}, False, 1000),
                expected,
            )

    def test_idle_baseline_is_never_replaced(self):
        for phase in [
            "BASELINE_SAVED",
            "STAGING_TESTED",
            "CUTOVER_READY",
            "COMPLETE",
            "ROLLED_BACK",
            "BLOCKED_APPROVAL",
        ]:
            self.assertEqual(recover.decide({"phase": phase}, False, 9999), "NO_ACTION")

    def test_rollback_requires_health_verification(self):
        self.assertEqual(recover.decide({"phase": "ROLLBACK_IN_PROGRESS"}, False, 0), "RESTORE")
        self.assertEqual(recover.decide({"phase": "ROLLBACK_IN_PROGRESS"}, True, 0), "VERIFY_ROLLBACK")

    def test_atomic_checkpoint_is_private_and_partial_write_preserves_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / "state.json"
            recover.atomic(p, {"phase": "BASELINE_SAVED"})
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            with patch.object(recover.os, "replace", side_effect=OSError("interrupted rename")):
                with self.assertRaises(OSError):
                    recover.atomic(p, {"phase": "CUTOVER_STARTED"})
            self.assertEqual(json.loads(p.read_text())["phase"], "BASELINE_SAVED")
            recover.atomic(p, {"phase": "CUTOVER_STARTED"})
            self.assertEqual(json.loads(p.read_text())["phase"], "CUTOVER_STARTED")

    def test_unapproved_production_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / "state.json"
            recover.atomic(
                p,
                {
                    "namespace": "watoom-code",
                    "deployment": "watoom-code",
                    "phase": "CUTOVER_STARTED",
                    "production_approved": False,
                },
            )
            with self.assertRaises(ValueError):
                recover.tick(p)

    def test_changed_deployment_identity_never_triggers_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / "state.json"
            recover.atomic(
                p,
                {
                    "namespace": "watoom-code-learning-fixture",
                    "deployment": "learning-app",
                    "deployment_uid": "baseline",
                    "phase": "CUTOVER_FAILED",
                    "replicas": 1,
                },
            )

            class Fake:
                def __init__(self, *args):
                    pass

                def kub(self, *args):
                    return {"metadata": {"uid": "different"}}

            with patch.object(recover, "Maintenance", Fake), patch.object(recover.subprocess, "run") as command:
                self.assertEqual(recover.tick(p)["action"], "BLOCKED_RECOVERY")
                command.assert_not_called()
            self.assertEqual(json.loads(p.read_text())["phase"], "BLOCKED_RECOVERY")

    def test_changed_configuration_is_preserved_and_restored_before_verification(self):
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "config").mkdir()
            config = root / "config/opencode.json"
            config.write_text('{"candidate":true}')
            prior = root / "original.json"
            prior.write_text('{"original":true}')
            original = {"apiVersion": "apps/v1", "kind": "Deployment", "spec": {"template": {"metadata": {}}}}
            manifest = root / "deployment.json"
            recover.atomic(manifest, original)
            state = root / "state.json"
            recover.atomic(
                state,
                {
                    "phase": "CUTOVER_FAILED",
                    "namespace": "watoom-code-learning-fixture",
                    "deployment": "learning-app",
                    "deployment_uid": "same",
                    "replicas": 1,
                    "config": str(config),
                    "baseline_config": str(prior),
                    "baseline_config_sha256": recover.digest(prior),
                    "baseline_deployment": str(manifest),
                    "baseline_deployment_sha256": recover.digest(manifest),
                    "candidate_config_sha256": recover.digest(config),
                    "recovery_nonce": "fixture",
                },
            )

            class Fake:
                ready = False

                def __init__(self, *args):
                    pass

                def kub(self, *args):
                    return {
                        "metadata": {"uid": "same"},
                        "spec": original["spec"],
                        "status": {"readyReplicas": int(self.ready)},
                    }

                def request(self, path):
                    return (
                        {"version": "fixture"}
                        if path == "/api/info"
                        else {"data": [] if path.startswith("/api/skill") else {}}
                    )

            with patch.object(recover, "Maintenance", Fake), patch.object(
                recover.subprocess, "run", return_value=SimpleNamespace(returncode=0, stderr=b"")
            ):
                self.assertEqual(recover.tick(state)["action"], "RESTORE")
                self.assertEqual(config.read_bytes(), prior.read_bytes())
                failed = list(root.glob("failed-config-*.json"))
                self.assertEqual(len(failed), 1)
                self.assertEqual(failed[0].read_text(), '{"candidate":true}')
                Fake.ready = True
                self.assertEqual(recover.tick(state)["phase"], "ROLLED_BACK")

    def test_unverifiable_restoration_has_a_bounded_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = pathlib.Path(tmp) / "state.json"
            recover.atomic(
                state,
                {
                    "phase": "ROLLBACK_IN_PROGRESS",
                    "namespace": "watoom-code-learning-fixture",
                    "deployment": "learning-app",
                    "rollback_started": 0,
                },
            )
            with patch.object(recover, "Maintenance") as maintenance:
                self.assertEqual(recover.tick(state)["action"], "BLOCKED_RECOVERY")
                maintenance.assert_not_called()

    def test_preflight_failure_does_not_restart_an_unchanged_healthy_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "config").mkdir()
            config = root / "config/opencode.json"
            config.write_text("{}")
            prior = root / "original.json"
            prior.write_text("{}")
            spec = {"template": {"metadata": {}}}
            manifest = root / "deployment.json"
            recover.atomic(manifest, {"spec": spec})
            state = root / "state.json"
            recover.atomic(
                state,
                {
                    "phase": "CUTOVER_FAILED",
                    "namespace": "watoom-code-learning-fixture",
                    "deployment": "learning-app",
                    "deployment_uid": "same",
                    "replicas": 1,
                    "config": str(config),
                    "baseline_config": str(prior),
                    "baseline_config_sha256": recover.digest(prior),
                    "baseline_deployment": str(manifest),
                    "baseline_deployment_sha256": recover.digest(manifest),
                    "candidate_config_sha256": recover.digest(config),
                    "recovery_nonce": "fixture",
                },
            )

            class Fake:
                def __init__(self, *args):
                    pass

                def kub(self, *args):
                    return {"metadata": {"uid": "same"}, "status": {"readyReplicas": 1}, "spec": spec}

                def request(self, path):
                    return (
                        {"version": "fixture"}
                        if path == "/api/info"
                        else {"data": [] if path.startswith("/api/skill") else {}}
                    )

            with patch.object(recover, "Maintenance", Fake), patch.object(recover.subprocess, "run") as command:
                self.assertEqual(recover.tick(state)["action"], "BASELINE_ALREADY_RUNNING")
                command.assert_not_called()
                self.assertEqual(recover.tick(state)["phase"], "ROLLED_BACK")


if __name__ == "__main__":
    unittest.main()
