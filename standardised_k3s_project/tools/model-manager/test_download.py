import unittest,tempfile,hashlib,io
from pathlib import Path
from download import fetch,DownloadError,safe_path
class Response(io.BytesIO):
 def __init__(self,data,status=200,headers=None): super().__init__(data); self.status=status; self.headers=headers or {}
class Opener:
 def __init__(self,res): self.res=res
 def open(self,req,timeout): self.req=req; return self.res
class Download(unittest.TestCase):
 def item(self,data): return {"path":"nested/m.gguf","size":len(data),"sha256":hashlib.sha256(data).hexdigest()}
 def test_integrity_dedup(self):
  with tempfile.TemporaryDirectory() as d:
   o=Opener(Response(b"abc")); a=fetch(d,"a/b","a"*40,self.item(b"abc"),reserve=0,opener=o)
   self.assertEqual(a["verification"],"remote-sha256")
   self.assertEqual(fetch(d,"a/b","a"*40,self.item(b"abc"),reserve=0,opener=None)["sha256"],a["sha256"])
 def test_resume(self):
  with tempfile.TemporaryDirectory() as d:
   q=Path(d)/"nested"; q.mkdir(); (q/"m.gguf.partial").write_bytes(b"a")
   o=Opener(Response(b"bc",206,{"Content-Range":"bytes 1-2/3"}))
   fetch(d,"a/b","a"*40,self.item(b"abc"),reserve=0,opener=o)
   self.assertEqual(o.req.get_header("Range"),"bytes=1-")
 def test_ignored_range(self):
  with tempfile.TemporaryDirectory() as d:
   q=Path(d)/"nested"; q.mkdir(); (q/"m.gguf.partial").write_bytes(b"a")
   fetch(d,"a/b","a"*40,self.item(b"abc"),reserve=0,opener=Opener(Response(b"abc")))
 def test_bad_digest(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(DownloadError): fetch(d,"a/b","a"*40,self.item(b"abc"),reserve=0,opener=Opener(Response(b"abd")))
   self.assertFalse((Path(d)/"nested/m.gguf").exists())
 def test_git_blob_integrity(self):
  data=b"config";item={"path":"config.json","size":len(data),"git_oid":hashlib.sha1(b"blob 6"+bytes([0])+data).hexdigest()}
  with tempfile.TemporaryDirectory() as d:
   result=fetch(d,"a/b","a"*40,item,reserve=0,opener=Opener(Response(data)))
   self.assertEqual(result["verification"],"remote-git-blob-sha1")
   self.assertEqual(fetch(d,"a/b","a"*40,item,reserve=0)["sha256"],result["sha256"])
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(DownloadError):fetch(d,"a/b","a"*40,item,reserve=0,opener=Opener(Response(b"wrong!")))
 def test_changed_resume_validator(self):
  import json
  with tempfile.TemporaryDirectory() as d:
   q=Path(d)/"nested";q.mkdir();(q/"m.gguf.partial").write_bytes(b"a")
   (q/"m.gguf.partial-validator.json").write_text(json.dumps({"revision":"a"*40,"path":"nested/m.gguf","etag":"old"}))
   with self.assertRaises(DownloadError):fetch(d,"a/b","a"*40,self.item(b"abc"),reserve=0,opener=Opener(Response(b"bc",206,{"Content-Range":"bytes 1-2/3","ETag":"new"})))
 def test_symlink(self):
  with tempfile.TemporaryDirectory() as d:
   (Path(d)/"nested").symlink_to("/tmp",target_is_directory=True)
   with self.assertRaises(DownloadError): safe_path(d,"nested/a")
 def test_cancel(self):
  with tempfile.TemporaryDirectory() as d:
   item=self.item(b"abc")
   with self.assertRaises(DownloadError): fetch(d,"a/b","a"*40,item,reserve=0,cancel=lambda:True,opener=Opener(Response(b"abc")))
   self.assertFalse((Path(d)/(item["path"]+".partial")).exists())
   self.assertFalse((Path(d)/(item["path"]+".partial-validator.json")).exists())
if __name__=="__main__": unittest.main()
