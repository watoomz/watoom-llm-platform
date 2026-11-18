import json,unittest
from hf import Hub
class Fixture(Hub):
 def __init__(self,files,index):
  self.files=files;self.index=index
 def get(self,path,text=False):
  if "/revision/" in path:return {"sha":"a"*40,"pipeline_tag":"text-to-image","cardData":{}},{}
  if path.endswith("/refs"):return {"branches":[{"name":"main"}],"tags":[]},{}
  if "/tree/" in path:return [{"type":"file","path":name,"size":10} for name in self.files],{}
  if path.endswith("model_index.json"):return json.dumps(self.index),{}
  raise AssertionError(path)
class Metadata(unittest.TestCase):
 def test_pipeline_closure_excludes_unrelated_weights(self):
  files=["model_index.json","unet/diffusion_pytorch_model.safetensors","unet/diffusion_pytorch_model.fp16.safetensors","unet/config.json","tokenizer/vocab.json","tokenizer/merges.txt","other-unrelated.safetensors","unused/config.json"]
  result=Fixture(files,{"_class_name":"StableDiffusionXLPipeline","unet":["diffusers","UNet2DConditionModel"],"tokenizer":["transformers","CLIPTokenizer"]}).inspect("https://huggingface.co/a/b")
  self.assertEqual(len(result["variants"]),2)
  default=result["variants"][0]
  self.assertEqual(default["bytes"],50)
  self.assertNotIn("other-unrelated.safetensors",[x["path"] for x in default["files"]])
  self.assertNotIn("unused/config.json",[x["path"] for x in default["files"]])
 def test_missing_component_precision_is_not_offered(self):
  files=["model_index.json","unet/m.fp16.safetensors","encoder/m.safetensors"]
  result=Fixture(files,{"unet":["diffusers","UNet"],"encoder":["transformers","Encoder"]}).inspect("https://huggingface.co/a/b")
  self.assertEqual(result["variants"],[])

class TaggedCheckpoint(unittest.TestCase):
 def test_published_sdxl_tag_without_pipeline_tag(self):
  class Tagged(Fixture):
   def get(self,path,text=False):
    if "/revision/" in path:return {"sha":"a"*40,"tags":["sdxl"],"cardData":{}},{}
    return super().get(path,text)
  result=Tagged(["checkpoint.safetensors"],{}).inspect("https://huggingface.co/a/b")
  self.assertEqual(result["kind"],"diffusion-checkpoint")
  self.assertIsNone(result["base_model"]) # explicit base selection remains required
  self.assertEqual(result["variants"][0]["bytes"],10)
 def test_repository_name_alone_does_not_establish_architecture(self):
  class Untagged(Fixture):
   def get(self,path,text=False):
    if "/revision/" in path:return {"sha":"a"*40,"tags":[],"cardData":{}},{}
    return super().get(path,text)
  self.assertEqual(Untagged(["checkpoint.safetensors"],{}).inspect("https://huggingface.co/a/sdxl-in-name")["kind"],"unsupported")
