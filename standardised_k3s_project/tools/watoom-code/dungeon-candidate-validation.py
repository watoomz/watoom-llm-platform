#!/usr/bin/env python3
"""Focused native application acceptance on the explicitly owned dungeon pair."""
import argparse,base64,hashlib,json,os,pathlib,re,sqlite3,subprocess,time,urllib.request
from maintenance_guard import Maintenance
import release_guard
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--evidence",required=True,type=pathlib.Path);ap.add_argument("--phase",required=True,choices=["native","gui","cancel","restart","replay-after-restart","gui-generate"]);ap.add_argument("--case",default="v2");a=ap.parse_args()
 if not re.fullmatch("[a-z0-9-]{1,20}",a.case):raise ValueError("Safe owned acceptance case ID required")
 evidence=a.evidence.resolve();out=evidence/"native-candidate";identity=json.loads((out/"identity.json").read_text())
 if identity["name"]!="watoom-code-dungeon-candidate" or identity["toolkit"]!="watoom-toolkit-dungeon-candidate" or identity["owner"]!=evidence.name:raise ValueError("Owned isolated pair required")
 m=Maintenance(identity["namespace"],identity["name"],out,True,True)
 for name in (identity["name"],identity["toolkit"]):
  if m.kub("get","deploy",name)["metadata"]["labels"]["watoom-test-owner"]!=evidence.name:raise ValueError("Candidate resource ownership mismatch")
 base="http://"+m.kub("get","svc",m.name)["spec"]["clusterIP"]+":4096"
 auth="Basic "+base64.b64encode(("opencode:"+m.password).encode()).decode()
 def api(path,body=None):
  request=urllib.request.Request(base+path,headers={"Authorization":auth,"Content-Type":"application/json"},data=json.dumps(body).encode() if body is not None else None)
  with urllib.request.urlopen(request,timeout=20) as response:
   raw=response.read();return json.loads(raw) if raw else None
 def save(name,value):
  path=out/name;path.write_text(json.dumps(value,indent=2));path.chmod(0o600)
 def sha(path):
  with path.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
 def walk(value):
  if isinstance(value,dict):
   yield value
   for child in value.values():yield from walk(child)
  elif isinstance(value,list):
   for child in value:yield from walk(child)
 if a.phase!="gui":
  workers=m.kub("get","pods","-l","app=watoom-toolkit-worker")["items"]
  if any(p.get("status",{}).get("phase") not in ("Succeeded","Failed") for p in workers):raise ValueError("Existing native worker must finish before serial acceptance")
 if a.phase=="gui-generate":
  owner=(out/"guard-owner.private").read_text().strip();gui=out/"gui-generation";gui.mkdir(mode=0o700)
  if api("/api/session/active")["data"]!={}:raise ValueError("Candidate has active work")
  operation=json.loads((out/"native-api-prompt.json").read_text())["operation"]
  operation={**operation,"job":"dungeon-gui-acceptance-v1"}
  api("/api/session/deployment-guard",{"action":"release","owner":owner})
  try:
   session=api("/api/session",{"agent":"build","location":{"directory":identity["project"]},"title":"Owned GUI dungeon generation"})["data"]["id"]
   save("gui-generation-prompt.json",{"session":session,"operation":operation,"agent":"build","approval_scope":["local-toolkit","world.compose"]})
   prompt="Call the directly exposed native watoom_specialist_run once with this exact JSON, await actual completion and report the artifacts. Do not use Code Mode, other tools or skills. Never print a simulated tool call: "+json.dumps(operation)
   env={**os.environ,"PLAYWRIGHT_MODULE":"/data/ai/projects/llm/watoom-code/native-next-review-20261014T212958Z/source/node_modules/.bun/playwright@1.59.1/node_modules/playwright",
    "CANDIDATE_PASSWORD":m.password,"CANDIDATE_BASE":base,"EVIDENCE":str(gui),"NATIVE_REPLAY_SESSION":session,"NATIVE_REPLAY_PROMPT":prompt,"NATIVE_SUBMIT_ONLY":"1"}
   with (gui/"submit.log").open("w") as log:subprocess.run(["node",str(pathlib.Path(__file__).with_name("agentmemory-browser.cjs"))],env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=80)
   deadline=time.monotonic()+1000;approved=[]
   while time.monotonic()<deadline:
    pending=api("/api/session/"+session+"/permission")["data"]
    for request in pending:
     if request["sessionID"]!=session or request["action"]!="watoom_specialist_run" or set(request["resources"])!={"local-toolkit","world.compose"}:raise ValueError("Unexpected permission request; no broad approval granted")
     api("/api/session/"+session+"/permission/"+request["id"]+"/reply",{"decision":"once"});approved.append(request["id"])
    if not api("/api/session/active")["data"] and api("/api/session/"+session)["data"].get("outcome") is not None:break
    time.sleep(2)
   else:raise TimeoutError("Owned GUI generation still active; left running")
   messages=api("/api/session/"+session+"/message");save("gui-generation-messages.private.json",messages)
   calls=[x for x in walk(messages) if x.get("type")=="tool" and x.get("name")=="watoom_specialist_run"]
   if len(calls)!=1 or calls[0].get("state",{}).get("status")!="completed":raise ValueError("GUI native tool did not complete exactly once")
   with sqlite3.connect("file:"+str(out/"state/application.sqlite")+"?mode=ro",uri=True) as db:row=db.execute("SELECT phase,outcome FROM _watoom_specialist_job WHERE job=?",(operation["job"],)).fetchone()
   if not row or row[0]!="completed":raise ValueError("GUI native outcome not durably completed")
   outcome=json.loads(row[1]);artifacts=outcome["artifacts"]
   if len(artifacts)!=8:raise ValueError("GUI native artifact set incomplete")
   for item in artifacts:
    path=out/"published"/item["reference"][9:]
    if not path.resolve().is_relative_to(out/"published") or sha(path)!=item["sha256"]:raise ValueError("GUI artifact hash mismatch")
   ref=next(x["reference"] for x in artifacts if x["reference"].endswith("/manifest.json"));manifest_path=out/"published"/ref[9:];manifest=json.loads(manifest_path.read_text())
   accepted=json.loads((out/"native-api-acceptance.json").read_text())
   if manifest["status"]!="PASS" or manifest["plan_sha256"]!=accepted["plan_sha256"]:raise ValueError("GUI generation differs from accepted plan")
   fixture=pathlib.Path(json.loads((evidence/"builder-vertical-landing-candidate-acceptance.json").read_text())["directory"])/"artifacts/asset.glb"
   if sha(manifest_path.parent/"asset.glb")!=sha(fixture):raise ValueError("GUI same-seed GLB changed")
   env.pop("NATIVE_SUBMIT_ONLY");env.pop("NATIVE_REPLAY_SESSION");env.pop("NATIVE_REPLAY_PROMPT")
   env.update(CREATIVE_ROUTE_SESSION=session,CREATIVE_ARTIFACT_JOBS=json.dumps([manifest["job_id"]]))
   with (gui/"view.log").open("w") as log:subprocess.run(["node",str(pathlib.Path(__file__).with_name("agentmemory-browser.cjs"))],env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=90)
   result={"status":"PASS","session":session,"job":operation["job"],"toolkit_job":manifest["job_id"],"authenticated_gui_submitted_and_completed":True,"native_artifacts":8,"explicit_owned_permission_once":approved,"global_permission_rules_changed":False,"plan_sha256":manifest["plan_sha256"],"same_seed_glb":"PASS byte-identical","visual_review":"PENDING inspect final screenshot"}
   save("native-gui-generation-acceptance.json",result);print(json.dumps(result),flush=True)
  finally:
   if api("/api/session/active")["data"]=={}:
    held=api("/api/session/deployment-guard",{"action":"acquire","owner":owner})["data"]
    if not held.get("held") or held.get("leases")!=0:raise ValueError("Could not close candidate admission")
  return
 if a.phase in ("restart","replay-after-restart"):
  from toolkit_release_fence import ToolkitFence
  owner=(out/"guard-owner.private").read_text().strip();phase=out/"restart-native"
  if a.phase=="restart":phase.mkdir(mode=0o700)
  elif json.loads((phase/"restart-runtime-recovery.json").read_text())["status"]!="PASS":raise ValueError("Verified guarded restart continuation required")
  accepted=json.loads((out/"native-api-acceptance.json").read_text())
  def guard():
   if api("/api/session/active")["data"]!={}:raise ValueError("Candidate has active execution")
   data=api("/api/session/deployment-guard")["data"]
   if not data.get("held") or data.get("leases")!=0:raise ValueError("Native guard must remain held")
   release_guard.durable_clearance(out/"state/application.sqlite")
  def cmd(args,input=None,timeout=60,cwd=None):
   result=subprocess.run(args,input=input,capture_output=True,timeout=timeout,cwd=cwd)
   if result.returncode:raise RuntimeError(result.stderr.decode(errors="replace")[-500:])
   return result.stdout
  guard()
  with sqlite3.connect("file:"+str(out/"state/application.sqlite")+"?mode=ro",uri=True) as db:
   before=list(db.execute("SELECT id,phase,outcome FROM _watoom_specialist_job ORDER BY id"))
  directories=sorted(p.name for p in (out/"toolkit-state/jobs").iterdir() if p.is_dir())
  if a.phase=="restart":
   (phase/"before-state.json").write_text(json.dumps({"rows":before,"directories":directories,"baseline":"Captured before either pod restart"}))
   fence=ToolkitFence(m.kub,cmd,pathlib.Path(__file__).resolve().parents[2],phase,guard,namespace=m.ns,service=identity["toolkit"],state=out/"toolkit-state",state_cwd=True)
   fence.acquire()
   for name in (identity["toolkit"],identity["name"]):
    guard()
    cmd(["kubectl","-n",m.ns,"rollout","restart","deployment/"+name])
    cmd(["kubectl","-n",m.ns,"rollout","status","deployment/"+name,"--timeout=120s"],timeout=130)
   deadline=time.monotonic()+40
   while True:
    try:guard();break
    except OSError:
     if time.monotonic()>deadline:raise
     time.sleep(1)
   fence.assert_held()
  else:
   baseline=json.loads((phase/"before-state.json").read_text());before=[tuple(row) for row in baseline["rows"]];directories=baseline["directories"];guard()
  with sqlite3.connect("file:"+str(out/"state/application.sqlite")+"?mode=ro",uri=True) as db:
   if list(db.execute("SELECT id,phase,outcome FROM _watoom_specialist_job ORDER BY id"))!=before:raise ValueError("Native durable jobs changed across restart")
  for item in accepted["artifacts"]:
   if sha(out/"published"/item["reference"][9:])!=item["sha256"]:raise ValueError("Native artifact changed across restart")
  if a.phase=="restart":fence.release()
  for name,image in ((identity["name"],identity["image"]),(identity["toolkit"],identity["toolkit_image"])):
   pods=m.kub("get","pods","-l","app="+name)["items"]
   running=[p for p in pods if p["status"]["phase"]=="Running" and not p["metadata"].get("deletionTimestamp")]
   if len(running)!=1 or running[0]["status"]["containerStatuses"][0]["imageID"].split("@")[-1]!=image.split("@")[-1]:raise ValueError("Actual restarted immutable image mismatch")
  url=next(e["url"] for e in json.loads((out/"config/opencode.json").read_text())["watoom_specialists"]["entries"] if e["descriptor"]["id"]=="local-toolkit")
  route_code='import os,json,sys,urllib.request;r=urllib.request.Request(sys.argv[1]+"/api/catalog",headers={"Authorization":"Bearer "+os.environ["WATOOM_TOKEN"]});d=json.load(urllib.request.urlopen(r,timeout=10));assert "world.compose" in d["capabilities"];print("AUTHENTICATED_ROUTE_PASS")'
  route_deadline=time.monotonic()+20
  while True:
   try:
    if m.exec(route_code,url).strip()!=b"AUTHENTICATED_ROUTE_PASS":raise ValueError("Unexpected backend route result")
    break
   except Exception:
    if time.monotonic()>route_deadline:raise
    time.sleep(1)
  operation=json.loads((out/"native-api-prompt.json").read_text())["operation"]
  api("/api/session/deployment-guard",{"action":"release","owner":owner})
  try:
   session=api("/api/session",{"agent":identity["agent"],"location":{"directory":identity["project"]},"title":"Owned cached native restart proof"})["data"]["id"]
   save("native-restart-prompt.json",{"session":session,"operation":operation,"expected":"Existing positively completed receipt only; no new native worker"})
   api("/api/session/"+session+"/prompt",{"text":"Call the directly exposed native watoom_specialist_run once with this exact JSON. This existing positively completed job should return verified cached artifacts. Do not create a new job ID, use Code Mode, or retry errors: "+json.dumps(operation)})
   deadline=time.monotonic()+150
   while api("/api/session/active")["data"]:
    if time.monotonic()>deadline:raise TimeoutError("Owned cached replay still active; left running")
    time.sleep(1)
   messages=api("/api/session/"+session+"/message");save("native-restart-messages.private.json",messages)
   calls=[x for x in walk(messages) if x.get("type")=="tool" and x.get("name")=="watoom_specialist_run"]
   if len(calls)!=1 or calls[0].get("state",{}).get("status")!="completed":raise ValueError("Actual native cached replay failed")
   if sorted(p.name for p in (out/"toolkit-state/jobs").iterdir() if p.is_dir())!=directories:raise ValueError("Completed native replay created another Toolkit job")
   with sqlite3.connect("file:"+str(out/"state/application.sqlite")+"?mode=ro",uri=True) as db:
    if list(db.execute("SELECT id,phase,outcome FROM _watoom_specialist_job ORDER BY id"))!=before:raise ValueError("Cached replay changed durable native identity/outcome")
   for item in accepted["artifacts"]:
    if sha(out/"published"/item["reference"][9:])!=item["sha256"]:raise ValueError("Cached artifact hash changed")
   save("native-restart-acceptance.json",{"status":"PASS","session":session,"job":accepted["job"],"toolkit_job":accepted["toolkit_job"],"application_restart":"PASS native guard persisted","toolkit_restart":"PASS durable owner persisted","completed_replay":"PASS actual native tool after restart, no new Toolkit job","artifacts_preserved":len(accepted["artifacts"]),"same_durable_outcomes":True})
   print(json.dumps({"status":"PASS","restart_and_actual_cached_replay":"PASS"}),flush=True)
  finally:
   if api("/api/session/active")["data"]=={}:
    held=api("/api/session/deployment-guard",{"action":"acquire","owner":owner})["data"]
    if not held.get("held") or held.get("leases")!=0:raise ValueError("Could not restore candidate native guard")
  return
 if a.phase=="cancel":
  owner=(out/"guard-owner.private").read_text().strip();journal=out/"native-cancel-prompt.json"
  if journal.exists():raise ValueError("Inspect existing cancellation fixture; never replay")
  if api("/api/session/active")["data"]!={}:raise ValueError("Candidate has active work")
  release_guard.durable_clearance(out/"state/application.sqlite")
  baseline=json.loads((out/"native-api-prompt.json").read_text());operation=baseline["operation"]
  operation={**operation,"job":"dungeon-cancel-acceptance-v1","payload":{**operation["payload"],"seed":43}}
  if not api("/api/session/deployment-guard")["data"].get("held"):raise ValueError("Expected held guard")
  api("/api/session/deployment-guard",{"action":"release","owner":owner})
  try:
   session=api("/api/session",{"agent":identity["agent"],"location":{"directory":identity["project"]},"title":"Owned native cancellation acceptance"})["data"]["id"]
   save(journal.name,{"session":session,"operation":operation})
   api("/api/session/"+session+"/prompt",{"text":"Call the directly exposed native watoom_specialist_run exactly once with this JSON, wait for the result, then stop. No other tools or Code Mode: "+json.dumps(operation)})
   started=time.monotonic();worker=None;operation_id=None
   while time.monotonic()-started<150:
    marker=out/"toolkit-state/job-active.json"
    if marker.exists():
     value=json.loads(marker.read_text());job=value["job_id"]
     pods=m.kub("get","pods","-l","watoom-job="+job)["items"]
     running=[x for x in pods if x["status"]["phase"]=="Running" and not x["metadata"].get("deletionTimestamp")]
     logfile=out/"toolkit-state/jobs"/job/"worker/unreal.log"
     if len(running)==1 and logfile.is_file() and logfile.stat().st_size>0:
      worker={"job_id":job,"pod_uid":running[0]["metadata"]["uid"],"kube_job":m.kub("get","job","watoom-3d-"+job)["metadata"]["uid"]}
      with sqlite3.connect("file:"+str(out/"state/application.sqlite")+"?mode=ro",uri=True) as db:
       row=db.execute("SELECT id,phase FROM _watoom_specialist_job WHERE job=?",(operation["job"],)).fetchone()
      if row and row[1]=="executing":operation_id=row[0];break
    if not api("/api/session/active")["data"]:raise ValueError("Cancellation fixture ended before an actual native worker started")
    time.sleep(1)
   if worker is None or operation_id is None:raise TimeoutError("No verified owned native worker; left existing operation untouched")
   save("native-cancel-before.json",{"session":session,"operation_id":operation_id,"worker":worker})
   api("/api/session/"+session+"/interrupt",{"resume":False})
   deadline=time.monotonic()+150
   while time.monotonic()<deadline:
    pods=m.kub("get","pods","-l","watoom-job="+worker["job_id"])["items"]
    if not api("/api/session/active")["data"] and not any(p["status"]["phase"] not in ("Succeeded","Failed") for p in pods):break
    time.sleep(1)
   else:raise TimeoutError("Owned cancellation cleanup not proven; do not force terminate or erase evidence")
   result_path=out/"toolkit-state/jobs"/worker["job_id"]/"result.json"
   receipt=json.loads(result_path.read_text())
   if receipt.get("status") not in ("FAIL","CANCELLED") or receipt.get("operation_id")!=operation_id:raise ValueError("Authoritative cancellation failure receipt missing")
   with sqlite3.connect("file:"+str(out/"state/application.sqlite")+"?mode=ro",uri=True) as db:
    phase=db.execute("SELECT phase FROM _watoom_specialist_job WHERE job=?",(operation["job"],)).fetchone()[0]
   if phase!="uncertain":raise ValueError("Interrupted external operation must remain quarantined from automatic replay")
   if not (out/"toolkit-state/jobs"/(".cancel-"+operation_id)).is_file():raise ValueError("Durable cancellation tombstone missing")
   manifest=out/"toolkit-state/jobs"/worker["job_id"]/"worker/artifacts/manifest.json"
   if manifest.exists():raise ValueError("Cancelled native fixture unexpectedly published success")
   save("native-cancel-acceptance.json",{"status":"PASS","session":session,"job":operation["job"],"worker":worker,"operation_id":operation_id,"toolkit_failure_receipt":str(result_path),"native_phase":phase,"replay_policy":"Quarantined; original ID is never replayed or deleted","no_success_publication":True,"owned_worker_stopped":True})
   print(json.dumps({"status":"PASS","cancelled_owned_worker":worker["job_id"],"native_phase":phase}),flush=True)
  finally:
   if api("/api/session/active")["data"]=={}:
    held=api("/api/session/deployment-guard",{"action":"acquire","owner":owner})["data"]
    if not held.get("held") or held.get("leases")!=0:raise ValueError("Could not close candidate admission")
  return
 if a.phase=="gui":
  accepted=json.loads((out/"native-api-acceptance.json").read_text());gui=out/"gui-native";gui.mkdir(mode=0o700)
  env={**os.environ,"PLAYWRIGHT_MODULE":"/data/ai/projects/llm/watoom-code/native-next-review-20261014T212958Z/source/node_modules/.bun/playwright@1.59.1/node_modules/playwright",
   "CANDIDATE_PASSWORD":m.password,"CANDIDATE_BASE":base,"EVIDENCE":str(gui),"CREATIVE_ROUTE_SESSION":accepted["session"],"CREATIVE_ARTIFACT_JOBS":json.dumps([accepted["toolkit_job"]])}
  with (gui/"runner.log").open("w") as log:subprocess.run(["node",str(pathlib.Path(__file__).with_name("agentmemory-browser.cjs"))],env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
  result=json.loads((gui/"creative-browser.json").read_text())
  if result["status"]!="PASS":raise ValueError("Actual authenticated native artifact GUI failed")
  print(json.dumps({"status":"PASS","gui":str(gui),"visual_review":"PENDING inspect screenshot pixels"}));return
 if api("/api/session/active")["data"]!={}:raise ValueError("Candidate already has active work; never terminate it")
 release_guard.durable_clearance(out/"state/application.sqlite")
 owner=(out/"guard-owner.private").read_text().strip()
 guard=api("/api/session/deployment-guard")["data"]
 if not guard.get("held"):raise ValueError("Expected held native admission guard")
 journal=out/"native-api-prompt.json"
 if journal.exists():raise ValueError("Inspect existing native admission; never submit twice")
 catalog=json.loads((evidence/"verified-dungeon-catalog.json").read_text())
 anchor=next(k for k,v in catalog["records"].items() if v.get("dungeon_adapter",{}).get("style")=="dungeon-builder")
 operation={"specialistID":"local-toolkit","capability":"world.compose","job":"dungeon-native-acceptance-"+a.case,"payload":{"task":"3d-creative","operation":"world","asset_id":anchor,"seed":42,"timeout":840,"dungeon":{"style":"dungeon-builder","rooms":4,"levels":2}}}
 api("/api/session/deployment-guard",{"action":"release","owner":owner})
 try:
  session=api("/api/session",{"agent":identity["agent"],"location":{"directory":identity["project"]},"title":"Owned native dungeon acceptance"})["data"]["id"]
  save(journal.name,{"status":"PREPARED","session":session,"operation":operation})
  api("/api/session/"+session+"/prompt",{"text":"Call the directly exposed native watoom_specialist_run function exactly once with this exact JSON, wait for the result, then stop. No Code Mode, other tools, skills or shell: "+json.dumps(operation)})
  deadline=time.monotonic()+1000;messages=None
  while time.monotonic()<deadline:
   if not api("/api/session/active")["data"] and api("/api/session/"+session)["data"].get("outcome") is not None:
    messages=api("/api/session/"+session+"/message");break
   time.sleep(2)
  if messages is None:raise TimeoutError("Owned native execution still active; left running, never terminated")
  save("native-api-messages.private.json",messages)
  calls=[item for item in walk(messages) if item.get("type")=="tool" and item.get("name")=="watoom_specialist_run"]
  if len(calls)!=1 or calls[0].get("state",{}).get("status")!="completed":raise ValueError("Native tool did not complete exactly once; inspect preserved messages")
  with sqlite3.connect("file:"+str(out/"state/application.sqlite")+"?mode=ro",uri=True) as db:
   row=db.execute("SELECT phase,outcome FROM _watoom_specialist_job WHERE job=?",(operation["job"],)).fetchone()
  if not row or row[0]!="completed":raise ValueError("Durable native job did not complete")
  outcome=json.loads(row[1]);artifacts=outcome["artifacts"]
  if len(artifacts)!=8:raise ValueError("Native artifact set incomplete")
  for item in artifacts:
   if not item["reference"].startswith("artifact:generated/watoom-toolkit-3d/v1/"):raise ValueError("Unexpected artifact root")
   path=out/"published"/item["reference"][9:]
   if not path.resolve().is_relative_to(out/"published") or path.is_symlink() or sha(path)!=item["sha256"] or path.stat().st_size!=item["bytes"]:raise ValueError("Native artifact hash mismatch")
  reference=next(item["reference"] for item in artifacts if item["reference"].endswith("/manifest.json"))
  manifest_path=out/"published"/reference[9:];manifest=json.loads(manifest_path.read_text())
  expected=json.loads((evidence/"verified-dungeon-catalog-acceptance.json").read_text())["native_public_preparation"]["dungeon-builder"]["plan_sha256"]
  if manifest["status"]!="PASS" or manifest["plan_sha256"]!=expected or manifest["inspection_candidate"] is not False:raise ValueError("Native public route did not reproduce accepted plan")
  fixture=pathlib.Path(json.loads((evidence/"builder-vertical-landing-candidate-acceptance.json").read_text())["directory"])/"artifacts/asset.glb"
  if sha(manifest_path.parent/"asset.glb")!=sha(fixture):raise ValueError("Same-seed regenerated GLB differs from independently accepted fixture; inspect before claiming determinism")
  toolkit_job=manifest["job_id"];receipt=json.loads((out/"toolkit-state/jobs"/toolkit_job/"result.json").read_text())
  if receipt["status"]!="PASS" or receipt["worker"]["image_id"].split("@")[-1]!=identity["toolkit_image"].split("@")[-1]:raise ValueError("Actual native worker did not run candidate image")
  result={"status":"PASS","session":session,"job":operation["job"],"toolkit_job":toolkit_job,"artifacts":artifacts,"manifest_sha256":sha(manifest_path),"plan_sha256":expected,"toolkit_image":identity["toolkit_image"],"image":identity["image"],"public_native_adapter_route":True,"deterministic_regeneration":"PASS byte-identical GLB from independent same-seed native runs"}
  save("native-api-acceptance.json",result);print(json.dumps({"status":"PASS","session":session,"toolkit_job":toolkit_job,"artifacts":len(artifacts)}),flush=True)
 finally:
  if api("/api/session/active")["data"]=={}:
   held=api("/api/session/deployment-guard",{"action":"acquire","owner":owner})["data"]
   if not held.get("held") or held.get("leases")!=0:raise ValueError("Could not hold idle candidate admission")
   release_guard.durable_clearance(out/"state/application.sqlite")
if __name__=="__main__":main()
