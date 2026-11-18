"""Durable Toolkit admission on the existing state volume, including controller crashes."""
import pathlib,fcntl,json,re,hashlib,hmac,os,secrets
from asset_catalog import atomic
class Busy(RuntimeError):pass
class Held(RuntimeError):pass
def _state(root):
    p=pathlib.Path(root)/"job-maintenance.json"
    if not p.exists():return {"version":1,"held":False}
    v=json.loads(p.read_text())
    if v.get("version")!=1 or type(v.get("held")) is not bool:raise RuntimeError("Invalid durable maintenance state")
    return v
def _lock(root):
    root=pathlib.Path(root);root.mkdir(parents=True,exist_ok=True)
    f=(root/"job-admission.lock").open("a+")
    try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:f.close();raise Busy("A Toolkit job is still running")
    return f
def _identity():
    return {"pid":os.getpid(),"start":pathlib.Path("/proc/self/stat").read_text().rsplit(")",1)[1].split()[19],
        "boot":pathlib.Path("/proc/sys/kernel/random/boot_id").read_text().strip()}
def _owner_alive(value):
    try:
        if pathlib.Path("/proc/sys/kernel/random/boot_id").read_text().strip()!=value["boot"]:return False
        return pathlib.Path("/proc",str(value["pid"]),"stat").read_text().rsplit(")",1)[1].split()[19]==value["start"]
    except FileNotFoundError:return False
def _marker(root):
    p=pathlib.Path(root)/"job-active.json"
    if not p.exists():return None
    v=json.loads(p.read_text())
    if v.get("version")!=1 or not re.fullmatch("[a-f0-9]{16}",str(v.get("job_id",""))) or v.get("mode") not in ("local","kube") or v.get("status") not in ("RUNNING","UNCERTAIN"):
        raise RuntimeError("Invalid durable active-job identity")
    owner=v.get("owner")
    if not isinstance(owner,dict) or type(owner.get("pid")) is not int or owner["pid"]<1 or not str(owner.get("start","")).isdigit() or not re.fullmatch("[a-f0-9-]{36}",str(owner.get("boot",""))) or not re.fullmatch("[a-f0-9]{32}",str(v.get("nonce",""))):
        raise RuntimeError("Invalid durable Toolkit owner")
    return v
def _remove(root):
    (pathlib.Path(root)/"job-active.json").unlink()
    fd=os.open(root,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
class Lease:
    def __init__(self,root,file,marker):self.root=pathlib.Path(root);self.file=file;self.marker=marker
    def close(self,clear=True):
        if self.file.closed:return
        try:
            current=_marker(self.root)
            if current!=self.marker:raise RuntimeError("Durable Toolkit lease ownership changed")
            if clear:_remove(self.root)
            else:atomic(self.root/"job-active.json",{**self.marker,"status":"UNCERTAIN"})
        finally:self.file.close()
    def __enter__(self):return self
    def __exit__(self,*_):self.close()
def status(root):
    state=_state(root);marker=_marker(root);active=marker is not None
    try:f=_lock(root);f.close()
    except Busy:active=True
    return {"version":1,"supported":True,"held":state["held"],"active":active,"unsettled":marker is not None}
def start(root,job_id=None,mode="local"):
    if job_id is None:job_id=secrets.token_hex(8)
    if not re.fullmatch("[a-f0-9]{16}",str(job_id)) or mode not in ("local","kube"):raise ValueError("Invalid Toolkit lease identity")
    f=_lock(root)
    try:
        if _state(root)["held"]:raise Held("Toolkit maintenance is active; retry after release")
        if _marker(root) is not None:raise Busy("Previous Toolkit operation requires verified reconciliation")
        marker={"version":1,"job_id":job_id,"mode":mode,"status":"RUNNING","owner":_identity(),"nonce":secrets.token_hex(16)}
        atomic(pathlib.Path(root)/"job-active.json",marker)
        return Lease(root,f,marker)
    except BaseException:f.close();raise
def reconcile(root,worker_stopped):
    """Clear no work blindly: dead controller or explicit cleanup uncertainty AND no worker."""
    try:f=_lock(root)
    except Busy:return False
    with f:
        marker=_marker(root)
        if marker is None:return False
        if marker["status"]=="RUNNING" and _owner_alive(marker["owner"]):return False
        if worker_stopped(marker) is not True:return False
        destination=pathlib.Path(root)/"jobs"/marker["job_id"]/"admission-recovery.json"
        atomic(destination,{"version":1,"status":"OWNER_LOST_WORKER_STOPPED","job_id":marker["job_id"],"previous":marker})
        _remove(root)
        return True
def change(root,action,owner):
    if action not in ("acquire","release") or not isinstance(owner,str) or not re.fullmatch("[a-f0-9]{64}",owner):raise ValueError("Invalid maintenance action or owner")
    digest=hashlib.sha256(owner.encode()).hexdigest()
    with _lock(root):
        if _marker(root) is not None:raise Busy("An active or unreconciled Toolkit operation remains")
        old=_state(root)
        if old["held"] and not hmac.compare_digest(old.get("owner_sha256",""),digest):raise Held("Toolkit maintenance belongs to another owner")
        if action=="release" and not old["held"]:raise Held("No matching maintenance owner")
        atomic(pathlib.Path(root)/"job-maintenance.json",{"version":1,"held":action=="acquire","owner_sha256":digest if action=="acquire" else None})
    return status(root)
