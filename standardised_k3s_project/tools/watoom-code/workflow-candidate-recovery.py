#!/usr/bin/env python3
"""Owned candidate only: supported interruption, durable queued input, restart, resume, compaction."""
import argparse,copy,json,os,pathlib,subprocess,time
from maintenance_guard import Maintenance
import release_guard
p=argparse.ArgumentParser();p.add_argument("--evidence",required=True,type=pathlib.Path);a=p.parse_args();r=a.evidence
identity=json.loads((r/"candidate-identity.json").read_text());ns=identity["namespace"];name=identity["name"]
assert ns=="watoom-code" and name.startswith("watoom-code-memory-candidate-")
m=Maintenance(ns,name,r,True,True)
baseline=m.kub("get","deploy",name)
assert baseline["metadata"]["labels"].get("watoom-test-owner")=="agentmemory-unblock-20261016T204420Z"
release_guard.active_clear(m.request("/api/session/active"))
session=json.loads((r/"workflow-session.private.json").read_text()) if (r/"workflow-session.private.json").exists() else m.request("/api/session",{"agent":"memory-fixture","location":{"directory":"/workspace"},"title":"Owned workflow interruption restart and compaction"})["data"];sid=session["id"]
(r/"workflow-session.private.json").write_text(json.dumps(session,indent=2))
def wait(predicate,seconds=90):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        value=predicate()
        if value:return value
        time.sleep(.25)
    raise RuntimeError("Owned workflow assertion deadline reached; inspect persisted session")
def messages():return m.request("/api/session/"+sid+"/message")["data"]
def idle():return m.request("/api/session/active")["data"]=={} and m.request("/api/session/deployment-guard")["data"]["leases"]==0
fact="Owned workflow durable recovery marker echidna-20261017"
query="""import sqlite3,json,sys
d=sqlite3.connect('file:/state/application.sqlite?mode=ro',uri=True)
print(json.dumps([json.loads(row[0]) for row in d.execute('SELECT body FROM _watoom_outbox WHERE body LIKE ?',('%'+sys.argv[1]+'%',))]))
"""
def checkpoints():return json.loads(m.exec(query,sid))
def detail(row):
    try:return json.loads(row["content"])
    except (ValueError,TypeError):return {}
if not any(detail(row).get("event")=="session.execution.interrupted" for row in checkpoints()):
    m.request("/api/session/"+sid+"/command",{"name":"remember","text":fact})
    m.request("/api/session/"+sid+"/prompt",{"id":"msg_owned_interruption_20261017","text":"Reply with the integers from one to one thousand, one per line. Do not use tools."})
    wait(lambda:sid in m.request("/api/session/active")["data"])
    result=m.request("/api/session/"+sid+"/interrupt",{})
    assert result["interrupted"] is True
    wait(idle)
assert any(detail(row).get("event")=="session.execution.interrupted" for row in checkpoints())
queued={"id":"msg_owned_restart_resume_20261017","text":"Reply with only RECOVERY_RESUMED. Do not use tools.","resume":False}
m.request("/api/session/"+sid+"/prompt",queued)
pending=m.request("/api/session/"+sid+"/inbox")["data"]
assert len(pending)==1 and pending[0]["id"]==queued["id"]
def clearance():
    release_guard.active_clear(m.request("/api/session/active"))
    # Intentional isolated restart fixture: only this explicitly owned parked input may remain.
    assert [x["id"] for x in m.request("/api/session/"+sid+"/inbox")["data"]]==[queued["id"]]
def save(owner):
    with (r/"workflow-restart-owner.private").open("w") as f:f.write(owner);f.flush();os.fsync(f.fileno())
owner=release_guard.acquire(m.request,m.request,save,clearance)
replacement=copy.deepcopy(baseline);replacement.pop("status",None)
replacement["metadata"]={k:replacement["metadata"][k] for k in ["name","namespace","labels"]}
replacement["spec"]["template"]["metadata"].setdefault("annotations",{})["watoom-acceptance/restart"]=str(time.time_ns())
try:
    subprocess.run(["kubectl","apply","-f","-"],input=json.dumps(replacement).encode(),check=True,capture_output=True)
    subprocess.run(["kubectl","-n",ns,"rollout","status","deploy/"+name,"--timeout=120s"],check=True,capture_output=True)
    wait(lambda:m.request("/api/session/deployment-guard")["data"]["held"])
    actual=next(c["imageID"] for c in m.pod()["status"]["containerStatuses"] if c["name"]=="app")
    assert actual.endswith(identity["image"].split("@")[1])
    assert m.request("/api/session/"+sid+"/inbox")["data"]==pending
    release_guard.active_clear(m.request("/api/session/active"))
finally:
    release_guard.release(m.request,m.request,owner)
# Same durable input ID can be retried after restart without duplication; resume is a scheduling flag.
m.request("/api/session/"+sid+"/prompt",queued)
assert len(m.request("/api/session/"+sid+"/inbox")["data"])==1
m.request("/api/session/"+sid+"/prompt",{**queued,"resume":True})
wait(lambda:any(x.get("type")=="assistant" and "RECOVERY_RESUMED" in json.dumps(x) for x in messages()))
wait(idle)
assert len([x for x in messages() if x["id"]==queued["id"]])==1
assert not m.request("/api/session/"+sid+"/inbox")["data"]
m.request("/api/session/"+sid+"/command",{"name":"recall","text":"echidna-20261017"})
assert fact in json.dumps(messages())
m.request("/api/session/"+sid+"/compact",{"id":"msg_owned_compaction_20261017"})
compacted=wait(lambda:next((x for x in messages() if x["id"]=="msg_owned_compaction_20261017" and x.get("status") in ("completed","failed")),None),180)
(r/"workflow-compaction.private.json").write_text(json.dumps(compacted,indent=2))
if compacted["status"]!="completed":raise RuntimeError("Real compaction did not complete; inspect owned compaction evidence")
wait(idle)
# Verify the retained recent turn and scoped memory in real inference after compaction.
m.request("/api/session/"+sid+"/prompt",{"id":"msg_owned_post_compaction_20261017","text":"After compaction, reply with the last completed assistant response and the durable recovery marker available in this session's verified memory. Do not resume the cancelled counting task. Do not use tools."})
def recovered_context():
    for message in messages():
        if message.get("type")!="assistant":continue
        text=" ".join(part.get("text","") for part in message.get("content",[]) if part.get("type")=="text")
        if "RECOVERY_RESUMED" in text and "echidna-20261017" in text:return message
    return None
recovered=wait(recovered_context)
wait(idle)
(r/"workflow-post-compaction.private.json").write_text(json.dumps(recovered,indent=2))
rows=checkpoints()
assert any(row["kind"]=="compaction" and detail(row).get("references") for row in rows)
(r/"workflow-checkpoints.private.json").write_text(json.dumps(rows,indent=2))
(r/"workflow-runtime-acceptance.json").write_text(json.dumps({"status":"PASS","image":identity["image"],"supported_owned_interruption":"PASS","interruption_checkpoint":"PASS","parked_input_survives_restart":"PASS","same_id_deduplication":"PASS","explicit_safe_resumption":"PASS","scoped_recall_after_restart":"PASS","real_compaction":"PASS","pre_compaction_references":"PASS","post_compaction_context_recovery":"PASS","user_sessions_interrupted":0},indent=2))
print("PASS owned interruption, durable queued restart, exactly-once resume, scoped recall and real compaction")
