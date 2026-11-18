#!/usr/bin/env python3
"""Read-only WatooM Blender readiness audit. Python stdlib, no installs/fetches/mutations of host configuration."""
import datetime, hashlib, json, os, pathlib, re, shutil, subprocess, sys, time
BASE=pathlib.Path('/data/ai/helper-scripts'); REPO=pathlib.Path('/data/github/watoom-standardised-homelab/standardised_k3s_project')
TS=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
OUT=BASE/'audits'/('blender-'+TS+'-'+str(os.getpid()))
try: OUT.mkdir(parents=True,mode=0o700,exist_ok=False)
except Exception as e: print('BLOCKED: cannot create private audit output:',str(e));sys.exit(2)
os.chmod(OUT,0o700)
CAP=OUT/'captures';CAP.mkdir(mode=0o700)
items=[]
SEC=re.compile(r'(?i)(password|token|secret|apikey|api_key|authorization|bearer|private.key|credential|cookie|session[_-]?key)')
def redact(v):
 s=str(v)
 lines=[]
 for line in s.splitlines():
  if SEC.search(line): lines.append('[REDACTED sensitive line]')
  else: lines.append(line[:700])
 return '\n'.join(lines)[:14000]
def check(cid,status,reason,evidence='',fix=''):
 items.append({'id':cid,'status':status,'reason':reason,'evidence':redact(evidence),'fix_class':fix})
def call(cid,args,timeout=12,mask=False):
 if not shutil.which(args[0]):check(cid,'BLOCKED','command not installed: '+args[0]);return None
 try:
  p=subprocess.run(args,capture_output=True,text=True,timeout=timeout,env={**os.environ,'GIT_PAGER':'cat','PAGER':'cat'},stdin=subprocess.DEVNULL)
  value=redact(p.stdout+'\n'+p.stderr)
  (CAP/(cid+'.txt')).write_text(value+'\n')
  os.chmod(CAP/(cid+'.txt'),0o600)
  check(cid,'PASS' if p.returncode==0 else 'WARN','exit='+str(p.returncode),value[:2400])
  return p.stdout if p.returncode==0 else None
 except subprocess.TimeoutExpired:check(cid,'BLOCKED',f'timeout {timeout}s');return None
 except Exception as e:check(cid,'BLOCKED',type(e).__name__+': '+str(e));return None

def read_file(cid,path,limit=8000):
 try:
  f=pathlib.Path(path)
  if not f.is_file():check(cid,'NOT TESTED','file absent: '+str(path));return None
  s=f.read_text(errors='replace')[:limit];check(cid,'PASS','file accessible',s[:1500]);return s
 except Exception as e:check(cid,'BLOCKED',str(e));return None
call('HOST-IDENTITY',['uname','-a']);call('HOST-OS',['cat','/etc/os-release']);call('HOST-DISK',['df','-hT','/data','/app','/']);call('HOST-FREE',['free','-h']);call('HOST-SWAP',['swapon','--show']);call('HOST-MOUNTS',['findmnt','-T','/data','-o','TARGET,SOURCE,FSTYPE,OPTIONS']);call('HOST-SELINUX',['getenforce']);call('HOST-GPU',['nvidia-smi','--query-gpu=name,memory.total,memory.used,power.limit,temperature.gpu,utilization.gpu,driver_version','--format=csv,noheader'],20);call('HOST-GPU-PROCS',['nvidia-smi','--query-compute-apps=pid,process_name,used_gpu_memory','--format=csv'],20)
call('HOST-PRESSURE',['cat','/proc/pressure/memory']);call('HOST-UPTIME',['uptime']);call('HOST-PROCESSES',['ps','-eo','pid,comm,rss','--sort=-rss']);call('HOST-LOGS',['journalctl','-k','-n','100','--no-pager'],14)
call('HOST-RECOVERY',['systemctl','list-timers','--all','--no-pager'],10)
call('HOST-LABELS',['ls','-ldZ','/data','/data/ai','/data/ai/projects','/data/ai/helper-scripts','/app'],10)
call('GIT-HEAD',['git','-C',str(REPO),'rev-parse','HEAD']);call('GIT-STATUS',['git','-C',str(REPO),'status','--short']);call('GIT-DIFF-STAT',['git','-C',str(REPO),'diff','--stat']);call('GIT-REMOTES',['git','-C',str(REPO),'remote','-v'])
# Store a redacted patch for investigative context, never print or expose credentials.
patch=call('GIT-PATCH-SANITISED',['git','-C',str(REPO),'diff','--','tools','config','manifests','scripts'],20)
if patch:
 (OUT/'git-patch-redacted.txt').write_text(redact(patch));os.chmod(OUT/'git-patch-redacted.txt',0o600)
call('K3S-NODES',['kubectl','get','nodes','-o','wide'],18);call('K3S-PODS',['kubectl','get','pods','-A','-o','wide'],22);call('K3S-WORKLOADS',['kubectl','get','deployments','-A','-o','wide'],18);call('K3S-RECENT-EVENTS',['kubectl','get','events','-A','--sort-by=.lastTimestamp'],22)
call('K3S-LLM-ARGS',['kubectl','-n','llama-cpp','get','deployment','llama-cpp-swift-qwen38-coder','-o','jsonpath={.spec.template.spec.containers[*].args}'],16)
call('K3S-TOP',['kubectl','top','pods','-A','--sort-by=memory'],20)
call('K3S-RBAC',['kubectl','auth','can-i','update','deployments','-n','llama-cpp'],16)
call('K3S-ROUTER',['kubectl','get','configmaps','-A','-o','custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name'],18)
# no secrets/env values collected by design
call('TOOLS-BLENDER',['which','blender']);ver=call('TOOLS-BLENDER-VERSION',['blender','--version'],12)
if ver and not re.search(r'Blender\s+5\.(?:[2-9]|\d{2,})',ver):check('TOOLS-BLENDER-API','WARN','EL4CTEO targets Blender 5.2+; version needs compatibility verification',ver[:200])
else:check('TOOLS-BLENDER-API','PASS' if ver else 'NOT TESTED','Version meets rough requirement' if ver else 'Could not verify Blender version')
for id,exe in [('TOOLS-PYTHON','python3'),('TOOLS-FFMPEG','ffmpeg'),('TOOLS-GODOT','godot'),('TOOLS-UNREAL','UnrealEditor'),('TOOLS-OPENCODE','opencode'),('TOOLS-GIT','git'),('TOOLS-NODE','node'),('TOOLS-UV','uv'),('TOOLS-BPY','blender')]:
 found=shutil.which(exe);check(id,'PASS' if found else 'NOT TESTED','executable: '+str(found))
for cid,p in [('PROJECT-MAGPIE','/data/ai/projects/games/magpie-flight'),('PROJECT-WOMBAT','/data/ai/projects/games/wombat-australia'),('PROJECT-BLENDER','/data/ai/projects/blender-assets'),('ENGINE-UNREAL','/data/ai/assets/unreal-engine'),('ASSET-FAB','/data/ai/assets/fab'),('WORKSPACE','/data/ai/projects'),('STAGING','/data/ai/helper-scripts/watoom-blender-asset-builder')]:
 x=pathlib.Path(p);check(cid,'PASS' if x.exists() else 'NOT TESTED','exists='+str(x.exists()),str(x))
for label,root in [('SKILLS-OPENCODE','/home/opencode/.config/opencode'),('SKILLS-AGENTS','/home/opencode/.agents/skills'),('SKILLS-ROOT','/root/.agents/skills'),('AGENTMEMORY-DATA','/data/ai')]:
 p=pathlib.Path(root);check(label,'PASS' if p.exists() else 'NOT TESTED','exists='+str(p.exists()),str(p))
call('OPENCODE-VERSIONS',['kubectl','get','deployments','-A','-o','custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name,IMAGE:.spec.template.spec.containers[*].image'],18)
call('OPENCODE-JOBS',['kubectl','get','jobs','-A','-o','wide'],18)
call('SELINUX-DENIALS',['ausearch','-m','avc','-ts','recent'],12)
# discover vendoring only, no internet traffic
pack=pathlib.Path(__file__).resolve().parent.parent
for name in ['EL4CTEO__blender-skills','arjun988__blender-skills','nicceasy__3d-product','kevinbadi__blender-skills']:
 x=pack/'upstream'/name;check('VENDOR-'+name,'PASS' if (x/'.git').exists() or (x/'README.md').exists() else 'NOT TESTED','local upstream present='+str(x.exists()),str(x),'upstream-vendor')
summary={'timestamp_utc':TS,'host':'read-only local inspection','audit_dir':str(OUT),'checks':items,'counts':{s:sum(i['status']==s for i in items) for s in ['PASS','FAIL','WARN','BLOCKED','NOT TESTED']},'limits':['No daemon/container environment variables or Kubernetes Secrets read','No full 128K inference smoke run; GPU busy rule','No network access or downloads','Not proof of live Blender/Godot/Unreal end-to-end integration']}
(OUT/'report.json').write_text(json.dumps(summary,indent=2));os.chmod(OUT/'report.json',0o600)
ordered=sorted(items,key=lambda x:['FAIL','WARN','BLOCKED','NOT TESTED','PASS'].index(x['status']))
md=['# WatooM Blender Readiness Audit','',f'UTC: {TS}',f'Output: `{OUT}`','', '## Findings (FAIL/WARN first)','']
for i in ordered:md.append(f"- **{i['id']}** [{i['status']}]: {i['reason']}")
md+=['','## Evidence snippets','']
for i in ordered:
 if i['status']!='PASS' and i['evidence']:md.extend(['### '+i['id'],'```text',i['evidence'][:900],'```'])
md+=['','## Unknowns','']+['- '+v for v in summary['limits']]
(OUT/'report.md').write_text('\n'.join(md)+'\n');os.chmod(OUT/'report.md',0o600)
print('AUDIT_DIR='+str(OUT))
print('STATUS_COUNTS='+json.dumps(summary['counts']))
print('APPLICABLE_FIX_CLASSES='+(','.join(sorted({i['fix_class'] for i in items if i['fix_class'] and i['status']!='PASS'})) or 'none'))
print('NOTE=Audit does not change running workloads.')
