"""Legacy-Service bootstrap plus the maintained durable Toolkit admission fence."""
import pathlib,json,secrets,os,hashlib,hmac
from toolkit_service_fence import ServiceFence
from release_guard import UnsafeRelease
class ToolkitFence:
 def __init__(self,kub,cmd,root,out,guard,*,namespace="watoom-code",service="watoom-toolkit",state=None,state_cwd=False):
  self.kub=kub;self.cmd=cmd;self.out=out;self.guard=guard;self.route_closed=False;self.owner=None
  self.namespace=namespace;self.service_name=service;self.state_cwd=state_cwd
  self.state=pathlib.Path(state) if state is not None else pathlib.Path("/data/ai/watoom-code/toolkit-state")
  self.source=root/"tools/watoom-toolkit"
 def admission(self,action=None):
  # Use the actual controller UID so new durable files remain readable after
  # restart. Owner tokens travel on stdin, never argv or diagnostic output.
  code='import sys,json;sys.path.insert(0,sys.argv[1]);import job_admission;v=json.load(sys.stdin);print(json.dumps(job_admission.change(sys.argv[2],v["action"],v["owner"]) if v["action"] else job_admission.status(sys.argv[2])))'
  # Enter an explicitly owned private state directory before dropping UID when
  # its report ancestors are intentionally non-traversable. No ACL relaxation.
  target="." if self.state_cwd else str(self.state)
  options={"cwd":str(self.state)} if self.state_cwd else {}
  return json.loads(self.cmd(["setpriv","--reuid=1009","--regid=1009","--clear-groups","--no-new-privs","python3","-B","-c",code,str(self.source),target],input=json.dumps({"action":action,"owner":self.owner}).encode(),**options))
 def save(self,name,value):
  path=self.out/name;raw=json.dumps(value,indent=2).encode()
  fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,"wb") as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
  fd=os.open(path.parent,os.O_RDONLY)
  try:os.fsync(fd)
  finally:os.close(fd)
 def ensure_closed(self):
  if self.route_closed:return
  def get(kind,name=None,labels=None):
   args=["get",kind]+([name] if name else [])+(["-l",",".join(k+"="+v for k,v in labels.items())] if labels else [])
   return self.kub(*args)
  def probe(pod):
   actual=self.kub("get","pod",pod["metadata"]["name"])
   code='import pathlib,json; p=pathlib.Path("/proc/1");cmd=(p/"cmdline").read_bytes().decode().strip(chr(0)).split(chr(0));count=sum(1 for table in ("tcp","tcp6") for line in (p/"net"/table).read_text().splitlines()[1:] if line.split()[1].split(":")[1]=="22AF" and line.split()[3] in ("01","03","08"));print(json.dumps({"server_pid":1,"server_command":cmd,"threads":len(list((p/"task").iterdir())),"established":count}))'
   value=json.loads(self.cmd(["kubectl","-n",self.namespace,"exec",pod["metadata"]["name"],"-c","toolkit","--","python3","-c",code]))
   value["pod_uid"]=actual["metadata"]["uid"];value["container_id"]=next(c["containerID"] for c in actual["status"]["containerStatuses"] if c["name"]=="toolkit")
   return value
  self.service=ServiceFence(get,lambda name,ops:self.cmd(["kubectl","-n",self.namespace,"patch","service",name,"--type=json","-p",json.dumps(ops)]),lambda v:self.save("toolkit-service-fence.private.json",v),self.guard,probe,service=self.service_name)
  # Mark recovery responsibility before acquire: a failed drain intentionally
  # retains its selector and must not fall through to an unfenced rollout.
  self.route_closed=True
  self.service.acquire(seconds=60)
 def acquire(self):
  if (self.out/"toolkit-admission-owner.private.json").exists():raise UnsafeRelease("Existing Toolkit owner recovery evidence must not be overwritten")
  self.ensure_closed()
  self.owner=secrets.token_hex(32)
  self.save("toolkit-admission-owner.private.json",{"owner":self.owner,"state":str(self.state)})
  self.admission("acquire")
  self.assert_held()
 def assert_held(self):
  self.guard()
  data=self.admission()
  if data.get("held") is not True or data.get("active") is not False:raise UnsafeRelease("Toolkit durable admission is not safely held")
  durable=json.loads((self.state/"job-maintenance.json").read_text())
  if not self.owner or not hmac.compare_digest(durable.get("owner_sha256",""),hashlib.sha256(self.owner.encode()).hexdigest()):raise UnsafeRelease("Toolkit durable owner changed")
 def open_route(self):
  self.assert_held()
  if self.route_closed:self.service.release();self.route_closed=False
 def release(self):
  self.assert_held()
  self.open_route()
  self.admission("release")
  self.owner=None
