#!/usr/bin/env python3
"""Prepare an owned application/Toolkit pair with fresh session state and RO sources.

Preparation emits private manifests only. No live application is changed.
"""
import argparse,copy,hashlib,json,os,pathlib,re,shutil,sqlite3,subprocess
from creative_release import bind
NS="watoom-code"
APP="watoom-code-dungeon-candidate"
TOOLKIT="watoom-toolkit-dungeon-candidate"
ENGINE=pathlib.Path("/data/ai/toolchains/unreal/5.8.3/runtime-74dc43e1a653")
EDITOR_SHA="74dc43e1a653fe3a46f68a1b3db6c3500d04d0f68a8878c9aa1b76b36a08fad3"
def kub(*args):
 return json.loads(subprocess.check_output(["kubectl","-n",NS,*args,"-o","json"],timeout=30))
def clean(value,name,owner):
 value=copy.deepcopy(value);value.pop("status",None)
 value["metadata"]={"name":name,"namespace":NS,"labels":{"app":name,"watoom-test-owner":owner}}
 value["spec"]["replicas"]=0
 value["spec"]["selector"]={"matchLabels":{"app":name}}
 value["spec"]["template"]["metadata"]={"labels":{"app":name,"watoom-test-owner":owner}}
 return value
def write(path,value):
 path.write_text(json.dumps(value,indent=2));path.chmod(0o600)
def owned_tree(root,uid):
 for p in [root,*root.rglob("*")]:
  if p.is_symlink():raise ValueError("Candidate state cannot contain symlinks")
  os.chown(p,uid,1009)
def prepare(evidence,app_image,toolkit_image,catalog,revision):
 for kind,image in (("code",app_image),("toolkit",toolkit_image)):
  if not re.fullmatch(r"127\.0\.0\.1:5000/watoom-"+kind+r"@sha256:[a-f0-9]{64}",image):raise ValueError("Correct immutable local images required")
 if not re.fullmatch("[a-f0-9]{40}",revision):raise ValueError("Exact Toolkit source commit required")
 if not evidence.is_relative_to("/data/ai/helper-scripts/reports"):raise ValueError("Private report root required")
 with (ENGINE/"Engine/Binaries/Linux/UnrealEditor").open("rb") as f:
  if hashlib.file_digest(f,"sha256").hexdigest()!=EDITOR_SHA:raise ValueError("Accepted editor changed")
 seed=json.loads(catalog.read_text())
 if seed.get("root")!="/assets" or seed.get("schema")!=1 or seed.get("cursor")!="":raise ValueError("Completed authoritative Catalog required")
 if len(seed.get("records",{}))<6309:raise ValueError("Fixture subset cannot replace global Catalog")
 styles={v.get("dungeon_adapter",{}).get("style") for v in seed["records"].values() if v.get("dungeon_adapter",{}).get("status")=="VERIFIED"}
 if not {"dungeon-builder","dungeon-forge"}<=styles:raise ValueError("Both accepted pack adapters required")
 out=evidence/"native-candidate";out.mkdir(mode=0o750);os.chown(out,0,1009)
 for name,uid in (("home",1001),("workspace",1001),("state",1001),("config",1001),("toolkit-state",1009),("published",1001)):
  path=out/name;path.mkdir(mode=0o770);os.chown(path,uid,1009)
 live=pathlib.Path("/data/ai/watoom-code")
 # Copy native instructions as opaque bytes; never print or interpret private skills.
 shutil.copytree(live/"config",out/"config",dirs_exist_ok=True,symlinks=True)
 owned_tree(out/"config",1001)
 agents=pathlib.Path(__file__).resolve().parents[2]/"ansible/roles/opencode-agent/files/v2-native/agents"
 managed=sorted(agents.glob("*.md"))
 required={"watoom-workflow","watoom-builder","watoom-investigator","watoom-reviewer","watoom-critic","watoom-kali","watoom-creative-writer"}
 if not required<={p.stem for p in managed}:raise ValueError("All maintained roles must be preserved")
 for path in managed:
  target=out/"config/agents"/path.name
  target.write_text(re.sub(r"(?m)^model:\n  providerID: watoom\n  model: [A-Za-z0-9_.-]+\n","",path.read_text()))
  os.chown(target,1001,1009)
 if (live/"skills").is_dir():shutil.copytree(live/"skills",out/"state/skills",symlinks=True)
 source_db=live/"catalog.sqlite"
 if not source_db.is_file():raise ValueError("Existing Skills Catalog is required")
 with sqlite3.connect("file:"+str(source_db)+"?mode=ro",uri=True) as src,sqlite3.connect(out/"state/catalog.sqlite") as dst:src.backup(dst)
 owned_tree(out/"state",1001)
 config=json.loads((out/"config/opencode.json").read_text())
 entries=[e for e in config["watoom_specialists"]["entries"] if e["descriptor"]["id"]=="local-toolkit"]
 if len(entries)!=1:raise ValueError("Exactly one existing Toolkit route required")
 entries[0]["url"]="http://"+TOOLKIT+"."+NS+".svc.cluster.local:8879"
 write(out/"rollback-config.private.json",config)
 # Actual Deployment UID is bound after the separately reviewed candidate creation.
 config=bind(config,toolkit_image,"PENDING_CANDIDATE_DEPLOYMENT_UID",revision,dungeon=True,native={"root":str(ENGINE),"editor_sha256":EDITOR_SHA})
 write(out/"config/opencode.json",config);os.chown(out/"config/opencode.json",1001,1009)
 fixture="""---
description: Owned native dungeon acceptance
mode: primary
model:
  providerID: watoom
  model: swift-qwen38-coder
steps: 3
permissions:
  - action: "*"
    resource: "*"
    effect: deny
  - action: watoom_specialist_run
    resource: "*"
    effect: allow
---
Call the requested directly exposed native watoom_specialist_run function once with the exact supplied JSON. Do not use Code Mode, other tools, skills or shell. Await the tool result and stop. If that function is absent from your actual provided tools, report TOOL_UNAVAILABLE; never print XML or a simulated call.
"""
 (out/"config/agents/dungeon-fixture.md").write_text(fixture);os.chown(out/"config/agents/dungeon-fixture.md",1001,1009)
 folder=out/"workspace/dungeon-fixture";folder.mkdir(mode=0o770);os.chown(folder,1001,1009)
 subprocess.run(["git","init","-q",str(folder)],check=True)
 subprocess.run(["git","-c","safe.directory="+str(folder),"-C",str(folder),"-c","user.name=OwnedAcceptance","-c","user.email=fixture@invalid","commit","--allow-empty","-qm","owned-dungeon-fixture"],check=True)
 owned_tree(folder,1001)
 published=out/"published/generated/watoom-toolkit-3d/v1";published.mkdir(parents=True,mode=0o770);owned_tree(out/"published",1009)
 cat=out/"toolkit-state/asset-catalog";cat.mkdir();write(cat/"catalog.json",seed);owned_tree(out/"toolkit-state",1009)
 # Worker UIDs 1010/1000 share GID1009. Override inherited report ACL group defaults.
 jobs=out/"toolkit-state/jobs";jobs.mkdir(exist_ok=True);os.chown(jobs,1009,1009)
 subprocess.run(["setfacl","-m","g::rwx,d:g::rwx",str(jobs)],check=True)
 app=clean(kub("get","deploy","watoom-code"),APP,evidence.name)
 toolkit=clean(kub("get","deploy","watoom-toolkit"),TOOLKIT,evidence.name)
 before_images={APP:next(c["image"] for c in app["spec"]["template"]["spec"]["containers"] if c["name"]=="app"),
  TOOLKIT:next(c["image"] for c in toolkit["spec"]["template"]["spec"]["containers"] if c["name"]=="toolkit")}
 before_engine=next(v["hostPath"]["path"] for v in toolkit["spec"]["template"]["spec"]["volumes"] if v["name"]=="unreal")
 for dep,name,image,uid in ((app,APP,app_image,1001),(toolkit,TOOLKIT,toolkit_image,1009)):
  spec=dep["spec"]["template"]["spec"];container=next(c for c in spec["containers"] if c["name"]==("app" if uid==1001 else "toolkit"))
  container["image"]=image;container["resources"]={"requests":{"cpu":"100m","memory":"256Mi"},"limits":{"cpu":"1","memory":"2Gi" if uid==1001 else "512Mi"}}
  spec["automountServiceAccountToken"]=uid==1009
  roots={"home":out/"home","workspace":out/"workspace","state":out/("state" if uid==1001 else "toolkit-state"),"config":out/"config","generated":out/"published","generated-3d":published,"unreal":ENGINE}
  writable={"home","workspace","state","generated","generated-3d","tmp"}
  for volume in spec["volumes"]:
   if volume["name"] in roots and "hostPath" in volume:volume["hostPath"]={"path":str(roots[volume["name"]]),"type":"Directory"}
  for mount in container["volumeMounts"]:
   if mount["name"] not in writable:mount["readOnly"]=True
  env={e["name"]:e for e in container.get("env",[])}
  values={"WATOOM_DEPLOYMENT_GATE_FILE":"/state/deployment-gate.json"} if uid==1001 else {
   "WATOOM_STATE":"/state","WATOOM_WORKSPACE":"/workspace","WATOOM_HOST_STATE":str(out/"toolkit-state"),"WATOOM_HOST_WORKSPACE":str(out/"workspace"),
   "WATOOM_3D_PUBLISH":"/generated","WATOOM_HOST_PUBLISH":str(published),"WATOOM_WORKER_IMAGE":image,"WATOOM_WORKER_NAMESPACE":NS,
   "WATOOM_DUNGEON_ENABLED":"1","WATOOM_UNREAL_EDITOR_SHA256":EDITOR_SHA,"WATOOM_HOST_UNREAL_ENGINE":str(ENGINE)}
  for key,value in values.items():env[key]={"name":key,"value":value}
  container["env"]=list(env.values())
  write(out/(name+".deployment.private.json"),dep)
  rollback=copy.deepcopy(dep);oldcontainer=next(c for c in rollback["spec"]["template"]["spec"]["containers"] if c["name"]==container["name"])
  oldcontainer["image"]=before_images[name]
  if uid==1009:
   oldenv={e["name"]:e for e in oldcontainer["env"] if e["name"] not in ("WATOOM_DUNGEON_ENABLED","WATOOM_UNREAL_EDITOR_SHA256","WATOOM_HOST_UNREAL_ENGINE")}
   oldenv["WATOOM_WORKER_IMAGE"]={"name":"WATOOM_WORKER_IMAGE","value":before_images[name]};oldcontainer["env"]=list(oldenv.values())
   next(v for v in rollback["spec"]["template"]["spec"]["volumes"] if v["name"]=="unreal")["hostPath"]["path"]=before_engine
  write(out/(name+".rollback.private.json"),rollback)
  service={"apiVersion":"v1","kind":"Service","metadata":{"name":name,"namespace":NS,"labels":{"watoom-test-owner":evidence.name}},"spec":{"selector":{"app":name},"ports":[{"name":"http","port":4096 if uid==1001 else 8879,"targetPort":4096 if uid==1001 else 8879}]}}
  write(out/(name+".service.json"),service)
 shutil.copyfile(pathlib.Path("/data/ai/watoom-code/toolkit-state/asset-catalog/catalog.json"),out/"rollback-catalog.private.json")
 write(out/"rollback-images.json",before_images)
 write(out/"identity.json",{"status":"PREPARED_NOT_ACTIVATED","namespace":NS,"name":APP,"toolkit":TOOLKIT,"owner":evidence.name,"image":app_image,"toolkit_image":toolkit_image,"source_commit":revision,"engine":str(ENGINE),"editor_sha256":EDITOR_SHA,"fresh_application_database":True,"project":"/workspace/dungeon-fixture","agent":"dungeon-fixture"})
 print(json.dumps({"status":"PREPARED_NOT_ACTIVATED","directory":str(out),"next":"Create owned zero-replica candidate resources, bind actual Toolkit UID, verify effective route before activation"}))
def activate(evidence):
 import secrets,urllib.request,urllib.error,time
 from maintenance_guard import Maintenance
 from creative_release import registry
 import release_guard
 out=evidence/"native-candidate";identity=json.loads((out/"identity.json").read_text())
 if identity["status"]!="PREPARED_NOT_ACTIVATED" or identity["owner"]!=evidence.name or identity["name"]!=APP or identity["toolkit"]!=TOOLKIT:raise ValueError("Inspect existing candidate state; never replay activation")
 if registry(identity["toolkit_image"],out/"toolkit-manifest.json")!=identity["source_commit"]:raise ValueError("Toolkit image does not match committed source")
 for kind,name in (("deployment",APP),("deployment",TOOLKIT),("service",APP),("service",TOOLKIT)):
  present=subprocess.check_output(["kubectl","-n",NS,"get",kind,name,"--ignore-not-found","-o","name"],timeout=30)
  if present.strip():raise ValueError("Existing candidate resource must be reconciled explicitly: "+name)
 if (out/"state/application.sqlite").exists():raise ValueError("Candidate must boot a fresh session database")
 identity["status"]="ACTIVATING";write(out/"identity.json",identity)
 for name in (TOOLKIT,APP):
  for kind in ("deployment.private","service"):
   subprocess.run(["kubectl","create","-f",str(out/(name+"."+kind+".json"))],check=True,stdout=subprocess.DEVNULL,timeout=30)
 deployment=kub("get","deploy",TOOLKIT);uid=deployment["metadata"]["uid"]
 oldconfig=json.loads((out/"rollback-config.private.json").read_text());oldentry=next(e for e in oldconfig["watoom_specialists"]["entries"] if e["descriptor"]["id"]=="local-toolkit")
 oldimage=json.loads((out/"rollback-images.json").read_text())[TOOLKIT]
 oldconfig=bind(oldconfig,oldimage,uid,oldentry["descriptor"]["sourceCommit"])
 write(out/"rollback-config.private.json",oldconfig)
 config=json.loads((out/"config/opencode.json").read_text())
 config=bind(config,identity["toolkit_image"],uid,identity["source_commit"],dungeon=True,native={"root":str(ENGINE),"editor_sha256":EDITOR_SHA})
 write(out/"config/opencode.json",config);os.chown(out/"config/opencode.json",1001,1009)
 for name in (TOOLKIT,APP):
  subprocess.run(["kubectl","-n",NS,"scale","deployment/"+name,"--replicas=1"],check=True,stdout=subprocess.DEVNULL,timeout=30)
  subprocess.run(["kubectl","-n",NS,"rollout","status","deployment/"+name,"--timeout=120s"],check=True,stdout=subprocess.DEVNULL,timeout=130)
  if name==TOOLKIT:
   service=kub("get","svc",name)
   with urllib.request.urlopen("http://"+service["spec"]["clusterIP"]+":8879/healthz",timeout=10) as response:
    if response.status!=200:raise ValueError("Toolkit application health failed")
 validate_activation(evidence)
def registry_preflight(out,entries):
 source=pathlib.Path("/data/ai/projects/llm/watoom-code/native-next-review-20261014T212958Z/source")
 bun=pathlib.Path("/data/ai/helper-scripts/.cache/bun-c29262d")
 code='import {SpecialistBackends} from "./packages/core/src/watoom/specialist-backends.ts";let value=await Bun.stdin.json();console.log(JSON.stringify(SpecialistBackends.registry(value).registry.list().map(x=>x.id)))'
 result=subprocess.run([str(bun),"--eval",code],cwd=source,input=json.dumps(entries),capture_output=True,text=True,timeout=30)
 if result.returncode:raise ValueError("Actual application registry rejected candidate configuration: "+result.stderr[-400:])
 ids=json.loads(result.stdout)
 if "local-toolkit" not in ids:raise ValueError("Native Toolkit absent from actual registry")
 write(out/"native-registry-preflight.json",{"status":"PASS","registered_ids":ids,"network_or_model_calls":False})
def validate_activation(evidence):
 import secrets,urllib.error
 from maintenance_guard import Maintenance
 import release_guard
 out=evidence/"native-candidate";identity=json.loads((out/"identity.json").read_text())
 if identity["status"] not in ("ACTIVATING","ACTIVATED_GUARDED") or identity["owner"]!=evidence.name or identity["name"]!=APP or identity["toolkit"]!=TOOLKIT:raise ValueError("Owned existing activation required")
 m=Maintenance(NS,APP,out,True,True)
 for name,image in ((APP,identity["image"]),(TOOLKIT,identity["toolkit_image"])):
  deployment=kub("get","deploy",name)
  if deployment["metadata"]["labels"]["watoom-test-owner"]!=evidence.name:raise ValueError("Candidate ownership changed")
  pods=kub("get","pods","-l","app="+name)["items"]
  running=[x for x in pods if x["status"]["phase"]=="Running" and not x["metadata"].get("deletionTimestamp")]
  if len(running)!=1 or running[0]["status"]["containerStatuses"][0]["imageID"].split("@")[-1]!=image.split("@")[-1]:raise ValueError("Actual candidate digest mismatch")
 uid=kub("get","deploy",TOOLKIT)["metadata"]["uid"]
 if m.request("/api/session/active")["data"]!={}:raise ValueError("Candidate has an active session")
 release_guard.durable_clearance(out/"state/application.sqlite")
 owner_path=out/"guard-owner.private"
 if not owner_path.exists():owner_path.write_text(secrets.token_hex(32));owner_path.chmod(0o600)
 owner=owner_path.read_text().strip()
 if not re.fullmatch("[a-f0-9]{64}",owner):raise ValueError("Exact native 64hex owner contract required")
 held=m.request("/api/session/deployment-guard")["data"]
 if held["held"]:
  code='import os,pathlib,json,sys;d=json.loads(pathlib.Path(os.environ["WATOOM_DEPLOYMENT_GATE_FILE"]).read_text());assert d["owner"]==sys.stdin.read();print("OWNED")'
  if m.exec(code,input=owner.encode()).strip()!=b"OWNED":raise ValueError("Native guard ownership unverified")
 else:held=m.request("/api/session/deployment-guard",{"action":"acquire","owner":owner})["data"]
 if held.get("held") is not True or held.get("leases")!=0:raise ValueError("Native admission guard did not hold")
 # Config API returns ordered entries. Match Config.latest: last document defining this key.
 layers=m.request("/api/config")
 entries=next(row["info"]["watoom_specialists"]["entries"] for row in reversed(layers) if row.get("type")=="document" and "watoom_specialists" in row.get("info",{}))
 toolkit=[x for x in entries if x["descriptor"]["id"]=="local-toolkit"]
 expected="http://"+TOOLKIT+"."+NS+".svc.cluster.local:8879"
 if len(toolkit)!=1 or toolkit[0]["url"]!=expected or toolkit[0]["descriptor"]["model"]["deploymentUID"]!=uid:raise ValueError("Effective config does not use isolated Toolkit")
 registry_preflight(out,entries)
 try:m.request("/api/config",authenticated=False)
 except urllib.error.HTTPError as error:
  if error.code!=401:raise
 else:raise ValueError("Anonymous candidate configuration access allowed")
 identity.update(status="ACTIVATED_GUARDED",toolkit_uid=uid);write(out/"identity.json",identity)
 result={"status":"PASS","candidate":APP,"toolkit":TOOLKIT,"effective_route":expected,"fresh_session_state":True,"native_guard":"HELD","actual_immutable_images":"PASS","live_deployment_changed":False}
 write(out/"activation-acceptance.json",result);print(json.dumps(result))
def main():
 global APP,TOOLKIT
 p=argparse.ArgumentParser();p.add_argument("--evidence",required=True,type=pathlib.Path)
 p.add_argument("--activate",action="store_true");p.add_argument("--finish-activation",action="store_true");p.add_argument("--catalog",type=pathlib.Path)
 for name in ("app-image","toolkit-image","revision"):p.add_argument("--"+name)
 p.add_argument("--candidate-suffix",default="dungeon")
 a=p.parse_args()
 if not re.fullmatch("[a-z0-9-]{1,24}",a.candidate_suffix):raise ValueError("Safe candidate suffix required")
 APP="watoom-code-"+a.candidate_suffix+"-candidate";TOOLKIT="watoom-toolkit-"+a.candidate_suffix+"-candidate"
 if a.activate:activate(a.evidence.resolve())
 elif a.finish_activation:validate_activation(a.evidence.resolve())
 else:
  if not all((a.catalog,a.app_image,a.toolkit_image,a.revision)):p.error("Preparation requires catalog and both immutable image identities/source revision")
  prepare(a.evidence.resolve(),a.app_image,a.toolkit_image,a.catalog.resolve(),a.revision)
if __name__=="__main__":main()
