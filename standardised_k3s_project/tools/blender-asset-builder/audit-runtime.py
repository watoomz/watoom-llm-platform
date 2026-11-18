#!/usr/bin/env python3
"""Read-only bounded host/container audit. Writes redacted evidence only."""
import pathlib,json,subprocess,datetime,os,re,hashlib,sys
P=pathlib.Path(__file__).resolve().parent.parent;ts=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=P/'evidence'/('audit-'+ts+'-'+str(os.getpid()));out.mkdir(parents=True,mode=0o700);os.chmod(out,0o700);checks=[]
def redact(s):
 return '\n'.join('[REDACTED]' if re.search(r'(?i)password|secret|authorization|api.?key|bearer|credential',line) else line[:1400] for line in s.splitlines())[-18000:]
def check(i,cmd,timeout=20):
 try:
  r=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout);data=redact(r.stdout+'\n'+r.stderr);f=out/(i+'.txt');f.write_text(data);f.chmod(0o600);checks.append(dict(id=i,status='PASS' if r.returncode==0 else 'WARN',returncode=r.returncode,evidence=f.name,sha256=hashlib.sha256(data.encode()).hexdigest()))
 except Exception as e:checks.append(dict(id=i,status='BLOCKED',reason=type(e).__name__))
def host(i,cmd,t=20):check(i,cmd,t)
def pod(i,cmd,t=25):check(i,['kubectl','-n','opencode','exec','deployment/opencode-v2-canary','--',*cmd],t)
host('HOST-OS',['cat','/etc/os-release']);host('HOST-RESOURCES',['free','-h']);host('HOST-STORAGE',['df','-h','/data']);host('HOST-GPU',['nvidia-smi','--query-gpu=uuid,name,memory.used,memory.total,utilization.gpu,power.limit,clocks.max.sm,clocks.max.memory','--format=csv,noheader']);host('HOST-GPU-JOBS',['nvidia-smi','--query-compute-apps=pid,process_name,used_gpu_memory','--format=csv'])
repo='/data/github/watoom-standardised-homelab/standardised_k3s_project'
host('GIT-HEAD',['git','-C',repo,'rev-parse','HEAD']);host('GIT-STATUS',['git','-C',repo,'status','--short']);host('GIT-INDEX',['git','-C',repo,'diff','--cached','--name-only'])
host('K3S-PODS',['kubectl','get','pods','-A','-o','wide']);host('K3S-RESOURCES',['kubectl','top','pods','-A'],30)
host('K3S-IMAGES',['kubectl','get','pods','-A','-o','custom-columns=NS:.metadata.namespace,NAME:.metadata.name,IMAGES:.status.containerStatuses[*].imageID,RESTARTS:.status.containerStatuses[*].restartCount'])
host('INFERENCE-SPEC',['kubectl','-n','llama-cpp','get','deployment','llama-cpp-swift-qwen38-coder','-o','jsonpath={.spec.template.spec.containers[*].image}{.spec.template.spec.containers[*].args}{.spec.replicas}'])
host('OPENCODE-MOUNTS',['kubectl','-n','opencode','get','deployment','opencode-v2-canary','-o','jsonpath={.spec.template.spec.volumes}{.spec.template.spec.containers[*].volumeMounts}'])
host('ADMISSION-SOURCES',['find','/data/ai/helper-scripts','-maxdepth','1','-iname','*gpu*'])
pod('BLENDER-VERSION',['blender','--version']);pod('GODOT-VERSION',['/workspace/.tools/bin/godot','--version']);pod('BLENDER-PYTHON',['blender','-b','--factory-startup','-t','2','--python-exit-code','1','--python-expr',"import bpy,json; print(json.dumps({'version':bpy.app.version_string,'python':__import__('sys').version,'addons':list(bpy.context.preferences.addons.keys())}))"],45)
pod('OPENCODE-VERSION',['opencode','--version']);pod('OPENCODE-AGENTS',['opencode','debug','agents'])
pod('UNREAL-EXECUTABLES',['find','/unreal-engine','-maxdepth','5','-type','f','-name','UnrealEditor*'],35)
pod('MEMORY-HEALTH',['python3','-c',"import os,urllib.request; r=urllib.request.Request(os.environ['AGENTMEMORY_URL'].rstrip('/')+'/agentmemory/health',headers={'Authorization':'Bearer '+os.environ['AGENTMEMORY_SECRET']}); print(urllib.request.urlopen(r,timeout=10).status)"])
host('MEMORY-STORAGE',['kubectl','-n','opencode','get','deployment','agentmemory','-o','jsonpath={.spec.template.spec.volumes}{.spec.template.spec.containers[*].image}'])
meta=P/'implementation/latest.json'
if meta.exists():
 m=json.loads(meta.read_text());r=pathlib.Path(m['host_root'])
 pod('CANARY-SKILL',['python3','-c',"import sys;sys.path.insert(0,'/workspace');from api_probe import api;d=api('/api/skill?location%5Bdirectory%5D="+m['container_root']+"');s=[{'id':x['id'],'path':x['path']} for x in d['data'] if x['id']=='watoom-blender-asset-builder'];print(__import__('json').dumps(s));assert s"])
 for cid,file,key in [('PIPELINE-QA','reports/quality.json','technical_pass'),('GODOT-IMPORT','engine-validation/result.json','status'),('VISUAL-REVIEW','reports/visual-review.json','status'),('MEMORY-REUSE','reports/memory-reuse.json','status'),('CANARY-AGENT','reports/agent-smoke.json','status'),('ROLLBACK-VALIDATION','reports/rollback-test.json','status')]:
  f=r/file
  if not f.exists():checks.append(dict(id=cid,status='NOT TESTED',reason='missing evidence'));continue
  d=json.loads(f.read_text());v=d.get(key);checks.append(dict(id=cid,status='PASS' if v is True or v=='PASS' else 'FAIL',evidence=str(f)))
 checks.append(dict(id='UNREAL-IMPORT',status='NOT TESTED',reason='no commandlet proven; FBX is export evidence only'))
 checks.append(dict(id='RIG-ANIMATION',status='NOT TESTED',reason='static fallback'))
 checks.append(dict(id='REFERENCE-MATCH',status='NOT TESTED',reason='no independently measured photographic ratios'))
 checks.append(dict(id='AUTONOMOUS-COMPLETE',status='BLOCKED',reason='deterministic magpie recipe tested; general reference-driven autonomous authoring remains incomplete'))
report=dict(timestamp=ts,checks=checks,counts={s:sum(c['status']==s for c in checks) for s in ['PASS','FAIL','WARN','BLOCKED','NOT TESTED']},limits=['No packages installed or workloads modified','GPU use forbidden by this CPU implementation','Exact semantic acceptance recorded separately'])
(out/'report.json').write_text(json.dumps(report,indent=2));(out/'report.md').write_text('# Runtime Blender audit\n\n'+'\n'.join('- '+x['id']+': '+x['status'] for x in checks));print('AUDIT_DIR='+str(out));print(json.dumps(report['counts']))
