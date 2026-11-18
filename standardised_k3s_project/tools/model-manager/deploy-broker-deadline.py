#!/usr/bin/env python3
"""Publish only the reviewed broker-client deadline overlay; preserve other image bytes."""
import argparse,hashlib,json,pathlib,re,sqlite3,subprocess,tempfile
p=argparse.ArgumentParser();p.add_argument("--i-approve",action="store_true");a=p.parse_args()
if not a.i_approve:raise SystemExit("Explicit deployment authorization required")
repo=pathlib.Path(__file__).resolve().parents[2];runtime=repo/"config/llm/model-manager/runtime.json"
original=runtime.read_bytes();config=json.loads(original);base=config["cpu_image"]["image"]
payload=(repo/"tools/model-manager/broker_service.py").read_bytes();sha=hashlib.sha256(payload).hexdigest()
def run(args):
 r=subprocess.run(args,text=True,capture_output=True,timeout=240)
 if r.returncode:raise RuntimeError(r.stderr[-1500:]+r.stdout[-1500:])
 return r.stdout.strip()
def idle():
 with sqlite3.connect("file:/data/ai/model-manager/catalog.sqlite?mode=ro",uri=True) as c:
  if c.execute("select count(*) from jobs where state in ('QUEUED','WAITING_NATIVE_IDLE','GENERATING','DOWNLOADING','REMOVING','CANCEL_REQUESTED')").fetchone()[0]:
   raise RuntimeError("Pending manager work; defer deployment")
idle()
obj=json.loads(run(["kubectl","-n","glance","get","deployment","model-manager","-o","json"]))
container=obj["spec"]["template"]["spec"]["containers"][0]
if container["image"]!=base:raise RuntimeError("Runtime/live image mismatch")
if any(x.get("file")=="broker_service.py" and x.get("sha256")==sha for x in config["cpu_image"].get("overlays",[])):
 actual=run(["kubectl","-n","glance","exec","deployment/model-manager","--","python3","-c","import hashlib;print(hashlib.sha256(open('/app/model-manager/broker_service.py','rb').read()).hexdigest())"])
 if actual!=sha:raise RuntimeError("Existing overlay source mismatch")
 print("PASS: matching deadline overlay already deployed")
 raise SystemExit(0)

tag="127.0.0.1:5000/watoom-model-manager:deadline-"+sha[:16]
with tempfile.TemporaryDirectory(prefix="broker-deadline-") as d:
 d=pathlib.Path(d);(d/"broker_service.py").write_bytes(payload)
 (d/"Dockerfile").write_text("FROM "+base+"\nCOPY --chown=1009:1009 broker_service.py /app/model-manager/broker_service.py\n")
 run(["docker","build","--network=none","--pull=false","-t",tag,str(d)])
 run(["docker","push",tag])
 digests=json.loads(run(["docker","image","inspect",tag,"--format","{{json .RepoDigests}}"]))
 image=next(x for x in digests if x.startswith("127.0.0.1:5000/watoom-model-manager@sha256:"))
idle()
if runtime.read_bytes()!=original:raise RuntimeError("Runtime source changed during build")
config["cpu_image"]["image"]=image
config["cpu_image"].setdefault("overlays",[]).append({"file":"broker_service.py","sha256":sha,"purpose":"4500-second generation wait covers both swaps and render","base_image":base})
runtime.write_text(json.dumps(config,indent=2)+"\n")
try:
 run(["kubectl","-n","glance","set","image","deployment/model-manager",container["name"]+"="+image])
 run(["kubectl","-n","glance","rollout","status","deployment/model-manager","--timeout=180s"])
 actual=run(["kubectl","-n","glance","exec","deployment/model-manager","--","python3","-c","import hashlib;print(hashlib.sha256(open('/app/model-manager/broker_service.py','rb').read()).hexdigest())"])
 if actual!=sha:raise RuntimeError("Deployed client hash mismatch")
except Exception:
 runtime.write_bytes(original)
 run(["kubectl","-n","glance","set","image","deployment/model-manager",container["name"]+"="+base])
 run(["kubectl","-n","glance","rollout","status","deployment/model-manager","--timeout=180s"])
 raise
print(json.dumps({"image":image,"client_sha256":sha,"generation_timeout":4500,"validation":"deployed hash verified"}))
