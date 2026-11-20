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
  models=module.update(data,inv,131072,8192)["providers"]["watoom"]["models"]
  self.assertEqual(models["a"]["limit"]["output"],8192);self.assertEqual(models["tiny"]["limit"]["output"],4096)
  for bad in (64,32769):
   with self.assertRaises(ValueError):module.update({},{"data":[]},131072,bad)
 def test_published_name_replaces_only_a_stub(self):
  data={"providers":{"watoom":{"models":{"mm-a":{"modelID":"mm-a","name":"mm-a"},"mm-b":{"modelID":"mm-b","name":"my label"}}}}}
  inv={"data":[{"id":"mm-a","name":"o/Repo (M-Q8_0.gguf)"},{"id":"mm-b","name":"o/Other"},{"id":"mm-c","name":"o/New"}]}
  models=module.update(data,inv)["providers"]["watoom"]["models"]
  self.assertEqual([models[k]["name"] for k in ("mm-a","mm-b","mm-c")],["o/Repo (M-Q8_0.gguf)","my label","o/New"])
 def test_image_input_follows_the_served_projector(self):
  data={"providers":{"watoom":{"models":{"was-vision":{"modelID":"was-vision","name":"x","capabilities":{"tools":True,"input":["text","image"],"output":["text"]}},
                                          "alias":{"modelID":"alias","name":"y","capabilities":{"tools":True,"input":["text","image"],"output":["text"]}}}}}}
  inv={"data":[{"id":"new-vision","vision":True},{"id":"was-vision","vision":False},{"id":"alias","vision":None}]}
  models=module.update(data,inv)["providers"]["watoom"]["models"]
  self.assertEqual({k:models[k]["capabilities"]["input"] for k in ("new-vision","was-vision","alias")},{"new-vision":["text","image"],"was-vision":["text"],"alias":["text","image"]})
  self.assertTrue(models["was-vision"]["capabilities"]["tools"])
 def test_invalid_budget(self):
  with self.assertRaises(ValueError):module.update({},{"data":[]},2000000)
 def test_budget_scales_with_the_served_context(self):
  data={"providers":{"watoom":{"models":{}}}}
  inv={"data":[{"id":"small","application_context":262144},{"id":"big","application_context":131072},{"id":"capped","application_context":262144,"context_limit":131072},{"id":"unknown"}]}
  models=module.update(data,inv)["providers"]["watoom"]["models"]
  self.assertEqual({k:models[k]["limit"]["context"] for k in ("small","big","capped","unknown")},{"small":262144,"big":131072,"capped":131072,"unknown":100000})
