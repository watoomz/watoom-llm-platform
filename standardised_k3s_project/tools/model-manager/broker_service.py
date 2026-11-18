"""Private Unix broker: UID-scoped model IDs, no browser/root HTTP endpoint."""
import argparse,json,os,socket,socketserver,struct,stat,errno,time
from pathlib import Path
from broker import Broker
from store import Store
from admission_errors import AdmissionBusy
def secure_socket(path,gid):
 # Shared /data parents can carry default ACLs: chmod changes their mask, not
 # the inherited owning-group entry. Remove ONLY this newly owned socket ACL.
 try:os.removexattr(path,"system.posix_acl_access")
 except OSError as error:
  if error.errno not in (errno.ENODATA,errno.ENOTSUP):raise
 os.chown(path,0,gid);os.chmod(path,0o660)
# Two controller RPCs (1800s each), generation (600s), artifact (30s), plus margin.
GENERATION_BROKER_TIMEOUT = 4500
# Optional generation stages; only sent when the client opts in with "progress": true.
STAGES = ("checking-native-idle","loading-model","generating","restoring-chat-model","publishing")
class Client:
 def __init__(self,path):self.path=path
 def __call__(self,action,record,request=None,progress=None):
  budget=GENERATION_BROKER_TIMEOUT if action=="generate" else 1800
  deadline=time.monotonic()+budget
  with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
   s.settimeout(budget);s.connect(self.path)
   message={"action":action,"id":record["id"],"revision":record["revision"],"request":request}
   if progress and action=="generate":message["progress"]=True
   s.sendall(json.dumps(message).encode()+b"\n")
   reader=s.makefile("rb")
   while True:
    raw=reader.readline(24*1024*1024+1)
    if len(raw)>24*1024*1024:raise ValueError("Broker response oversized")
    response=json.loads(raw)
    if set(response)!={"progress"}:break
    if response["progress"] in STAGES:
     # A failed stage write must never abandon a running GPU transaction.
     try:progress(response["progress"])
     except Exception:pass
    # Progress lines must not extend the overall deadline.
    remaining=deadline-time.monotonic()
    if remaining<=0:raise TimeoutError("Broker generation deadline exceeded")
    s.settimeout(remaining)
   if response.get("code")=="admission_busy":raise AdmissionBusy(response["error"])
   if "error" in response:raise ValueError(response["error"])
   return response["result"]
def main():
 p=argparse.ArgumentParser();p.add_argument("--config",required=True);a=p.parse_args()
 config=json.loads(Path(a.config).read_text())
 catalog=Path(config["catalog"])
 if catalog.is_symlink():raise SystemExit("Refuse symlink catalog")
 store=Store(config["catalog"])
 for suffix in ("","-wal","-shm"):
  path=Path(str(catalog)+suffix)
  if path.exists():
   if path.is_symlink():raise SystemExit("Refuse symlink catalog sidecar")
   os.chown(path,config["ui_uid"],config["ui_gid"]);os.chmod(path,0o640)
 broker=Broker(config,store)
 class Handler(socketserver.StreamRequestHandler):
  def handle(self):
   pid,uid,gid=struct.unpack("3i",self.request.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,struct.calcsize("3i")))
   try:
    if uid!=config["ui_uid"]:raise PermissionError("Unauthorized peer")
    raw=self.rfile.readline(65537)
    if len(raw)>65536:raise ValueError("Oversized request")
    request=json.loads(raw)
    if request["action"] not in ("register","retire","generate"):raise ValueError("Unsupported operation")
    row=store.db.execute("SELECT record FROM models WHERE id=?",(request["id"],)).fetchone()
    if not row:raise ValueError("Installation unknown")
    record=json.loads(row[0])
    if request["revision"]!=record["revision"]:raise ValueError("Stale revision")
    if config.get("stage_only",True):raise ValueError("Production registration is approval-gated; files remain downloaded")
    stream=self.wfile
    def report(stage):
     # Advisory only: a vanished client must not abort the GPU transaction.
     nonlocal stream
     if stream is None or stage not in STAGES:return
     try:stream.write(json.dumps({"progress":stage}).encode()+b"\n");stream.flush()
     except OSError:stream=None
    if request.get("progress") is True and request["action"]=="generate":
     result=broker(request["action"],record,request.get("request"),progress=report)
    else:result=broker(request["action"],record,request.get("request"))
    response={"result":result}
   except Exception as e:response={"error":type(e).__name__+": "+str(e)[:160],"code":"admission_busy" if isinstance(e,AdmissionBusy) else "operation_failed"}
   self.wfile.write(json.dumps(response).encode()+b"\n")
 path=Path(config["socket"])
 if os.geteuid()!=0:raise SystemExit("Broker requires root")
 import fcntl
 lifetime=(Path(config["state"])/"daemon.lock").open("a")
 fcntl.flock(lifetime,fcntl.LOCK_EX|fcntl.LOCK_NB)
 if path.exists():
  if not path.is_socket() or path.lstat().st_uid!=0:raise SystemExit("Refuse foreign socket path")
  path.unlink()
 path.parent.mkdir(parents=True,exist_ok=True)
 with socketserver.UnixStreamServer(str(path),Handler) as server:
  secure_socket(path,config["ui_gid"])
  try:server.serve_forever()
  finally:path.unlink(missing_ok=True)
if __name__=="__main__":main()
