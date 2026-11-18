import unittest,copy
from unittest.mock import patch
from toolkit_service_fence import ServiceFence
from release_guard import UnsafeRelease
class FenceTests(unittest.TestCase):
 def setUp(self):
  self.service={"metadata":{"uid":"service","resourceVersion":"1"},"spec":{"type":"ClusterIP","selector":{"app":"toolkit"}}}
  self.pod={"metadata":{"uid":"pod"},"status":{"phase":"Running","containerStatuses":[{"name":"toolkit","containerID":"container"}]}}
  self.states=[];self.guards=0;self.busy=2
 def get(self,kind,name=None,labels=None):
  if kind=="service":return copy.deepcopy(self.service)
  if kind=="pods":return {"items":[self.pod] if labels=={"app":"toolkit"} else []}
  if kind=="endpointslices":return {"items":[{"endpoints":None}]}
  return {"items":[]}
 def patch(self,name,ops):
  for op in ops:
   parts=op["path"].strip("/").split("/");target=self.service
   for part in parts[:-1]:target=target[part]
   if op["op"]=="test" and target[parts[-1]]!=op["value"]:raise UnsafeRelease("CAS conflict")
   if op["op"]=="replace":target[parts[-1]]=op["value"]
 def guard(self):self.guards+=1
 def probe(self,pod):
  self.busy-=1
  return {"container_id":"container","pod_uid":"pod","server_pid":1,"server_command":["python3","-B","/opt/watoom/agent.py"],"threads":2 if self.busy>=0 else 1,"established":1 if self.busy>=0 else 0}
 def fence(self):return ServiceFence(self.get,self.patch,self.states.append,self.guard,self.probe)
 def test_waits_for_handlers_and_restores_exact_selector(self):
  fence=self.fence()
  with patch("toolkit_service_fence.time.sleep"):fence.acquire()
  self.assertEqual(self.states[-1]["status"],"HELD");self.assertGreater(self.guards,3)
  fence.release();self.assertEqual(self.service["spec"]["selector"],{"app":"toolkit"})
 def test_failed_job_does_not_hide_a_still_running_worker_pod(self):
  fence=self.fence();base=fence.get
  def get(kind,name=None,labels=None):
   if kind=="jobs":return {"items":[{"status":{"failed":1}}]}
   if kind=="pods" and labels=={"app":"watoom-toolkit-worker"}:return {"items":[{"status":{"phase":"Running"}}]}
   return base(kind,name,labels)
  fence.get=get;self.busy=-1
  with patch("toolkit_service_fence.time.sleep"),patch("toolkit_service_fence.time.monotonic",side_effect=[0,0,1]):
   with self.assertRaises(UnsafeRelease):fence.acquire(seconds=.1)
  self.assertEqual(self.states[-1]["status"],"ACQUIRING")
  self.assertNotEqual(self.service["spec"]["selector"],{"app":"toolkit"})
 def test_refuses_changed_service_on_release(self):
  fence=self.fence()
  with patch("toolkit_service_fence.time.sleep"):fence.acquire()
  self.service["metadata"]["uid"]="replacement"
  with self.assertRaises(UnsafeRelease):fence.release()
 def test_refuses_restarted_or_unknown_server(self):
  fence=self.fence();fence.probe=lambda p:{"pod_uid":"different"}
  with self.assertRaises(UnsafeRelease):fence.acquire()
  self.assertNotEqual(self.service["spec"]["selector"],{"app":"toolkit"})
if __name__=="__main__":unittest.main()
