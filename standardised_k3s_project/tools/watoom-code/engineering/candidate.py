#!/usr/bin/env python3
"""Isolated exact-image engineering acceptance and independently exercised rollback."""
import argparse,copy,hashlib,json,os,pathlib,secrets,shutil,sqlite3,subprocess,sys,time,urllib.error,re
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from maintenance_guard import Maintenance
import release_guard
p=argparse.ArgumentParser();p.add_argument("--evidence",type=pathlib.Path,required=True);p.add_argument("--resume",action="store_true");p.add_argument("--name",default="watoom-code-engineering-candidate");a=p.parse_args()
if not re.fullmatch(r"watoom-code-[a-z0-9-]{1,40}",a.name):raise ValueError("Owned candidate name required")
root=a.evidence.resolve();build=json.loads((root/"build.json").read_text())
if a.resume:
    out=root/"candidate";name=a.name;ns="watoom-code"
    def cmd(args,data=None):return subprocess.check_output(args,input=data,timeout=180)
    m=Maintenance(ns,name,out,True,True)
    if m.kub("get","deploy",name)["metadata"].get("labels",{}).get("watoom-test-owner")!=root.name:raise RuntimeError("Candidate ownership mismatch")
    receipt=json.loads((out/"resume.json").read_text())
    session=receipt["session"];directory=receipt["directory"];fact=receipt["fact"]
    owner=(out/"guard-owner.private").read_text()
    def wait(image,held):
        deadline=time.monotonic()+180
        while True:
            try:
                c=next(c for c in m.pod()["status"]["containerStatuses"] if c["name"]=="app")
                assert c["ready"] and c["imageID"].endswith(image.split("@")[1])
                assert isinstance(m.request("/api/info")["version"],str)
                release_guard.validate(m.request("/api/session/deployment-guard"),held)
                release_guard.active_clear(m.request("/api/session/active"));return
            except Exception:
                if time.monotonic()>deadline:raise
                time.sleep(2)
else:
    out=root/"candidate";out.mkdir(mode=0o755)
    name=a.name;ns="watoom-code"
    def cmd(args,data=None):return subprocess.check_output(args,input=data,timeout=180)
    for kind in ["deployment","service"]:
        if cmd(["kubectl","-n",ns,"get",kind,name,"--ignore-not-found","-o","json"]).strip():raise RuntimeError("Candidate name already exists; inspect its owner before reuse")
    live=json.loads(cmd(["kubectl","-n",ns,"get","deploy","watoom-code","-o","json"]))
    for folder in ["home","workspace","state","generated"]:
        d=out/folder;d.mkdir(mode=0o750);os.chown(d,1001,1009)
    shutil.copytree("/data/ai/watoom-code/config",out/"config")
    # Copy skill bytes without interpreting sensitive owner content.
    for d in [out/"config",*(out/"config").rglob("*")]:
        if not d.is_symlink():os.chown(d,1001,1009)
    source=pathlib.Path("/data/ai/watoom-code/catalog.sqlite")
    if source.exists():
        release_guard.snapshot_database(source,out/"state/catalog.sqlite")
        os.chown(out/"state/catalog.sqlite",1001,1009)
    deployment=copy.deepcopy(live);deployment.pop("status",None)
    deployment["metadata"]={"name":name,"namespace":ns,"labels":{"app":name,"watoom-test-owner":root.name}}
    deployment["spec"]["replicas"]=1
    deployment["spec"]["selector"]={"matchLabels":{"app":name}}
    deployment["spec"]["template"]["metadata"]={"labels":{"app":name,"watoom-test-owner":root.name}}
    spec=deployment["spec"]["template"]["spec"];spec["automountServiceAccountToken"]=False
    container=next(c for c in spec["containers"] if c["name"]=="app")
    container["image"]=build["image"]
    container["resources"]={"requests":{"cpu":"100m","memory":"256Mi"},"limits":{"cpu":"2","memory":"2Gi"}}
    for volume in spec["volumes"]:
        if volume["name"] in ["home","config","workspace","state","generated"]:
            volume["hostPath"]={"path":str(out/volume["name"]),"type":"Directory"}
    for mount in container["volumeMounts"]:
        if mount["name"] not in ["home","workspace","state","generated"]:mount["readOnly"]=True
    service={"apiVersion":"v1","kind":"Service","metadata":{"name":name,"namespace":ns,"labels":{"watoom-test-owner":root.name}},"spec":{"selector":{"app":name},"ports":[{"port":4096,"targetPort":4096}]}}
    (out/"deployment.private.json").write_text(json.dumps(deployment));(out/"deployment.private.json").chmod(0o600)
    cmd(["kubectl","apply","-f","-"],json.dumps({"apiVersion":"v1","kind":"List","items":[deployment,service]}).encode())
    m=Maintenance(ns,name,out,True,True)
    def wait(image,held):
        deadline=time.monotonic()+180
        while True:
            try:
                pod=m.pod();c=next(c for c in pod["status"]["containerStatuses"] if c["name"]=="app")
                assert c["ready"] and c["imageID"].endswith(image.split("@")[1])
                assert isinstance(m.request("/api/info")["version"],str)
                release_guard.validate(m.request("/api/session/deployment-guard"),held)
                release_guard.active_clear(m.request("/api/session/active"))
                return
            except Exception:
                if time.monotonic()>deadline:raise
                time.sleep(2)
    wait(build["image"],False)
    assert m.exec("import subprocess;subprocess.run(['python3','/opt/watoom-engineering/smoke.py'],check=True,timeout=90)") is not None
    directory="/workspace/engineering-"+root.name
    m.exec("import pathlib,subprocess,sys;p=pathlib.Path(sys.argv[1]);p.mkdir();subprocess.run(['git','-C',str(p),'init','-q'],check=True);subprocess.run(['git','-C',str(p),'-c','user.name=Acceptance','-c','user.email=fixture@invalid','commit','--allow-empty','-qm','owned engineering fixture'],check=True)",directory)
    session=m.request("/api/session",{"location":{"directory":directory},"title":"Owned engineering acceptance"})["data"]["id"]
    fact="Owned engineering durability "+root.name
    for command in ["remember","recall"]:m.request("/api/session/"+session+"/command",{"name":command,"text":fact})
    assert fact in json.dumps(m.request("/api/session/"+session+"/message"))
    owner=secrets.token_hex(32)
    (out/"guard-owner.private").write_text(owner);(out/"guard-owner.private").chmod(0o600)
    release_guard.validate(m.request("/api/session/deployment-guard",{"action":"acquire","owner":owner}),True)
    try:
        m.request("/api/session/deployment-guard",{"action":"acquire","owner":secrets.token_hex(32)})
    except urllib.error.HTTPError as error:assert error.code in (409,423,503)
    else:raise AssertionError("Concurrent owner admitted")
    try:
        m.request("/api/session/"+session+"/prompt",{"text":"OWNED_FENCE_PROBE_MUST_NOT_RUN"})
    except urllib.error.HTTPError as error:assert error.code in (409,423,500,503)
    else:raise AssertionError("New execution admitted under deployment fence")
    (out/"resume.json").write_text(json.dumps({"session":session,"directory":directory,"fact":fact}))
# Prove the same no-inference command works when open and is refused when held.
release_guard.release(m.request,lambda path,body:m.request(path,body),owner)
m.request("/api/session/"+session+"/command",{"name":"recall","text":fact})
release_guard.validate(m.request("/api/session/deployment-guard",{"action":"acquire","owner":owner}),True)
before=m.request("/api/session/"+session+"/message")
try:m.request("/api/session/"+session+"/command",{"name":"recall","text":fact})
except urllib.error.HTTPError as error:assert error.code in (409,423,500,503)
else:raise AssertionError("Command admitted under fence")
assert m.request("/api/session/"+session+"/message")==before
release_guard.validate(m.request("/api/session/deployment-guard"),True)
release_guard.active_clear(m.request("/api/session/active"))
def switch(image):
    release_guard.active_clear(m.request("/api/session/active"))
    release_guard.validate(m.request("/api/session/deployment-guard"),True)
    cmd(["kubectl","-n",ns,"set","image","deploy/"+name,"app="+image])
    wait(image,True)
    assert fact in json.dumps(m.request("/api/session/"+session+"/message"))
    assert sqlite3.connect("file:"+str(out/"state/application.sqlite")+"?mode=ro",uri=True).execute("pragma integrity_check").fetchone()==("ok",)
baseline=build["runtime_image"]
switch(baseline)
switch(build["image"])
try:raise ValueError("OWNED_INJECTED_VALIDATION_FAILURE")
except ValueError:switch(baseline)
switch(build["image"])
base="http://"+m.kub("get","svc",name)["spec"]["clusterIP"]+":4096"
gui=out/("gui-"+str(time.time_ns()) if (out/"gui").exists() else "gui");gui.mkdir()
env={**os.environ,"PLAYWRIGHT_MODULE":"/data/ai/projects/llm/watoom-code/native-next-review-20261014T212958Z/source/node_modules/.bun/playwright@1.59.1/node_modules/playwright","CANDIDATE_PASSWORD":m.password,"CANDIDATE_BASE":base,"EVIDENCE":str(gui),"MEMORY_ROUTE_SESSION":session,"MEMORY_GUI_FACT":fact}
with (gui/"runner.log").open("w") as log:
    subprocess.run(["node",str(pathlib.Path(__file__).resolve().parents[1]/"agentmemory-browser.cjs")],env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=100)
try:m.request("/api/info",authenticated=False)
except urllib.error.HTTPError as error:assert error.code==401
else:raise AssertionError("Anonymous API admitted")
report={key:"PASS" for key in ["guard_boot","guard_race","rollback","authenticated_api","authenticated_gui","memory","engineering_tools"]}
report.update(status="PASS",image=build["image"],acceptance_root=str(out),source_commit=build["source_commit"],application_binary_sha256=build["inputs"]["opencode"])
(root/"candidate-acceptance.json").write_text(json.dumps(report,indent=2))
# Retain candidate state and held guard for review; stop only this proven idle candidate.
release_guard.active_clear(m.request("/api/session/active"))
cmd(["kubectl","-n",ns,"scale","deploy/"+name,"--replicas=0"])
print(json.dumps(report),flush=True)
