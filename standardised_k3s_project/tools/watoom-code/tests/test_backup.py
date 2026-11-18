import gzip, pathlib, sqlite3, sys, tempfile, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import backup

class BackupTests(unittest.TestCase):
    def test_wal_database_copy_is_verified_counted_and_compressed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);source=root/"application.sqlite"
            live=sqlite3.connect(source);live.execute("pragma journal_mode=wal")
            live.execute("create table session_v2(id)");live.executemany("insert into session_v2 values (?)",[(i,) for i in range(5)]);live.commit()
            result=backup.copy_sqlite(source,root/"out/application.sqlite");live.close()
            self.assertEqual(result,{"integrity":"ok","rows":{"session_v2":5}})
            self.assertFalse((root/"out/application.sqlite").exists())
            self.assertEqual(sorted(p.name for p in (root/"out").iterdir()),["application.sqlite.gz"])
            restored=root/"restored.sqlite";restored.write_bytes(gzip.decompress((root/"out/application.sqlite.gz").read_bytes()))
            with sqlite3.connect(restored) as db:self.assertEqual(db.execute("select count(*) from session_v2").fetchone()[0],5)
    def test_prune_keeps_newest_verified_runs_and_ignores_others(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=pathlib.Path(tmp)
            for stamp in ["20261001T000000Z","20261002T000000Z","20261003T000000Z"]:
                (dest/stamp).mkdir();(dest/stamp/"manifest.json").write_text("{}")
            (dest/"20261004T000000Z").mkdir()
            (dest/"notes").mkdir()
            backup.prune(dest,2)
            self.assertEqual(sorted(d.name for d in dest.iterdir()),["20261002T000000Z","20261003T000000Z","20261004T000000Z","notes"])
    def test_metric_is_written_atomically_and_world_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=pathlib.Path(tmp)/"textfile";backup.write_metric(directory,1793000000,42)
            text=(directory/"watoom-backup.prom").read_text()
            self.assertIn('watoom_backup_last_success_timestamp_seconds{target="watoom-code"} 1793000000',text)
            self.assertEqual((directory/"watoom-backup.prom").stat().st_mode & 0o777,0o644)
            self.assertFalse(any(p.name.startswith(".") for p in directory.iterdir()))
    def test_metric_parents_are_traversable_under_private_umask(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            old=os.umask(0o077)
            try:backup.write_metric(pathlib.Path(tmp)/"node_exporter/textfile",1,1)
            finally:os.umask(old)
            self.assertEqual((pathlib.Path(tmp)/"node_exporter").stat().st_mode & 0o777,0o755)
if __name__=="__main__":unittest.main()
