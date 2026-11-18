"""Authenticated Glance skill editor UI. No Git or filesystem write access: all work goes via the root broker."""
import argparse,base64,hmac,json,secrets,socket,time,urllib.parse
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path

WEB=Path(__file__).parent/"web"
MAX_BODY=600*1024

class Broker:
 def __init__(self,path):self.path=path
 def __call__(self,request):
  with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
   s.settimeout(90);s.connect(self.path);s.sendall(json.dumps(request).encode()+b"\n")
   raw=s.makefile("rb").readline(4*1024*1024)
  response=json.loads(raw)
  if "error" in response:
   error=ValueError(response["error"]);error.code=response.get("code");raise error
  return response["result"]

class Application:
 def __init__(self,password,origin,broker,prefix="/skills"):
  self.password=password;self.origin=origin;self.broker=broker;self.prefix=prefix.rstrip("/")
  self.csrf=secrets.token_urlsafe(32);self.sessions={}
 def handler(self):
  app=self
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def send(self,code,value,kind="application/json"):
    raw=json.dumps(value).encode() if kind=="application/json" else value
    self.send_response(code);self.send_header("Content-Type",kind);self.send_header("Content-Length",str(len(raw)))
    for k,v in {"Cache-Control":"no-store","X-Content-Type-Options":"nosniff","Referrer-Policy":"same-origin","Content-Security-Policy":"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'self'; object-src 'none'; base-uri 'none'; form-action 'self'"}.items():self.send_header(k,v)
    self.end_headers();self.wfile.write(raw)
   def route(self):
    path=urllib.parse.urlsplit(self.path).path
    if not path.startswith(app.prefix+"/"):return None
    return path[len(app.prefix):]
   def query(self,key):
    return urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get(key,[""])[0]
   def authenticated(self,path):
    cookie=SimpleCookie()
    try:cookie.load(self.headers.get("Cookie",""))
    except Exception:pass
    session=cookie.get("se_session")
    if session and app.sessions.get(session.value,0)>time.time():return True
    expected="Basic "+base64.b64encode(("admin:"+app.password).encode()).decode()
    if hmac.compare_digest(self.headers.get("Authorization",""),expected):return True
    if path=="/":
     self.send_response(303);self.send_header("Location",app.prefix+"/login");self.end_headers();return False
    self.send_response(401);self.send_header("WWW-Authenticate",'Basic realm="Skill editor"');self.end_headers();return False
   def do_GET(self):
    path=self.route()
    if path is None:return self.send(404,{"error":"Not found"})
    if path=="/login":
     return self.send(200,(WEB/"login.html").read_bytes().replace(b'action="/',('action="'+app.prefix+'/').encode()).replace(b'href="/',('href="'+app.prefix+'/').encode()),"text/html; charset=utf-8")
    if path=="/style.css":return self.send(200,(WEB/"style.css").read_bytes(),"text/css")
    if not self.authenticated(path):return
    try:
     if path=="/api/session":return self.send(200,{"csrf":app.csrf})
     if path=="/api/skills":return self.send(200,app.broker({"action":"list"}))
     if path=="/api/skill":return self.send(200,app.broker({"action":"read","name":self.query("name")}))
     if path=="/api/history":return self.send(200,app.broker({"action":"history","name":self.query("name")}))
    except ValueError as e:return self.send(400,{"error":str(e)[:300]})
    except Exception:return self.send(503,{"error":"Skill service unavailable"})
    files={"/":("index.html","text/html; charset=utf-8"),"/app.js":("app.js","text/javascript")}
    if path in files:
     name,kind=files[path];raw=(WEB/name).read_bytes()
     if name=="index.html":raw=raw.replace(b'href="/',('href="'+app.prefix+'/').encode()).replace(b'src="/',('src="'+app.prefix+'/').encode())
     return self.send(200,raw,kind)
    self.send(404,{"error":"Not found"})
   def do_POST(self):
    path=self.route()
    if path is None:return self.send(404,{"error":"Not found"})
    size=int(self.headers.get("Content-Length","0") or 0)
    if path=="/login":
     if self.headers.get("Origin")!=app.origin or not 0<size<4096:return self.send(403,{"error":"Login origin rejected"})
     value=urllib.parse.parse_qs(self.rfile.read(size).decode())
     if not hmac.compare_digest(value.get("password",[""])[0],app.password):return self.send(401,{"error":"Invalid credentials"})
     token=secrets.token_urlsafe(32);now=time.time()
     for key in [k for k,v in app.sessions.items() if v<now]:app.sessions.pop(key,None)
     app.sessions[token]=now+3600
     self.send_response(303);self.send_header("Location",app.prefix+"/")
     self.send_header("Set-Cookie","se_session="+token+"; HttpOnly; SameSite=Strict; Path="+app.prefix+"/"+("; Secure" if app.origin.startswith("https:") else ""));self.end_headers();return
    if not self.authenticated(path):return
    if self.headers.get("Origin")!=app.origin or not hmac.compare_digest(self.headers.get("X-CSRF-Token",""),app.csrf):return self.send(403,{"error":"Origin/CSRF rejected"})
    if path!="/api/save":return self.send(404,{"error":"Not found"})
    try:
     if not 0<size<=MAX_BODY:raise ValueError("Invalid request size")
     value=json.loads(self.rfile.read(size))
     result=app.broker({"action":"save","name":value["name"],"content":value["content"],"blob":value["blob"],"message":value.get("message","")})
     return self.send(200,result)
    except (ValueError,KeyError,TypeError) as e:return self.send(409 if getattr(e,"code",None)=="conflict" else 400,{"error":str(e)[:300]})
    except Exception:return self.send(503,{"error":"Skill service unavailable"})
  return Handler

def main():
 p=argparse.ArgumentParser()
 for flag in ("--password-file","--origin","--broker-socket"):p.add_argument(flag,required=True)
 p.add_argument("--listen",default="0.0.0.0");p.add_argument("--port",type=int,default=8788);p.add_argument("--prefix",default="/skills")
 a=p.parse_args();password=Path(a.password_file).read_text().strip()
 if len(password)<24:raise SystemExit("Password must have at least 24 characters")
 app=Application(password,a.origin,Broker(a.broker_socket),a.prefix)
 ThreadingHTTPServer((a.listen,a.port),app.handler()).serve_forever()

if __name__=="__main__":main()
