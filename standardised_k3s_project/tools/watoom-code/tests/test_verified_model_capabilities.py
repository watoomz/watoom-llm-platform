import importlib.util,pathlib,copy,unittest
ROOT=pathlib.Path(__file__).resolve().parents[3]
SPEC=importlib.util.spec_from_file_location('verified_caps',ROOT/'ansible/roles/watoom-code/files/enable-verified-model-capabilities.py');MODULE=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MODULE)
class Capabilities(unittest.TestCase):
 def test_only_qualified_metadata_changes(self):
  doc={'model':'watoom/tiel','providers':{'watoom':{'settings':{'baseURL':'unchanged'},'models':{'tiel':{'capabilities':{'tools':False,'input':['text'],'output':['text']},'limit':{'context':100000,'output':4096}},'other':{'capabilities':{'tools':False,'input':['text'],'output':['text']}}}}}}
  before=copy.deepcopy(doc);result=MODULE.update(doc,{'tiel':{'tools':True,'input':['text'],'output':['text']}})
  self.assertTrue(result['providers']['watoom']['models']['tiel']['capabilities']['tools'])
  self.assertEqual(result['providers']['watoom']['models']['other'],before['providers']['watoom']['models']['other'])
  self.assertEqual(result['providers']['watoom']['models']['tiel']['limit'],before['providers']['watoom']['models']['tiel']['limit'])
  self.assertEqual(result['model'],before['model']);self.assertEqual(result['providers']['watoom']['settings'],before['providers']['watoom']['settings'])
 def test_absent_models_are_not_invented(self):
  self.assertEqual(MODULE.update({'providers':{'watoom':{'models':{}}}},{'missing':{'tools':True,'input':['text'],'output':['text']}}),{'providers':{'watoom':{'models':{}}}})
 def test_qualified_vision_preserves_tools_and_budget(self):
  doc={'providers':{'watoom':{'models':{'tiel':{'limit':{'context':100000,'output':4096}}}}}}
  caps={'tools':True,'input':['text','image'],'output':['text']}
  result=MODULE.update(doc,{'tiel':caps})['providers']['watoom']['models']['tiel']
  self.assertEqual(result['capabilities'],caps)
  self.assertEqual(result['limit'],{'context':100000,'output':4096})
 def test_unqualified_modalities_rejected(self):
  with self.assertRaises(ValueError):MODULE.update({'providers':{'watoom':{'models':{'tiel':{}}}}},{'tiel':{'tools':True,'input':['text','audio'],'output':['text']}})
if __name__=='__main__':unittest.main()
