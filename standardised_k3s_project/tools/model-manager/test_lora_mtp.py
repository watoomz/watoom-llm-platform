"""T-0086: GGUF LoRA adapters on an installed GGUF base, MTP speculation proven from the GGUF header, real names and
the read-only all-models inventory row parsing."""
import struct,tempfile,unittest
from pathlib import Path
from gguf_header import inspect,context_limit
from settings import LLM,validate,propose
from workload import build
from broker import display_name,server_settings
from store import Store
IMAGES={"backend_auth_file":"/data/ai/private/model-manager/backend-key"}
def gguf(path,pairs):
 body=b""
 for key,value in pairs:
  k=key.encode();body+=struct.pack("<Q",len(k))+k
  if isinstance(value,str):v=value.encode();body+=struct.pack("<IQ",8,len(v))+v
  else:body+=struct.pack("<II",4,value)
 Path(path).write_bytes(b"GGUF"+struct.pack("<IQQ",3,0,len(pairs))+body)
class Header(unittest.TestCase):
 def test_mtp_and_adapter_facts(self):
  with tempfile.TemporaryDirectory() as d:
   gguf(d+"/m.gguf",[("general.architecture","qwen35"),("general.type","model"),("qwen35.context_length",262144),("qwen35.nextn_predict_layers",1)])
   facts=inspect(d+"/m.gguf")
   self.assertEqual((facts["architecture"],facts["context_length"],facts["nextn_predict_layers"]),("qwen35",262144,1))
   self.assertEqual(context_limit(d+"/m.gguf"),262144)
   gguf(d+"/a.gguf",[("general.architecture","qwen35"),("general.type","adapter"),("adapter.type","lora")])
   facts=inspect(d+"/a.gguf");self.assertEqual((facts["type"],facts["adapter_type"],facts["nextn_predict_layers"]),("adapter","lora",0))
class Settings(unittest.TestCase):
 def test_mtp_needs_proof_and_draft_count(self):
  values=dict(LLM,speculation="draft-mtp",draft_count=4)
  with self.assertRaises(ValueError):validate(values,"gguf")
  with self.assertRaises(ValueError):validate(values,"gguf",capabilities={"mtp":False})
  validate(values,"gguf",capabilities={"mtp":True})
  with self.assertRaises(ValueError):validate(dict(values,draft_count=0),"gguf",capabilities={"mtp":True})
 def test_gguf_lora_is_a_language_model(self):
  self.assertEqual(propose({"kind":"gguf-lora","revision":"a"*40,"documents":{}})["values"]["context"],131072)
  validate(dict(LLM),"gguf-lora")
class Fit(unittest.TestCase):
 # Real header values (2026-11-19): Qwen3.5-4B hybrid (8 full-attention layers) and a Qwen3.8-27B with an MTP head.
 SMALL={"block_count":32,"head_count":16,"head_count_kv":4,"key_length":256,"value_length":256,"embedding_length":2560,"full_attention_interval":4,"context_length":262144,"nextn_predict_layers":0}
 BIG={"block_count":65,"head_count":24,"head_count_kv":4,"key_length":256,"value_length":256,"embedding_length":5120,"full_attention_interval":4,"context_length":262144,"nextn_predict_layers":1}
 def test_small_models_fit_their_native_maximum_and_big_ones_less(self):
  from settings import fit_context,kv_bytes_per_token
  self.assertEqual(kv_bytes_per_token(self.SMALL,"f16","f16"),8*4*512*2)
  self.assertEqual(fit_context(self.SMALL,4482402848,"f16","f16"),262144)
  self.assertLess(fit_context(self.BIG,17033680416,"q4_0","q4_0"),131072)
  sliding={"block_count":6,"head_count":8,"head_count_kv":2,"key_length":512,"value_length":512,"sliding_window_pattern":[True,True,True,True,True,False],"context_length":131072}
  self.assertEqual(kv_bytes_per_token(sliding,"f16","f16"),1*2*1024*2)
  self.assertIsNone(fit_context({"context_length":4096},1,"f16","f16"))
class Workload(unittest.TestCase):
 def record(self,kind,**settings):
  return {"id":"ab"*32,"kind":kind,"settings":dict(LLM,**settings)}
 def args(self,deployment):return deployment["spec"]["template"]["spec"]["containers"][0]["args"]
 def test_plain_gguf_args_unchanged(self):
  args=self.args(build(self.record("gguf"),[{"path":"/data/ai/models/gguf/model-manager/x/m.gguf"}],IMAGES)[0])
  self.assertEqual(args[-2:],["--spec-type","none"]);self.assertNotIn("--lora",args)
 def test_gguf_runs_swift_runtime(self):
  # T-0123: Model Manager models run Swift's runtime: CUDA graphs on, prompt-cache checkpoints, RAM cache, /app/lib first.
  c=build(self.record("gguf"),[{"path":"/data/ai/models/gguf/model-manager/x/m.gguf"}],IMAGES)[0]["spec"]["template"]["spec"]["containers"][0]
  env={e["name"]:e["value"] for e in c["env"]}
  self.assertNotIn("GGML_CUDA_DISABLE_GRAPHS",env)
  self.assertEqual((env["LLAMA_ARG_CTX_CHECKPOINTS"],env["LLAMA_ARG_CACHE_RAM"]),("12","2048"))
  self.assertTrue(env["LD_LIBRARY_PATH"].startswith("/app/lib:"))
 def test_qwen_template_and_default_effort(self):
  r=self.record("gguf");r["settings"]=dict(r["settings"],reasoning="on",reasoning_effort="low",chat_template="qwen38")
  d=build(r,[{"path":"/data/ai/models/gguf/model-manager/x/m.gguf"}],IMAGES)[0]["spec"]["template"]["spec"]
  args=d["containers"][0]["args"]
  self.assertEqual(args[args.index("--reasoning-effort")+1],"low")
  self.assertEqual(args[args.index("--chat-template-file")+1],"/chat-template/qwen38-27b.jinja")
  self.assertIn({"name":"chat-template","hostPath":{"path":"/app/model-manager/chat-templates/qwen38-27b.jinja","type":"File"}},d["volumes"])
  r["settings"]["chat_template"]="/etc/passwd"
  with self.assertRaises(ValueError):build(r,[{"path":"/data/ai/models/gguf/model-manager/x/m.gguf"}],IMAGES)
 def test_turbo_kv_is_valid_and_sized_conservatively(self):
  from settings import validate,CACHE_BYTES
  validate(dict(LLM,cache_k="turbo5",cache_v="turbo4"),"gguf",capabilities={"mtp":False,"vision":False},max_context=131072)
  self.assertGreater(CACHE_BYTES["turbo5"],CACHE_BYTES["turbo4"]);self.assertGreaterEqual(CACHE_BYTES["turbo4"],CACHE_BYTES["q4_0"])
 def test_lora_serves_base_with_adapter(self):
  artifacts=[{"path":"/data/ai/models/loras/model-manager/a/adapter.gguf"},{"path":"/data/ai/models/gguf/model-manager/b/base.gguf"}]
  args=self.args(build(self.record("gguf-lora"),artifacts,IMAGES)[0])
  self.assertEqual(args[args.index("--model")+1],"/models/base.gguf");self.assertEqual(args[args.index("--lora")+1],"/models/adapter.gguf")
  with self.assertRaises(ValueError):build(self.record("gguf-lora"),artifacts[:1],IMAGES)
 def test_projector_serves_vision_only_with_header_proof(self):
  model={"path":"/data/ai/models/gguf/model-manager/x/m.gguf"};proj={"path":"/data/ai/models/gguf/model-manager/x/mmproj-F16.gguf"}
  record=self.record("gguf",projector="mmproj-F16.gguf",projector_gpu=True)
  with self.assertRaises(ValueError):build(record,[model,proj],IMAGES)
  record["capabilities"]={"vision":True}
  args=self.args(build(record,[model,proj],IMAGES)[0])
  self.assertEqual(args[args.index("--model")+1],"/models/m.gguf");self.assertEqual(args[args.index("--mmproj")+1],"/models/mmproj-F16.gguf")
  self.assertNotIn("--no-mmproj-offload",args)
  record["settings"]["projector_gpu"]=False
  self.assertIn("--no-mmproj-offload",self.args(build(record,[model,proj],IMAGES)[0]))
  with self.assertRaises(ValueError):build(record,[proj,model],IMAGES)  # projector must be last
 def test_lora_with_projector_keeps_base_position(self):
  artifacts=[{"path":"/data/ai/models/loras/model-manager/a/adapter.gguf"},{"path":"/data/ai/models/gguf/model-manager/b/base.gguf"},{"path":"/data/ai/models/loras/model-manager/a/mmproj-BF16.gguf"}]
  record=dict(self.record("gguf-lora",projector="mmproj-BF16.gguf",projector_gpu=True),capabilities={"vision":True})
  args=self.args(build(record,artifacts,IMAGES)[0])
  self.assertEqual([args[args.index(f)+1] for f in ("--model","--lora","--mmproj")],["/models/base.gguf","/models/adapter.gguf","/models/mmproj-BF16.gguf"])
 def test_mtp_only_with_header_proof(self):
  record=self.record("gguf",speculation="draft-mtp",draft_count=4)
  with self.assertRaises(ValueError):build(record,[{"path":"/data/ai/models/gguf/model-manager/x/m.gguf"}],IMAGES)
  record["capabilities"]={"mtp":True}
  args=self.args(build(record,[{"path":"/data/ai/models/gguf/model-manager/x/m.gguf"}],IMAGES)[0])
  self.assertEqual(args[-4:],["--spec-type","draft-mtp","--spec-draft-n-max","4"])
class Names(unittest.TestCase):
 def test_display_names(self):
  with tempfile.TemporaryDirectory() as d:
   store=Store(d+"/s.sqlite")
   with store.db:
    store.db.execute("INSERT INTO artifacts VALUES(?,?,?,?)",("a1","/data/ai/models/gguf/model-manager/x/Model-Q8_0.gguf",1,"d"))
    store.db.execute("INSERT INTO artifacts VALUES(?,?,?,?)",("a2","/data/ai/models/loras/model-manager/y/adapter.gguf",1,"d"))
    store.db.execute("INSERT INTO models VALUES(?,?,?)",("base","r",'{"repository":"o/Base-GGUF","artifacts":["a1"]}'))
   self.assertEqual(display_name({"repository":"o/Base-GGUF","artifacts":["a1"],"settings":{}},store),"o/Base-GGUF (Model-Q8_0.gguf)")
   self.assertEqual(display_name({"repository":"o/Base-GGUF","artifacts":["a1"],"settings":{"speculation":"draft-mtp"}},store),"o/Base-GGUF (Model-Q8_0.gguf) · MTP")
   self.assertEqual(display_name({"repository":"h/Adapter","kind":"gguf-lora","artifacts":["a2","a1"],"dependencies":["base"],"settings":{}},store),"h/Adapter on o/Base-GGUF")
   self.assertIsNone(display_name({"artifacts":[]}))
 def test_server_settings_from_args_and_env(self):
  container={"args":["--ctx-size","131072","--spec-type","draft-mtp","--lora","/models/a.gguf"],"env":[{"name":"LLAMA_ARG_MODEL","value":"/models/m.gguf"},{"name":"LLAMA_ARG_CACHE_TYPE_K","value":"q4_0"}]}
  s=server_settings(container)
  self.assertEqual((s["model"],s["lora"],s["context"],s["speculation"],s["cache_k"]),("/models/m.gguf","/models/a.gguf","131072","draft-mtp","q4_0"))
from hf import Hub
class Repo(Hub):
 def __init__(self,files,tags):self.files=files;self.tags=tags
 def get(self,path,text=False):
  if "/revision/" in path:return {"sha":"a"*40,"tags":self.tags,"cardData":{"base_model":"Qwen/Qwen3.8-27B"}},{}
  if path.endswith("/refs"):return {"branches":[],"tags":[]},{}
  if "/tree/" in path:return [{"type":"file","path":name,"size":10} for name in self.files],{}
  return "",{}
class Inspect(unittest.TestCase):
 def test_gguf_lora_and_mtp_variants(self):
  lora=Repo(["README.md","Qwen3.8-27B-opencode-lora-F16.gguf"],["gguf","lora"]).inspect("https://huggingface.co/h/adapter")
  self.assertEqual(lora["kind"],"gguf-lora");self.assertEqual([v["id"] for v in lora["variants"]],["Qwen3.8-27B-opencode-lora-F16.gguf"])
  model=Repo(["M-MTP-IQ4_XS.gguf","M-IQ4_XS.gguf","mmproj-BF16.gguf"],["gguf"]).inspect("https://huggingface.co/d/m")
  self.assertEqual(model["kind"],"gguf");self.assertEqual({v["id"]:v["mtp_published"] for v in model["variants"]},{"M-MTP-IQ4_XS.gguf":True,"M-IQ4_XS.gguf":False})
if __name__=="__main__":unittest.main()

class Vision(unittest.TestCase):
 PROJ="/data/ai/models/gguf/qwen35-defiant-fable-9b/mmproj-BF16.gguf"
 def test_mmproj_header(self):
  import os
  if not os.path.exists(self.PROJ):self.skipTest("live projector absent")
  from gguf_header import inspect
  h=inspect(self.PROJ);self.assertEqual((h["type"],h["vision_encoder"],h["projection_dim"]),("mmproj",True,4096))
 def test_propose_turns_vision_on_when_published(self):
  meta={"kind":"gguf","revision":"a"*40,"documents":{},"projectors":[{"path":"mmproj-F16.gguf","size":1}]}
  values=propose(meta)["values"];self.assertEqual((values["projector"],values["projector_gpu"]),("mmproj-F16.gguf",True))
  self.assertIsNone(propose({"kind":"gguf","revision":"a"*40,"documents":{}})["values"]["projector"])
  from settings import validate
  with self.assertRaises(ValueError):validate({"projector":"mmproj-F16.gguf"},"gguf",capabilities={})
  with self.assertRaises(ValueError):validate({"projector":"model.gguf"},"gguf",capabilities={"vision":True})
  validate({"projector":"mmproj-F16.gguf"},"gguf",capabilities={"vision":True})
 def test_display_name_says_vision(self):
  from broker import display_name
  self.assertTrue(display_name({"repository":"o/R","settings":{"projector":"mmproj-F16.gguf"}}).endswith(" · Vision"))

class Description(unittest.TestCase):
 def test_published_text_only(self):
  from hf import card_description as c
  self.assertEqual(c({"description":"A published description of this model, long enough."},None),"A published description of this model, long enough.")
  self.assertEqual(c({},"---\nlicense: mit\n---\n# T\n\n![b](x)\n\n**Ornith** is a 9B [vision](https://x) model for agentic coding.\n"),"Ornith is a 9B vision model for agentic coding.")
  self.assertEqual(c({},"<small><b>Note:</b> this model halves thinking tokens &lt;1% loss</small>\nsecond line of the same paragraph.\n"),"Note: this model halves thinking tokens <1% loss second line of the same paragraph.")
  self.assertIsNone(c({},"# heading\n\n| a | b |\n\n```\ncode block that is long enough to count\n```"))
  self.assertTrue(c({},"model "*200).endswith("…"))
 def test_description_does_not_change_identity(self):
  from store import model_identity
  sel={"repository":"o/r","revision":"a"*40,"kind":"gguf","files":[],"settings":{}}
  self.assertEqual(model_identity(sel),model_identity(dict(sel,description="text",max_context=4096)))
