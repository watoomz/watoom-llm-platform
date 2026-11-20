import json, pathlib, tempfile, unittest
from broker import apply_reasoning_variants

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "ansible/roles/watoom-code/files/enable-reasoning-variants.py"


class ReasoningVariants(unittest.TestCase):
    def test_reregistered_model_gets_its_variants_back_and_missing_spec_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as d:
            app = pathlib.Path(d) / "opencode.json"
            app.write_text(json.dumps({"providers": {"watoom": {"models": {"mm-a": {"name": "A"}, "mm-b": {"name": "B"}}}}}))
            spec = pathlib.Path(d) / "spec.json"
            self.assertFalse(apply_reasoning_variants(str(app), spec, SCRIPT))
            spec.write_text(json.dumps({"models": ["mm-a"], "variants": [{"id": "low", "body": {"reasoning_effort": "low"}}]}))
            self.assertTrue(apply_reasoning_variants(str(app), spec, SCRIPT))
            models = json.loads(app.read_text())["providers"]["watoom"]["models"]
            self.assertEqual([v["id"] for v in models["mm-a"]["variants"]], ["low"])
            self.assertNotIn("variants", models["mm-b"])
            self.assertFalse(apply_reasoning_variants(str(app), spec, SCRIPT))


if __name__ == "__main__":
    unittest.main()
