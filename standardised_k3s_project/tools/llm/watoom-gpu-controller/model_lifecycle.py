"""Never-started enrollment distinct from legacy cutover acknowledgment.

All operations run under the existing controller ownership lock. Enrollment
cannot scale; Kubernetes admission remains the only replica-write authority.
A durable managed-models ledger is replayed before constructing the actuator.
"""
import hashlib,json,re,ipaddress
from pathlib import Path
from controller import Unsafe,Conflict
from kubernetes_api import APIError
def spec_identity(obj):
    spec=dict(obj["spec"]); spec.pop("replicas",None)
    return {"uid":obj["metadata"]["uid"],"spec_sha256":hashlib.sha256(json.dumps(spec,sort_keys=True,separators=(",",":")).encode()).hexdigest()}
def read_ledger(root):
    path=Path(root)/"managed-models.json"
    if not path.exists(): return {}
    value=json.loads(path.read_text())
    if value.get("version")!=1 or not isinstance(value.get("models"),dict): raise Unsafe("Invalid enrollment ledger")
    return value["models"]
def overlay(config,records):
    config=json.loads(json.dumps(config))
    for name,entry in records.items():
        if name in config["models"]: raise Unsafe("Managed enrollment collides with legacy model")
        if entry.get("status")!="enrolled-never-started" or not re.fullmatch(r"llama-cpp-mm-[a-f0-9]{16}",name): raise Unsafe("Invalid managed enrollment")
        if isinstance(config["models"],dict):config["models"][name]=entry["alias"]
        elif isinstance(config["models"],list):config["models"].append(name)
        else:raise Unsafe("Unsupported configured model inventory")
        for key,record_key in (("urls","url"),("aliases","alias"),("deployment_identity","identity")):
            config.setdefault(key,{})[name]=entry[record_key]
        config.setdefault("backend_types",{})[name]=entry["backend"]
    return config
class Lifecycle:
    def __init__(self,runtime,atomic):
        self.r=runtime; self.atomic=atomic
    def quiet(self):
        r=self.r; r.store._check(); s=r.store.load()
        if s.owner or s.uncertain or r.journal.pending() or r.actuator.unknown: raise Conflict("GPU ownership or mutation pending")
        if s.phase not in ("qwen-ready","model-ready"): raise Conflict("Controller not settled")
        # Enrollment never activates. Retirement additionally requires stopped target.
    def change(self,request):
        r=self.r; self.quiet(); name=request.get("deployment","")
        if not re.fullmatch(r"llama-cpp-mm-[a-f0-9]{16}",name): raise Unsafe("Only manager-owned deployments may enroll")
        records=read_ledger(r.root); action=request["action"]
        if action=="enroll-model":
            if name in r.actuator.allowed: raise Conflict("Deployment already enrolled")
            record=request["record"]
            if record.get("backend") not in ("gguf","sdxl"): raise Unsafe("Unsupported backend")
            if not re.fullmatch(r"mm-[a-f0-9]{16}",record.get("alias","")): raise Unsafe("Invalid alias")
            expected="http://"+name+"."+r.c["namespace"]+".svc.cluster.local:8080"
            if record.get("url")!=expected:
                old_allowed=r.api.allowed
                try:
                    r.api.allowed=frozenset(set(old_allowed)|{name})
                    service=r.api.get_service(name)
                finally:r.api.allowed=old_allowed
                spec=service["spec"]
                if service["metadata"].get("labels",{}).get("watoom.io/model-manager")!="owned" or spec.get("type","ClusterIP")!="ClusterIP" or spec.get("selector")!={"app":name} or spec.get("externalIPs") or len(spec.get("ports",[]))!=1:raise Unsafe("Owned internal Service required")
                port=spec["ports"][0]
                if port.get("port")!=8080 or port.get("targetPort")!=8080:raise Unsafe("Unexpected Service port")
                address=ipaddress.ip_address(spec["clusterIP"])
                verified="http://"+("["+str(address)+"]" if address.version==6 else str(address))+":8080"
                if record.get("service_identity")!=spec_identity(service) or record.get("url")!=verified:raise Unsafe("Backend URL or Service identity mismatch")
            # The root broker first creates replicas=0 and grants named read permission.
            old=r.api.allowed
            try:
                r.api.allowed=frozenset(set(old)|{name})
                obj=r.api.get(name)
            finally: r.api.allowed=old
            if obj["metadata"].get("labels",{}).get("watoom.io/model-manager")!="owned": raise Unsafe("Missing ownership label")
            if obj["spec"].get("replicas")!=0 or obj.get("status",{}).get("replicas",0)!=0 or obj["metadata"].get("generation")!=1: raise Unsafe("Enrollment requires never-started deployment")
            actual=spec_identity(obj)
            if actual!=record.get("identity"): raise Unsafe("Enrollment identity mismatch")
            if not r.actuator.probe(name,"stopped"): raise Unsafe("Live or terminating GPU pod exists")
            record=dict(record,status="enrolled-never-started"); records[name]=record
        elif action=="retire-model":
            if name not in records: raise Unsafe("Cannot retire legacy or unmanaged model")
            if request.get("identity")!=records[name]["identity"]: raise Conflict("Stale removal identity")
            if name in (r.c["primary"],r.c["mesh"]): raise Unsafe("Recovery target protected")
            try:obj=r.actuator._get(name)
            except APIError as error:
                if error.status!=404:raise
                obj=None # Proven absent owned deployment, never an unknown outcome.
            if (obj is not None and obj["spec"].get("replicas")!=0) or not r.actuator.probe(name,"stopped"): raise Conflict("Target must be controller-stopped before retirement")
            if s_selected(r)==name: raise Conflict("Selected model cannot be retired")
            del records[name]
        else: raise Unsafe("Unknown lifecycle action")
        # Ledger write precedes effective config. Restart replays identical enrollment.
        config=overlay(r.base_config,records)
        self.atomic(r.root/"managed-models.json",{"version":1,"models":records})
        r.c.clear(); r.c.update(config)
        allowed=frozenset(config["models"])
        r.api.allowed=allowed; r.actuator.allowed=allowed
        r.audit(action,r.store.load())
        return {"status":"enrolled" if action=="enroll-model" else "retired","deployment":name}
def s_selected(r):
    if r.store.load().phase=="qwen-ready":return r.c["primary"]
    p=r.root/"selected-model.json"
    return json.loads(p.read_text()).get("deployment") if p.exists() else None
