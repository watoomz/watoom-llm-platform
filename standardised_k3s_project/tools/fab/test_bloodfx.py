import unittest,importlib.util,pathlib,tempfile,json
from PIL import Image
spec=importlib.util.spec_from_file_location("bake",pathlib.Path(__file__).with_name("bloodfx-bake.py"));bake=importlib.util.module_from_spec(spec);spec.loader.exec_module(bake)
class BakeTests(unittest.TestCase):
 def test_alpha_and_unpremultiply(self):
  image=Image.new("RGBA",(1,1),(50,0,0,127));self.assertEqual(bake.rgba_from_inverse_opacity(image).getpixel((0,0)),(100,0,0,128))
 def test_requires_real_native_render(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d);(p/"software-render-receipt.json").write_text(json.dumps({"status":"RUNNING"}))
   with self.assertRaises(ValueError):bake.bake(p,p/"output")
 def test_bound_and_sprite_resource(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d);(p/"raw").mkdir()
   for i in range(2):Image.new("RGBA",(256,256),(100+i*50,0,0,0)).save(p/"raw"/(str(i)+".png"))
   receipt={"status":"PASS_NATIVE_SAMPLED_RENDER","actual_software_device":True,"exit_code":0,"assets":[{"asset":"/Game/Blood/Test","duration":1.0,"ortho_width":256,"frames":[{"path":"raw/0.png","time":0.0},{"path":"raw/1.png","time":1.0}]}]}
   (p/"software-render-receipt.json").write_text(json.dumps(receipt));m=bake.bake(p,p/"output")
   self.assertEqual(m["assets"][0]["frames"],2);self.assertFalse(m["native_3d_preserved"])
   self.assertIn('res://bloodfx/frames/Test/frame_000.png',(p/"output/bloodfx/resources/Test.tres").read_text())
if __name__=="__main__":unittest.main()
