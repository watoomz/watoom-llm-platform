import json, pathlib, subprocess, sys, tempfile, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import release_ledger

class ReleaseLedgerTests(unittest.TestCase):
    def test_append_is_ordered_and_records_iac_commit_and_dirtiness(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = pathlib.Path(tmp) / "repo"; repo.mkdir()
            git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)
            git("init", "-q"); (repo / "f").write_text("1"); git("add", "f")
            git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "c")
            ledger = pathlib.Path(tmp) / "state" / "ledger.jsonl"
            self.assertIsNone(release_ledger.latest(ledger))
            first = release_ledger.append("img@sha256:" + "a" * 64, "c" * 40, repo, "test", "/ev1", ledger=ledger)
            (repo / "f").write_text("2")
            second = release_ledger.append("img@sha256:" + "b" * 64, "d" * 40, repo, "test", "/ev2", ledger=ledger, note="x")
            self.assertFalse(first["iac_dirty"]); self.assertTrue(second["iac_dirty"])
            self.assertEqual(len(first["iac_commit"]), 40)
            self.assertEqual([e["image"][-1] for e in release_ledger.entries(ledger)], ["a", "b"])
            self.assertEqual(release_ledger.latest(ledger)["note"], "x")
            self.assertEqual(ledger.stat().st_mode & 0o777, 0o644)

if __name__ == "__main__":
    unittest.main()
