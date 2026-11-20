import json, pathlib, subprocess, tempfile, unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[3] / "ansible/roles/watoom-code/files/enable-reasoning-variants.py"
SPEC = {
    "models": ["a", "absent"],
    "variants": [
        {"id": "xhigh", "body": {"reasoning_effort": "xhigh"}},
        {"id": "off", "body": {"chat_template_kwargs": {"enable_thinking": False}}},
    ],
}


class Variants(unittest.TestCase):
    def test_sets_listed_models_only_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "opencode.json"
            p.write_text(
                json.dumps(
                    {
                        "keep": 1,
                        "providers": {"watoom": {"models": {"a": {"limit": {"context": 5}}, "b": {"name": "b"}}}},
                    }
                )
            )
            run = lambda spec=SPEC: subprocess.run(
                ["python3", str(SCRIPT), str(p), json.dumps(spec)], capture_output=True, text=True
            )
            r = run()
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.strip(), "CHANGED")
            v = json.loads(p.read_text())
            m = v["providers"]["watoom"]["models"]
            self.assertEqual(m["a"]["variants"], SPEC["variants"])
            self.assertEqual(m["a"]["limit"], {"context": 5})
            self.assertNotIn("variants", m["b"])
            self.assertEqual(v["keep"], 1)
            self.assertEqual(run().stdout.strip(), "UNCHANGED")
            self.assertNotEqual(run({"models": ["a"], "variants": [{"id": "x", "command": "rm"}]}).returncode, 0)


if __name__ == "__main__":
    unittest.main()
