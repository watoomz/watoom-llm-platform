#!/usr/bin/env python3
"""One real model turn exercises compiled native checkpoints with an owned CPU MCP fixture."""
import argparse,json,pathlib,time
from maintenance_guard import Maintenance
p=argparse.ArgumentParser();p.add_argument("--evidence",required=True,type=pathlib.Path);a=p.parse_args();r=a.evidence
identity=json.loads((r/"candidate-identity.json").read_text())
assert identity["namespace"]=="watoom-code" and identity["name"].startswith("watoom-code-memory-candidate-")
m=Maintenance(identity["namespace"],identity["name"],r,True,True)
cm=m.kub("get","configmap",identity["name"])
assert "owned-mesh-checkpoint-fixture" in cm["data"]["mesh-fixture.py"]
request_id="owned-native-mesh-20261017"
session=m.request("/api/session",{"agent":"memory-fixture","location":{"directory":"/workspace"},"title":"Owned native Mesh checkpoint ordering acceptance"})["data"]
(r/"mesh-fixture-session.private.json").write_text(json.dumps(session))
args={"prompt":"Owned CPU checkpoint fixture cube","request_id":request_id}
prompt="Execute one owned CPU test: call the existing MCP watoom-llama-mesh generate tool exactly once, using Code Mode execute and its actual catalog path, with these exact arguments: "+json.dumps(args)+". This is a fake CPU fixture; no GPU backend exists in this candidate. After the result, reply with only FIXTURE_COMPLETE. Do not call shell, other tools, or create files."
m.request("/api/session/"+session["id"]+"/prompt",{"text":prompt})
query="""import sqlite3,json,sys
d=sqlite3.connect('file:/state/application.sqlite?mode=ro',uri=True)
print(json.dumps([json.loads(row[0]) for row in d.execute('SELECT body FROM _watoom_outbox WHERE body LIKE ?',('%'+sys.argv[1]+'%',))]))
"""
deadline=time.monotonic()+180
while time.monotonic()<deadline:
    rows=json.loads(m.exec(query,request_id))
    if any(json.loads(row["content"]).get("phase")=="PRIMARY_RESTORED" for row in rows):
        break
    time.sleep(2)
else:
    (r/"mesh-fixture-messages.private.json").write_text(json.dumps(m.request("/api/session/"+session["id"]+"/message")))
    raise RuntimeError("Compiled checkpoint fixture did not complete; inspect owned session, never retry under a new request ID")
phases={json.loads(row["content"])["phase"] for row in rows}
assert {"GPU_HANDOVER_PENDING","PRIMARY_RESTORED"}.issubset(phases)
assert len([row for row in rows if row["job"]=="gpu:"+session["id"]+":"+request_id])==2
marker=json.loads(m.exec("import pathlib;print(pathlib.Path('/workspace/owned-mesh-checkpoint-fixture.json').read_text())"))
assert marker=={"request_id":request_id,"pre_checkpoint_verified":True,"no_gpu_work":True}
(r/"mesh-fixture-checkpoints.private.json").write_text(json.dumps(rows,indent=2))
(r/"mesh-fixture-acceptance.json").write_text(json.dumps({"status":"PASS","image":identity["image"],"compiled_native_pre_before_effect":"PASS","compiled_native_post_restoration":"PASS","single_submission":"PASS","actual_gpu_work":False},indent=2))
print("PASS compiled native checkpoint ordering, existing Code Mode/MCP execution, and restoration receipt")
