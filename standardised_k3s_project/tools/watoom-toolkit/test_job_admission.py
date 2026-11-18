import unittest,tempfile,pathlib,subprocess,sys,threading,json
import job_admission as admission
class AdmissionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);self.owner="a"*64
 def tearDown(self):self.tmp.cleanup()
 def test_running_job_prevents_maintenance(self):
  with admission.start(self.root):
   with self.assertRaises(admission.Busy):admission.change(self.root,"acquire",self.owner)
   self.assertTrue(admission.status(self.root)["active"])
 def test_guard_survives_process_restart(self):
  admission.change(self.root,"acquire",self.owner)
  result=subprocess.run([sys.executable,"-c","import job_admission,sys;job_admission.start(sys.argv[1])",str(self.root)],capture_output=True,text=True,cwd=pathlib.Path(__file__).parent)
  self.assertNotEqual(result.returncode,0);self.assertIn("Held",result.stderr)
  admission.change(self.root,"release",self.owner)
  with admission.start(self.root):pass
 def test_foreign_owner_cannot_release(self):
  admission.change(self.root,"acquire",self.owner)
  with self.assertRaises(admission.Held):admission.change(self.root,"release","b"*64)
  self.assertTrue(admission.status(self.root)["held"])
 def test_job_guard_race_has_one_winner(self):
  for i in range(12):
   barrier=threading.Barrier(2);out=[];held=[]
   def job():
    barrier.wait()
    try:
     lease=admission.start(self.root);held.append(lease);out.append("job")
    except (admission.Busy,admission.Held):out.append("job-refused")
   def guard():
    barrier.wait()
    try:admission.change(self.root,"acquire",self.owner);out.append("guard")
    except admission.Busy:out.append("guard-refused")
   a=threading.Thread(target=job);b=threading.Thread(target=guard);a.start();b.start();a.join();b.join()
   self.assertFalse("job" in out and "guard" in out,out)
   for lease in held:lease.close()
   if admission.status(self.root)["held"]:admission.change(self.root,"release",self.owner)
 def test_corrupt_state_fails_closed(self):
  (self.root/"job-maintenance.json").write_text('{"version":1,"held":"no"}')
  with self.assertRaises(RuntimeError):admission.start(self.root)
 def test_controller_crash_retains_admission_until_worker_stop_verified(self):
  code="import job_admission,sys,os; lease=job_admission.start(sys.argv[1],'c'*16,'kube'); os._exit(0)"
  result=subprocess.run([sys.executable,"-c",code,str(self.root)],cwd=pathlib.Path(__file__).parent)
  self.assertEqual(result.returncode,0)
  self.assertTrue(admission.status(self.root)["active"])
  with self.assertRaises(admission.Busy):admission.start(self.root)
  with self.assertRaises(admission.Busy):admission.change(self.root,"acquire",self.owner)
  self.assertFalse(admission.reconcile(self.root,lambda marker:False))
  self.assertTrue(admission.reconcile(self.root,lambda marker:marker["job_id"]=="c"*16))
  self.assertFalse(admission.status(self.root)["active"])
  recovery=json.loads((self.root/"jobs"/("c"*16)/"admission-recovery.json").read_text())
  self.assertEqual(recovery["status"],"OWNER_LOST_WORKER_STOPPED")
  with admission.start(self.root):pass
 def test_pending_worker_cleanup_stays_fenced(self):
  lease=admission.start(self.root,"d"*16,"kube");lease.close(clear=False)
  with self.assertRaises(admission.Busy):admission.change(self.root,"acquire",self.owner)
  self.assertFalse(admission.reconcile(self.root,lambda marker:False))
  self.assertTrue(admission.reconcile(self.root,lambda marker:True))
 def test_live_lease_cannot_be_reconciled(self):
  with admission.start(self.root):
   self.assertFalse(admission.reconcile(self.root,lambda marker:True))
 def test_owner_is_not_exposed(self):
  admission.change(self.root,"acquire",self.owner)
  self.assertNotIn(self.owner,json.dumps(admission.status(self.root)))
  self.assertNotIn(self.owner,(self.root/"job-maintenance.json").read_text())
if __name__=="__main__":unittest.main()
