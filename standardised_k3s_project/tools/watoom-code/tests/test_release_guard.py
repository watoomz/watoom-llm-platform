import unittest,sys,pathlib,tempfile,sqlite3,json
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import release_guard as g
class Fake:
    def __init__(self):self.held=False;self.leases=0;self.saved=False;self.applied=False;self.healthy=True;self.running=False
    def get(self,path):
        if path.endswith("/active"):return {"data":{"ses_race":{"type":"running"}} if self.running else {}}
        if path.endswith("/info"):
            if not self.healthy:raise RuntimeError("app unhealthy despite Kubernetes ready")
            return {"version":"fixture"}
        return {"data":{"version":1,"supported":True,"held":self.held,"leases":self.leases}}
    def post(self,path,body):
        if body["action"]=="acquire":
            if self.leases:raise g.UnsafeRelease("work won race")
            assert self.saved
            self.held=True
        else:self.held=False
        return self.get(path)
    def save(self,owner):self.saved=True
class Tests(unittest.TestCase):
    def test_atomic_gate_rejects_race(self):
        f=Fake()
        def race():f.leases=1
        with self.assertRaises(g.UnsafeRelease):g.acquire(f.get,f.post,f.save,race)
        self.assertFalse(f.held)
        self.assertFalse(f.applied)
    def test_failed_candidate_rolls_back_under_same_fence(self):
        f=Fake();owner=g.acquire(f.get,f.post,f.save,lambda:None)
        self.assertTrue(f.held)
        f.healthy=False
        with self.assertRaises(RuntimeError):g.runtime(f.get,"new","new")
        self.assertTrue(f.held)
        f.healthy=True
        g.runtime(f.get,"old","old")
        g.release(f.get,f.post,owner)
        self.assertFalse(f.held)
    def test_failed_rollback_keeps_fence(self):
        f=Fake();g.acquire(f.get,f.post,f.save,lambda:None);f.healthy=False
        with self.assertRaises(RuntimeError):g.runtime(f.get,"old","old")
        self.assertTrue(f.held)
    def test_unsupported_baseline_fails_closed(self):
        with self.assertRaises(g.UnsafeRelease):g.validate({"data":{"version":0}},False)
    def test_rollout_and_wrong_digest_are_insufficient(self):
        f=Fake()
        with self.assertRaises(g.UnsafeRelease):g.runtime(f.get,"old","wrong")

class DurableTests(unittest.TestCase):
    def test_claims_queues_and_gpu_ownership_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            path=pathlib.Path(root)/"fixture.sqlite"
            with sqlite3.connect(path) as db:
                db.executescript("CREATE TABLE session_pending(id);CREATE TABLE session_inbox(id);CREATE TABLE session_v2(time_suspended);CREATE TABLE kv(key,value);CREATE TABLE _watoom_specialist_job(phase,specialist_body,generation);")
                db.execute("INSERT INTO _watoom_specialist_job VALUES(?,?,?)",("uncertain",json.dumps({"execution":"cpu"}),None))
            self.assertTrue(all(x==0 for x in g.durable_clearance(path).values()))
            with sqlite3.connect(path) as db:db.execute("INSERT INTO session_inbox VALUES('fixture')")
            with self.assertRaises(g.UnsafeRelease):g.durable_clearance(path)
            with sqlite3.connect(path) as db:
                db.execute("DELETE FROM session_inbox")
                db.execute("INSERT INTO session_v2 VALUES(1)")
            with self.assertRaises(g.UnsafeRelease):g.durable_clearance(path)
            with sqlite3.connect(path) as db:
                db.execute("DELETE FROM session_v2")
                db.execute("UPDATE _watoom_specialist_job SET generation=1")
            with self.assertRaises(g.UnsafeRelease):g.durable_clearance(path)
    def test_v225_schema_without_session_pending_checks_inbox_and_jobs(self):
        with tempfile.TemporaryDirectory() as root:
            path=pathlib.Path(root)/"fixture.sqlite"
            with sqlite3.connect(path) as db:
                db.executescript("CREATE TABLE session_inbox(id);CREATE TABLE job(id,status);CREATE TABLE session_v2(time_suspended);CREATE TABLE kv(key,value);CREATE TABLE _watoom_specialist_job(phase,specialist_body,generation);")
                db.execute("INSERT INTO job VALUES('done','completed')")
            checks=g.durable_clearance(path)
            self.assertNotIn("session_pending",checks);self.assertEqual(checks["running_jobs"],0)
            with sqlite3.connect(path) as db:db.execute("INSERT INTO job VALUES('live','running')")
            with self.assertRaises(g.UnsafeRelease):g.durable_clearance(path)
            with sqlite3.connect(path) as db:
                db.execute("DELETE FROM job")
                db.execute("INSERT INTO session_inbox VALUES('fixture')")
            with self.assertRaises(g.UnsafeRelease):g.durable_clearance(path)
if __name__=="__main__":unittest.main()

