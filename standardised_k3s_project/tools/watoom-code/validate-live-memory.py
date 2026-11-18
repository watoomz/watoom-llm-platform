#!/usr/bin/env python3
"""Bounded authenticated API/GUI smoke test in a newly owned Git project; no inference."""
import argparse,pathlib,json,subprocess,os,socket,time,base64,urllib.request,uuid
from maintenance_guard import Maintenance,run
from release_guard import active_clear
ap=argparse.ArgumentParser()
ap.add_argument("--namespace",default="watoom-code");ap.add_argument("--deployment",required=True);ap.add_argument("--evidence",type=pathlib.Path,required=True);ap.add_argument("--playwright-module",required=True)
a=ap.parse_args();a.evidence.mkdir(parents=True,exist_ok=True)
m=Maintenance(a.namespace,a.deployment,a.evidence,True,True)
uid=uuid.uuid4().hex;directory="/workspace/.watoom-validation/agentmemory-"+uid
code="""import pathlib,subprocess,sys
p=pathlib.Path(sys.argv[1])
p.mkdir(parents=True,exist_ok=False)
subprocess.run(["git","-C",str(p),"init","-q"],check=True)
subprocess.run(["git","-C",str(p),"-c","user.name=MemoryValidation","-c","user.email=fixture@invalid","commit","--allow-empty","-qm","owned-memory-validation"],check=True)
"""
m.exec(code,directory)
sessions=[]
for title in ["Owned live memory write fixture","Owned live memory separate recall fixture"]:
 sessions.append(m.request("/api/session",{"location":{"directory":directory},"title":title})["data"])
(a.evidence/"owned-live-sessions.private.json").write_text(json.dumps(sessions,indent=2))
first,second=[s["id"] for s in sessions];project=sessions[0]["projectID"]
fact="Owned release validation "+uid+" observatory marker"
m.request("/api/session/"+first+"/command",{"name":"remember","text":fact})
m.request("/api/session/"+second+"/command",{"name":"recall","text":uid})
assert fact in json.dumps(m.request("/api/session/"+second+"/message"))
# Use one explicitly owned administrative tunnel, close it before release clearance.
sock=socket.socket();sock.bind(("127.0.0.1",0));port=sock.getsockname()[1];sock.close()
pod=m.pod()["metadata"]["name"]
with (a.evidence/"owned-gui-forward.log").open("wb") as log:
 forward=subprocess.Popen(["kubectl","-n",a.namespace,"port-forward","--address=127.0.0.1","pod/"+pod,str(port)+":4096"],stdout=log,stderr=log)
 try:
  for i in range(50):
   try:
    with socket.create_connection(("127.0.0.1",port),.2):break
   except OSError:time.sleep(.1)
  else:raise RuntimeError("Owned GUI forward did not start")
  env={**os.environ,"PLAYWRIGHT_MODULE":a.playwright_module,"CANDIDATE_PASSWORD":m.password,"CANDIDATE_BASE":"http://127.0.0.1:"+str(port),"EVIDENCE":str(a.evidence),"MEMORY_PROJECT_DIRECTORY":directory,"MEMORY_GUI_FACT":"Owned GUI release validation "+uid}
  result=subprocess.run(["node",str(pathlib.Path(__file__).with_name("agentmemory-browser.cjs"))],env=env,capture_output=True,text=True,timeout=150)
  (a.evidence/"live-browser.log").write_text(result.stdout+result.stderr)
  if result.returncode:raise RuntimeError("Authenticated visible GUI validation failed; private evidence retained")
  browser=json.loads((a.evidence/"candidate-browser.json").read_text())
  assert browser["authenticated_gui"]=="PASS"
  sessions.append({"id":browser["sessionID"],"projectID":project})
 finally:
  forward.terminate()
  try:forward.wait(timeout=10)
  except subprocess.TimeoutExpired:forward.kill();forward.wait()
(a.evidence/"owned-live-sessions.private.json").write_text(json.dumps(sessions,indent=2))
# Back up receipts/messages before deleting only test-owned remote records.
ids=[s["id"] for s in sessions]
query="""import sqlite3,json,sys
d=sqlite3.connect("file:/state/application.sqlite?mode=ro",uri=True)
sessions=json.loads(sys.argv[1])
print(json.dumps([row for row in d.execute("select id,state,body,receipt from _watoom_outbox") if any(json.loads(row[2])["job"].startswith("explicit:"+s+":") for s in sessions)]))
"""
rows=json.loads(m.exec(query,json.dumps(ids)))
(a.evidence/"owned-live-outbox.private.json").write_text(json.dumps(rows,indent=2))
assert len(rows)==2 and all(x[1]=="observed" for x in rows)
secret=m.kub("get","secret","watoom-code-auth")["data"]
service=m.kub("get","svc","agentmemory")
url="http://"+service["spec"]["clusterIP"]+":"+str(service["spec"]["ports"][0]["port"])
auth="Bearer "+base64.b64decode(secret["AGENTMEMORY_SECRET"]).decode()
def memory(path,body=None):
 req=urllib.request.Request(url+path,headers={"Authorization":auth,"Content-Type":"application/json"},data=None if body is None else json.dumps(body).encode())
 with urllib.request.urlopen(req,timeout=15) as response:return json.load(response)
before=memory("/agentmemory/export");(a.evidence/"memory-before-cleanup.private.json").write_text(json.dumps(before))
removed=set()
for _,state,body,receipt in rows:
 event=json.loads(body);receipt=json.loads(receipt)
 assert event["scope"]["project"]==project and event["scope"]["repository"]==directory
 record=next(x for x in before["memories"] if x["id"]==receipt["memoryId"])
 assert record["content"]==body and record["project"]==project
 assert receipt["scope"]==event["scope"] and receipt["digest"]==event["digest"]
 memory("/agentmemory/forget",{"memoryId":receipt["memoryId"]});removed.add(receipt["memoryId"])
after=memory("/agentmemory/export")
assert {x["id"] for x in before["memories"]}-{x["id"] for x in after["memories"]}==removed
active_clear(m.request("/api/session/active"))
receipt={"status":"PASS","authenticated_api":"PASS","authenticated_gui":"PASS","cross_session_memory":"PASS","receipt_scope":"PASS","owned_record_cleanup":"PASS","directory":directory,"sessions":ids,"inference_requests":0}
(a.evidence/"live-memory-validation.json").write_text(json.dumps(receipt,indent=2))
print(json.dumps({"status":"PASS","test_owned_memory_records_removed":len(removed),"inference_requests":0}))
