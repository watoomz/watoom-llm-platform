import unittest,tempfile,pathlib,sys,os
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from worker_directories import prepare_worker_directories
class Directories(unittest.TestCase):
 def test_missing_created_without_deleting_existing_cache(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);self.assertEqual(prepare_worker_directories(root),['.godot','.opencode'])
   (root/'.godot/keep').write_text('unchanged');self.assertEqual(prepare_worker_directories(root),[]);self.assertEqual((root/'.godot/keep').read_text(),'unchanged')
 def test_symlink_mount_refused(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);(root/'.godot').symlink_to('/tmp')
   with self.assertRaises(ValueError):prepare_worker_directories(root)
