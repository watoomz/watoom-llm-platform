#!/usr/bin/env python3
"""Authenticated, no-inference acceptance and fault injection on the owned candidate only."""
import argparse,pathlib,json,subprocess,urllib.request,urllib.error,base64,time,copy,concurrent.futures,os
import release_guard
ap=argparse.ArgumentParser();ap.add_argument("--evidence",required=True,type=pathlib.Path);a=ap.parse_args();r=a.evidence
identity=json.loads((r/"candidate-identity.json").read_text());ns=identity["namespace"];name=identity["name"]
if ns!="watoom-code" or not name.startswith("watoom-code-memory-candidate-"):raise RuntimeError("Owned candidate required")
def cmd(args,input=None,timeout=40):return subprocess.check_output(args,input=input,timeout=timeout,stderr=subprocess.PIPE)
def kub(*args):return json.loads(cmd(["kubectl","-n",ns,*args,"-o","json"]))
baseline=kub("get","deploy",name)
if baseline["metadata"]["labels"].get("watoom-test-owner")!="agentmemory-unblock-20261016T204420Z":raise RuntimeError("Candidate ownership mismatch")
(r/"candidate-before-faults.private.json").write_text(json.dumps(baseline,indent=2))
password=(r/"candidate-password.private").read_text();auth="Basic "+base64.b64encode(("opencode:"+password).encode()).decode()
def endpoint():
    pods=kub("get","pods","-l","app="+name)["items"]
    ready=[x for x in pods if not x["metadata"].get("deletionTimestamp") and all(c.get("ready") for c in x.get("status",{}).get("containerStatuses",[])) and x.get("status",{}).get("podIP")]
    if len(ready)!=1:raise RuntimeError("Candidate not uniquely running")
    if not any(c.get("imageID","").endswith(identity["image"].split("@")[1]) for c in ready[0]["status"]["containerStatuses"]):raise RuntimeError("Candidate digest mismatch")
    return "http://"+ready[0]["status"]["podIP"]+":4096"
def request(path,body=None,method=None):
    req=urllib.request.Request(endpoint()+path,headers={"Authorization":auth,"Content-Type":"application/json"},data=json.dumps(body).encode() if body is not None else None,method=method)
    with urllib.request.urlopen(req,timeout=20) as response:
        raw=response.read();return json.loads(raw) if raw else None
def state():
    code="import sqlite3,json;d=sqlite3.connect('file:/state/application.sqlite?mode=ro',uri=True);print(json.dumps({'pending':d.execute('select count(*) from session_inbox').fetchone()[0],'claims':d.execute('select count(*) from session_v2 where time_suspended is not null').fetchone()[0],'outbox':d.execute('select id,state,attempts,body,receipt from _watoom_outbox').fetchall()}))"
    return json.loads(cmd(["kubectl","-n",ns,"exec","deploy/"+name,"-c","app","--","python3","-c",code]))
def clearance():
    release_guard.active_clear(request("/api/session/active"))
    v=state()
    if v["pending"] or v["claims"]:raise RuntimeError("Candidate work not idle")
def apply(deployment):
    d=copy.deepcopy(deployment);d.pop("status",None)
    d["metadata"]={k:d["metadata"][k] for k in ["name","namespace","labels"] if k in d["metadata"]}
    cmd(["kubectl","apply","-f","-"],input=json.dumps(d).encode())
    cmd(["kubectl","-n",ns,"rollout","status","deploy/"+name,"--timeout=90s"],timeout=100)
def validate():
    for i in range(30):
        try:
            release_guard.runtime(request,identity["image"],identity["image"]);return
        except (RuntimeError,urllib.error.URLError):time.sleep(.25)
    raise RuntimeError("Authenticated guarded candidate readiness failed")
def acquire(phase):
    def save(owner):
        with (r/("candidate-"+phase+"-owner.private")).open("w") as f:f.write(owner);f.flush();os.fsync(f.fileno())
    return release_guard.acquire(request,request,save,clearance)
summary={"image":identity["image"],"authenticated_api":"PASS"}
history=json.loads((r/"candidate-test-sessions.private.json").read_text()) if (r/"candidate-test-sessions.private.json").exists() else []
for attempt in range(40):
    commands=request("/api/command?directory=/workspace")
    if {"remember","recall"}.issubset({item["name"] for item in commands["data"]}):break
    time.sleep(.25)
else:raise RuntimeError("Candidate command registry did not activate")
sessions=[request("/api/session",{"agent":"memory-fixture","location":{"directory":"/workspace"},"title":title}) for title in ("Owned memory write fixture","Owned separate-session recall fixture")]
first=sessions[0]["data"]["id"];second=sessions[1]["data"]["id"]
fact="WatooM isolated acceptance 20261016T204420Z: platypus observatory marker 9c17"
request("/api/session/"+first+"/command",{"name":"remember","text":fact})
request("/api/session/"+second+"/command",{"name":"recall","text":"platypus observatory marker 9c17"})
assert fact in json.dumps(request("/api/session/"+second+"/message"))
summary["explicit_cross_session"]="PASS"
# Distinct Git root proves project isolation, without any model request.
code="import pathlib,subprocess;p=pathlib.Path('/workspace/other-project');p.mkdir(exist_ok=True);subprocess.run(['git','init','-q',str(p)],check=True);subprocess.run(['git','-C',str(p),'-c','user.name=MemoryFixture','-c','user.email=fixture@invalid','commit','--allow-empty','-qm','distinct-other-project'],check=True)"
cmd(["kubectl","-n",ns,"exec","deploy/"+name,"-c","app","--","python3","-c",code])
other=request("/api/session",{"agent":"memory-fixture","location":{"directory":"/workspace/other-project"},"title":"Other isolated project"})
assert other["data"]["projectID"]!=sessions[0]["data"]["projectID"]
sessions.append(other)
request("/api/session/"+other["data"]["id"]+"/command",{"name":"recall","text":"platypus observatory marker 9c17"})
assert fact not in json.dumps(request("/api/session/"+other["data"]["id"]+"/message"))
summary["project_isolation"]="PASS"
denied=request("/api/session",{"agent":"memory-fixture","location":{"directory":"/workspace"},"permissions":[{"action":"watoom_memory_remember","resource":"*","effect":"deny"}]})
sessions.append(denied);(r/"candidate-test-sessions.private.json").write_text(json.dumps(history+sessions,indent=2))
before=len(state()["outbox"])
for session,text in [(denied["data"]["id"],"denied fixture write"),(first,"password=fixture-not-a-real-secret")]:
    try:request("/api/session/"+session+"/command",{"name":"remember","text":text});raise RuntimeError("Expected rejection")
    except urllib.error.HTTPError as error:
        assert error.code==500
        assert "CommandExecutionError" in error.read().decode()
assert len(state()["outbox"])==before
summary["authorization_and_secret_rejection"]="PASS"
# A live owned shell is invisible to execution.active, but holds a native work lease.
with concurrent.futures.ThreadPoolExecutor(1) as pool:
    pending=pool.submit(request,"/api/session/"+first+"/shell",{"command":"python3 -c 'import time;time.sleep(2)' "})
    for i in range(40):
        if request("/api/session/deployment-guard")["data"]["leases"]>0:break
        time.sleep(.025)
    else:raise RuntimeError("Shell admission lease missing")
    try:request("/api/session/deployment-guard",{"action":"acquire","owner":"f"*64});raise RuntimeError("Active work incorrectly fenced")
    except urllib.error.HTTPError as error:assert error.code==409
    pending.result()
# Session.shell intentionally queues an admit-only notification. Cancel only these
# fixture-owned synthetic rows through the native inbox operation; never consume them
# with a model or edit the database to bypass clearance.
for item in request("/api/session/"+first+"/inbox")["data"]:
    if item["type"]!="synthetic":raise RuntimeError("Unexpected candidate pending work")
    request("/api/session/"+first+"/inbox/"+item["id"],method="DELETE")
summary["guard_race"]="PASS";print("PASS candidate auth, isolation, admission race",flush=True)
# Failed candidate configuration is restored while the durable fence survives both replacements.
owner=acquire("rollback")
before=len(state()["outbox"])
try:request("/api/session/"+first+"/command",{"name":"remember","text":"must-not-write-under-fence"});raise RuntimeError("Guard admitted work")
except urllib.error.HTTPError as error:assert error.code in (400,409,500,503)
assert len(state()["outbox"])==before
failed=copy.deepcopy(baseline)
env=failed["spec"]["template"]["spec"]["containers"][0]["env"]
env[:]=[x for x in env if x["name"]!="OPENCODE_PASSWORD"]+[{"name":"OPENCODE_PASSWORD","value":"deliberately-invalid-fixture-password"}]
try:
    apply(failed)
    try:request("/api/info");raise RuntimeError("Fault injection did not fail auth")
    except urllib.error.HTTPError as error:assert error.code==401
finally:
    apply(baseline)
validate()
summary["guard_boot"]="PASS";summary["rollback"]="PASS"
release_guard.release(request,request,owner)
request("/api/session/"+second+"/command",{"name":"recall","text":"platypus observatory marker 9c17"})
assert fact in json.dumps(request("/api/session/"+second+"/message"))
summary["restart_recovery"]="PASS";print("PASS candidate rollback and restart persistence",flush=True)
# Memory outage preserves a committed local fact; uncertain delivery is never blindly replayed.
owner=acquire("outage")
offline=copy.deepcopy(baseline);env=offline["spec"]["template"]["spec"]["containers"][0]["env"]
for entry in env:
    if entry["name"]=="AGENTMEMORY_URL":entry["value"]="http://127.0.0.1:1"
try:
    apply(offline);validate();release_guard.release(request,request,owner)
    request("/api/session/"+first+"/command",{"name":"remember","text":"outage-owned-fact-20261016T204420Z"})
    assert any(row[1]=="uncertain" and "outage-owned-fact" in row[3] for row in state()["outbox"])
    owner=acquire("outage-restore")
finally:
    # The only candidate fault is restored even if an assertion fails.
    apply(baseline)
validate();release_guard.release(request,request,owner)
rows=state()["outbox"]
assert any(row[1]=="uncertain" and row[2]==1 and "outage-owned-fact" in row[3] and json.loads(row[3])["job"].startswith("explicit:"+first+":") for row in rows)
request("/api/session/"+first+"/command",{"name":"remember","text":fact})
assert len([row for row in state()["outbox"] if json.loads(row[3])["content"]==fact and json.loads(row[3])["job"].startswith("explicit:"+first+":")])==1
summary["memory_outage_and_dedup"]="PASS";summary["memory"]="PASS"
(r/"candidate-runtime-acceptance.json").write_text(json.dumps(summary,indent=2))
print(json.dumps(summary),flush=True)
