import tempfile,unittest
from pathlib import Path
from store import Store
from worker import Worker
class Queue(unittest.TestCase):
 def test_cancel_queued_never_downloads(self):
  with tempfile.TemporaryDirectory() as root:
   store=Store(Path(root)/"catalog.sqlite");key=store.enqueue({"files":[]})
   store.cancel(key);self.assertEqual(store.jobs()[0]["state"],"CANCELLED")
   self.assertFalse(Worker(store,None).once())
 def test_removed_installation_can_be_queued_again(self):
  with tempfile.TemporaryDirectory() as root:
   store=Store(Path(root)/"catalog.sqlite");selection={"kind":"gguf","files":[]}
   key=store.enqueue(selection);store.transition(key,"REGISTERED_NOT_TESTED")
   self.assertEqual(store.enqueue(selection),key)
   self.assertEqual(store.jobs()[0]["state"],"QUEUED")
 def test_removal_is_durable(self):
  with tempfile.TemporaryDirectory() as root:
   store=Store(Path(root)/"catalog.sqlite")
   class Ops:
    def remove(self,*args,**kwargs):return {"files":"retained"}
   store.enqueue({"operation":"remove","id":"x","revision":"a"*40,"confirmation":"c"})
   self.assertTrue(Worker(store,Ops()).once())
   self.assertEqual(Store(Path(root)/"catalog.sqlite").jobs()[0]["state"],"REMOVED_FILES_RETAINED")

class ImageAdmission(unittest.TestCase):
 def test_native_busy_waits_without_duplicate_and_then_runs(self):
  from admission_errors import AdmissionBusy
  with tempfile.TemporaryDirectory() as root:
   store=Store(Path(root)/"catalog.sqlite");key=store.enqueue({"operation":"generate","id":"x","revision":"a"*40,"prompt":"A bench"})
   class Ops:
    calls=0
    def generate(self,*args,**kwargs):
     self.calls+=1
     if self.calls==1:raise AdmissionBusy("Native work active")
     return {"tested":True,"restoration":{"verified":True}}
   ops=Ops();worker=Worker(store,ops);self.assertFalse(worker.once());self.assertEqual(store.jobs()[0]["state"],"WAITING_NATIVE_IDLE");self.assertTrue(worker.once());self.assertEqual(store.jobs()[0]["state"],"GENERATION_VERIFIED");self.assertEqual(len(store.jobs()),1);store.close()
 def test_uncertain_execution_is_never_requeued(self):
  with tempfile.TemporaryDirectory() as root:
   store=Store(Path(root)/"catalog.sqlite");store.enqueue({"operation":"generate","id":"x","revision":"a"*40,"prompt":"A bench"})
   class Ops:
    def generate(self,*args,**kwargs):raise ValueError("Inference not confirmed idle; GPU remains fenced")
   worker=Worker(store,Ops());self.assertTrue(worker.once());self.assertEqual(store.jobs()[0]["state"],"FAILED");self.assertFalse(worker.once());store.close()
 def test_interrupted_generation_is_not_replayed(self):
  with tempfile.TemporaryDirectory() as root:
   store=Store(Path(root)/"catalog.sqlite");key=store.enqueue({"operation":"generate","id":"x","revision":"a"*40,"prompt":"A bench"});store.transition(key,"GENERATING")
   self.assertTrue(Worker(store,None).once());self.assertEqual(store.jobs()[0]["state"],"FAILED");store.close()
 def test_waiting_image_can_be_cancelled(self):
  with tempfile.TemporaryDirectory() as root:
   store=Store(Path(root)/"catalog.sqlite");key=store.enqueue({"operation":"generate","id":"x"});store.transition(key,"WAITING_NATIVE_IDLE");store.cancel(key);self.assertEqual(store.jobs()[0]["state"],"CANCELLED");self.assertFalse(Worker(store,None).once());store.close()

class SingleConsumer(unittest.TestCase):
 def test_overlapping_workers_cannot_consume_same_queue(self):
  import threading,time,tempfile
  from pathlib import Path
  with tempfile.TemporaryDirectory() as tmp:
   first=Worker(Store(Path(tmp)/'catalog.sqlite'),None);second=Worker(Store(Path(tmp)/'catalog.sqlite'),None)
   entered1=threading.Event();entered2=threading.Event();release=threading.Event()
   def once1():entered1.set();release.wait(3);first.stopping=True;return True
   def once2():entered2.set();second.stopping=True;return True
   first.once=once1;second.once=once2
   a=threading.Thread(target=first.run,daemon=True);b=threading.Thread(target=second.run,daemon=True)
   a.start();self.assertTrue(entered1.wait(1));b.start()
   try:self.assertFalse(entered2.wait(.15))
   finally:release.set();a.join(3);b.join(3);first.store.close();second.store.close()
   self.assertTrue(entered2.is_set());self.assertFalse(a.is_alive() or b.is_alive())
