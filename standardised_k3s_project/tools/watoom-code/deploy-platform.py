#!/usr/bin/env python3
"""Deploy only the WatooM Code app from authoritative IaC; rollback on failed gates."""
import tarfile
import tempfile
import argparse,base64,datetime,hashlib,importlib.util,json,os,pathlib,re,subprocess,time,urllib.request,urllib.error
import bounded_process
import release_guard
import release_ledger
import maintenance_guard
import mesh_release
import skills_release
import creative_release
import secrets
import ssl
import jinja2,yaml
NS="watoom-code"
def atomic_write(path, content):
    metadata=path.stat()
    descriptor,temporary=tempfile.mkstemp(prefix="."+path.name+".release-",dir=path.parent)
    try:
        with os.fdopen(descriptor,"wb") as stream:
            os.fchmod(stream.fileno(),metadata.st_mode & 0o777)
            os.fchown(stream.fileno(),metadata.st_uid,metadata.st_gid)
            stream.write(content if isinstance(content,bytes) else content.encode());stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
        directory=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)

def main():
    import sys
    if '--render-routing-only' in sys.argv:
        from render_routing_release import promote
        return promote()
    if '--dev-workspace-only' in sys.argv:
        from dev_release import main as promote_dev
        return promote_dev()
    if '--rollback-blender-evidence' in sys.argv:
        return creative_release.rollback_blender_toolkit()
    if '--blender-toolkit-only' in sys.argv:
        return creative_release.promote_blender_toolkit()
    if '--prompt-skills-only' in sys.argv:
        return skills_release.promote_native_blender(prompt_skills=True)
    if '--blender-skills-only' in sys.argv:
        return skills_release.promote_native_blender()
    parser=argparse.ArgumentParser();parser.add_argument("--iac-root",required=True,type=pathlib.Path);parser.add_argument("--evidence",required=True,type=pathlib.Path);parser.add_argument("--image",required=True);parser.add_argument("--candidate-evidence",type=pathlib.Path)
    parser.add_argument("--prompt-builder",action="store_true");parser.add_argument("--engineering-tools",action="store_true");parser.add_argument("--skills-collection",type=pathlib.Path);parser.add_argument("--toolkit-image");parser.add_argument("--asset-catalog",type=pathlib.Path);parser.add_argument("--native-gui-fixture",type=pathlib.Path);parser.add_argument("--mesh-integration",action="store_true");parser.add_argument("--leave-forwarding-stopped",action="store_true");parser.add_argument("--bootstrap-maintenance",action="store_true");parser.add_argument("--i-approve",action="store_true");parser.add_argument("--administrative-access-closed",action="store_true");parser.add_argument("--bootstrap-evidence",type=pathlib.Path)
    a=parser.parse_args();r=a.iac_root.resolve();out=a.evidence.resolve()
    print("RISK: replaces only the idle production application image. Native admission fencing, snapshots, exact-image validation and automatic scoped rollback protect existing work. Inference and network settings are preserved.",flush=True)
    if not a.i_approve:raise release_guard.UnsafeRelease("--i-approve required")
    if not re.fullmatch(r"127\.0\.0\.1:5000/watoom-code@sha256:[a-f0-9]{64}",a.image):raise ValueError("Immutable local app image required")
    out.mkdir(exist_ok=False,mode=0o700);os.chmod(out,0o700)
    def cmd(args,timeout=60,input=None,cwd=None):
        p=bounded_process.run(args,input=input,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,cwd=cwd)
        if p.returncode:raise RuntimeError("Command failed: "+str(args[:5])+"; "+p.stderr.decode(errors="replace")[-300:])
        return p.stdout
    def kub(*args):return json.loads(cmd(["kubectl","-n",NS,*args,"-o","json"]))
    secret=kub("get","secret","watoom-code-auth")["data"]
    auth="Basic "+base64.b64encode(b"opencode:"+base64.b64decode(secret["OPENCODE_PASSWORD"])).decode()
    ip=kub("get","svc","watoom-code")["spec"]["clusterIP"]
    def get(path,authenticated=True):
        req=urllib.request.Request("http://"+ip+":4096"+path,headers={"Authorization":auth} if authenticated else {})
        with urllib.request.urlopen(req,timeout=15) as response:return json.load(response)
    def clearance():
        deployment=kub("get","deploy","watoom-code")
        spec=deployment["spec"]["template"]["spec"]
        appcontainer=next(x for x in spec["containers"] if x["name"]=="app")
        volume=next(x for x in spec["volumes"] if x["name"]=="state")
        mount=next(x for x in appcontainer["volumeMounts"] if x["name"]=="state")
        database=next(x.get("value") for x in appcontainer["env"] if x["name"]=="OPENCODE_DB")
        if pathlib.Path(volume.get("hostPath",{}).get("path","/")).resolve()!=pathlib.Path("/data/ai/watoom-code") or mount.get("mountPath")!="/state" or mount.get("readOnly") or database!="/state/application.sqlite":
            raise release_guard.UnsafeRelease("Durable database path does not match the actual workload")
        if deployment["spec"].get("replicas")!=1 or deployment["spec"].get("strategy",{}).get("type")!="Recreate":
            raise release_guard.UnsafeRelease("Execution status contract requires a single Recreate process")
        checks=release_guard.durable_clearance(pathlib.Path("/data/ai/watoom-code/application.sqlite"))
        (out/"durable-clearance.json").write_text(json.dumps(checks,indent=2))
        if get("/api/session/active").get("data")!={}:raise RuntimeError("Active WatooM Code work; deployment blocked")
        jobs=json.loads(cmd(["kubectl","get","jobs","-A","-o","json"]))["items"]
        if any(x.get("status",{}).get("active") for x in jobs):raise RuntimeError("Active cluster job; deployment blocked")
    clearance()
    (out/"models-before.json").write_text(json.dumps(get("/api/model"),indent=2))
    baseline_connected=set()
    if a.toolkit_image or a.skills_collection or a.engineering_tools or a.prompt_builder:
        baseline_connected={entry["name"] for entry in get("/api/mcp?directory=/workspace")["data"] if entry["status"]["status"]=="connected"}
        (out/"mcp-connected-before.json").write_text(json.dumps(sorted(baseline_connected),indent=2))
    def verify_existing_mcp():
        if not baseline_connected:return
        deadline=time.monotonic()+60
        while True:
            current={entry["name"] for entry in get("/api/mcp?directory=/workspace")["data"] if entry["status"]["status"]=="connected"}
            if baseline_connected.issubset(current):return
            if time.monotonic()>=deadline:raise release_guard.UnsafeRelease("Previously connected MCP servers did not recover")
            time.sleep(.5)

    # The baseline must support the durable fence too; an older rollback image cannot
    # safely be bootstrapped by an idle observation alone.
    maintenance=None
    baseline_native=True
    try:release_guard.validate(get("/api/session/deployment-guard"), False)
    except urllib.error.HTTPError as error:
        if not a.bootstrap_maintenance:
            raise release_guard.UnsafeRelease("Baseline native admission guard unavailable (HTTP "+str(error.code)+"); bootstrap promotion blocked") from None
        if not a.bootstrap_evidence:raise release_guard.UnsafeRelease("Independent old-image bootstrap acceptance required")
        boot=json.loads(a.bootstrap_evidence.read_text())
        old=kub("get","deploy","watoom-code")["spec"]["template"]["spec"]["containers"][0]["image"]
        if boot.get("old_image")!=old or any(boot.get(k)!="PASS" for k in ("status","existing_connections_preserved","new_service_connections_blocked","service_endpoints_blocked","live_connection_drain_refusal","old_image_authenticated_rollback")):
            raise release_guard.UnsafeRelease("Independent bootstrap acceptance does not match baseline")
        maintenance=maintenance_guard.Maintenance(NS,"watoom-code",out,a.i_approve,a.administrative_access_closed)
        def get(path,authenticated=True):return maintenance.request(path,authenticated=authenticated)
        baseline_native=False
    if not a.candidate_evidence:raise release_guard.UnsafeRelease("Isolated candidate acceptance evidence required")
    accepted=json.loads(a.candidate_evidence.read_text())
    if accepted.get("image")!=a.image or any(accepted.get(k)!="PASS" for k in ("guard_boot","guard_race","rollback","authenticated_api","authenticated_gui","memory")):
        raise release_guard.UnsafeRelease("Candidate acceptance is incomplete or image does not match")
    if a.engineering_tools and (accepted.get("engineering_tools")!="PASS" or not re.fullmatch("[a-f0-9]{64}",accepted.get("application_binary_sha256",""))):
        raise release_guard.UnsafeRelease("Exact-image engineering acceptance required")
    if baseline_native and (not a.native_gui_fixture or not a.native_gui_fixture.is_file()):raise release_guard.UnsafeRelease("Owned fenced GUI fixture required before promotion")
    if a.prompt_builder:
        if accepted.get("prompt_builder")!="PASS":raise release_guard.UnsafeRelease("Exact-image prompt page browser acceptance required")
        native_before=get("/api/skill?directory=/workspace")["data"]
        (out/"native-skills-before.private.json").write_text(json.dumps(native_before))
    baseline=kub("get","deploy","watoom-code");(out/"deployment-before.json").write_text(json.dumps(baseline,indent=2))
    config=pathlib.Path("/data/ai/watoom-code/config/opencode.json")
    config_before=config.read_bytes();(out/"opencode-before.private.json").write_bytes(config_before)
    workflow=config.parent/"agents/watoom-workflow.md";workflow_before=workflow.read_bytes()
    (out/"workflow-before.md").write_bytes(workflow_before)
    defaults=r/"ansible/roles/watoom-code/defaults/main.yml";defaults_before=defaults.read_text()
    (out/"defaults-before.yml").write_text(defaults_before)
    vars=yaml.safe_load(defaults_before)
    pins=r/"ansible/vars/watoom-code.yml";pins_before=pins.read_text()
    (out/"pins-before.yml").write_text(pins_before)
    vars.update(yaml.safe_load(pins_before))
    new_digest=a.image.split("@")[1]
    req=urllib.request.Request("http://127.0.0.1:5000/v2/watoom-code/manifests/"+new_digest,headers={"Accept":"application/vnd.oci.image.manifest.v1+json"})
    with urllib.request.urlopen(req,timeout=10) as response:manifest_bytes=response.read()
    if "sha256:"+hashlib.sha256(manifest_bytes).hexdigest()!=new_digest:raise release_guard.UnsafeRelease("New immutable manifest digest mismatch")
    new_manifest=json.loads(manifest_bytes)
    with urllib.request.urlopen("http://127.0.0.1:5000/v2/watoom-code/blobs/"+new_manifest["config"]["digest"],timeout=10) as response:new_metadata=json.load(response)
    source_commit=new_metadata.get("config",{}).get("Labels",{}).get("org.opencontainers.image.revision","")
    if not re.fullmatch("[a-f0-9]{40}",source_commit):raise release_guard.UnsafeRelease("New image lacks committed source provenance")
    (out/"image-source-commit.txt").write_text(source_commit+"\n")
    vars["watoom_code_image"]=a.image
    if a.mesh_integration:
        if not a.i_approve:raise release_guard.UnsafeRelease("Reviewed Mesh integration requires --i-approve")
        vars["watoom_code_mesh_enabled"]=True
    template=(r/"ansible/roles/watoom-code/templates/resources.json.j2").read_text()
    environment=jinja2.Environment(undefined=jinja2.StrictUndefined)
    from ansible.plugins.filter.core import FilterModule as ansible_core_filters  # the role template uses Ansible's bool/to_json
    environment.filters.update(ansible_core_filters().filters())
    resources=json.loads(environment.from_string(template).render(**vars))
    rendered=next(x for x in resources["items"] if x.get("kind")=="Deployment" and x["metadata"]["name"]=="watoom-code")
    # Promotion preserves the exact verified workload; template drift is not a release.
    app=json.loads(json.dumps(baseline));app.pop("status",None)
    for key in ["resourceVersion","uid","creationTimestamp","generation","managedFields"]:app["metadata"].pop(key,None)
    app["metadata"].get("annotations",{}).pop("kubectl.kubernetes.io/last-applied-configuration",None)
    appcontainer=next(c for c in app["spec"]["template"]["spec"]["containers"] if c["name"]=="app")
    appcontainer["image"]=a.image
    desired_gate=next(e for c in rendered["spec"]["template"]["spec"]["containers"] if c["name"]=="app" for e in c["env"] if e["name"]=="WATOOM_DEPLOYMENT_GATE_FILE")
    gate_entries=[e for e in appcontainer["env"] if e["name"]=="WATOOM_DEPLOYMENT_GATE_FILE"]
    if gate_entries and gate_entries!=[desired_gate]:raise release_guard.UnsafeRelease("Existing gate configuration differs")
    if not gate_entries:appcontainer["env"].append(desired_gate)
    config_desired=config_before
    if a.mesh_integration:
        app,config_desired=mesh_release.desired(app,rendered,json.loads(config_before),
            config.parent/"watoom-tools/watoom-llama-mesh.py",
            r/"ansible/roles/llm-model-lab/files/watoom-llama-mesh.py",
            vars["watoom_code_mesh_bridge_host"])
    def toolkit_native_guard():
        if baseline_native:
            release_guard.validate(get("/api/session/deployment-guard"),True)
            release_guard.active_clear(get("/api/session/active"))
        else:maintenance.verify_closed()
    creative=None
    if a.toolkit_image:
        creative=creative_release.Release(kub,cmd,r,out,a.toolkit_image,accepted,json.loads(config_desired),a.asset_catalog,native_guard=toolkit_native_guard)
        config_desired=json.dumps(creative.config,indent=2).encode()
    skills=None
    if a.skills_collection:
        if not a.i_approve:raise release_guard.UnsafeRelease("Skills integration requires --i-approve")
        if creative:raise release_guard.UnsafeRelease("Keep the already accepted Toolkit unchanged during Skills promotion")
        skills=skills_release.Release(r,out,accepted,a.skills_collection,json.loads(config_desired))
        config_desired=json.dumps(skills.config,indent=2).encode()
    defaults_desired=defaults_before
    pins_desired=re.sub(r"^watoom_code_image:.*$", 'watoom_code_image: "'+a.image+'"',pins_before,flags=re.M)
    if skills:
        if len(re.findall(r"^watoom_code_skills_enabled:.*$",defaults_desired,re.M))!=1:raise release_guard.UnsafeRelease("Skills feature setting required")
        defaults_desired=re.sub(r"^watoom_code_skills_enabled:.*$","watoom_code_skills_enabled: true",defaults_desired,flags=re.M)
    if a.mesh_integration:
        defaults_desired=re.sub(r"^watoom_code_mesh_enabled:.*$","watoom_code_mesh_enabled: true",defaults_desired,flags=re.M)
    if creative:
        if vars["watoom_code_toolkit_image"]!=creative.old:raise release_guard.UnsafeRelease("IaC Toolkit baseline differs from live")
        if len(re.findall(r"^watoom_code_toolkit_image:.*$",pins_desired,re.M))!=1:raise release_guard.UnsafeRelease("Unique Toolkit image pin required")
        pins_desired=re.sub(r"^watoom_code_toolkit_image:.*$", "watoom_code_toolkit_image: '"+a.toolkit_image+"'",pins_desired,flags=re.M)
        if len(re.findall(r"^watoom_code_toolkit_source_commit:.*$",pins_desired,re.M))!=1:raise release_guard.UnsafeRelease("Toolkit provenance setting required")
        pins_desired=re.sub(r"^watoom_code_toolkit_source_commit:.*$","watoom_code_toolkit_source_commit: "+creative.revision,pins_desired,flags=re.M)
        if len(re.findall(r"^watoom_code_creative_enabled:.*$",defaults_desired,re.M))!=1:raise release_guard.UnsafeRelease("Creative release feature setting required")
        defaults_desired=re.sub(r"^watoom_code_creative_enabled:.*$","watoom_code_creative_enabled: true",defaults_desired,flags=re.M)
        if creative.native:
            for name,value in {"watoom_code_dungeon_enabled":"true","watoom_code_unreal_root":creative.native["root"],"watoom_code_unreal_editor_sha256":creative.native["editor_sha256"]}.items():
                pattern=r"^"+name+r":.*$"
                if len(re.findall(pattern,defaults_desired,re.M))!=1:raise release_guard.UnsafeRelease("Unique native engine IaC field required")
                defaults_desired=re.sub(pattern,name+": "+value,defaults_desired,flags=re.M)
    (out/"opencode-desired.private.json").write_bytes(config_desired)
    (out/"deployment-desired.json").write_text(json.dumps(app,indent=2))
    cmd(["kubectl","apply","--dry-run=server","-f","-"],input=json.dumps(app).encode())
    def post(path,body):
        if maintenance:return maintenance.request(path,body)
        req=urllib.request.Request("http://"+ip+":4096"+path,headers={"Authorization":auth,"Content-Type":"application/json"},data=json.dumps(body).encode())
        with urllib.request.urlopen(req,timeout=15) as response:return json.load(response)
    def save_owner(owner):
        with (out/"guard-owner.private").open("x") as stream:
            stream.write(owner);stream.flush();os.fsync(stream.fileno())
    # Fence path must survive replacement, and be identical for baseline/candidate.
    def gate_path(deployment):
        return next((x.get("value") for x in deployment["spec"]["template"]["spec"]["containers"][0].get("env",[]) if x["name"]=="WATOOM_DEPLOYMENT_GATE_FILE"),None)
    if baseline_native and (not gate_path(baseline) or gate_path(baseline)!=gate_path(app)):raise release_guard.UnsafeRelease("Shared persistent fence path differs or missing")
    source_line=re.compile(r"^watoom_code_image_source_commit:.*$",re.M)
    if len(source_line.findall(pins_desired))!=1:raise release_guard.UnsafeRelease("Unique application image source setting required")
    pins_desired=source_line.sub("watoom_code_image_source_commit: "+source_commit,pins_desired)
    (out/"pins-desired.yml").write_text(pins_desired)
    # project_layout.yml owns each project group root as 1009:1009/2770 with an app ACL.
    workspace_probe=maintenance_guard.Maintenance(NS,"watoom-code",out,True,True)
    for group in vars["watoom_code_project_groups"]:
        workspace=pathlib.Path(vars["watoom_code_project_groups_root"])/group
        if not workspace.is_dir() or workspace.is_symlink() or (workspace.stat().st_uid,workspace.stat().st_gid,workspace.stat().st_mode & 0o7777)!=(1009,1009,0o2770):
            raise release_guard.UnsafeRelease("Project group "+group+" differs from maintained project-layout identity")
        access=json.loads(workspace_probe.exec("import os,json,sys;print(json.dumps({'uid':os.getuid(),'accessible':os.access(sys.argv[1],os.R_OK|os.W_OK|os.X_OK)}))",str(workspace)))
        if access!={"uid":vars["watoom_code_uid"],"accessible":True}:raise release_guard.UnsafeRelease("Application cannot access project group "+group)
    (out/"workspace-access.json").write_text(json.dumps(access,indent=2))
    changed=False
    def rollback():
        if kub("get","deploy","watoom-code")["spec"] not in (baseline["spec"],app["spec"]):raise release_guard.UnsafeRelease("Application changed during fenced rollback; refusing overwrite")
        restore=json.loads(json.dumps(baseline));restore.pop("status",None)
        for key in ["resourceVersion","uid","creationTimestamp","generation","managedFields"]:restore["metadata"].pop(key,None)
        annotations=restore["metadata"].get("annotations",{});annotations.pop("kubectl.kubernetes.io/last-applied-configuration",None)
        current=defaults.read_text()
        if current not in (defaults_desired,defaults_before):raise release_guard.UnsafeRelease("IaC defaults changed concurrently; refusing overwrite")
        atomic_write(defaults,defaults_before)
        if pins.read_text() not in (pins_desired,pins_before):raise release_guard.UnsafeRelease("IaC pins changed concurrently; refusing overwrite")
        atomic_write(pins,pins_before)
        if config.read_bytes() not in (config_desired,config_before):raise release_guard.UnsafeRelease("Application config changed concurrently; refusing rollback overwrite")
        atomic_write(config,config_before)
        if skills:skills.rollback()
        if creative:creative.rollback()
        cmd(["kubectl","apply","-f","-"],input=json.dumps(restore).encode())
        cmd(["kubectl","-n",NS,"rollout","status","deployment/watoom-code","--timeout=240s"],timeout=250)
        pods=kub("get","pods","-l","app=watoom-code")["items"]
        ids=[c["imageID"] for pod in pods if not pod["metadata"].get("deletionTimestamp") for c in pod.get("status",{}).get("containerStatuses",[]) if c["name"]=="app" and c.get("ready")]
        old=baseline["spec"]["template"]["spec"]["containers"][0]["image"]
        if len(ids)!=1 or ids[0].split("@")[-1]!=old.split("@")[-1]:raise release_guard.UnsafeRelease("Rollback image identity failed")
        if baseline_native:release_guard.runtime(get,old,old)
        else:
            release_guard.active_clear(get("/api/session/active"))
            if not isinstance(get("/api/info").get("version"),str):raise release_guard.UnsafeRelease("Baseline authenticated rollback failed")
            maintenance.verify_closed()
            clearance()
        if skills or a.engineering_tools:verify_existing_mcp()
        if creative:
            creative.verify_route(False)
            verify_existing_mcp()
        release_fence()
        (out/"rollback.json").write_text(json.dumps({"status":"PASS","restored_image":baseline["spec"]["template"]["spec"]["containers"][0]["image"]},indent=2))
    if baseline["spec"].get("replicas")!=1 or app["spec"].get("replicas")!=1 or baseline["spec"].get("strategy",{}).get("type")!="Recreate" or app["spec"].get("strategy",{}).get("type")!="Recreate":
        raise release_guard.UnsafeRelease("Guard protocol requires one Recreate process and persistent state volume")
    if gate_path(app)!="/state/watoom-release-guard.json":
        raise release_guard.UnsafeRelease("Fence path is outside the verified persistent state volume")
    state_before=next(x for x in baseline["spec"]["template"]["spec"]["volumes"] if x["name"]=="state")
    state_after=next(x for x in app["spec"]["template"]["spec"]["volumes"] if x["name"]=="state")
    if state_before!=state_after:raise release_guard.UnsafeRelease("Persistent state volume identity changed")
    guard_file=pathlib.Path("/data/ai/watoom-code/watoom-release-guard.json")
    def release_fence():
        if creative:creative.release_admission()
        if not maintenance:
            release_guard.release(get,post,owner);return
        # External admission remains closed while either native or bootstrap ownership is removed.
        if maintenance.held:maintenance.verify_closed()
        try:release_guard.validate(get("/api/session/deployment-guard"),True)
        except urllib.error.HTTPError:
            if json.loads(guard_file.read_text())!={"version":1,"owner":owner}:raise release_guard.UnsafeRelease("Bootstrap fence ownership mismatch")
            guard_file.unlink()
            fd=os.open(guard_file.parent,os.O_RDONLY)
            try:os.fsync(fd)
            finally:os.close(fd)
        else:release_guard.release(get,post,owner)
        if maintenance.held:maintenance.release()
        else:maintenance.restore_access()
    if maintenance:
        owner=secrets.token_hex(32);save_owner(owner)
        created=False
        try:
            maintenance.begin()
            deadline=time.monotonic()+20
            while True:
                try:maintenance.verify_closed();break
                except release_guard.UnsafeRelease:
                    if time.monotonic()>deadline:raise
                    time.sleep(.5)
            clearance()
            maintenance.pause_access()
            maintenance.drain(clearance,45)
            fd=os.open(guard_file,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            try:os.write(fd,json.dumps({"version":1,"owner":owner}).encode());os.fsync(fd)
            finally:os.close(fd)
            created=True
            os.chown(guard_file,1001,1009)
            fd=os.open(guard_file.parent,os.O_RDONLY)
            try:os.fsync(fd)
            finally:os.close(fd)
            maintenance.drain(clearance,10)
        except BaseException:
            if created:guard_file.unlink()
            if maintenance.held:maintenance.release()
            raise
    else:owner=release_guard.acquire(get,post,save_owner,clearance)
    try:
        for filename in ("application.sqlite","catalog.sqlite"):
            source=pathlib.Path("/data/ai/watoom-code")/filename
            if source.exists():
                release_guard.snapshot_database(source,out/(filename+".before"))
        with tarfile.open(out/"config-before.private.tar.gz","w:gz") as archive:archive.add(config.parent,arcname="config")
        with tarfile.open(out/"config-before.private.tar.gz") as archive:archive.getmembers()
        oldimage=baseline["spec"]["template"]["spec"]["containers"][0]["image"]
        olddigest=oldimage.split("@")[1]
        req=urllib.request.Request("http://127.0.0.1:5000/v2/watoom-code/manifests/"+olddigest,headers={"Accept":"application/vnd.oci.image.manifest.v1+json"})
        with urllib.request.urlopen(req,timeout=10) as response:raw=response.read()
        if "sha256:"+hashlib.sha256(raw).hexdigest()!=olddigest:raise release_guard.UnsafeRelease("Baseline immutable manifest mismatch")
        (out/"baseline-registry-manifest.json").write_bytes(raw)
        metadata=json.loads(raw)
        for blob in [metadata["config"],*metadata["layers"]]:
            with urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:5000/v2/watoom-code/blobs/"+blob["digest"],method="HEAD"),timeout=10) as response:
                if response.status!=200:raise release_guard.UnsafeRelease("Rollback blob unavailable")
        manifest={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in out.iterdir() if path.is_file() and not path.name.endswith(("-wal","-shm"))}
        (out/"snapshot-sha256.json").write_text(json.dumps(manifest,indent=2))
        clearance()
        image_line=re.compile(r"^watoom_code_image:.*$",re.M)
        if len(image_line.findall(pins_before))!=1:raise ValueError("IaC image setting is not unique")
        if defaults.read_text()!=defaults_before or pins.read_text()!=pins_before:raise release_guard.UnsafeRelease("IaC defaults changed concurrently; refusing overwrite")
        if kub("get","deploy","watoom-code")["spec"]!=baseline["spec"]:raise release_guard.UnsafeRelease("Application configuration changed concurrently; refusing overwrite")
        if config.read_bytes()!=config_before:raise release_guard.UnsafeRelease("Application configuration changed concurrently")
        changed=True
        if skills:skills.apply(atomic_write)
        if creative:creative.apply(atomic_write)
        atomic_write(defaults,defaults_desired)
        atomic_write(pins,pins_desired)
        atomic_write(config,config_desired)
        cmd(["kubectl","apply","-f","-"],input=json.dumps(app).encode())
        cmd(["kubectl","-n",NS,"rollout","status","deployment/watoom-code","--timeout=240s"],timeout=250)
        pods=kub("get","pods","-l","app=watoom-code")["items"]
        running=[x for x in pods if x.get("status",{}).get("phase")=="Running" and not x["metadata"].get("deletionTimestamp")]
        if len(running)!=1:raise RuntimeError("App pod identity ambiguous")
        actual=next(x for x in running[0]["status"]["containerStatuses"] if x["name"]=="app")
        if actual["imageID"].split("@")[-1]!=a.image.split("@")[-1]:raise RuntimeError("Running digest mismatch")
        deadline=time.monotonic()+60
        while True:
            try:models=get("/api/model")["data"]
            except urllib.error.HTTPError as error:
                # The new app answers 503 until router discovery settles; keep polling inside the same deadline.
                if error.code!=503 or time.monotonic()>=deadline:raise
                time.sleep(0.25);continue
            enabled={x["id"] for x in models if x["providerID"]=="watoom" and x["enabled"]}
            if len(enabled)>=9 and {"swift-qwen38-coder","gemma-4-e4b","llama-mesh","active-model"}.issubset(enabled):break
            if time.monotonic()>=deadline:raise RuntimeError("Router discovery did not settle within 60 seconds")
            time.sleep(0.25)
        (out/"models-after.json").write_text(json.dumps(models,indent=2))
        local={x["id"] for x in models if x["providerID"]=="watoom" and x["enabled"]}
        if not {"swift-qwen38-coder","gemma-4-e4b","llama-mesh","active-model"}.issubset(local):raise RuntimeError("Native router catalog incomplete")
        before=json.loads((out/"models-before.json").read_text())["data"]
        free_ids={x["id"] for x in before if x["providerID"]=="opencode" and x["enabled"]}
        after_free={x["id"] for x in models if x["providerID"]=="opencode" and x["enabled"]}
        if not free_ids.issubset(after_free):raise RuntimeError("Existing OpenCode free models lost")
        expected_models={(x["providerID"],x["id"]) for x in before if x["enabled"]}
        deadline=time.monotonic()+45
        while not expected_models.issubset({(x["providerID"],x["id"]) for x in models if x["enabled"]}):
            if time.monotonic()>deadline:raise RuntimeError("Existing enabled provider models lost")
            time.sleep(.5)
            models=get("/api/model")["data"]

        try:get("/api/config",False)
        except urllib.error.HTTPError as error:
            if error.code!=401:raise
        else:raise RuntimeError("Authentication boundary regressed")
        release_guard.runtime(get,a.image,actual["imageID"].split("@")[0]+"@"+actual["imageID"].split("@")[-1])
        commands=get("/api/command?directory=/workspace")["data"]
        if not {"remember","recall"}.issubset({x["name"] for x in commands}):raise release_guard.UnsafeRelease("Authoritative memory command registry unavailable")
        if a.engineering_tools:
            client=maintenance_guard.Maintenance(NS,"watoom-code",out,True,True)
            code="import pathlib,hashlib,subprocess,sys;assert hashlib.sha256(pathlib.Path('/usr/local/bin/opencode').read_bytes()).hexdigest()==sys.argv[1];subprocess.run(['python3','/opt/watoom-engineering/smoke.py'],check=True,timeout=90)"
            (out/"engineering-runtime.log").write_bytes(client.exec(code,accepted["application_binary_sha256"]))
            verify_existing_mcp()
        if a.mesh_integration:
            deadline=time.monotonic()+45
            while True:
                statuses=get("/api/mcp?directory=/workspace")["data"]
                if any(x["name"]=="watoom-llama-mesh" and x["status"]["status"]=="connected" for x in statuses):break
                if time.monotonic()>deadline:raise release_guard.UnsafeRelease("Mesh MCP did not become application-ready")
                time.sleep(.5)
        if maintenance:
            release_guard.release(get,post,owner)
            try:
                validator=r/"tools/watoom-code/validate-live-memory.py"
                playwright="/data/ai/projects/llm/watoom-code/native-next-review-20261014T212958Z/source/node_modules/.bun/playwright@1.59.1/node_modules/playwright"
                with (out/"live-memory-runner.log").open("wb") as log:
                    result=bounded_process.run(["python3",str(validator),"--deployment","watoom-code","--evidence",str(out/"live-memory"),"--playwright-module",playwright],stdout=log,stderr=subprocess.STDOUT,timeout=180)
                if result.returncode:raise release_guard.UnsafeRelease("Live authenticated memory API/GUI validation failed")
            finally:
                release_guard.validate(post("/api/session/deployment-guard",{"action":"acquire","owner":owner}),True)
            maintenance.drain(clearance,20)
            # Public-route validation occurs with native admission still held.
            maintenance.release(restore_access=False)
            tls=kub("get","secret","watoom-code-lan-tls")["data"]
            cert=base64.b64decode(tls.get("ca.crt",tls["tls.crt"]))
            context=ssl.create_default_context(cadata=cert.decode());context.verify_flags|=ssl.VERIFY_X509_PARTIAL_CHAIN
            public="https://watoom-code.internal.homelab.example"
            def published(path):
                request=urllib.request.Request(public+path,headers={"Authorization":auth})
                with urllib.request.urlopen(request,context=context,timeout=20) as response:return json.load(response)
            if not isinstance(published("/api/info").get("version"),str):raise release_guard.UnsafeRelease("Traefik application readiness failed")
            commands=published("/api/command?directory=/workspace")["data"]
            if not {"remember","recall"}.issubset({x["name"] for x in commands}):raise release_guard.UnsafeRelease("Public command registry failed")
            pubkey=cmd(["openssl","x509","-pubkey","-noout"],input=base64.b64decode(tls["tls.crt"]))
            der=cmd(["openssl","pkey","-pubin","-outform","DER"],input=pubkey)
            spki=base64.b64encode(hashlib.sha256(der).digest()).decode()
            smoke=json.loads((out/"live-memory/live-memory-validation.json").read_text())
            env={**os.environ,"PLAYWRIGHT_MODULE":playwright,"CANDIDATE_PASSWORD":maintenance.password,"CANDIDATE_BASE":public,"EVIDENCE":str(out/"live-memory"),"MEMORY_ROUTE_SESSION":smoke["sessions"][-1],"MEMORY_GUI_FACT":"Owned GUI release validation "+smoke["directory"].split("agentmemory-")[-1],"TRUSTED_TLS_SPKI":spki}
            with (out/"traefik-browser-runner.log").open("wb") as log:
                result=bounded_process.run(["node",str(r/"tools/watoom-code/agentmemory-browser.cjs")],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=90)
            if result.returncode:raise release_guard.UnsafeRelease("Authenticated Traefik GUI validation failed")
            release_guard.validate(get("/api/session/deployment-guard"),True)
            maintenance.keep_access_stopped=a.leave_forwarding_stopped
        if baseline_native:
            with (out/"native-fenced-gui-runner.log").open("wb") as log:
                result=bounded_process.run(["python3",str(r/"tools/watoom-code/validate-fenced-gui.py"),"--evidence",str(out/"native-gui"),"--fixture",str(a.native_gui_fixture)],stdout=log,stderr=subprocess.STDOUT,timeout=120)
            if result.returncode:raise release_guard.UnsafeRelease("Fenced authenticated public API/GUI validation failed")
        root=accepted.get("acceptance_root","isolated-candidate")
        report={"status":"PASS","image":a.image,"running_image_id":actual["imageID"],"local_models":sorted(local),"free_models":sorted(after_free),"acceptance_root":root}
        if a.engineering_tools:report["engineering_tools"]="PASS"
        if creative:
            creative.verify(a.toolkit_image)
            creative.verify_route()
            verify_existing_mcp()
            if any(path.read_bytes()!=new for path,old,new in creative.agents):raise release_guard.UnsafeRelease("Deployed managed agents differ")
            report.update({"toolkit_image":a.toolkit_image,"all_six_agents":"PASS","creative_candidate_acceptance":"PASS"})
        if skills:
            report.update(skills.verify(get))
            verify_existing_mcp()
            with (out/"skills-public-gui.log").open("wb") as log:
                result=bounded_process.run(["python3",str(r/"tools/watoom-code/validate-skills-gui.py"),"--evidence",str(out/"skills-public-gui")],stdout=log,stderr=subprocess.STDOUT,timeout=180)
            if result.returncode:raise release_guard.UnsafeRelease("Authenticated public Skills navigation/page validation failed")
            report["skills_authenticated_gui"]="PASS"
        if a.prompt_builder:
            normalize=lambda entries:{x["id"]:hashlib.sha256(re.sub(r"^- (opencode version|install/channel):.*$","",x["content"],flags=re.M).encode()).hexdigest() for x in entries}
            if normalize(get("/api/skill?directory=/workspace")["data"])!=normalize(native_before):raise release_guard.UnsafeRelease("Native skills changed during prompt-page promotion")
            verify_existing_mcp()
            with (out/"prompt-builder-public-gui.log").open("wb") as log:
                result=bounded_process.run(["python3",str(r/"tools/watoom-code/validate-prompt-builder.py"),"--evidence",str(out/"prompt-builder-public-gui")],stdout=log,stderr=subprocess.STDOUT,timeout=180)
            if result.returncode:raise release_guard.UnsafeRelease("Published prompt builder validation failed")
            report["prompt_builder"]="PASS"
        (out/"release.json").write_text(json.dumps(report,indent=2))
        release_ledger.append(a.image,source_commit,r,"deploy-platform",out)
    except Exception:
        if maintenance and not maintenance.held:
            maintenance.begin()
            deadline=time.monotonic()+20
            while True:
                try:maintenance.verify_closed();break
                except release_guard.UnsafeRelease:
                    if time.monotonic()>deadline:raise
                    time.sleep(.5)
            maintenance.drain(clearance,20)
        if changed:rollback()
        else:release_fence()
        raise
    # Release only after the validated result is durable. Failure here retains recovery
    # evidence; never roll back a healthy deployment after admissions may reopen.
    release_fence()
    print(json.dumps(report,indent=2))
if __name__=="__main__":
    try:main()
    except release_guard.UnsafeRelease as error:
        print("RESULT=BLOCKED\nREASON="+str(error))
        raise SystemExit(2)
