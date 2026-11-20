import unittest,tempfile
from hf import parse_url,MetadataError
from settings import propose,validate
from store import Store
class Core(unittest.TestCase):
 def test_urls(self):
  self.assertEqual(parse_url("https://huggingface.co/a/b/blob/main/f.gguf"),("a/b","main","f.gguf"))
  for url in ("http://huggingface.co/a/b","https://user@huggingface.co/a/b","https://huggingface.co/a/b/tree/main/%2e%2e/x","https://localhost/a/b","https://huggingface.co/a/b/tree/main/a%2fb"):
   with self.assertRaises((ValueError,MetadataError)): parse_url(url)
 def test_slash_revision(self):
  self.assertEqual(parse_url("https://huggingface.co/a/b/tree/refs%2Fpr%2F2")[1],"refs/pr/2")
  with self.assertRaises(ValueError):parse_url("https://huggingface.co/a/b/tree/main%2F..")
 def test_baseline(self):
  m={"kind":"gguf","revision":"a"*40,"documents":{}}
  s=propose(m); self.assertEqual(s["values"]["context"],131072); self.assertEqual((s["values"]["cache_k"],s["values"]["cache_v"],s["values"]["ubatch"]),("turbo5","turbo4",1024));self.assertEqual(s["values"]["output_tokens"],4096)
  m["documents"]={"config.json":{"max_position_embeddings":8192}}
  self.assertEqual(propose(m)["values"]["context"],8192)
 def test_lora(self):
  s=propose({"kind":"lora","revision":"a"*40,"base_model":"a/base"})
  self.assertNotIn("context",s["values"]); self.assertEqual(s["values"]["base_model"],"a/base")
 def test_capability(self):
  with self.assertRaises(ValueError): validate({"speculation":"draft-mtp"},"gguf")
  with self.assertRaises(ValueError): validate({"context":131072},"lora")
 def test_durable(self):
  with tempfile.TemporaryDirectory() as d:
   path=d+"/state.sqlite"; a=Store(path); key=a.enqueue({"revision":"a"*40})
   self.assertEqual(key,a.enqueue({"revision":"a"*40})); a.transition(key,"DOWNLOADING",123)
   a.save_overrides("a@sha",{"context":131072}); b=Store(path)
   self.assertEqual(b.jobs()[0]["progress"],123); self.assertEqual(b.overrides("a@sha")["context"],131072); self.assertEqual(b.overrides("other"),{})
if __name__=="__main__": unittest.main()

class KubernetesNames(unittest.TestCase):
 def test_model_identity_fits_label_and_full_digest_is_retained(self):
  from workload import build
  from settings import LLM
  identity="a"*64
  deployment,service,_=build({"id":identity,"kind":"gguf","settings":dict(LLM)},[{"path":"/data/ai/models/gguf/model-manager/owned/model.gguf"}],{"backend_auth_file":"/data/ai/private/model-manager/backend-key"})
  for obj in (deployment,service):
   self.assertTrue(all(len(v)<=63 for v in obj["metadata"]["labels"].values()))
   self.assertEqual(obj["metadata"]["annotations"]["watoom.io/model-id"],identity)
  self.assertTrue(all(len(v)<=63 for v in deployment["spec"]["template"]["metadata"]["labels"].values()))

class SuccessfulRecovery(unittest.TestCase):
 def test_restart_clears_only_obsolete_errors_after_success(self):
  from store import Store
  import tempfile,json
  from pathlib import Path
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/"catalog.sqlite";s=Store(path)
   with s.db:
    s.db.execute("INSERT INTO models VALUES(?,?,?)",("owned","r",json.dumps({"registered":True,"configured":True,"registration_error":"previous attempt"})))
    s.db.execute("INSERT INTO models VALUES(?,?,?)",("failed","r",json.dumps({"registered":False,"registration_error":"still blocked"})))
   s.close();s=Store(path)
   self.assertNotIn("registration_error",json.loads(s.db.execute("SELECT record FROM models WHERE id='owned'").fetchone()[0]))
   self.assertEqual(json.loads(s.db.execute("SELECT record FROM models WHERE id='failed'").fetchone()[0])["registration_error"],"still blocked")
   s.close()
