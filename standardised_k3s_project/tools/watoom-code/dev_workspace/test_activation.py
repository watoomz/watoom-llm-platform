import importlib.util, pathlib, tempfile, unittest, json, base64, sys
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
spec = importlib.util.spec_from_file_location("dev_activation", pathlib.Path(__file__).with_name("activation.py"))
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class Recovery(unittest.TestCase):
    def test_incomplete_activation_restores_bytes_disables_runtime_and_releases_owned_fence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            config = root / "opencode.json"
            agent = root / "agent.md"
            journal = root / "activation.json"
            evidence = root / "evidence"
            evidence.mkdir()
            before = b'{"plugins":[]}'
            after = b'{"plugins":["dev"]}'
            config.write_bytes(after)
            agent.write_bytes(b"owned-agent")
            (root / "config.json").write_text('{"enabled":true}')
            a.atomic(
                journal,
                {
                    "phase": "APPLYING",
                    "before": base64.b64encode(before).decode(),
                    "after": base64.b64encode(after).decode(),
                    "agent_sha": a.digest(b"owned-agent"),
                    "evidence": str(evidence),
                    "owner": "owned-token",
                },
            )

            class Manager:
                def request(self, path, body=None):
                    return {"data": {"held": True}}

            with patch.multiple(a, HOME=root, CONFIG=config, AGENT=agent, JOURNAL=journal), patch.object(
                a, "manager", return_value=Manager()
            ), patch.object(a, "write", side_effect=lambda path, data: path.write_bytes(data)), patch.object(
                a.release_guard, "release"
            ) as release:
                a.recover()
                release.assert_called_once()
                self.assertEqual(release.call_args.args[-1], "owned-token")
                self.assertEqual(config.read_bytes(), before)
                self.assertFalse(json.loads((root / "config.json").read_text())["enabled"])
                self.assertFalse(agent.exists())
                self.assertTrue((evidence / "rolled-back-agent.md").exists())
                self.assertEqual(json.loads(journal.read_text())["phase"], "ROLLED_BACK")
                a.recover()
                self.assertEqual(release.call_count, 1)


if __name__ == "__main__":
    unittest.main()
