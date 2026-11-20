import json,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[3]
ROLE=ROOT/"ansible/roles/watoom-code"
SCRIPT=ROLE/"files/enable-model-display-names.py"
class ModelDisplayNames(unittest.TestCase):
 def base(self):
  return {"providers":{"watoom":{"models":{
   "tiel-coder-35b-a3b-mtp":{"modelID":"tiel-coder-35b-a3b-mtp","name":"old-name","limit":{"context":100000,"output":16384}},
   "other":{"modelID":"other","name":"keep me","limit":{"context":8192}},
  }}},"keep":"untouched"}
 def test_renames_known_models_and_adds_fable_cold_fusion(self):
  with tempfile.TemporaryDirectory() as directory:
   path=pathlib.Path(directory)/"opencode.json";path.write_text(json.dumps(self.base()))
   first=subprocess.run(["python3",str(SCRIPT),str(path),"16384"],capture_output=True,text=True)
   self.assertEqual(first.returncode,0,first.stderr);self.assertEqual(first.stdout.strip(),"CHANGED")
   value=json.loads(path.read_text());models=value["providers"]["watoom"]["models"]
   self.assertEqual(models["tiel-coder-35b-a3b-mtp"]["name"],"peculiar-ragdoll/Cyber-Tiel-Coder-35B-A3B-GGUF-MTP (IQ4_XS)")
   self.assertEqual(models["other"]["name"],"keep me")
   self.assertEqual(value["keep"],"untouched")
   self.assertIn("fable-cold-fusion-27b-mtp",models)
   self.assertEqual(models["fable-cold-fusion-27b-mtp"]["limit"],{"context":100000,"output":16384})
   self.assertEqual(models["fable-cold-fusion-27b-mtp"]["capabilities"]["input"],["text"])
 def test_is_idempotent(self):
  with tempfile.TemporaryDirectory() as directory:
   path=pathlib.Path(directory)/"opencode.json";path.write_text(json.dumps(self.base()))
   subprocess.run(["python3",str(SCRIPT),str(path),"16384"],capture_output=True,text=True)
   before=path.read_bytes()
   second=subprocess.run(["python3",str(SCRIPT),str(path),"16384"],capture_output=True,text=True)
   self.assertEqual(second.stdout.strip(),"UNCHANGED");self.assertEqual(path.read_bytes(),before)
 def test_does_not_overwrite_an_already_present_fable_cold_fusion_entry(self):
  with tempfile.TemporaryDirectory() as directory:
   path=pathlib.Path(directory)/"opencode.json";data=self.base()
   data["providers"]["watoom"]["models"]["fable-cold-fusion-27b-mtp"]={"modelID":"fable-cold-fusion-27b-mtp","name":"operator-customized","limit":{"context":131072,"output":4096}}
   path.write_text(json.dumps(data))
   subprocess.run(["python3",str(SCRIPT),str(path),"16384"],capture_output=True,text=True)
   value=json.loads(path.read_text())
   self.assertEqual(value["providers"]["watoom"]["models"]["fable-cold-fusion-27b-mtp"]["name"],"operator-customized")
 def test_replaces_a_router_discovery_stub(self):
  with tempfile.TemporaryDirectory() as directory:
   path=pathlib.Path(directory)/"opencode.json";data=self.base()
   data["providers"]["watoom"]["models"]["fable-cold-fusion-27b-mtp"]={"modelID":"fable-cold-fusion-27b-mtp","name":"fable-cold-fusion-27b-mtp","capabilities":{"tools":False,"input":["text"],"output":["text"]},"limit":{"context":100000,"output":16384}}
   path.write_text(json.dumps(data))
   first=subprocess.run(["python3",str(SCRIPT),str(path),"16384"],capture_output=True,text=True)
   self.assertEqual(first.stdout.strip(),"CHANGED")
   entry=json.loads(path.read_text())["providers"]["watoom"]["models"]["fable-cold-fusion-27b-mtp"]
   self.assertTrue(entry["capabilities"]["tools"])
   self.assertTrue(entry["name"].startswith("DavidAU/"))
if __name__=="__main__":unittest.main()
