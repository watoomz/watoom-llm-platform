"""Isolated browser acceptance. Never uses production models/controller."""
import argparse,hashlib,json,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from server import Application
from operations import Operations
from worker import Worker
class FixtureHub:
 def inspect(self,url):
  from hf import parse_url
  if parse_url(url)[0]!="fixture/model":raise ValueError("Fixture server accepts only fixture/model")
  data=b"manager-browser-fixture";item={"path":"fixture.gguf","size":len(data),"sha256":hashlib.sha256(data).hexdigest()}
  return {"repository":"fixture/model","revision":"a"*40,"kind":"gguf","base_model":None,"documents":{},"refs":{"branches":[{"name":"main","ref":"refs/heads/main"}],"tags":[]},"source":url,"variants":[{"id":"fixture-Q4","files":[item],"bytes":len(data),"precision":"Q4_0"}]}
 token=None
def main():
 p=argparse.ArgumentParser();p.add_argument("--state",required=True);p.add_argument("--password-file",required=True);p.add_argument("--port",type=int,default=18787);a=p.parse_args()
 app=Application(a.state,Path(a.password_file).read_text().strip(),"http://127.0.0.1:"+str(a.port));app.hub=FixtureHub()
 def downloader(root,repo,revision,item,progress,cancel):
  if cancel():raise ValueError("Cancelled")
  path=Path(root)/item["path"];path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b"manager-browser-fixture");progress(path.stat().st_size)
  return {"path":str(path),"bytes":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
 def broker(action,record):
  # Explicit fixture result, never evidence of production registration.
  return {"configured":True,"registered":False,"fixture":True,"registration_error":"Fixture only: no Kubernetes resources"} if action=="register" else {"retired":True,"fixture":True}
 app.operations=Operations(app.store,Path(a.state)/"fixture-models",broker,downloader,metadata_reader=lambda path:None);app.worker=Worker(app.store,app.operations)
 threading.Thread(target=app.worker.run,daemon=True).start()
 ThreadingHTTPServer(("127.0.0.1",a.port),app.handler()).serve_forever()
if __name__=="__main__":main()
