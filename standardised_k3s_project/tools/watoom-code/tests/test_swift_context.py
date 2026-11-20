import json, pathlib, subprocess, tempfile, unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
ROLE = ROOT / "ansible/roles/watoom-code"
SCRIPT = ROLE / "files/enable-swift-context.py"


class SwiftContext(unittest.TestCase):
    def test_migration_preserves_output_and_other_models(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "opencode.json"
            data = {
                "providers": {
                    "watoom": {
                        "models": {
                            "swift-qwen38-coder": {"limit": {"context": 131072, "output": 4096}},
                            "other": {"limit": {"context": 8192}},
                        }
                    }
                },
                "keep": "untouched",
            }
            path.write_text(json.dumps(data))
            first = subprocess.run(["python3", str(SCRIPT), str(path), "100000"], capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            value = json.loads(path.read_text())
            data["providers"]["watoom"]["models"]["swift-qwen38-coder"]["limit"]["context"] = 100000
            self.assertEqual(value, data)
            before = path.read_bytes()
            second = subprocess.run(["python3", str(SCRIPT), str(path)], capture_output=True, text=True)
            self.assertEqual(second.stdout.strip(), "UNCHANGED")
            self.assertEqual(path.read_bytes(), before)

    def test_invalid_capacity_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "opencode.json"
            path.write_text("{}")
            before = path.read_bytes()
            result = subprocess.run(["python3", str(SCRIPT), str(path), "200000"], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(path.read_bytes(), before)

    def test_iac_uses_one_stable_default(self):
        self.assertIn("watoom_code_swift_context_tokens: 100000", (ROLE / "defaults/main.yml").read_text())
        self.assertIn(
            '"context": {{ watoom_code_swift_context_tokens | int }}', (ROLE / "templates/opencode.json.j2").read_text()
        )
        self.assertIn(
            "opencode.json {{ watoom_code_swift_context_tokens | int }}", (ROLE / "tasks/main.yml").read_text()
        )


if __name__ == "__main__":
    unittest.main()
