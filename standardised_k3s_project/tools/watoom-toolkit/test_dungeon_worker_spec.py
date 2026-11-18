import json,unittest,pathlib,tempfile,os
from unittest.mock import patch
import kube_worker
class NativeWorkerBoundary(unittest.TestCase):
 def spec(self,argv=None,timeout=840,**kwargs):
  return kube_worker.job_spec("a"*16,argv or ["python3","-B","/opt/watoom/dungeon_worker.py",json.dumps({"task":"3d-creative","dungeon":{"style":"dungeon-builder"},"output":"/old"})],timeout,
   "/data/ai/state/jobs/job/worker","local/image@sha256:"+"b"*64,task="3d-creative",host_assets="/data/ai/assets",**kwargs)
 def test_only_fixed_native_worker_gets_extended_deadline_and_ro_mounts(self):
  spec=self.spec(host_engine="/data/ai/builds/accepted/source",host_catalog="/data/ai/state/asset-catalog/catalog.json")
  pod=spec["spec"]["template"]["spec"];container=pod["containers"][0]
  self.assertEqual(spec["spec"]["activeDeadlineSeconds"],840)
  self.assertFalse(pod["automountServiceAccountToken"])
  self.assertEqual(pod["securityContext"]["runAsUser"],1009)
  self.assertEqual(next(v for v in pod["volumes"] if v["name"]=="catalog")["hostPath"]["type"],"File")
  self.assertEqual(container["resources"]["limits"]["memory"],"6Gi")
  self.assertEqual(container["resources"]["requests"]["memory"],"6Gi")
  self.assertEqual(container["resources"]["limits"]["cpu"],"2")
  self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
  for name in ("unreal-engine","catalog","asset-library"):
   self.assertTrue(next(v for v in container["volumeMounts"] if v["name"]==name)["readOnly"])
  self.assertEqual(json.loads(container["command"][-1])["output"],"/job/artifacts")
 def test_normal_or_lookalike_command_cannot_expand_bounds(self):
  for command in (["python3","-B","/opt/watoom/creative.py","{}"],["python3","-B","/tmp/dungeon_worker.py","{}"]):
   with self.assertRaisesRegex(ValueError,"bounds"):self.spec(command)
 def test_insufficient_host_headroom_never_creates_worker(self):
  with tempfile.TemporaryDirectory() as directory:
   state=pathlib.Path(directory);root=state/"job"
   argv=["python3","-B","/opt/watoom/dungeon_worker.py","{}"]
   environment={"WATOOM_WORKER_IMAGE":"local/image@sha256:"+"b"*64,"WATOOM_HOST_STATE":"/host/state","WATOOM_HOST_WORKSPACE":"/host/workspace","WATOOM_WORKER_NAMESPACE":"test"}
   with patch.dict(os.environ,environment),patch.object(pathlib.Path,"read_text",return_value="MemAvailable: 1000000 kB\\n"),patch.object(kube_worker,"api") as api:
    with self.assertRaisesRegex(ValueError,"host reserve"):kube_worker.execute(argv,840,root,state,state,{"task":"3d-creative","dungeon":{}})
    api.assert_not_called()
 def test_delete_acceptance_does_not_prove_worker_stopped(self):
  with patch.object(kube_worker,"api",side_effect=[{"metadata":{"deletionTimestamp":"now"}},{"items":[{"status":{"phase":"Running"}}]}]):
   self.assertFalse(kube_worker.worker_stopped("a"*16))
  with patch.object(kube_worker,"api",side_effect=[{},{"items":[]}]):
   self.assertTrue(kube_worker.worker_stopped("a"*16))
 def test_missing_or_unavailable_worker_evidence_never_passes(self):
  with patch.object(kube_worker,"api",side_effect=RuntimeError("API unavailable")):
   with self.assertRaises(RuntimeError):kube_worker.worker_stopped("a"*16)
 def test_accepted_editor_pin_is_required_and_checked(self):
  import creative
  with patch.dict(os.environ,{"WATOOM_UNREAL_EDITOR_SHA256":""}),patch.object(creative.asset_catalog,"checksum") as checksum:
   with self.assertRaisesRegex(ValueError,"configured"):creative.native_engine_sha()
   checksum.assert_not_called()
  with patch.dict(os.environ,{"WATOOM_UNREAL_EDITOR_SHA256":"a"*64}),patch.object(creative.asset_catalog,"checksum",return_value="b"*64):
   with self.assertRaisesRegex(ValueError,"does not match"):creative.native_engine_sha()
  with patch.dict(os.environ,{"WATOOM_UNREAL_EDITOR_SHA256":"a"*64}),patch.object(creative.asset_catalog,"checksum",return_value="a"*64):
   self.assertEqual(creative.native_engine_sha(),"a"*64)
 def test_native_requires_trusted_engine_and_catalog(self):
  for config in ({},{"host_engine":"/engine"},{"host_engine":"/engine","host_catalog":"relative"}):
   with self.assertRaises(ValueError):self.spec(**config)
  with self.assertRaises(ValueError):self.spec(timeout=841,host_engine="/engine",host_catalog="/catalog")
if __name__=="__main__":unittest.main()
