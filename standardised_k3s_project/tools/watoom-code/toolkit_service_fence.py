"""One-time bootstrap fence for the legacy Toolkit without durable admission.

The caller must hold the native application guard. This uses the existing
ClusterIP Service, drains existing HTTP handlers and independently owned workers,
and retains a private CAS recovery snapshot. It never terminates a process.
The supported durable Toolkit guard should be used after bootstrap.
"""
import copy,json,re,secrets,time
from release_guard import UnsafeRelease
class ServiceFence:
 def __init__(self,get,patch,save,guard,probe,service="watoom-toolkit"):
  self.get=get;self.patch=patch;self.save=save;self.guard=guard;self.probe=probe;self.service=service;self.before=None;self.selector=None
 def acquire(self,seconds=60):
  self.guard()
  before=self.get("service",self.service)
  if before["spec"].get("type")!="ClusterIP" or not before["spec"].get("selector"):raise UnsafeRelease("Internal selector Service required")
  pods=self.get("pods",None,before["spec"]["selector"]).get("items",[])
  live=[p for p in pods if not p["metadata"].get("deletionTimestamp") and p.get("status",{}).get("phase")=="Running"]
  if len(live)!=1:raise UnsafeRelease("Legacy Toolkit identity ambiguous")
  self.pod=live[0];self.before=before
  containers=[c for c in self.pod.get("status",{}).get("containerStatuses",[]) if c.get("name")=="toolkit"]
  if len(containers)!=1 or not containers[0].get("containerID"):raise UnsafeRelease("Legacy container identity unavailable")
  self.container_id=containers[0]["containerID"]
  self.selector={"watoom-release-fence":secrets.token_hex(16)}
  self.save({"schema":1,"status":"ACQUIRING","service":before,"pod_uid":self.pod["metadata"]["uid"],"selector":self.selector})
  self.patch(self.service,[{"op":"test","path":"/metadata/uid","value":before["metadata"]["uid"]},{"op":"test","path":"/metadata/resourceVersion","value":before["metadata"]["resourceVersion"]},{"op":"test","path":"/spec/selector","value":before["spec"]["selector"]},{"op":"replace","path":"/spec/selector","value":self.selector}])
  deadline=time.monotonic()+seconds;quiet=0
  while time.monotonic()<deadline:
   self.guard()
   current=self.get("service",self.service)
   if current["metadata"]["uid"]!=before["metadata"]["uid"] or current["spec"]["selector"]!=self.selector:raise UnsafeRelease("Service fence changed concurrently")
   slices=self.get("endpointslices",None,{"kubernetes.io/service-name":self.service}).get("items",[])
   endpoints=sum(len(s.get("endpoints") or []) for s in slices)
   workers=self.get("jobs",None,{"app":"watoom-toolkit-worker"}).get("items",[])
   unsettled=any(not j.get("status",{}).get("succeeded") and not j.get("status",{}).get("failed") for j in workers)
   worker_pods=self.get("pods",None,{"app":"watoom-toolkit-worker"}).get("items",[])
   unsettled=unsettled or any(p.get("status",{}).get("phase") not in ("Succeeded","Failed") for p in worker_pods)
   state=self.probe(self.pod)
   if state.get("container_id")!=self.container_id or state.get("pod_uid")!=self.pod["metadata"]["uid"] or state.get("server_pid")!=1 or state.get("server_command")!=["python3","-B","/opt/watoom/agent.py"]:raise UnsafeRelease("Legacy server identity changed")
   # ThreadingHTTPServer has one main thread; every in-flight handler owns
   # another thread, including preparation before its durable receipt exists.
   idle=endpoints==0 and not unsettled and state.get("threads")==1 and state.get("established")==0
   quiet=quiet+1 if idle else 0
   if quiet>=3:
    self.save({"schema":1,"status":"HELD","service":before,"pod_uid":self.pod["metadata"]["uid"],"selector":self.selector,"drain":state})
    return
   time.sleep(.5)
  raise UnsafeRelease("Legacy requests/workers did not drain; fence retained for recovery")
 def release(self):
  if self.before is None or self.selector is None:raise UnsafeRelease("No owned Service fence")
  self.guard()
  self.patch(self.service,[{"op":"test","path":"/metadata/uid","value":self.before["metadata"]["uid"]},{"op":"test","path":"/spec/selector","value":self.selector},{"op":"replace","path":"/spec/selector","value":self.before["spec"]["selector"]}])
  self.save({"schema":1,"status":"RELEASED","service_uid":self.before["metadata"]["uid"],"selector":self.before["spec"]["selector"]})
