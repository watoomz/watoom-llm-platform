#!/usr/bin/env python3
"""Read-only verification of maintained WatooM changes against deployed state.
Never emits credentials, skill contents, Kubernetes secrets or configuration bodies.
"""
import argparse, hashlib, json, pathlib, re, subprocess, sys
import yaml

ROOT=pathlib.Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser()
p.add_argument("--evidence",required=True,type=pathlib.Path)
a=p.parse_args()
checks={}
def run(args,cwd=None):
    return subprocess.check_output(args,cwd=cwd,stderr=subprocess.PIPE,timeout=30)
def check(name,value):
    checks[name]="PASS" if value else "FAIL"
def digest(path):
    return hashlib.sha256(path.read_bytes()).digest()
def kub(namespace,kind,name):
    return json.loads(run(["kubectl","-n",namespace,"get",kind,name,"-o","json"]))
app=yaml.safe_load((ROOT/"ansible/roles/watoom-code/defaults/main.yml").read_text())
app.update(yaml.safe_load((ROOT/"ansible/vars/watoom-code.yml").read_text()))
kali=yaml.safe_load((ROOT/"ansible/roles/pi-kali-agent/defaults/main.yml").read_text())
wb=yaml.safe_load((ROOT/"ansible/roles/watoom-kali-workbench-mcp/defaults/main.yml").read_text())
for name,key in [("watoom-code","watoom_code_image"),("watoom-toolkit","watoom_code_toolkit_image")]:
    deploy=kub("watoom-code","deployment",name)
    check(name+" immutable image",app[key] in [c["image"] for c in deploy["spec"]["template"]["spec"]["containers"]])
memory=kub("watoom-code","deployment","agentmemory")
live_env={e["name"]:e.get("value") for c in memory["spec"]["template"]["spec"]["containers"] for e in c.get("env",[])}
check("agentmemory embeddings match production vars",all((live_env.get(e["name"])==e["value"].replace("{{ watoom_code_memory_embedding_url }}",app["watoom_code_memory_embedding_url"])) if app["watoom_code_memory_embeddings"] else e["name"] not in live_env for e in app["watoom_code_memory_embedding_env"]))
sys.path.insert(0,str(ROOT/"tools/watoom-code"))
import release_ledger
latest=release_ledger.latest()
check("deployed application source pin",bool(latest) and latest["image"]==app["watoom_code_image"] and latest["source_commit"]==app["watoom_code_image_source_commit"])
for name in ["watoom-workflow","watoom-builder","watoom-investigator","watoom-reviewer","watoom-critic","watoom-kali"]:
    src=ROOT/"ansible/roles/opencode-agent/files/v2-native/agents"/(name+".md")
    dst=pathlib.Path("/data/ai/watoom-code/config/agents")/(name+".md")
    # Mirror native_agents.yml: lookup(file) rstrips, then the model block is removed.
    rendered=re.sub(r"(?m)^model:\n  providerID: watoom\n  model: [A-Za-z0-9_.-]+\n","",src.read_text().rstrip())
    check("agent "+name,rendered==dst.read_text())
# Byte comparison only: owner-sensitive instructions are never interpreted or printed.
for name in app["watoom_code_native_skills"]:
    src=ROOT/"ansible/roles/watoom-code/files/skills"/name
    dst=pathlib.Path("/data/ai/watoom-code/config/skills")/name
    files=[f for f in src.rglob("*") if f.is_file()]
    check("native skill "+name,bool(files) and all((dst/f.relative_to(src)).is_file() and digest(f)==digest(dst/f.relative_to(src)) for f in files))
for name in ["redhat-source.json","redhat-LICENSE","plurigrid-source.json","plurigrid-LICENSE"]:
    check("skill provenance "+name,digest(ROOT/"ansible/roles/watoom-code/files/skills"/name)==digest(pathlib.Path("/data/ai/watoom-code/config/skills")/name))
deploy=kub(wb["watoom_kali_workbench_namespace"],"deployment",wb["watoom_kali_workbench_name"])
spec=deploy["spec"]["template"]["spec"]
cmname=next(v["configMap"]["name"] for v in spec["volumes"] if v["name"]=="source")
cm=kub(wb["watoom_kali_workbench_namespace"],"configmap",cmname)
check("Kali MCP implementation",hashlib.sha256(cm["data"]["workbench-mcp.mjs"].encode()).digest()==digest(ROOT/"ansible/roles/watoom-kali-workbench-mcp/files/workbench-mcp.mjs"))
template=(ROOT/"ansible/roles/watoom-kali-workbench-mcp/templates/workbench-mcp.yaml.j2").read_text()
check("Kali WatooM Code registration ingress maintained",wb["watoom_kali_workbench_allow_watoom_code"] and "watoom-code" in template)
runtime=json.loads(run(["docker","inspect",kali["kali_workbench_container"]]))[0]
host=runtime["HostConfig"]
check("Kali runtime image",runtime["Config"]["Image"]==kali["kali_workbench_image"])
check("Kali capabilities",host["CapDrop"]==["ALL"] and set(host["CapAdd"])=={"CAP_NET_RAW","CAP_NET_BIND_SERVICE"} and not host["Privileged"])
check("Kali isolation",host["NetworkMode"]=="bridge" and "no-new-privileges:true" in host["SecurityOpt"] and runtime["ProcessLabel"].startswith("system_u:system_r:container_t:"))
check("Kali resource envelope",all(host[k]==kali[v] for k,v in [("Memory","kali_runtime_memory_bytes"),("MemorySwap","kali_runtime_memory_swap_bytes"),("NanoCpus","kali_runtime_nano_cpus"),("PidsLimit","kali_runtime_pids_limit")]))
check("Kali persistent mount",any(m["Source"]==kali["kali_workbench_data_dir"] and m["Destination"]=="/work" and m["RW"] for m in runtime["Mounts"]))
for name in ["metasploit-db.py","watoom-kali-metasploit-db.service","watoom-kali-metasploit-db.timer"]:
    dst=pathlib.Path("/data/ai/helper-scripts/kali-metasploit-db.py") if name.endswith(".py") else pathlib.Path("/etc/systemd/system")/name
    check("Metasploit "+name,digest(ROOT/"tools/kali"/name)==digest(dst))
check("Metasploit restart timer",run(["systemctl","is-enabled","watoom-kali-metasploit-db.timer"]).strip()==b"enabled")
candidate=json.loads((ROOT/"tools/watoom-code/engineering/release.json").read_text())
check("engineering release state",
    candidate["image"]==app["watoom_code_image"] and candidate["application_source_commit"]==app["watoom_code_image_source_commit"]
    if candidate["status"]=="DEPLOYED"
    else candidate.get("superseded_by") in {e["image"] for e in release_ledger.entries()} if candidate["status"]=="SUPERSEDED"
    else candidate["status"]=="CANDIDATE_ACCEPTED_PROMOTION_PENDING" and candidate["previous_image"]==app["watoom_code_image"])
check("engineering toolchain pinned",(ROOT/"tools/watoom-code/Containerfile").read_text().count("FROM "+candidate["toolchain_image"])==1)
check("secrets remain ignored",subprocess.run(["git","check-ignore","--quiet",".private/service-logins.md"],cwd=ROOT).returncode==0)
maintained=[
"tools/watoom-code/engineering/Containerfile","tools/watoom-code/engineering/smoke.py","tools/watoom-code/engineering/build.py","tools/watoom-code/engineering/candidate.py",
"tools/unreal/recover-editor.py","tools/unreal/render-editor.py","tools/unreal/render-probe.py","tools/unreal/continue-render.py","tools/unreal/lend-render-capacity.py",
"tools/watoom-toolkit/dungeon_layout.py","tools/watoom-toolkit/dungeon_pipeline.py","tools/watoom-toolkit/dungeon_unreal.py","tools/watoom-code/source/watoom-code-dungeon.patch",
"tools/fab/download-owned.py","ansible/playbooks/kali-metasploit-db.yml"]
tracked=run(["git","ls-files","--",*maintained],ROOT).decode().splitlines()
check("recovery pipeline download and engineering sources tracked",set(tracked)==set(maintained))
report={"status":"PASS" if all(v=="PASS" for v in checks.values()) else "FAIL","checks":checks,
"engineering_deployment":candidate["status"],"Unreal":"COMPILED_ACCEPTANCE_PENDING","dungeon":"SOURCE_CANDIDATE_NATIVE_ACCEPTANCE_PENDING",
"runtime_changed":False,"secrets_or_skill_contents_emitted":False}
a.evidence.parent.mkdir(parents=True,exist_ok=True)
a.evidence.write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps({"status":report["status"],"checks":len(checks),"failed":[k for k,v in checks.items() if v=="FAIL"],"evidence":str(a.evidence)}))
sys.exit(0 if report["status"]=="PASS" else 1)
