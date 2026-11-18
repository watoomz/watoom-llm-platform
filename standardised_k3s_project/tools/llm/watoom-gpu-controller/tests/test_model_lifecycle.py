import json,tempfile,unittest
from pathlib import Path
from g3h_service import Runtime
from model_lifecycle import spec_identity,read_ledger
from controller import State,Unsafe,Conflict
from durable_store import DurableStore
NAME="llama-cpp-mm-"+"a"*16
class API:
 def __init__(self):
  self.allowed=frozenset(("qwen","mesh"));self.started=False;self.uid="owned"
 def get_service(self,name):
  return {"metadata":{"uid":"service-owned","labels":{"watoom.io/model-manager":"owned"}},"spec":{"type":"ClusterIP","clusterIP":"10.243.1.2","selector":{"app":name},"ports":[{"port":8080,"targetPort":8080}]}}
 def get(self,name):
  return {"metadata":{"uid":self.uid if name==NAME else name,"generation":2 if self.started else 1,"labels":{"watoom.io/model-manager":"owned"}},"spec":{"replicas":1 if self.started and name==NAME else 0},"status":{}}
class LifecycleTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.api=API()
  self.config={"state_root":str(self.root),"primary":"qwen","mesh":"mesh","namespace":"llama-cpp","models":["qwen","mesh"],"urls":{},"aliases":{},"deployment_identity":{},"stop_timeout":1,"startup_timeout":1}
  self.runtime=Runtime(self.config,api=self.api,probe=lambda *a:True)
  DurableStore(self.root/"state.json").save(State())
  self.record={"alias":"mm-"+"a"*16,"url":"http://"+NAME+".llama-cpp.svc.cluster.local:8080","backend":"gguf","identity":spec_identity(self.api.get(NAME))}
 def tearDown(self):self.tmp.cleanup()
 def enroll(self,**kw):return self.runtime.handle({"action":"enroll-model","deployment":NAME,"record":self.record},private=kw.get("private",True),pid=123,uid=kw.get("uid",0))
 def test_enroll_restart_retire(self):
  self.assertEqual(self.enroll()["status"],"enrolled")
  self.assertIn(NAME,self.runtime.actuator.allowed)
  restarted=Runtime(self.config,api=API(),probe=lambda *a:True)
  self.assertIn(NAME,restarted.actuator.allowed)
  result=restarted.handle({"action":"retire-model","deployment":NAME,"identity":self.record["identity"]},private=True,pid=123,uid=0)
  self.assertEqual(result["status"],"retired");self.assertNotIn(NAME,read_ledger(self.root))
 def test_owned_service_cluster_ip_enrollment_and_wrong_target(self):
  self.record.update(url="http://10.243.1.2:8080",service_identity=spec_identity(self.api.get_service(NAME)))
  self.assertEqual(self.enroll()["status"],"enrolled")
 def test_foreign_service_ip_rejected(self):
  self.record.update(url="http://10.243.1.3:8080",service_identity=spec_identity(self.api.get_service(NAME)))
  with self.assertRaises(Unsafe):self.enroll()
 def test_live_dictionary_inventory_is_preserved(self):
  config={**self.config,"models":{"qwen":"qwen-alias","mesh":"mesh-alias"}}
  self.runtime=Runtime(config,api=self.api,probe=lambda *a:True)
  self.enroll()
  self.assertEqual(self.runtime.c["models"]["qwen"],"qwen-alias")
  self.assertEqual(self.runtime.c["models"][NAME],self.record["alias"])
 def test_retire_proven_absent_owned_deployment(self):
  from kubernetes_api import APIError
  self.enroll()
  self.runtime.actuator._get=lambda name:(_ for _ in ()).throw(APIError("missing",404))
  result=self.runtime.handle({"action":"retire-model","deployment":NAME,"identity":self.record["identity"]},private=True,pid=123,uid=0)
  self.assertEqual(result["status"],"retired")
 def test_stale_selection_after_primary_recovery_does_not_block_retirement(self):
  self.enroll()
  (self.root/"selected-model.json").write_text(json.dumps({"deployment":NAME}))
  result=self.runtime.handle({"action":"retire-model","deployment":NAME,"identity":self.record["identity"]},private=True,pid=123,uid=0)
  self.assertEqual(result["status"],"retired")
 def test_wrong_uid_and_public_rejected(self):
  for kw in ({"uid":1009},{"private":False}):
   with self.assertRaises(Unsafe):self.enroll(**kw)
 def test_started_rejected(self):
  self.api.started=True
  with self.assertRaises(Unsafe):self.enroll()
 def test_identity_rejected(self):
  self.api.uid="replaced"
  with self.assertRaises(Unsafe):self.enroll()
 def test_owner_rejected(self):
  DurableStore(self.root/"state.json").save(State("mesh-active","busy",4))
  with self.assertRaises(Conflict):self.enroll()
 def test_duplicate(self):
  self.enroll()
  with self.assertRaises(Conflict):self.enroll()
if __name__=="__main__":unittest.main()
