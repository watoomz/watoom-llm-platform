"""Approved one-time bootstrap barrier on published Service and pod-to-pod ingress.
Privileged host/kubectl access is an administrative bypass: operators must close
port-forwards and refrain from opening them during the documented window.
Existing TCP connections are never killed; drain failure aborts without rollout.
"""
import json, pathlib, subprocess, time, urllib.request, urllib.error, base64, os, signal
from release_guard import UnsafeRelease, active_clear

def run(args, data=None, timeout=120):
    p=subprocess.run(args,input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
    if p.returncode: raise UnsafeRelease("Maintenance command failed: "+p.stderr.decode(errors="replace")[-300:])
    return p.stdout
class Maintenance:
    def __init__(self, namespace, name, evidence, approval, admin_quiet):
        if not approval or not admin_quiet:
            raise UnsafeRelease("Documented --i-approve and closed administrative port-forwards required")
        self.ns=namespace;self.name=name;self.out=pathlib.Path(evidence)
        self.policy=name+"-release-maintenance";self.held=False
        deployment=self.kub("get","deploy",self.name)
        container=next(c for c in deployment["spec"]["template"]["spec"]["containers"] if c["name"]=="app")
        entry=next(e for e in container["env"] if e["name"]=="OPENCODE_PASSWORD")
        if "value" in entry:self.password=entry["value"]
        else:
            ref=entry["valueFrom"]["secretKeyRef"]
            self.password=base64.b64decode(self.kub("get","secret",ref["name"])["data"][ref["key"]]).decode()
    def kub(self,*args):return json.loads(run(["kubectl","-n",self.ns,*args,"-o","json"]))
    def pod(self):
        pods=[p for p in self.kub("get","pods","-l","app="+self.name)["items"] if not p["metadata"].get("deletionTimestamp") and p.get("status",{}).get("phase")=="Running"]
        if len(pods)!=1:raise UnsafeRelease("Maintenance requires one identified app pod")
        return pods[0]
    def exec(self, code, *args, input=None):
        return run(["kubectl","-n",self.ns,"exec","-i",self.pod()["metadata"]["name"],"-c","app","--","python3","-c",code,*args], data=input)
    def request(self,path,body=None,authenticated=True,method=None):
        code="""import os,json,sys,urllib.request,base64
h={"Content-Type":"application/json","Connection":"close"}
if sys.argv[3]=="true":h["Authorization"]="Basic "+base64.b64encode(("opencode:"+sys.stdin.read()).encode()).decode()
req=urllib.request.Request("http://127.0.0.1:4096"+sys.argv[1],headers=h,data=None if sys.argv[2]=="null" else sys.argv[2].encode(),method=sys.argv[4] or None)
try:
 with urllib.request.urlopen(req,timeout=12) as f:
  raw=f.read();print(json.dumps({"status":f.status,"body":json.loads(raw) if raw else None}))
except urllib.error.HTTPError as e:print(json.dumps({"status":e.code,"body":None}))
"""
        value=json.loads(self.exec(code,path,json.dumps(body),"true" if authenticated else "false",method or "", input=self.password.encode()))
        if value["status"] not in (200,204):raise urllib.error.HTTPError(path,value["status"],"Maintenance API failed",{},None)
        return value["body"]
    def transport(self):
        code="""import pathlib,json,os
connections=[]
for table in ["tcp","tcp6"]:
 for line in pathlib.Path("/proc/net/"+table).read_text().splitlines()[1:]:
  x=line.split()
  if int(x[1].split(":")[1],16)==4096 and x[3] not in ["0A","06"]:connections.append({"local":x[1],"remote":x[2],"state":x[3]})
processes=[]
for p in pathlib.Path("/proc").iterdir():
 if not p.name.isdigit() or int(p.name) in [1,os.getpid()]:continue
 try:
  cmd=(p/"cmdline").read_bytes()
  if cmd:processes.append({"pid":int(p.name),"executable":cmd.split(bytes([0]))[0].decode(errors="replace")})
 except OSError:pass
print(json.dumps({"connections":connections,"processes":processes}))
"""
        return json.loads(self.exec(code))
    def begin(self):
        self.service=self.kub("get","svc",self.name)
        policies=self.kub("get","networkpolicy")["items"]
        labels=self.pod()["metadata"]["labels"]
        for p in policies:
            # Egress-only policies cannot admit ingress around the barrier. Omitted
            # policyTypes always implies Ingress, so treat it as additive.
            if "Ingress" not in p["spec"].get("policyTypes",["Ingress"]):continue
            selector=p["spec"]["podSelector"]
            if selector.get("matchExpressions") or all(labels.get(k)==v for k,v in selector.get("matchLabels",{}).items()):
                raise UnsafeRelease("Existing additive policy may bypass maintenance; refusing")
        self.out.mkdir(parents=True,exist_ok=True)
        (self.out/"maintenance-service-before.json").write_text(json.dumps(self.service,indent=2))
        manifest={"apiVersion":"networking.k8s.io/v1","kind":"NetworkPolicy","metadata":{"name":self.policy,"namespace":self.ns,"labels":{"watoom-release-owner":self.name}},"spec":{"podSelector":{"matchLabels":{"app":self.name}} ,"policyTypes":["Ingress"]}}
        (self.out/"maintenance-policy.json").write_text(json.dumps(manifest,indent=2))
        if run(["kubectl","-n",self.ns,"get","networkpolicy",self.policy,"--ignore-not-found"]).strip():
            raise UnsafeRelease("Maintenance policy already exists; use saved recovery evidence")
        # Set held before first mutation, so partial acquisition can always be restored.
        self.held=True
        run(["kubectl","apply","-f","-"],json.dumps(manifest).encode())
        selector={**self.service["spec"].get("selector",{}),"watoom-release-maintenance":"closed"}
        run(["kubectl","-n",self.ns,"patch","svc",self.name,"--type=json","-p",json.dumps([{"op":"replace","path":"/spec/selector","value":selector}])])
    def pause_access(self):
        if self.name!="watoom-code":return
        # Only the verified staging access supervisors, never application sessions.
        active_clear(self.request("/api/session/active"))
        if self.transport()["processes"]:raise UnsafeRelease("Application child processes active")
        state={"unit_active":False,"supervisors":[]}
        unit="watoom-stage-lan-forward.service"
        status=subprocess.run(["systemctl","is-active",unit],capture_output=True,text=True)
        if status.returncode==0:
            content=run(["systemctl","cat",unit]).decode()
            if "/data/ai/helper-scripts/watoom-stage-lan-relay.py serve" not in content:raise UnsafeRelease("Unrecognized access relay unit")
            (self.out/"maintenance-relay-unit.before").write_text(content)
            state["unit_active"]=True
        expected="/data/github/watoom-standardised-homelab/standardised_k3s_project/tools/watoom-code/forward.py"
        for proc in pathlib.Path("/proc").iterdir():
            if not proc.name.isdigit():continue
            try:
                args=proc.joinpath("cmdline").read_bytes().split(bytes([0]))
                if expected.encode() not in args:continue
                stat=proc.joinpath("stat").read_text().split()
                children=proc.joinpath("task",proc.name,"children").read_text().split()
                if any(pathlib.Path("/proc",child,"comm").read_text().strip()!="kubectl" for child in children):raise UnsafeRelease("Unknown staging forward child")
                state["supervisors"].append({"pid":int(proc.name),"start":stat[21],"children":[int(x) for x in children]})
            except (FileNotFoundError,ProcessLookupError):continue
        self.access=state
        with (self.out/"maintenance-access-before.json").open("w") as f:
            json.dump(state,f,indent=2);f.flush();os.fsync(f.fileno())
        for item in state["supervisors"]:
            os.kill(item["pid"],signal.SIGSTOP)
            for pid in item["children"]:
                try:os.kill(pid,signal.SIGTERM)
                except ProcessLookupError:pass
        if state["unit_active"]:run(["systemctl","stop",unit])
    def restore_access(self):
        state=getattr(self,"access",None)
        if not state:return
        if getattr(self,"keep_access_stopped",False):
            for item in state["supervisors"]:
                p=pathlib.Path("/proc",str(item["pid"]),"stat")
                if p.exists() and p.read_text().split()[21]==item["start"]:
                    os.kill(item["pid"],signal.SIGTERM);os.kill(item["pid"],signal.SIGCONT)
            if state["unit_active"]:run(["systemctl","disable","watoom-stage-lan-forward.service"])
            (self.out/"legacy-forwarding-stopped.json").write_text(json.dumps({"status":"PASS","reason":"User requested leaving forwarding stopped after verified Traefik access"},indent=2))
            self.access=None
            return
        for item in state["supervisors"]:
            p=pathlib.Path("/proc",str(item["pid"]),"stat")
            if not p.exists() or p.read_text().split()[21]!=item["start"]:raise UnsafeRelease("Access supervisor identity changed; recovery evidence retained")
            os.kill(item["pid"],signal.SIGCONT)
        if state["unit_active"]:run(["systemctl","start","watoom-stage-lan-forward.service"])
        self.access=None
    def verify_closed(self):
        svc=self.kub("get","svc",self.name)
        if svc["spec"].get("selector",{}).get("watoom-release-maintenance")!="closed":raise UnsafeRelease("Service barrier lost")
        policy=self.kub("get","networkpolicy",self.policy)
        expected=json.loads((self.out/"maintenance-policy.json").read_text())
        if policy["spec"]!=expected["spec"]:raise UnsafeRelease("Ingress barrier changed")
        slices=self.kub("get","endpointslices","-l","kubernetes.io/service-name="+self.name)["items"]
        if any(s.get("endpoints") for s in slices):raise UnsafeRelease("Published endpoints not yet drained")
    def drain(self, clearance, seconds=45):
        deadline=time.monotonic()+seconds
        while True:
            self.verify_closed()
            state=self.transport()
            (self.out/"maintenance-transport.json").write_text(json.dumps(state,indent=2))
            if not state["connections"] and not state["processes"]:
                active_clear(self.request("/api/session/active"));clearance();self.verify_closed()
                if not self.transport()["connections"]:return
            if time.monotonic()>=deadline:raise UnsafeRelease("Connections/processes did not drain; nothing terminated")
            time.sleep(1)
    def release(self, restore_access=True):
        if not self.held:return
        # Restore only our selector with compare-and-swap; preserve unrelated updates.
        current=self.kub("get","svc",self.name)
        expected={**self.service["spec"].get("selector",{}),"watoom-release-maintenance":"closed"}
        selector=current["spec"].get("selector")
        if selector==expected:
            run(["kubectl","-n",self.ns,"patch","svc",self.name,"--type=json","-p",json.dumps([{"op":"test","path":"/spec/selector","value":expected},{"op":"replace","path":"/spec/selector","value":self.service["spec"]["selector"]}])])
        elif selector!=self.service["spec"].get("selector"):raise UnsafeRelease("Maintenance selector changed concurrently")
        # Acquisition may fail before either mutation; restore only resources actually created.
        raw=run(["kubectl","-n",self.ns,"get","networkpolicy",self.policy,"--ignore-not-found","-o","json"])
        if raw.strip():
            actual=json.loads(raw)
            if actual["spec"]!=json.loads((self.out/"maintenance-policy.json").read_text())["spec"] or actual["metadata"].get("labels",{}).get("watoom-release-owner")!=self.name:raise UnsafeRelease("Maintenance policy changed concurrently")
            run(["kubectl","-n",self.ns,"delete","networkpolicy",self.policy,"--wait=true"])
        self.held=False
        if restore_access:self.restore_access()
