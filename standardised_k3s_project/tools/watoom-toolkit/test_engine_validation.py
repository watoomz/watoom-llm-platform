import unittest,json,three_d,kube_worker
class EngineValidationBoundary(unittest.TestCase):
 def test_explicit_opt_in_only(self):
  good={'task':'3d-inspect','path':'asset.blend','parameters':{'engine_validation':1},'timeout':420}
  three_d.validate(good)
  for patch in [{'task':'3d-repair'},{'parameters':{'engine_validation':True}},{'parameters':{'engine_validation':0}},{'parameters':{'engine_validation':1,'script':'untrusted'}}]:
   with self.assertRaises(ValueError):three_d.validate({**good,**patch})
 def test_isolation_and_cpu_budget(self):
  request={'task':'3d-inspect','parameters':{'engine_validation':1},'input':'/input/asset.blend','expected_engine_sha256':'a'*64}
  argv=['python3','-B','/opt/watoom/engine_validate_worker.py',json.dumps(request)]
  args=('b'*16,argv,420,'/data/owned','image@sha256:'+'a'*64)
  spec=kube_worker.job_spec(*args,input_file='/data/input.blend',task='3d-inspect',host_engine='/data/pinned-engine')['spec']['template']['spec']
  self.assertFalse(spec['automountServiceAccountToken'])
  container=spec['containers'][0]
  self.assertEqual(container['resources']['limits']['memory'],'3Gi')
  self.assertNotIn('nvidia.com/gpu',container['resources']['limits'])
  self.assertTrue(next(x for x in container['volumeMounts'] if x['name']=='unreal-engine')['readOnly'])
  self.assertEqual(spec['securityContext']['runAsUser'],1009)
  self.assertTrue(kube_worker.task_native(argv,request))
  with self.assertRaises(ValueError):kube_worker.job_spec(*args,input_file='/data/input.blend',task='3d-inspect')
  with self.assertRaises(ValueError):kube_worker.job_spec(args[0],argv,421,*args[3:],task='3d-inspect',host_engine='/data/pinned-engine')
class MetaHumanCatalogBoundary(unittest.TestCase):
 def test_source_package_is_searchable_without_import_claim(self):
  import tempfile,pathlib,asset_catalog
  with tempfile.TemporaryDirectory() as tmp:
   root=pathlib.Path(tmp);pack=root/'fab'/'ultimate-metahuman-body';pack.mkdir(parents=True)
   package=pack/'mhc_base.mhpkg';package.write_bytes(b'source-package-fixture')
   catalog=asset_catalog.Catalog(root,root/'catalog-state.json')
   self.assertIn('.mhpkg',asset_catalog.FORMATS)
   metadata=catalog.metadata('fab/ultimate-metahuman-body/mhc_base.mhpkg',package)
   self.assertIn('characters',metadata['categories'])
   self.assertEqual(metadata['engine_compatibility']['unreal'],'UNVERIFIED')
   self.assertEqual(metadata['engine_compatibility']['godot'],'SOURCE_PACKAGE_NOT_DIRECTLY_IMPORTABLE')
if __name__=='__main__':unittest.main()
