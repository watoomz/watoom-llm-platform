import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from cutover import router_plan,activate
class Plan(unittest.TestCase):
 def fixture(self):
  return {"data":{"router.py":"old","client.py":"preserved"}},{"spec":{"template":{"spec":{"containers":[{"name":"router","env":[{"name":"KEEP","value":"kept"}],"volumeMounts":[]}],"volumes":[{"name":"existing","emptyDir":{}}]}}}}
 def test_scoped_plan_preserves_unrelated_state(self):
  cm,dep=self.fixture();old=copy.deepcopy(dep);new_cm,new_dep=router_plan(cm,dep,"new")
  self.assertEqual(dep,old);self.assertEqual(new_cm["data"]["client.py"],"preserved")
  self.assertEqual(new_dep["spec"]["template"]["spec"]["volumes"][0],old["spec"]["template"]["spec"]["volumes"][0])
  self.assertEqual(router_plan(new_cm,new_dep,"new"),(new_cm,new_dep))
 def test_foreign_volume_collision(self):
  cm,dep=self.fixture();dep["spec"]["template"]["spec"]["volumes"].append({"name":"managed-key","emptyDir":{}})
  with self.assertRaises(ValueError):router_plan(cm,dep,"new")
 def test_no_activation_without_exact_approval(self):
  with tempfile.TemporaryDirectory() as d:
   out=Path(d);(out/"cutover-plan.json").write_text(json.dumps({"commit":"a"*40}))
   with self.assertRaises(RuntimeError):activate(out,None,False)

class Transactions(unittest.TestCase):
 def fixture(self):
  return {"metadata":{"uid":"owned","resourceVersion":"1"},"data":{"router.py":"old"}}
 def test_intent_survives_failed_mutation(self):
  import cutover
  with tempfile.TemporaryDirectory() as d:
   out=Path(d);current=self.fixture()
   with patch("cutover.patch",side_effect=RuntimeError("API unavailable")):
    with self.assertRaises(RuntimeError):cutover.transactional_patch(out,"ns","cm","router",current,"/data",{"router.py":"new"})
   self.assertEqual(cutover.journal(out)["patches"][0]["after"],{"router.py":"new"})
   with patch("cutover.get",return_value=current),patch("cutover.patch") as mutation:
    self.assertEqual(cutover.restore_patches(out,apply=True),[]);mutation.assert_not_called()
 def test_changed_value_restores_without_late_receipts(self):
  import cutover
  with tempfile.TemporaryDirectory() as d:
   out=Path(d);current=self.fixture()
   with patch("cutover.patch"):
    cutover.transactional_patch(out,"ns","cm","router",current,"/data",{"router.py":"new"})
   changed=copy.deepcopy(current);changed["data"]={"router.py":"new"}
   with patch("cutover.get",return_value=changed),patch("cutover.patch") as mutation:
    cutover.restore_patches(out,apply=True)
    self.assertEqual(mutation.call_args.args[-1][0]["value"],current["data"])
 def test_independent_edit_or_uid_blocks_all_restores(self):
  import cutover
  with tempfile.TemporaryDirectory() as d:
   out=Path(d);current=self.fixture()
   with patch("cutover.patch"):
    for name in ("one","two"):cutover.transactional_patch(out,"ns","cm",name,current,"/data",{"router.py":"new"})
   changed=copy.deepcopy(current);changed["data"]={"router.py":"new"}
   foreign=copy.deepcopy(current);foreign["data"]={"router.py":"independent"}
   for invalid in (foreign,{**changed,"metadata":{"uid":"replacement"}}):
    with patch("cutover.get",side_effect=[changed,invalid]),patch("cutover.patch") as mutation:
     with self.assertRaises(RuntimeError):cutover.restore_patches(out,apply=True)
     mutation.assert_not_called()
 def test_atomic_private_receipt(self):
  from manage import write
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/"receipt.json";write(path,{"step":1});write(path,{"step":2})
   self.assertEqual(json.loads(path.read_text()),{"step":2})
   self.assertEqual(path.stat().st_mode&0o777,0o600)
   self.assertEqual(list(Path(d).iterdir()),[path])

class LargePatch(unittest.TestCase):
 def test_large_config_uses_private_file_not_command_argument(self):
  import cutover,os
  current={"metadata":{"uid":"u","resourceVersion":"1"}}
  captured=[]
  def command(args):
   captured.append(args)
   filename=args[args.index("--patch-file")+1]
   self.assertEqual(os.stat(filename).st_mode&0o777,0o600)
   self.assertGreater(len(Path(filename).read_bytes()),200000)
   self.assertIn("🦜",Path(filename).read_text())
   self.assertNotIn(chr(92)+"ud83e",Path(filename).read_text())
   return "{}"
  with patch("cutover.run",side_effect=command):
   cutover.patch("ns","cm","large",current,[{"op":"replace","path":"/data","value":{"large":"🦜"+"x"*250000}}])
  self.assertFalse(Path(captured[0][captured[0].index("--patch-file")+1]).exists())
  self.assertLess(max(map(len,captured[0])),1000)

class RestoredCode(unittest.TestCase):
 def test_restoration_loads_installed_runtime_in_fresh_interpreter(self):
  import cutover,os
  with patch("cutover.run") as execute,patch("cutover.rpc",return_value={"owner":None,"uncertain":False,"phase":"qwen-ready"}):
   cutover.restore_owner(object(),"operator-test",52)
  args=execute.call_args.args[0]
  self.assertEqual(args[1],"-c")
  self.assertIn("from g3h_service import Runtime,process_identity",args[2])
  self.assertIn("Live operator identity or ownership changed",args[2])
  self.assertIn("runtime.actuator.generation=generation",args[2])
  self.assertEqual(args[-1],str(os.getpid()))

class ResumeIntents(unittest.TestCase):
 def test_identical_resume_intent_restores_once(self):
  import cutover
  with tempfile.TemporaryDirectory() as d:
   out=Path(d);current={"metadata":{"uid":"u","resourceVersion":"1"},"data":{"old":"value"}}
   with patch("cutover.patch"):
    for _ in range(2):cutover.transactional_patch(out,"ns","cm","same",current,"/data",{"new":"value"})
   self.assertEqual(len(cutover.journal(out)["patches"]),1)
   # Also reconcile an older duplicate journal produced before deduplication.
   transaction=cutover.journal(out);transaction["patches"]*=2;cutover.write(out/"transaction.json",transaction)
   current["data"]={"new":"value"}
   with patch("cutover.get",return_value=current),patch("cutover.patch") as mutation:
    cutover.restore_patches(out,apply=True);self.assertEqual(mutation.call_count,1)

class ReleaseRollback(unittest.TestCase):
 def test_prepared_release_protects_uid_and_spec(self):
  import cutover
  obj={"metadata":{"uid":"u","labels":{"watoom.io/owner":"model-manager"},"annotations":{"watoom.io/model-manager-release":"new"}},"spec":{"port":8787}}
  with tempfile.TemporaryDirectory() as d:
   out=Path(d);(out/"rollback-release.json").write_text(json.dumps({"resources":{k:cutover.resource_identity(obj) for k in ("deployment","service","ingressroute")}}))
   with patch("cutover.run",return_value=json.dumps(obj)):self.assertEqual(len(cutover.owned_resources(out)),3)
   for changed in ({**obj,"spec":{"port":1}},{**obj,"metadata":{**obj["metadata"],"uid":"replacement"}}):
    with patch("cutover.run",return_value=json.dumps(changed)):
     with self.assertRaises(RuntimeError):cutover.owned_resources(out)
 def test_original_snapshot_is_preserved(self):
  import cutover
  with tempfile.TemporaryDirectory() as d:
   out=Path(d);original={"commit":"old","candidate_files":{},"controller_files":{}}
   (out/"cutover-plan.json").write_text(json.dumps(original))
   (out/"rollback-release.json").write_text(json.dumps({"commit":"new","candidate_files":{"file":"newhash"},"controller_files":{"file":"oldhash"}}))
   self.assertEqual(cutover.rollback_plan(out)["commit"],"new")
   self.assertEqual(json.loads((out/"cutover-plan.json").read_text()),original)

class TrackedManifests(unittest.TestCase):
 def test_router_manifests_carry_authored_router(self):
  from render_router_manifest import MANIFESTS,ROUTER,render
  for path in MANIFESTS:
   self.assertEqual(path.read_text(),render(path.read_text(),ROUTER.read_text()),path.name+" is stale: run render_router_manifest.py")
