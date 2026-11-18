#!/usr/bin/env python3
"""Crash only an owned isolated Toolkit controller; prove its independent Job stays fenced."""
import argparse,pathlib,json,subprocess,os,time,secrets,shutil,hashlib
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--evidence",required=True,type=pathlib.Path);ap.add_argument("--source-overlay",type=pathlib.Path);a=ap.parse_args()
 evidence=a.evidence.resolve()
 if not evidence.is_relative_to("/data/ai/helper-scripts/reports"):raise ValueError("Private evidence root required")
 namespace="watoom-code";stamp=time.strftime("%Y%m%d%H%M%S",time.gmtime())
 base=pathlib.Path("/data/ai/builds")/evidence.name/("restart-acceptance-"+stamp);base.mkdir(parents=True)
 state=base/"state";fixture=base/"fixture";workspace=base/"workspace"
 for path in (state,fixture,workspace):path.mkdir(mode=0o770);os.chown(path,1009,1009)
 (state/"delay").write_text("90");os.chown(state/"delay",1009,1009)
 def kub(*args,body=None,timeout=30):
  result=subprocess.run(["kubectl","-n",namespace,*args],input=json.dumps(body) if body is not None else None,capture_output=True,text=True,timeout=timeout)
  if result.returncode:raise RuntimeError("kubectl operation failed: "+result.stderr[-600:])
  return json.loads(result.stdout) if result.stdout.strip().startswith(("{","[")) else result.stdout
 deployment=kub("get","deployment","watoom-toolkit","-o","json")
 template=deployment["spec"]["template"]["spec"];image=next(c["image"] for c in template["containers"] if c["name"]=="toolkit")
 service_account=template.get("serviceAccountName")
 if service_account!="watoom-toolkit-controller" or "@sha256:" not in image:raise ValueError("Observed immutable controller/runtime required")
 source=a.source_overlay.resolve() if a.source_overlay else None
 if source and not source.is_relative_to("/data/ai/builds"):raise ValueError("Frozen isolated source overlay required")
 harness="""import sys,os,pathlib,threading,time,signal
sys.path.insert(0,"/opt/watoom")
import agent
def command(payload,jobdir):
 if payload!={"task":"probe","timeout":120}:raise ValueError("Fixture accepts only its controlled probe")
 delay=float(pathlib.Path("/state/delay").read_text())
 return ["python3","-B","-c","import time;time.sleep("+str(delay)+");print('controlled fixture worker')"]
agent.make_command=command
def crash():
 while not pathlib.Path("/state/crash-trigger").exists():time.sleep(.1)
 os._exit(137)
threading.Thread(target=crash,daemon=True).start()
signal.signal(signal.SIGTERM,lambda *_:os._exit(0))
agent.main()
"""
 (fixture/"server.py").write_text(harness)
 token=secrets.token_hex(32);owner=secrets.token_hex(32);pods=[];worker=None;client=None;report={"status":"RUNNING","fixture_only":True,"base":str(base),"image":image}
 def save(stage,**values):
  report.update(stage=stage,**values);(evidence/"toolkit-restart-acceptance.json").write_text(json.dumps(report,indent=2));print(stage,flush=True)
 def pod_spec(name):
  mounts=[{"name":"state","mountPath":"/state"},{"name":"workspace","mountPath":"/workspace"},{"name":"fixture","mountPath":"/fixture","readOnly":True},{"name":"tmp","mountPath":"/tmp"}]
  volumes=[{"name":"state","hostPath":{"path":str(state),"type":"Directory"}},{"name":"workspace","hostPath":{"path":str(workspace),"type":"Directory"}},{"name":"fixture","hostPath":{"path":str(fixture),"type":"Directory"}},{"name":"tmp","emptyDir":{"sizeLimit":"128Mi"}}]
  if source:mounts.append({"name":"source","mountPath":"/opt/watoom","readOnly":True});volumes.append({"name":"source","hostPath":{"path":str(source),"type":"Directory"}})
  return {"apiVersion":"v1","kind":"Pod","metadata":{"name":name,"namespace":namespace,"labels":{"watoom-test-owner":evidence.name}},"spec":{"restartPolicy":"Never","activeDeadlineSeconds":360,"serviceAccountName":service_account,"automountServiceAccountToken":True,"securityContext":{"runAsUser":1009,"runAsGroup":1009,"fsGroup":1009,"seccompProfile":{"type":"RuntimeDefault"}},"containers":[{"name":"toolkit","image":image,"command":["python3","-B","/fixture/server.py"],"env":[{"name":"WATOOM_TOKEN","value":token},{"name":"WATOOM_STATE","value":"/state"},{"name":"WATOOM_WORKSPACE","value":"/workspace"},{"name":"WATOOM_WORKER_IMAGE","value":image},{"name":"WATOOM_HOST_STATE","value":str(state)},{"name":"WATOOM_HOST_WORKSPACE","value":str(workspace)},{"name":"WATOOM_WORKER_NAMESPACE","value":namespace},{"name":"HOME","value":"/tmp"},{"name":"PYTHONDONTWRITEBYTECODE","value":"1"}],"resources":{"requests":{"cpu":"100m","memory":"128Mi"},"limits":{"cpu":"1","memory":"1Gi"}},"securityContext":{"allowPrivilegeEscalation":False,"readOnlyRootFilesystem":True,"capabilities":{"drop":["ALL"]}},"volumeMounts":mounts}],"volumes":volumes}}
 def http_args(pod,path,body=None):
  code="import os,json,sys,urllib.request,urllib.error;r=urllib.request.Request('http://127.0.0.1:8879'+sys.argv[1],data=json.dumps(json.loads(sys.argv[2])).encode() if len(sys.argv)>2 else None,headers={'Authorization':'Bearer '+os.environ['WATOOM_TOKEN'],'Content-Type':'application/json'});\ntry:\n response=urllib.request.urlopen(r,timeout=140);print(json.dumps({'code':response.status,'body':json.load(response)}))\nexcept urllib.error.HTTPError as error:print(json.dumps({'code':error.code,'body':json.load(error)}))"
  return ["kubectl","-n",namespace,"exec",pod,"-c","toolkit","--","python3","-c",code,path]+([json.dumps(body)] if body is not None else [])
 def http(pod,path,body=None):
  result=subprocess.run(http_args(pod,path,body),capture_output=True,text=True,timeout=150)
  if result.returncode:raise RuntimeError("Owned HTTP fixture unavailable")
  return json.loads(result.stdout)
 def start(name):
  result=kub("create","-f","-","-o","json",body=pod_spec(name));pods.append((name,result["metadata"]["uid"]))
  deadline=time.monotonic()+60
  while time.monotonic()<deadline:
   try:
    if http(name,"/healthz")["code"]==200:return
   except RuntimeError:pass
   time.sleep(1)
  raise RuntimeError("Isolated controller startup failed")
 def delete_pod(name,uid):
  value=kub("get","pod",name,"-o","json")
  if value["metadata"]["uid"]!=uid:raise RuntimeError("Fixture pod UID changed")
  kub("delete","pod",name,"--wait=true","--timeout=30s",timeout=35)
 try:
  first="toolkit-restart-a-"+stamp;second="toolkit-restart-b-"+stamp
  start(first);save("FIRST_CONTROLLER_READY")
  log=(base/"interrupted-http.log").open("w");client=subprocess.Popen(http_args(first,"/api/jobs",{"task":"probe","timeout":120}),stdout=log,stderr=subprocess.STDOUT)
  deadline=time.monotonic()+40
  while time.monotonic()<deadline:
   marker=state/"job-active.json"
   if marker.exists():
    jobid=json.loads(marker.read_text())["job_id"];items=kub("get","pods","-l","watoom-job="+jobid,"-o","json")["items"]
    if any(p.get("status",{}).get("phase")=="Running" for p in items):
     worker=kub("get","job","watoom-3d-"+jobid,"-o","json");break
   time.sleep(.5)
  if worker is None:raise RuntimeError("Independent owned worker did not start")
  save("WORKER_RUNNING",job=worker["metadata"]["name"],job_uid=worker["metadata"]["uid"])
  (state/"crash-trigger").write_text("owned-test-only");deadline=time.monotonic()+30
  while time.monotonic()<deadline:
   if kub("get","pod",first,"-o","json").get("status",{}).get("phase")=="Failed":break
   time.sleep(.5)
  else:raise RuntimeError("Owned controller crash did not occur")
  client.wait(timeout=15);(state/"crash-trigger").unlink();(state/"delay").write_text(".1")
  start(second)
  status=http(second,"/api/maintenance");new=http(second,"/api/jobs",{"task":"probe","timeout":120});guard=http(second,"/api/maintenance",{"action":"acquire","owner":owner})
  if status["body"].get("active") is not True or new["code"]!=409 or guard["code"]!=409:raise RuntimeError("Restart incorrectly admitted new work or maintenance")
  save("RESTART_FENCED_INDEPENDENT_WORKER",new_work_refused=True,maintenance_refused=True)
  deadline=time.monotonic()+125
  while time.monotonic()<deadline:
   current=kub("get","job",worker["metadata"]["name"],"-o","json")
   if current["metadata"]["uid"]!=worker["metadata"]["uid"]:raise RuntimeError("Worker UID changed")
   if current.get("status",{}).get("succeeded")==1:break
   time.sleep(1)
  else:raise RuntimeError("Owned worker did not finish")
  kub("delete","job",worker["metadata"]["name"],"--cascade=foreground","--wait=true","--timeout=30s",timeout=35);worker=None
  status=http(second,"/api/maintenance")
  if status["body"].get("active") is not False:raise RuntimeError("Verified worker disappearance did not reconcile lease")
  guard=http(second,"/api/maintenance",{"action":"acquire","owner":owner});blocked=http(second,"/api/jobs",{"task":"probe","timeout":120})
  if guard["body"].get("held") is not True or blocked["code"]!=503:raise RuntimeError("Durable maintenance fence failed after restart")
  http(second,"/api/maintenance",{"action":"release","owner":owner})
  complete=http(second,"/api/jobs",{"task":"probe","timeout":120})
  if complete["code"]!=200 or complete["body"].get("status")!="PASS":raise RuntimeError("Post-recovery normal job did not pass")
  report.update(status="PASS",old_worker_not_killed=True,automatic_kube_reconciliation=True,maintenance_after_restart="PASS",normal_work_after_recovery="PASS")
  save("COMPLETE")
 except BaseException as error:
  report.update(status="FAIL",error=type(error).__name__+": "+str(error));save("FAILED");raise
 finally:
  cleanup_errors=[]
  if worker is not None:
   try:
    current=kub("get","job",worker["metadata"]["name"],"-o","json")
    if current["metadata"]["uid"]!=worker["metadata"]["uid"]:raise RuntimeError("Owned fixture Job UID changed")
    kub("delete","job",worker["metadata"]["name"],"--cascade=foreground","--wait=true","--timeout=30s",timeout=35)
   except Exception as error:cleanup_errors.append(type(error).__name__+": "+str(error))
  for name,uid in reversed(pods):
   try:delete_pod(name,uid)
   except Exception as error:cleanup_errors.append(type(error).__name__+": "+str(error))
  if client is not None and client.poll() is None:
   try:client.wait(timeout=15)
   except subprocess.TimeoutExpired:client.terminate();client.wait(timeout=5)
  report["owned_fixture_cleanup"]="FAIL" if cleanup_errors else "PASS"
  if cleanup_errors:report.update(status="FAIL",cleanup_errors=cleanup_errors)
  (evidence/"toolkit-restart-acceptance.json").write_text(json.dumps(report,indent=2))
  if cleanup_errors:raise RuntimeError("Owned fixture cleanup incomplete; exact identities preserved")
if __name__=="__main__":main()
