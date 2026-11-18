import json,pathlib,subprocess,tempfile,unittest
SCRIPT=pathlib.Path(__file__).resolve().parents[3]/"ansible/roles/watoom-code/files/enable-coordinator-guard.py"
class Upgrade(unittest.TestCase):
 def test_versioned_package_replaces_in_place_preserves_other_config(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/"opencode.json";p.write_text(json.dumps({"keep":"yes","media":{"audio":{"keep":True},"image":{"auto_resize":True,"max_width":1600,"max_base64_bytes":1048576}},"plugins":["searxng",{"package":"/config/watoom-tools/coordinator-guard","options":{"keep":True,"verifiedVisionModels":["local/verified"]}}]}))
   target="/config/watoom-tools/coordinator-guard-"+"a"*64
   result=subprocess.run(["python3",str(SCRIPT),str(p),target],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr);value=json.loads(p.read_text())
   self.assertEqual(value["keep"],"yes");self.assertEqual(value["plugins"][0],"searxng")
   self.assertEqual(value["media"],{"audio":{"keep":True},"image":{"auto_resize":False,"max_width":1600,"max_base64_bytes":1048576}})
   self.assertEqual(value["plugins"][1]["package"],target);self.assertTrue(value["plugins"][1]["options"]["keep"])
   self.assertIn("local/verified",value["plugins"][1]["options"]["verifiedVisionModels"])
   self.assertEqual(subprocess.check_output(["python3",str(SCRIPT),str(p),target],text=True).strip(),"UNCHANGED")
