"""Authenticated manager. UI has no Kubernetes or GPU-write privileges."""
import argparse,base64,hmac,json,secrets,threading,urllib.parse,time
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from hf import Hub
from settings import propose,validate
from operations import Operations
from broker_service import Client
from worker import Worker
from store import Store
class Application:
 def __init__(self,root,password,origin,models=None,broker_socket=None,prefix="",hf_token=None,maintenance_file=None,image_mcp_token=None):
  self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
  self.store=Store(self.root/"catalog.sqlite");self.lock=threading.RLock()
  self.maintenance_file=Path(maintenance_file) if maintenance_file else None
  self.image_mcp_token=image_mcp_token
  self.prefix=prefix.rstrip("/");self.password=password;self.origin=origin;self.csrf=secrets.token_urlsafe(32);self.sessions={};self.hub=Hub(hf_token)
  def download(*args,**kwargs):
   from download import fetch
   return fetch(*args,token=self.hub.token,**kwargs)
  self.operations=Operations(self.store,models or self.root/"models",Client(broker_socket),download) if broker_socket else None
  self.worker=Worker(self.store,self.operations,lambda:bool(self.maintenance_file and self.maintenance_file.exists())) if self.operations else None
  if self.worker:threading.Thread(target=self.worker.run,daemon=True).start()
 def handler(self):
  app=self
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def finish(self):
    try:super().finish()
    finally:app.store.close()

   def send(self,code,value,kind="application/json"):
    raw=json.dumps(value).encode() if kind=="application/json" else value
    self.send_response(code);self.send_header("Content-Type",kind);self.send_header("Content-Length",str(len(raw)))
    for k,v in {"Cache-Control":"no-store","X-Content-Type-Options":"nosniff","Content-Security-Policy":"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'self'; object-src 'none'"}.items():self.send_header(k,v)
    self.end_headers();self.wfile.write(raw)
   def authenticated(self):
    cookie=SimpleCookie()
    try:cookie.load(self.headers.get("Cookie",""))
    except Exception:pass
    session=cookie.get("mm_session")
    if session and app.sessions.get(session.value,0)>time.time():return True
    expected="Basic "+base64.b64encode(("admin:"+app.password).encode()).decode()
    if not hmac.compare_digest(self.headers.get("Authorization",""),expected):
     if self.path=="/":
      self.send_response(303);self.send_header("Location",app.prefix+"/login");self.end_headers();return False
     self.send_response(401);self.send_header("WWW-Authenticate",'Basic realm="Model manager"');self.end_headers();return False
    return True
   def do_GET(self):
    if urllib.parse.urlsplit(self.path).path==app.prefix+"/mcp":return self.send(405,{"error":"Use MCP POST"})
    if app.prefix:
     if not self.path.startswith(app.prefix+"/"):return self.send(404,{"error":"Not found"})
     self.path=self.path[len(app.prefix):]
    if self.path=="/login":
     return self.send(200,(b'<html lang="en"><title>Model Manager sign in</title><h1>Model Manager sign in</h1><form method="post" action="/login"><label>Password <input name="password" type="password" required></label><button>Sign in</button></form><p>Password reminder: /data/github/watoom-standardised-homelab/standardised_k3s_project/.private/llm-passwords.json (server-local, excluded from Git).</p></html>').replace(b'action="/login"',('action="'+app.prefix+'/login"').encode()),"text/html")
    if not self.authenticated():return
    if self.path=="/api/session":return self.send(200,{"csrf":app.csrf})
    if self.path.startswith("/api/result?"):
     key=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("id",[""])[0]
     return self.send(200,app.store.result(key))
    if self.path=="/api/jobs":return self.send(200,app.store.jobs())
    if self.path=="/api/models":return self.send(200,[json.loads(r[0]) for r in app.store.db.execute("SELECT record FROM models")])
    files={"/":("index.html","text/html; charset=utf-8"),"/app.js":("app.js","text/javascript"),"/style.css":("style.css","text/css")}
    if self.path in files:
     name,kind=files[self.path];return self.send(200,(Path(__file__).parent/"web"/name).read_bytes().replace(b'href="/',('href="'+app.prefix+'/').encode()).replace(b'src="/',('src="'+app.prefix+'/').encode()) if name=="index.html" else (Path(__file__).parent/"web"/name).read_bytes(),kind)
    self.send(404,{"error":"Not found"})
   def do_POST(self):
    if urllib.parse.urlsplit(self.path).path==app.prefix+"/mcp":
     from image_mcp import handle
     return handle(self,app)
    if app.maintenance_file and app.maintenance_file.exists():return self.send(503,{"error":"Manager maintenance: no new operations admitted; existing data retained"})
    if app.prefix:
     if not self.path.startswith(app.prefix+"/"):return self.send(404,{"error":"Not found"})
     self.path=self.path[len(app.prefix):]
    if self.path=="/login":
     count=int(self.headers.get("Content-Length","0"))
     if self.headers.get("Origin")!=app.origin or not 0<count<4096:return self.send(403,{"error":"Login origin rejected"})
     value=urllib.parse.parse_qs(self.rfile.read(count).decode())
     if not hmac.compare_digest(value.get("password",[""])[0],app.password):return self.send(401,{"error":"Invalid credentials"})
     token=secrets.token_urlsafe(32);app.sessions[token]=time.time()+3600
     self.send_response(303);self.send_header("Location",app.prefix+"/")
     self.send_header("Set-Cookie","mm_session="+token+"; HttpOnly; SameSite=Strict; Path="+app.prefix+"/"+("; Secure" if app.origin.startswith("https:") else ""));self.end_headers();return
    if not self.authenticated():return
    if self.headers.get("Origin")!=app.origin or not hmac.compare_digest(self.headers.get("X-CSRF-Token",""),app.csrf):return self.send(403,{"error":"Origin/CSRF rejected"})
    try:
     size=int(self.headers.get("Content-Length","0"))
     if not 0<size<=65536:raise ValueError("Invalid request size")
     value=json.loads(self.rfile.read(size))
     with app.lock:
      if self.path=="/api/generate":
       if not app.operations:raise ValueError("Lifecycle service unavailable")
       prompt=value.get("prompt","")
       if not isinstance(prompt,str) or not 1<=len(prompt)<=4096:raise ValueError("Prompt must contain 1–4096 characters")
       import uuid
       return self.send(202,{"job":app.store.enqueue({"operation":"generate","id":value["id"],"revision":value["revision"],"prompt":prompt,"nonce":uuid.uuid4().hex})})
      if self.path=="/api/cancel":
       app.store.cancel(value["id"]);return self.send(202,{"state":"Cancellation requested; partial files retained"})
      if self.path=="/api/retry":
       app.store.retry(value["id"]);return self.send(202,{"state":"Queued"})
      if self.path in ("/api/remove-plan","/api/remove"):
       if not app.operations:raise ValueError("Lifecycle service unavailable")
       if self.path=="/api/remove-plan":return self.send(200,app.operations.plan_remove(value["id"],value["revision"]))
       plan=app.operations.plan_remove(value["id"],value["revision"])
       if value.get("confirmation")!=plan["confirmation"]:raise ValueError("Fresh removal confirmation required")
       return self.send(202,{"job":app.store.enqueue({"operation":"remove","id":value["id"],"revision":value["revision"],"delete":bool(value.get("delete",False)),"confirmation":plan["confirmation"]})})
      metadata=app.hub.inspect(value["url"]);identity=metadata["repository"]+"@"+metadata["revision"]
      if self.path=="/api/inspect":return self.send(200,{"metadata":metadata,"settings":propose(metadata,app.store.overrides(identity))})
      if self.path=="/api/install":
       if not app.operations:raise ValueError("Lifecycle service unavailable")
       if value["revision"]!=metadata["revision"]:raise ValueError("Revision changed; inspect again")
       variant=next((x for x in metadata["variants"] if x["id"]==value["variant"]),None)
       if not variant or variant["bytes"] is None:raise ValueError("Complete variant with exact size required")
       values=value["settings"];validate(values,metadata["kind"],max_context=propose(metadata)["max_context"])
       selection={"repository":metadata["repository"],"revision":metadata["revision"],"kind":metadata["kind"],"files":variant["files"],"settings":values,"max_context":propose(metadata)["max_context"]}
       if metadata["kind"] in ("lora","diffusion-checkpoint"):
        if not value.get("base_install"):raise ValueError("Choose an installed compatible base; no automatic base download")
        selection.update(base_install=value["base_install"],base_repository=metadata["base_model"])
       return self.send(202,{"job":app.store.enqueue(selection)})
      if self.path=="/api/overrides":
       values=propose(metadata,safe_only=True)["values"] if value.get("safe_only") else value.get("values",{})
       validate(values,metadata["kind"],max_context=propose(metadata)["max_context"])
       app.store.save_overrides(identity,values);return self.send(200,propose(metadata,values,safe_only=value.get("safe_only",False)))
     self.send(404,{"error":"Not found"})
    except (ValueError,KeyError,TypeError) as e:self.send(400,{"error":str(e)[:200]})
    except Exception:self.send(503,{"error":"Operation unavailable"})
  return Handler
def main():
 p=argparse.ArgumentParser();p.add_argument("--state",required=True);p.add_argument("--password-file",required=True);p.add_argument("--listen",default="127.0.0.1");p.add_argument("--port",type=int,default=8787);p.add_argument("--origin",required=True);p.add_argument("--models");p.add_argument("--broker-socket");p.add_argument("--hf-token-file");p.add_argument("--maintenance-file");p.add_argument("--prefix",default="");p.add_argument("--image-mcp-token-file")
 a=p.parse_args();password=Path(a.password_file).read_text().strip()
 if len(password)<24:raise SystemExit("Password must have at least 24 characters")
 token=Path(a.image_mcp_token_file).read_text().strip() if a.image_mcp_token_file else None
 if token is not None and len(token)<32:raise SystemExit("Image API token must have at least 32 characters")
 app=Application(a.state,password,a.origin,a.models,a.broker_socket,a.prefix,Path(a.hf_token_file).read_text().strip() if a.hf_token_file else None,a.maintenance_file,token)
 ThreadingHTTPServer((a.listen,a.port),app.handler()).serve_forever()
if __name__=="__main__":main()
