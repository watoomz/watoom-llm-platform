import json,os,tempfile,unittest
from pathlib import Path
from image_publish import publish
class Publication(unittest.TestCase):
 def test_bytes_and_receipt_new_only(self):
  with tempfile.TemporaryDirectory() as root:
   os.chmod(root,0o700);name="17925300000000000-"+"a"*16;out=publish(root,name,b"fixture-png",{"verified":True});self.assertEqual((Path(root)/name/"image.png").read_bytes(),b"fixture-png");self.assertEqual(json.loads((Path(root)/name/"receipt.json").read_text()),{"verified":True});self.assertEqual(out["bytes"],11);self.assertEqual(out["path"],str(Path(root)/name/"image.png"));self.assertEqual(out["receipt"],str(Path(root)/name/"receipt.json"))
   with self.assertRaises(FileExistsError):publish(root,name,b"changed",{})
 def test_symlink_and_traversal_refused(self):
  with tempfile.TemporaryDirectory() as root:
   real=Path(root)/"real";real.mkdir();link=Path(root)/"link";link.symlink_to(real,target_is_directory=True)
   with self.assertRaises(OSError):publish(link,"17925300000000000-"+"b"*16,b"x",{})
   with self.assertRaises(ValueError):publish(real,"../escape",b"x",{})
 def test_writable_publication_root_refused(self):
  with tempfile.TemporaryDirectory() as root:
   os.chmod(root,0o777)
   with self.assertRaises(ValueError):publish(root,"17925300000000000-"+"c"*16,b"x",{})
