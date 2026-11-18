import unittest,tempfile,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from observability import publish
class Tests(unittest.TestCase):
 def test_allowlisted_export_preserves_state_and_hides_secrets(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'state.json';value={'phase':'qwen-ready','owner':None,'generation':9,'uncertain':False,'token':'must-not-export'};source.write_text(json.dumps(value))
   before=source.read_bytes();out=root/'public';out.mkdir();target=out/'status.json'
   result=publish(root,target,'primary')
   self.assertEqual(source.read_bytes(),before);self.assertNotIn('token',result);self.assertEqual(result['generation'],9);self.assertEqual(target.stat().st_mode&0o777,0o644)
 def test_pending_intent_marks_uncertain(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'state.json').write_text(json.dumps({'phase':'qwen-ready','owner':None,'generation':1,'uncertain':False}));(root/'intents').mkdir();(root/'intents/pending.json').write_text('{"status":"pending"}')
   self.assertTrue(publish(root,root/'status.json','primary')['uncertain'])
 def test_symlink_parent_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'link').symlink_to(root,target_is_directory=True)
   with self.assertRaises(ValueError):publish(root,root/'link/status.json','primary')
if __name__=='__main__':unittest.main()
