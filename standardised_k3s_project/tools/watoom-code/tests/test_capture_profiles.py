import unittest, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from capture_profiles import exit_evidence, frame_evidence_errors


class Frames(unittest.TestCase):
    def test_identical_ability_showcase_rejected(self):
        self.assertTrue(frame_evidence_errors("p7", [{"sha256": "a"} for _ in range(8)]))

    def test_varied_frames_not_rejected_by_duplicate_gate(self):
        self.assertFalse(frame_evidence_errors("p7", [{"sha256": str(i)} for i in range(8)]))

    def test_p6_unchanged(self):
        self.assertFalse(frame_evidence_errors("p6", [{"sha256": "a"} for _ in range(3)]))


class Exit(unittest.TestCase):
    def test_deadline_kill_is_named_not_a_script_error(self):
        timed_out, errors = exit_evidence(1, "STEP 5\n", 600.4, 600, [])
        self.assertTrue(timed_out)
        self.assertIn("WORKER_DEADLINE_EXCEEDED", errors[0])
        self.assertIn("600s limit", errors[0])

    def test_systemd_runtime_limit_line(self):
        self.assertTrue(exit_evidence(1, "Service reached runtime time limit. Stopping.", 120, 600, [])[0])

    def test_runner_timeout(self):
        self.assertTrue(exit_evidence(None, "", 630, 600, [])[0])

    def test_silent_early_exit_reports_log_tail(self):
        timed_out, errors = exit_evidence(1, "a\nb\nlast words\n", 12, 600, [])
        self.assertFalse(timed_out)
        self.assertIn("GODOT_EXIT_1", errors[0])
        self.assertIn("last words", errors[0])

    def test_script_error_and_success_unchanged(self):
        self.assertEqual(exit_evidence(1, "SCRIPT ERROR: x", 12, 600, ["SCRIPT ERROR: x"]), (False, []))
        self.assertEqual(exit_evidence(0, "", 30, 600, []), (False, []))
