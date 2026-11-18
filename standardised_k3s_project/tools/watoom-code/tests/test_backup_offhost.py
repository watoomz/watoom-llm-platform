import json, os, pathlib, sys, tempfile, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import backup_offhost
from backup import sha256

class OffhostTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); root = pathlib.Path(self.tmp.name)
        self.dest, self.target, self.receipts = root / "dest", root / "export", root / "receipts"
        self.dest.mkdir(); self.receipts.mkdir(); self.gid = os.getgid()
    def tearDown(self):
        self.tmp.cleanup()
    def run_(self, stamp, corrupt=False):
        run = self.dest / stamp; (run / "home").mkdir(parents=True)
        (run / "a.gz").write_bytes(stamp.encode()); (run / "home/b.db.gz").write_bytes(b"b")
        files = {n: sha256(run / n) for n in ["a.gz", "home/b.db.gz"]}
        (run / "manifest.json").write_text(json.dumps({"files": files}))
        if corrupt: (run / "a.gz").write_bytes(b"changed")
        return files

    def test_exports_newest_verified_runs_and_prunes_old(self):
        for s in ["20261020T000000Z", "20261021T000000Z", "20261022T000000Z"]: self.run_(s)
        self.run_("20261023T000000Z", corrupt=True)
        self.assertEqual(backup_offhost.export(self.dest, self.target, 2, self.gid), ["20261021T000000Z", "20261022T000000Z"])
        (self.dest / "20261020T000000Z").rename(self.dest / "x")
        self.run_("20261024T000000Z")
        self.assertEqual(backup_offhost.export(self.dest, self.target, 2, self.gid), ["20261022T000000Z", "20261024T000000Z"])
        self.assertEqual(sorted(p.name for p in self.target.iterdir()), ["20261022T000000Z", "20261024T000000Z"])
        f = self.target / "20261024T000000Z/home/b.db.gz"
        self.assertEqual(oct(f.stat().st_mode & 0o777), "0o640")
        self.assertTrue((self.target / "20261024T000000Z/manifest.json").is_file())

    def test_receipt_must_match_manifest_exactly(self):
        files = self.run_("20261022T000000Z"); self.run_("20261023T000000Z")
        backup_offhost.export(self.dest, self.target, 3, self.gid)
        self.assertIsNone(backup_offhost.check_receipts(self.target, self.receipts))
        (self.receipts / "a.json").write_text(json.dumps({"run": "20261022T000000Z", "files": files}))
        (self.receipts / "b.json").write_text(json.dumps({"run": "20261023T000000Z", "files": {**files, "a.gz": "0"}}))
        (self.receipts / "c.json").write_text(json.dumps({"run": "../../etc", "files": {}}))
        (self.receipts / "d.json").write_text("not json")
        self.assertEqual(backup_offhost.check_receipts(self.target, self.receipts), "20261022T000000Z")

    def test_metric(self):
        backup_offhost.write_metric(self.receipts, "20261022T000000Z")
        text = (self.receipts / "watoom_backup_offhost.prom").read_text()
        self.assertIn('watoom_backup_offhost_verified_run_timestamp_seconds{target="watoom-code",host="rig"} 1792627200', text)

class InstallLocationTests(unittest.TestCase):
    def test_backup_units_never_execute_from_a_checkout(self):
        playbooks = pathlib.Path(__file__).resolve().parents[3] / "ansible/playbooks"
        for name in ["watoom-code-backup.yml", "watoom-backup-offhost.yml"]:
            text = (playbooks / name).read_text()
            self.assertIn("include_tasks: tasks/watoom-backup-libexec.yml", text)
            for line in text.splitlines():
                if "Exec" in line or "_tool:" in line:
                    self.assertNotIn("playbook_dir", line, name)
                    self.assertNotIn("/tools/", line, name)

if __name__ == "__main__":
    unittest.main()
