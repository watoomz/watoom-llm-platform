import importlib.util
import pathlib
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE.parent / "watoom-model-perf-accumulator.py"

spec = importlib.util.spec_from_file_location("watoom_model_perf_accumulator", SCRIPT)
acc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acc)


class AccumulateTests(unittest.TestCase):
    def test_first_observation_counts_in_full(self):
        state = {}
        total = acc.accumulate(state, "swift-qwen38-coder", "generated_tokens", 100.0)
        self.assertEqual(total, 100.0)
        self.assertEqual(state["swift-qwen38-coder"]["_raw_generated_tokens"], 100.0)

    def test_normal_increase_adds_delta(self):
        state = {"m": {"generated_tokens": 100.0, "_raw_generated_tokens": 100.0}}
        total = acc.accumulate(state, "m", "generated_tokens", 150.0)
        self.assertEqual(total, 150.0)

    def test_counter_reset_adds_post_reset_value_not_negative_delta(self):
        # Process restarted: raw counter dropped from 500 back to 20 (not a loss of 480).
        state = {"m": {"generated_tokens": 500.0, "_raw_generated_tokens": 500.0}}
        total = acc.accumulate(state, "m", "generated_tokens", 20.0)
        self.assertEqual(total, 520.0)
        self.assertEqual(state["m"]["_raw_generated_tokens"], 20.0)

    def test_unknown_model_starts_fresh(self):
        state = {"other": {"generated_tokens": 999.0, "_raw_generated_tokens": 999.0}}
        total = acc.accumulate(state, "new-model", "generated_tokens", 5.0)
        self.assertEqual(total, 5.0)
        self.assertEqual(state["other"]["generated_tokens"], 999.0)


if __name__ == "__main__":
    unittest.main()
