import unittest, tempfile, pathlib, json, sys, sqlite3, gc, hashlib
from unittest.mock import patch, Mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import maintenance_guard, release_guard


class RecoveryTests(unittest.TestCase):
    def fixture(self, folder):
        m = maintenance_guard.Maintenance.__new__(maintenance_guard.Maintenance)
        m.ns = "owned"
        m.name = "owned"
        m.policy = "owned-release-maintenance"
        m.out = pathlib.Path(folder)
        m.held = True
        m.service = {"spec": {"selector": {"app": "owned"}}}
        m.kub = Mock(return_value=m.service)
        m.restore_access = Mock()
        policy = {
            "metadata": {"labels": {"watoom-release-owner": "owned"}},
            "spec": {"podSelector": {"matchLabels": {"app": "owned"}}, "policyTypes": ["Ingress"]},
        }
        (m.out / "maintenance-policy.json").write_text(json.dumps(policy))
        return m, policy

    def test_partial_acquisition_policy_removed_without_overwriting_service(self):
        with tempfile.TemporaryDirectory() as folder:
            m, policy = self.fixture(folder)
            with patch.object(maintenance_guard, "run", side_effect=[json.dumps(policy).encode(), b""]) as command:
                m.release()
            self.assertFalse(m.held)
            m.restore_access.assert_called_once()
            self.assertIn("delete", command.call_args_list[-1].args[0])
            self.assertFalse(any("patch" in call.args[0] for call in command.call_args_list))

    def test_failure_before_any_mutation_needs_no_cleanup_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            m, _ = self.fixture(folder)
            with patch.object(maintenance_guard, "run", return_value=b"") as command:
                m.release()
            self.assertFalse(m.held)
            self.assertEqual(command.call_count, 1)
            m.restore_access.assert_called_once()

    def test_concurrent_service_edit_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            m, _ = self.fixture(folder)
            m.kub.return_value = {"spec": {"selector": {"app": "another-owner"}}}
            with patch.object(maintenance_guard, "run") as command:
                with self.assertRaises(release_guard.UnsafeRelease):
                    m.release()
            command.assert_not_called()
            self.assertTrue(m.held)
            m.restore_access.assert_not_called()

    def test_wal_snapshot_is_standalone_and_digest_stable_after_close(self):
        with tempfile.TemporaryDirectory() as folder:
            source = pathlib.Path(folder) / "source.sqlite"
            destination = pathlib.Path(folder) / "before.sqlite"
            with sqlite3.connect(source) as db:
                db.execute("pragma journal_mode=wal")
                db.execute("create table fact(value text)")
                db.execute("insert into fact values ('committed')")
                db.commit()
                release_guard.snapshot_database(source, destination)
                digest = hashlib.sha256(destination.read_bytes()).digest()
                gc.collect()
                self.assertEqual(digest, hashlib.sha256(destination.read_bytes()).digest())
                self.assertFalse(pathlib.Path(str(destination) + "-wal").exists())
                with sqlite3.connect("file:" + str(destination) + "?immutable=1&mode=ro", uri=True) as copy:
                    self.assertEqual(copy.execute("select value from fact").fetchone()[0], "committed")


if __name__ == "__main__":
    unittest.main()
