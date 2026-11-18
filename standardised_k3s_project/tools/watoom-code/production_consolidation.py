#!/usr/bin/env python3
"""Production evidence, verified recovery snapshots and fenced application releases.
No session replay, model switching, volume deletion or competing GPU controller.
"""
import argparse, datetime, hashlib, json, os, pathlib, secrets, sqlite3, string, subprocess, tarfile, time
import release_guard, release_ledger
from maintenance_guard import Maintenance, run

PRODUCTION = ("watoom-code", "watoom-code")
ARTIFACTS = pathlib.Path("/data/ai/artifacts/watoom-code-production-consolidation")

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp-" + str(os.getpid()))
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, indent=2); stream.flush(); os.fsync(stream.fileno())
    os.replace(temp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)

def kub(*args):
    return json.loads(run(["kubectl", *args, "-o", "json"]))

def classify(item):
    ns = item["metadata"].get("namespace", ""); name = item["metadata"]["name"]
    if ns == "watoom-code-rig-jobs":
        return "RETIRED_STAGE"
    if ns == PRODUCTION[0] and name in ("watoom-code", "watoom-toolkit", "agentmemory"):
        return "KEEP_PRODUCTION"
    return "INVESTIGATE"

def checkpoint(database, out):
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    release_guard.snapshot_database(database, out / "application.sqlite")
    with sqlite3.connect("file:" + str(out / "application.sqlite") + "?mode=ro", uri=True) as db:
        sessions = db.execute("select id,parent_id,directory,model,time_updated,time_suspended from session_v2").fetchall()
        summaries = db.execute("WITH ranked AS (SELECT session_id,id,seq,data,row_number() OVER (PARTITION BY session_id,json_extract(data, '$.status') ORDER BY seq DESC) AS rank FROM session_message WHERE type='compaction') SELECT session_id,id,seq,data FROM ranked WHERE rank=1").fetchall()
        tables = {name for (name,) in db.execute("select name from sqlite_master where type='table'")}
        pending = {t: db.execute("select * from " + t).fetchall() for t in ("session_pending", "session_inbox", "_watoom_checkpoint", "_watoom_outbox", "job") if t in tables}
        projects = db.execute("select id,worktree,name from project").fetchall()
    save(out / "session-checkpoints.private.json", {"sessions":sessions,"compactions":summaries,"pending":pending,"projects":projects,
        "recovery":"Use native existing-session resume only after reconciling uncertain tool operations. Do not automatically enqueue another prompt. Original history retained in application.sqlite."})
    return {"sessions":len(sessions), "children":sum(x[1] is not None for x in sessions), "projects":len(projects)}

def inventory(out):
    resources = kub("get", "deploy,pods,svc,ingress,cm,pvc,cronjob,job,hpa", "-A")["items"]
    selected = [x for x in resources if "opencode" in x["metadata"].get("namespace", "") or "opencode" in x["metadata"]["name"] or "watoom-code" in x["metadata"]["name"]]
    save(out / "resources.private.json", selected)
    rows=[]
    for x in selected:
        spec=x.get("spec",{});m=x["metadata"]
        rows.append({"RESOURCE":x["kind"]+"/"+m["name"],"NAMESPACE_OR_PATH":m.get("namespace", ""),
          "CURRENT_STATE":{"replicas":spec.get("replicas"),"ready":x.get("status",{}).get("readyReplicas")},
          "OWNER":m.get("ownerReferences",m.get("labels",{})),"DEPENDENCIES":spec.get("template",{}).get("spec",{}).get("volumes",[]),
          "ACTIVE_CONSUMERS":"INVESTIGATE; zero replicas alone does not prove retirement safety", "PERSISTENT_DATA":"retained; see volume dependencies",
          "CLASSIFICATION":classify(x),"RECOMMENDED_ACTION":"preserve until references, workers and recovery archive verified"})
    save(out / "inventory.json", rows)
    return rows

def verify_hashes(out):
    hashes={str(p.relative_to(out)):hashlib.file_digest(p.open("rb"),"sha256").hexdigest() for p in out.rglob("*") if p.is_file() and p.name!="SHA256SUMS.json"}
    save(out / "SHA256SUMS.json",hashes)
    for name,digest in hashes.items():
        if hashlib.file_digest((out/name).open("rb"),"sha256").hexdigest()!=digest:raise RuntimeError("Backup hash mismatch")

def deploy(root, out, image):
    if not image.startswith("127.0.0.1:5000/watoom-code@sha256:") or len(image.split("sha256:")[-1])!=64:raise ValueError("Immutable app image required")
    m=Maintenance(*PRODUCTION,out,True,True)
    baseline=m.kub("get","deploy",PRODUCTION[1]);save(out/"deployment.before.private.json",baseline)
    controller=pathlib.Path("/data/ai/helper-scripts/state/gpu-controller")
    before=json.loads((controller/"state.json").read_text())
    def clearance():
        release_guard.durable_clearance(pathlib.Path("/data/ai/watoom-code/application.sqlite"))
        now=json.loads((controller/"state.json").read_text());leases=json.loads((controller/"inference-leases.json").read_text())
        if now!=before or now["owner"] is not None or now["uncertain"] or now["phase"]!="qwen-ready" or leases["leases"]:raise RuntimeError("GPU work not idle")
        if any(x.get("status",{}).get("active") for x in m.kub("get","jobs")["items"]):raise RuntimeError("Active workers")
    def owner_save(owner):save(out/"guard-owner.private.json",{"owner":owner})
    owner=release_guard.acquire(m.request,lambda p,b:m.request(p,b),owner_save,clearance)
    healthy=True;changed=False
    try:
        counts=checkpoint(pathlib.Path("/data/ai/watoom-code/application.sqlite"),out/"checkpoint")
        clearance();healthy=False;changed=True
        env=dict(os.environ,ANSIBLE_CONFIG=str(root/"ansible/ansible.cfg"),ANSIBLE_ROLES_PATH=str(root/"ansible/roles"))
        cmd=["ansible-playbook","-i","ansible/inventories/homelab/hosts.yml","ansible/playbooks/watoom-code-context.yml","-e",json.dumps({"watoom_context_guard_held":True,"watoom_context_image":image})]
        result=subprocess.run(cmd,cwd=root,env=env,capture_output=True,text=True,timeout=300)
        (out/"ansible.log").write_text(result.stdout+result.stderr)
        if result.returncode:raise RuntimeError("Scoped Ansible deployment failed; see private log")
        pod=m.pod();actual=next(c["imageID"] for c in pod["status"]["containerStatuses"] if c["name"]=="app")
        if image.split("@")[1] not in actual:raise RuntimeError("Running image ID mismatch")
        release_guard.runtime(m.request,image,actual)
        after=checkpoint(pathlib.Path("/data/ai/watoom-code/application.sqlite"),out/"after")
        if counts!=after:raise RuntimeError("Session/project preservation counts changed under fence")
        if json.loads((controller/"state.json").read_text())!=before:raise RuntimeError("GPU state changed")
        save(out/"result.json",{"status":"PASS","image":actual,"preserved":after,"gpu_controller_unchanged":True,"info":m.request("/api/info")})
        release_ledger.append(actual,release_ledger.image_revision(actual),root,"production_consolidation deploy",out)
        healthy=True
    except BaseException:
        if changed:
            run(["kubectl","-n",m.ns,"patch","deployment",m.name,"--type=merge","-p",json.dumps({"spec":{"template":baseline["spec"]["template"]}})])
            run(["kubectl","-n",m.ns,"rollout","status","deployment/"+m.name,"--timeout=240s"],timeout=260)
            m.request("/api/info");healthy=True
        raise
    finally:
        if healthy:release_guard.release(m.request,lambda p,b:m.request(p,b),owner)

def maintain_model(root, out):
    # The existing coordinator remains the sole GPU transaction owner.
    m=Maintenance(*PRODUCTION,out,True,True)
    def clearance():
        release_guard.durable_clearance(pathlib.Path("/data/ai/watoom-code/application.sqlite"))
        if any(x.get("status",{}).get("active") for x in m.kub("get","jobs")["items"]):raise RuntimeError("Active worker jobs")
    owner=release_guard.acquire(m.request,lambda p,b:m.request(p,b),lambda owner:save(out/"guard-owner.private.json",{"owner":owner}),clearance)
    try:
        save(out/"checkpoint-counts.json",checkpoint(pathlib.Path("/data/ai/watoom-code/application.sqlite"),out/"checkpoint"))
        clearance()
        with (out/"model-maintenance.log").open("w") as log:
            result=subprocess.run(["python3",str(root/"scripts/watoom-qwen-maintenance.py"),"--apply","--approve-downtime"],stdout=log,stderr=subprocess.STDOUT,timeout=600)
        if result.returncode:raise RuntimeError("Existing model coordinator failed; inspect retained log and its rollback record")
        current=kub("-n","llama-cpp","get","deploy","llama-cpp-swift-qwen38-coder")
        args=next(c["args"] for c in current["spec"]["template"]["spec"]["containers"] if c["name"]=="llama-server")
        if args[args.index("--reasoning")+1]!="on" or args[args.index("--reasoning-effort")+1]!="low":raise RuntimeError("Reasoning flags did not activate")
        if current.get("status",{}).get("readyReplicas")!=1:raise RuntimeError("Model not ready")
        state=json.loads(pathlib.Path("/data/ai/helper-scripts/state/gpu-controller/state.json").read_text())
        if state["phase"]!="qwen-ready" or state["owner"] is not None or state["uncertain"]:raise RuntimeError("GPU controller not restored")
        import urllib.request
        router=kub("-n","llama-cpp","get","svc","llm-router")["spec"]["clusterIP"]
        with urllib.request.urlopen("http://"+router+":8000/v1/models",timeout=15) as response:models=json.load(response)
        if not any(x["id"]=="swift-qwen38-coder" for x in models["data"]):raise RuntimeError("Router model readiness failed")
        save(out/"result.json",{"status":"PASS","reasoning":"on","reasoning_effort":"low","model_ready":True,"router_ready":True,"controller":state,"resume":"No production sessions interrupted; native active/durable clearance held throughout. Historical idle sessions were not replayed."})
    finally:
        release_guard.release(m.request,lambda p,b:m.request(p,b),owner)

def retire_legacy(root,out):
    archive=ARTIFACTS/"legacy-opencode-v2-canary-20261029"
    hashes=json.loads((archive/"SHA256SUMS.json").read_text())
    for name,digest in hashes.items():
        if hashlib.file_digest((archive/name).open("rb"),"sha256").hexdigest()!=digest:raise RuntimeError("Legacy archive hash mismatch")
    restore=json.loads((archive/"restore-read.json").read_text())
    if not restore["sqlite_files_read"]:raise RuntimeError("No legacy database restore-read proof")
    d=kub("-n","opencode","get","deploy","opencode-v2-canary")
    if d["spec"]["replicas"]!=0 or kub("-n","opencode","get","pods","-l","app=opencode-v2-canary")["items"]:raise RuntimeError("Legacy active; retirement blocked")
    if any(x["spec"]["scaleTargetRef"]["name"]=="opencode-v2-canary" for x in kub("-n","opencode","get","hpa")["items"]):raise RuntimeError("Legacy autoscaler present")
    if "when: opencode_agent_restore_retired | default(false)" not in (root/"ansible/playbooks/opencode-agent.yml").read_text():raise RuntimeError("Legacy reconciler is not disabled")
    saved=json.loads((archive/"resources.private.json").read_text())
    if d["metadata"]["uid"]!=saved["deployment"]["metadata"]["uid"]:raise RuntimeError("Legacy identity changed")
    selected=[{"api_version":"apps/v1","kind":"Deployment","name":"opencode-v2-canary","uid":d["metadata"]["uid"]}]
    for service in saved["services"]:
        live=kub("-n","opencode","get","svc",service["metadata"]["name"])
        if live["metadata"]["uid"]!=service["metadata"]["uid"]:raise RuntimeError("Legacy service replaced")
        slices=kub("-n","opencode","get","endpointslices","-l","kubernetes.io/service-name="+live["metadata"]["name"])
        if any(x.get("endpoints") for x in slices["items"]):raise RuntimeError("Legacy service has consumers")
        selected.append({"api_version":"v1","kind":"Service","name":live["metadata"]["name"],"uid":live["metadata"]["uid"]})
    ingress=kub("-n","opencode","get","ingressroute","opencode")
    if ingress["spec"]!=saved["ingress"]["spec"]:raise RuntimeError("Legacy ingress changed")
    selected.append({"api_version":ingress["apiVersion"],"kind":"IngressRoute","name":"opencode","uid":ingress["metadata"]["uid"]})
    save(out/"retirement-plan.json",selected)
    values={"watoom_legacy_archive_verified":True,"watoom_legacy_deployment_uid":d["metadata"]["uid"],"watoom_legacy_resources":selected}
    env=dict(os.environ,ANSIBLE_CONFIG=str(root/"ansible/ansible.cfg"),ANSIBLE_ROLES_PATH=str(root/"ansible/roles"))
    result=subprocess.run(["ansible-playbook","-i","ansible/inventories/homelab/hosts.yml","ansible/playbooks/watoom-code-retire-legacy.yml","-e",json.dumps(values)],cwd=root,env=env,capture_output=True,text=True,timeout=180)
    (out/"ansible.log").write_text(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError("Legacy retirement failed; archive and plan retained")
    m=Maintenance(*PRODUCTION,out,True,True);m.request("/api/info")
    save(out/"result.json",{"status":"PASS","retired":selected,"persistent_data_deleted":False,"archive":str(archive),"production_available":True,"rig_and_bazzite":"preserved production dependencies"})

def native_message_id(now_ms=None):
    # Native ascending format: msg_ + low 48 bits of (ms*0x1000+counter) as hex + 14 base62 characters.
    ms=int(time.time()*1000) if now_ms is None else now_ms
    return "msg_%012x"%((ms*0x1000+1)&0xffffffffffff)+"".join(secrets.choice(string.digits+string.ascii_letters) for _ in range(14))

def recover_session(out, session_id, request_id):
    if not session_id:raise ValueError("Existing --session-id required")
    if request_id and not request_id.startswith("msg_"):raise ValueError("--request-id must be a native msg_ identifier")
    generated=not request_id;request_id=request_id or native_message_id()
    # Persist before admission so a retry can reuse the same ID and rely on native inbox deduplication.
    save(out/"request-id.json",{"request_id":request_id,"generated":generated,"retry":"--request-id "+request_id})
    m=Maintenance(*PRODUCTION,out,True,True)
    release_guard.active_clear(m.request("/api/session/active"))
    release_guard.durable_clearance(pathlib.Path("/data/ai/watoom-code/application.sqlite"))
    with sqlite3.connect("file:/data/ai/watoom-code/application.sqlite?mode=ro",uri=True) as db:
        row=db.execute("select id,parent_id,directory from session_v2 where id=?",(session_id,)).fetchone()
        if not row:raise ValueError("Unknown original session")
        latest=db.execute("select data from session_message where session_id=? and type='assistant' order by seq desc limit 1",(session_id,)).fetchone()
        if latest and any(p.get("type")=="tool" and p.get("state",{}).get("status") not in ("completed","error") for p in json.loads(latest[0]).get("content",[])):raise RuntimeError("Uncertain tool completion: reconcile before resuming")
    checkpoint(pathlib.Path("/data/ai/watoom-code/application.sqlite"),out/"checkpoint")
    # Native inbox deduplicates the stable message ID; no host-side retry/replay of model/tool requests.
    result=m.request("/api/session/"+session_id+"/prompt",{"id":request_id,"text":"Recover the existing task from its latest successful checkpoint and original durable history. Reconcile the actual Git/files/artifacts and tool receipts first. Do not repeat completed or uncertain non-idempotent operations; report any uncertain completion. Continue with the next exact pending step, preserving safety constraints."})
    save(out/"result.json",{"status":"ADMITTED","original_session":row,"request_id":request_id,"request_id_generated":generated,"admission":result,"note":"Admission is not proof of completion; observe original session."})

def main():
    p=argparse.ArgumentParser();p.add_argument("action",choices=["inventory","checkpoint","deploy","maintain-model","retire-legacy","recover-session"])
    p.add_argument("--iac-root",type=pathlib.Path,default=pathlib.Path(__file__).resolve().parents[2]);p.add_argument("--image");p.add_argument("--session-id");p.add_argument("--request-id");a=p.parse_args()
    os.umask(0o077);out=ARTIFACTS/(a.action+"-"+datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"));out.mkdir(parents=True,mode=0o700);out.chmod(0o700)
    if a.action=="inventory":inventory(out)
    elif a.action=="checkpoint":save(out/"result.json",checkpoint(pathlib.Path("/data/ai/watoom-code/application.sqlite"),out/"checkpoint"))
    elif a.action=="recover-session":recover_session(out,a.session_id,a.request_id)
    elif a.action=="retire-legacy":retire_legacy(a.iac_root.resolve(),out)
    elif a.action=="maintain-model":maintain_model(a.iac_root.resolve(),out)
    else:deploy(a.iac_root.resolve(),out,a.image or "")
    verify_hashes(out);print("PASS ARTIFACT="+str(out))
if __name__=="__main__":main()
