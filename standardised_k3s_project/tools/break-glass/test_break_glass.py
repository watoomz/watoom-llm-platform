import json
import os
import pathlib
import sqlite3
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import break_glass as bg  # noqa: E402

SCHEMA = """
create table session_v2 (id text primary key, parent_id text, time_suspended integer, time_updated integer not null default 0,
  resume_attempts integer not null default 0, time_idle integer, idle_outcome text);
create table session_inbox (id text primary key, session_id text not null, type text not null, payload text not null,
  delivery text not null, enqueued_seq integer not null, time_created integer not null);
create table job (notification_id text primary key, id text not null, session_id text not null, child_session_id text,
  kind text not null, title text, status text not null, output text, error text, recovery text not null default '',
  time_created integer not null default 0, time_updated integer not null default 0);
create table kv (key text primary key, value text);
create table _watoom_specialist_job (id text primary key, scope text not null default '', job text not null default '',
  specialist text not null default '', capability text not null default '', input_digest text not null default '',
  phase text not null, primary_body text not null default '{}', specialist_body text not null default '{}',
  generation integer, body text, outcome text, error text);
"""


def fixture(path):
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    db.executemany("insert into session_v2(id,parent_id,time_suspended,time_updated,time_idle,idle_outcome) values (?,?,?,?,?,?)", [
        ("root-held", None, 111, 5, None, None),          # root claim: not an orphan
        ("parent-ok", None, None, 5, 9, "interrupted"),
        ("child-orphan", "parent-ok", 222, 6, None, None),  # parent interrupted and idle: orphan
        ("free", None, None, 7, None, None),
    ])
    db.execute("insert into session_inbox values ('i1','root-held','prompt','{}','queued',1,1)")
    db.execute("insert into job(notification_id,id,session_id,kind,status) values ('n1','j1','root-held','shell','running')")
    db.execute("insert into job(notification_id,id,session_id,kind,status) values ('n2','j2','root-held','shell','completed')")
    db.execute("insert into kv values ('job.background/a', ?)", (json.dumps({"status": "running", "keep": 1}),))
    db.execute("insert into kv values ('job.background/b', ?)", (json.dumps({"status": "completed"}),))
    db.execute("insert into kv values ('other', 'x')")
    db.execute("insert into _watoom_specialist_job(id,phase,specialist_body,generation) values ('s1','running','{}',NULL)")
    db.execute("insert into _watoom_specialist_job(id,phase,specialist_body,generation) values ('s2','uncertain','{\"execution\":\"gpu\"}',4)")
    db.execute("insert into _watoom_specialist_job(id,phase,specialist_body,generation) values ('s3','completed','{}',NULL)")
    db.commit()
    db.close()


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.db = self.dir / "application.sqlite"
        fixture(self.db)

    def test_diagnose_counts_every_gate_and_flags_orphans(self):
        d = bg.db_diagnose(self.db)
        claims = {c["id"]: c["orphan"] for c in d["claims"]}
        self.assertEqual(claims, {"root-held": False, "child-orphan": True})
        self.assertEqual((d["inbox"], d["running_jobs"], d["background_jobs"], d["unsettled_specialists"], d["uncertain_gpu_specialists"]), (1, 1, 1, 1, 1))

    def test_repair_clears_gates_keeps_history_and_saves_evidence(self):
        counts = bg.db_repair(self.db, self.dir / "evidence.json")
        self.assertEqual(counts, {"claims": 2, "inbox": 1, "jobs": 1, "background": 1, "specialists": 1})
        d = bg.db_diagnose(self.db)
        self.assertEqual((d["claims"], d["inbox"], d["running_jobs"], d["background_jobs"], d["unsettled_specialists"]), ([], 0, 0, 0, 0))
        self.assertEqual(d["uncertain_gpu_specialists"], 1, "GPU-uncertain specialists belong to the GPU controller, not to this repair")
        db = sqlite3.connect(self.db)
        self.assertEqual(db.execute("select count(*) from session_v2").fetchone()[0], 4, "sessions are never deleted")
        self.assertEqual(db.execute("select status from job where id='j1'").fetchone()[0], "cancelled")
        self.assertEqual(db.execute("select status from job where id='j2'").fetchone()[0], "completed")
        self.assertEqual(json.loads(db.execute("select value from kv where key='job.background/a'").fetchone()[0]), {"status": "cancelled", "keep": 1})
        self.assertEqual(db.execute("select value from kv where key='other'").fetchone()[0], "x")
        self.assertEqual(db.execute("select time_updated from session_v2 where id='root-held'").fetchone()[0], 5, "time_updated is preserved like the app's own release")
        evidence = json.loads((self.dir / "evidence.json").read_text())
        self.assertEqual([c["id"] for c in evidence["claims"]], ["root-held", "child-orphan"])
        self.assertEqual(len(evidence["inbox"]), 1)

    def test_repair_is_atomic_when_a_step_fails(self):
        sqlite3.connect(self.db).executescript("drop table kv; create table kv (key text primary key);")  # value column gone
        with self.assertRaises(sqlite3.Error):
            bg.db_repair(self.db, self.dir / "evidence.json")
        db = sqlite3.connect(self.db)
        self.assertEqual(db.execute("select count(*) from session_v2 where time_suspended is not null").fetchone()[0], 2, "a failed repair must roll back completely")
        self.assertEqual(db.execute("select count(*) from session_inbox").fetchone()[0], 1)
        self.assertEqual(db.execute("select status from job where id='j1'").fetchone()[0], "running")
        self.assertFalse((self.dir / "evidence.json").exists())

    def test_repair_leaves_file_ownership_unchanged(self):
        before = self.db.stat()
        bg.db_repair(self.db, self.dir / "evidence.json")
        for suffix in ("", "-wal", "-shm"):
            side = pathlib.Path(str(self.db) + suffix)
            if side.exists():
                self.assertEqual((side.stat().st_uid, side.stat().st_gid), (before.st_uid, before.st_gid))


class RequestTests(unittest.TestCase):
    def test_validation(self):
        t = time.time()
        self.assertIsNone(bg.valid_request({"mode": "stale", "time": t}, t))
        self.assertIsNone(bg.valid_request({"mode": "force", "time": t - 100}, t))
        self.assertEqual(bg.valid_request({"mode": "force", "time": t - 1000}, t), "request expired")
        self.assertEqual(bg.valid_request({"mode": "force", "time": t + 600}, t), "request expired")
        self.assertEqual(bg.valid_request({"mode": "wipe", "time": t}, t), "invalid mode")
        self.assertEqual(bg.valid_request("force", t), "invalid mode")
        self.assertEqual(bg.valid_request({"mode": "force"}, t), "request expired")


class ProblemTests(unittest.TestCase):
    def healthy(self):
        return {"app": {"replicas": 1, "ready": 1, "guard_file_present": False},
                "database": {"claims": [], "inbox": 0, "running_jobs": 0, "background_jobs": 0, "unsettled_specialists": 0, "uncertain_gpu_specialists": 0},
                "workers": {"pods": [], "jobs": [], "units": []},
                "gpu": {"owner": None, "phase": "qwen-ready", "uncertain": False, "owner_ended": False, "dead_leases": []},
                "inference": {"router_ready": 1, "selected_model": "m", "selected_model_ready": 1}}

    def test_healthy_has_no_problems(self):
        self.assertEqual(bg.problems(self.healthy()), [])

    def test_each_wedge_is_reported(self):
        r = self.healthy()
        r["app"]["guard_file_present"] = True
        r["database"]["claims"] = [{"orphan": True}]
        r["workers"]["pods"] = [{"name": "w1", "stale": True}]
        r["gpu"].update(owner="job1", owner_ended=True, phase="model-ready")
        r["inference"]["router_ready"] = 0
        text = " | ".join(bg.problems(r))
        for needle in ("guard is held", "execution claim", "stale worker", "ended", "not qwen-ready", "Inference not ready"):
            self.assertIn(needle, text)

    def test_live_job_is_not_a_problem(self):
        r = self.healthy()
        r["database"].update(claims=[{"id": "s", "orphan": False}], inbox=1, running_jobs=2)
        r["gpu"]["owner"] = "job1"
        self.assertEqual(bg.problems(r), [])
        r["database"]["claims"] = []
        self.assertTrue(any("queued session inputs" in x for x in bg.problems(r)), "the same markers without a live owner are stuck")

    def test_probe_errors_surface_instead_of_hiding(self):
        r = self.healthy()
        r["gpu"] = {"error": "ControllerUnavailable: x"}
        self.assertIn("gpu could not be inspected", bg.problems(r)[0])


if __name__ == "__main__":
    unittest.main()
