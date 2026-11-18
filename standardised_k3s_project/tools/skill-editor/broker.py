"""Root-only skill broker: SKILL.md text edits become single-path Git commits, then live copies.

The authenticated web pod never touches Git or the live skill tree. It sends
list/read/history/save requests over a Unix socket; only the configured UI uid
may connect. A save is refused unless the committed file is unchanged since the
editor loaded it (optimistic concurrency) and the working copy is clean.
"""
import argparse,errno,fcntl,json,os,re,socket,socketserver,stat,struct,subprocess,tempfile
from pathlib import Path

NAME=re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}")
MAX_BYTES=256*1024
FRONTMATTER=re.compile(r"---\r?\n(.*?)\r?\n---\r?\n",re.S)

class Conflict(ValueError):pass

def frontmatter_name(text):
 m=FRONTMATTER.match(text)
 if not m:return None
 n=re.search(r"^name:\s*['\"]?([^'\"\r\n]+?)['\"]?\s*$",m.group(1),re.M)
 d=re.search(r"^description:\s*\S",m.group(1),re.M)
 return n.group(1) if n and d else None

class Skills:
 def __init__(self,config):
  self.repo=Path(config["repo"]);self.rel=config["skills_path"].strip("/")
  self.live=Path(config["live_root"]);self.live_uid=config["live_uid"];self.live_gid=config["live_gid"]
  self.branch=config.get("branch","main");self.lock_path=Path(config["state"])/"save.lock"
  self.author=(config["author_name"],config["author_email"])
 def git(self,*args,check=True,input=None):
  cmd=["git","-c","safe.directory="+str(self.repo),"-c","user.name="+self.author[0],"-c","user.email="+self.author[1],"-C",str(self.repo),*args]
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=60,input=input)
  if check and p.returncode:raise RuntimeError("git "+args[0]+" failed: "+p.stderr.strip()[-200:])
  return p
 def path(self,name):
  if not isinstance(name,str) or not NAME.fullmatch(name):raise ValueError("Invalid skill name")
  rel=self.rel+"/"+name+"/SKILL.md";full=self.repo/rel
  base=(self.repo/self.rel).resolve()
  if full.is_symlink() or full.parent.is_symlink() or not full.is_file() or full.resolve().parent.parent!=base:raise ValueError("Unknown skill")
  return rel,full
 def head_blob(self,rel):
  p=self.git("rev-parse","HEAD:"+rel,check=False)
  if p.returncode:raise ValueError("Skill is not committed")
  return p.stdout.strip()
 def live_file(self,name):
  return self.live/name/"SKILL.md"
 def live_state(self,name,content):
  f=self.live_file(name)
  if not f.is_file() or f.is_symlink():return "absent"
  return "matches" if f.read_bytes()==content else "differs"
 def list(self):
  root=self.repo/self.rel;items=[]
  for d in sorted(root.iterdir()):
   if d.is_symlink() or not d.is_dir() or not NAME.fullmatch(d.name):continue
   f=d/"SKILL.md"
   if f.is_file() and not f.is_symlink():items.append({"name":d.name,"bytes":f.stat().st_size,"live":self.live_state(d.name,f.read_bytes())})
  return {"skills":items,"branch":self.current_branch(),"unpushed":self.unpushed()}
 def current_branch(self):
  return self.git("symbolic-ref","--short","-q","HEAD",check=False).stdout.strip() or None
 def unpushed(self):
  p=self.git("rev-list","--count","origin/"+self.branch+".."+self.branch,check=False)
  return int(p.stdout.strip()) if p.returncode==0 and p.stdout.strip().isdigit() else None
 def read(self,name):
  rel,full=self.path(name);raw=full.read_bytes()
  last=self.git("log","-1","--format=%h%x00%cI%x00%s","--",rel).stdout.strip().split("\x00")
  return {"name":name,"content":raw.decode("utf-8"),"blob":self.head_blob(rel),"dirty":self.dirty(rel,full),"live":self.live_state(name,raw),
          "last_commit":dict(zip(("commit","date","subject"),last)) if len(last)==3 else None,"path":rel}
 def history(self,name):
  rel,_=self.path(name)
  out=self.git("log","-20","--format=%h%x00%cI%x00%s","--",rel).stdout.strip().splitlines()
  return {"name":name,"commits":[dict(zip(("commit","date","subject"),line.split("\x00"))) for line in out if line.count("\x00")==2]}
 def dirty(self,rel,full):
  working=self.git("hash-object","--",str(full)).stdout.strip()
  staged=self.git("diff","--cached","--quiet","--",rel,check=False).returncode
  return working!=self.head_blob(rel) or staged!=0
 def save(self,name,content,base_blob,message=""):
  rel,full=self.path(name)
  if not isinstance(content,str):raise ValueError("Content must be text")
  data=content.encode("utf-8")
  if not 0<len(data)<=MAX_BYTES or "\x00" in content:raise ValueError("SKILL.md must be 1 byte to 256 KiB of text")
  if not isinstance(message,str) or len(message)>200 or "\n" in message:raise ValueError("Commit note must be one line of at most 200 characters")
  self.lock_path.parent.mkdir(parents=True,exist_ok=True)
  with self.lock_path.open("a") as lock:
   fcntl.flock(lock,fcntl.LOCK_EX)
   if self.current_branch()!=self.branch:raise Conflict("Repository is not on "+self.branch+"; saving is disabled")
   if self.head_blob(rel)!=base_blob:raise Conflict("This skill was changed since you opened it; reload before saving")
   if self.dirty(rel,full):raise Conflict("Repository copy has uncommitted changes; resolve them before saving here")
   old=full.read_bytes()
   if data==old:return {"changed":False,"commit":None,"live":self.sync_live(name,data)}
   expected=frontmatter_name(old.decode("utf-8"))
   if frontmatter_name(content)!=expected:raise ValueError("Keep the front matter: '---', 'name: "+str(expected)+"' and a 'description:' line")
   self.write_atomic(full,data,stat.S_IMODE(full.stat().st_mode),full.stat().st_uid,full.stat().st_gid)
   subject="skills("+name+"): "+(message.strip() or "edit via Glance skill editor")
   try:
    self.git("commit","--only","-m",subject,"-m","Edited-Via: glance-skill-editor","--",rel)
   except Exception:
    self.write_atomic(full,old,stat.S_IMODE(full.stat().st_mode),full.stat().st_uid,full.stat().st_gid)
    raise
   commit=self.git("rev-parse","--short","HEAD").stdout.strip()
   return {"changed":True,"commit":commit,"live":self.sync_live(name,data),"blob":self.head_blob(rel)}
 def sync_live(self,name,data):
  target=self.live_file(name)
  if not target.parent.is_dir() or target.parent.is_symlink() or target.is_symlink():return "absent"
  self.write_atomic(target,data,0o644,self.live_uid,self.live_gid)
  return "matches"
 @staticmethod
 def write_atomic(path,data,mode,uid,gid):
  fd,tmp=tempfile.mkstemp(prefix=".skill-editor-",dir=path.parent)
  try:
   with os.fdopen(fd,"wb") as f:f.write(data);f.flush();os.fsync(f.fileno())
   os.chown(tmp,uid,gid);os.chmod(tmp,mode);os.replace(tmp,path)
  finally:
   if os.path.exists(tmp):os.unlink(tmp)

def handle(skills,request):
 action=request.get("action")
 if action=="list":return skills.list()
 if action=="read":return skills.read(request["name"])
 if action=="history":return skills.history(request["name"])
 if action=="save":return skills.save(request["name"],request["content"],request["blob"],request.get("message",""))
 raise ValueError("Unsupported operation")

def main():
 p=argparse.ArgumentParser();p.add_argument("--config",required=True);a=p.parse_args()
 if os.geteuid()!=0:raise SystemExit("Skill broker requires root")
 config=json.loads(Path(a.config).read_text());skills=Skills(config)
 class Handler(socketserver.StreamRequestHandler):
  def handle(self):
   uid=struct.unpack("3i",self.request.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,struct.calcsize("3i")))[1]
   try:
    if uid!=config["ui_uid"]:raise PermissionError("Unauthorized peer")
    raw=self.rfile.readline(MAX_BYTES*2+4096)
    if len(raw)>MAX_BYTES*2+4096:raise ValueError("Oversized request")
    response={"result":handle(skills,json.loads(raw))}
   except Conflict as e:response={"error":str(e)[:300],"code":"conflict"}
   except (ValueError,KeyError,TypeError,PermissionError,UnicodeDecodeError) as e:response={"error":str(e)[:300],"code":"invalid"}
   except Exception as e:response={"error":type(e).__name__+": "+str(e)[:200],"code":"failed"}
   try:self.wfile.write(json.dumps(response).encode()+b"\n")
   except OSError:pass
 path=Path(config["socket"])
 if path.exists() or path.is_symlink():
  if not path.is_socket() or path.lstat().st_uid!=0:raise SystemExit("Refuse foreign socket path")
  path.unlink()
 class Server(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):daemon_threads=True
 with Server(str(path),Handler) as server:
  try:os.removexattr(path,"system.posix_acl_access")
  except OSError as error:
   if error.errno not in (errno.ENODATA,errno.ENOTSUP):raise
  os.chown(path,0,config["ui_gid"]);os.chmod(path,0o660)
  try:server.serve_forever()
  finally:path.unlink(missing_ok=True)

if __name__=="__main__":main()
