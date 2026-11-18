import importlib.util,pathlib,unittest
path=pathlib.Path(__file__).resolve().parents[3]/"ansible/roles/watoom-code/files/enable-model-context.py"
spec=importlib.util.spec_from_file_location("context_migration",path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class Context(unittest.TestCase):
 def test_standard_budget_and_lower_published_cap(self):
  data={"providers":{"watoom":{"models":{"swift":{"capabilities":{"tools":True}}}}}}
  out=module.update(data,{"data":[{"id":"swift"},{"id":"small"},{"id":"limited","context_limit":8192},{"id":"llama-mesh"}]})
  models=out["providers"]["watoom"]["models"]
  self.assertEqual(models["small"]["limit"],{"context":100000,"output":16384})
  self.assertEqual(models["limited"]["limit"]["context"],8192)
  self.assertTrue(models["swift"]["capabilities"]["tools"]);self.assertFalse(models["small"]["capabilities"]["tools"])
  self.assertNotIn("llama-mesh",models)
 def test_output_budget_is_explicit_bounded_and_half_the_context_at_most(self):
  data={"providers":{"watoom":{"models":{}}}}
  inv={"data":[{"id":"a"},{"id":"tiny","context_limit":8192}]}
  models=module.update(data,inv,100000,8192)["providers"]["watoom"]["models"]
  self.assertEqual(models["a"]["limit"]["output"],8192);self.assertEqual(models["tiny"]["limit"]["output"],4096)
  for bad in (64,32769):
   with self.assertRaises(ValueError):module.update({},{"data":[]},100000,bad)
 def test_invalid_budget(self):
  with self.assertRaises(ValueError):module.update({},{"data":[]},131072)
