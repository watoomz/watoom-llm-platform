#!/usr/bin/env python3
"""Prepare one owned memory fixture, then validate the published GUI under admission fencing."""
import argparse,base64,hashlib,json,os,pathlib,ssl,subprocess,urllib.request,uuid
from maintenance_guard import Maintenance
import release_guard
p=argparse.ArgumentParser();p.add_argument("--evidence",required=True,type=pathlib.Path);p.add_argument("--fixture",type=pathlib.Path);p.add_argument("--prepare",action="store_true");a=p.parse_args()
a.evidence.mkdir(parents=True,exist_ok=True)
m=Maintenance("watoom-code","watoom-code",a.evidence,True,True)
if a.prepare:
    release_guard.validate(m.request("/api/session/deployment-guard"),False)
    token=uuid.uuid4().hex;directory="/workspace/.watoom-validation/release-"+token
    code="import pathlib,subprocess,sys;p=pathlib.Path(sys.argv[1]);p.mkdir(parents=True,exist_ok=False);subprocess.run(['git','-C',str(p),'init','-q'],check=True);subprocess.run(['git','-C',str(p),'-c','user.name=ReleaseValidation','-c','user.email=fixture@invalid','commit','--allow-empty','-qm','owned-release-fixture'],check=True)"
    m.exec(code,directory)
    session=m.request("/api/session",{"location":{"directory":directory},"title":"Owned fenced release GUI fixture"})["data"]
    fact="Owned fenced release validation "+token
    m.request("/api/session/"+session["id"]+"/command",{"name":"remember","text":fact})
    m.request("/api/session/"+session["id"]+"/command",{"name":"recall","text":token})
    assert fact in json.dumps(m.request("/api/session/"+session["id"]+"/message"))
    (a.evidence/"native-gui-fixture.json").write_text(json.dumps({"session":session["id"],"directory":directory,"fact":fact},indent=2))
    print("PASS owned no-inference release fixture prepared")
else:
    if not a.fixture:raise RuntimeError("Owned fixture required")
    fixture=json.loads(a.fixture.read_text())
    assert fixture["directory"].startswith("/workspace/.watoom-validation/release-")
    release_guard.validate(m.request("/api/session/deployment-guard"),True)
    assert fixture["fact"] in json.dumps(m.request("/api/session/"+fixture["session"]+"/message"))
    tls=m.kub("get","secret","watoom-code-lan-tls")["data"]
    cert=base64.b64decode(tls.get("ca.crt",tls["tls.crt"]))
    context=ssl.create_default_context(cadata=cert.decode());context.verify_flags|=ssl.VERIFY_X509_PARTIAL_CHAIN
    public="https://watoom-code.internal.homelab.example"
    auth="Basic "+base64.b64encode(("opencode:"+m.password).encode()).decode()
    request=urllib.request.Request(public+"/api/info",headers={"Authorization":auth})
    with urllib.request.urlopen(request,context=context,timeout=20) as f:assert isinstance(json.load(f).get("version"),str)
    pem=subprocess.check_output(["openssl","x509","-pubkey","-noout"],input=base64.b64decode(tls["tls.crt"]))
    der=subprocess.check_output(["openssl","pkey","-pubin","-outform","DER"],input=pem)
    env={**os.environ,"PLAYWRIGHT_MODULE":"/data/ai/projects/llm/watoom-code/native-next-review-20261014T212958Z/source/node_modules/.bun/playwright@1.59.1/node_modules/playwright","CANDIDATE_PASSWORD":m.password,"CANDIDATE_BASE":public,"EVIDENCE":str(a.evidence),"MEMORY_ROUTE_SESSION":fixture["session"],"MEMORY_GUI_FACT":fixture["fact"],"TRUSTED_TLS_SPKI":base64.b64encode(hashlib.sha256(der).digest()).decode()}
    q=subprocess.run(["node",str(pathlib.Path(__file__).with_name("agentmemory-browser.cjs"))],env=env,capture_output=True,text=True,timeout=90)
    (a.evidence/"native-fenced-browser.log").write_text(q.stdout+q.stderr)
    if q.returncode:raise RuntimeError("Authenticated published GUI failed; fence remains held for rollback")
    release_guard.validate(m.request("/api/session/deployment-guard"),True)
    (a.evidence/"native-fenced-gui.json").write_text(json.dumps({"status":"PASS","authenticated_api":"PASS","authenticated_gui":"PASS","admissions_remained_fenced":True,"route":public},indent=2))
    print("PASS published authenticated API and GUI while native admission remained fenced")
