#!/usr/bin/env python3
"""Exercise the actual production workflow prompt/guard in isolated staging."""
import argparse,pathlib,json,sys,os,time,hashlib,secrets,subprocess,shutil,fcntl
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
from maintenance_guard import Maintenance
from release_guard import active_clear,acquire,release
from recover import atomic
p=argparse.ArgumentParser();p.add_argument('--evidence',required=True,type=pathlib.Path);p.add_argument('--namespace',required=True);a=p.parse_args()
if not a.namespace.startswith('watoom-code-learning-'):raise ValueError('Staging only')
root=a.evidence;stage=root/'staging';source=pathlib.Path(__file__).resolve().parent;repo=source.parents[2];m=Maintenance(a.namespace,'learning-app',root,True,True);prod=Maintenance('watoom-code','watoom-code',root,True,True)
active_clear(m.request('/api/session/active'));active_clear(prod.request('/api/session/active'))
sys.path.insert(0,'/data/ai/helper-scripts/gpu-controller');from client import GPUClient
controller=GPUClient('/data/ai/helper-scripts/state/gpu-controller-private/worker.sock',timeout=10);gpu=controller.call('status')
if gpu.get('owner') is not None or gpu.get('phase')!='qwen-ready':raise RuntimeError('Primary model is not idle and admitted')
agent=next(x for x in prod.request('/api/agent?location%5Bdirectory%5D=%2Fworkspace')['data'] if x['id']=='watoom-workflow')
original_prod=json.loads(pathlib.Path('/data/ai/watoom-code/config/opencode.json').read_text());guard=next(x['package'] for x in original_prod['plugins'] if isinstance(x,dict) and 'coordinator-guard' in x['package']);guardhost=pathlib.Path('/data/ai/watoom-code/config')/pathlib.Path(guard).relative_to('/config');dest=stage/'config/production-guard';shutil.copytree(guardhost,dest,dirs_exist_ok=True)
out=stage/('production-role-proof-'+str(time.time_ns()));out.mkdir(mode=0o700);config=stage/'config/opencode.json';prior=out/'config.json';prior.write_bytes(config.read_bytes());prior.chmod(0o600);before_manifest=(stage/'manifests.json').read_bytes();candidate=json.loads(config.read_text())
candidate['agents']['watoom-workflow']={k:agent[k] for k in ['system','description','mode','permissions','steps']};candidate['agents']['watoom-workflow']['steps']=6
candidate['plugins'].insert(0,{'package':'/config/production-guard','options':{'verifiedVisionModels':['watoom/swift-qwen38-coder']}});candidate['plugins'][1]['options']['agent']='watoom-workflow';candidatefile=out/'candidate.json';atomic(candidatefile,candidate)
live=m.kub('get','deploy','learning-app');manifest=out/'deployment.json';atomic(manifest,{'apiVersion':'apps/v1','kind':'Deployment','metadata':{'name':'learning-app','namespace':a.namespace,'labels':live['metadata'].get('labels',{})},'spec':live['spec']});sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();checkpoint=stage/'recovery-state.json';s={'phase':'CUTOVER_STARTED','namespace':a.namespace,'deployment':'learning-app','deployment_uid':live['metadata']['uid'],'replicas':1,'baseline_deployment':str(manifest),'baseline_deployment_sha256':sha(manifest),'baseline_config':str(prior),'baseline_config_sha256':sha(prior),'candidate_config_sha256':sha(candidatefile),'config':str(config),'directory':'/workspace','grace_until':time.time()+300,'health_failures':0,'recovery_nonce':secrets.token_hex(16),'production_approved':False,'owned_sessions':[],'baseline_skills':[k['id'] for k in m.request('/api/skill?location%5Bdirectory%5D=%2Fworkspace')['data']]};atomic(checkpoint,s)
def update(**values):
 with checkpoint.with_suffix('.lock').open('a') as lock:fcntl.flock(lock,fcntl.LOCK_EX);v=json.loads(checkpoint.read_text());v.update(values);atomic(checkpoint,v)
error=None;start=time.monotonic()
try:
 acquire(lambda p:m.request(p),lambda p,b:m.request(p,b),lambda owner:update(owner=owner),lambda:None)
 marker=out/'expiry.json';atomic(marker,{'checkpoint':str(checkpoint),'nonce':s['recovery_nonce']});subprocess.run(['systemd-run','--quiet','--unit=watoom-role-fixture-expiry-'+str(time.time_ns()),'--on-active=300s','/usr/bin/python3','-I',str(source/'expire_fixture.py'),'--input',str(marker)],check=True,timeout=10)
 atomic(config,candidate);os.chown(config,1001,1001);os.chmod(config,0o600);prepared=json.loads(before_manifest);next(d for d in prepared['items'] if d.get('kind')=='Deployment' and d['metadata']['name']=='learning-app')['spec']['template']['metadata']['annotations']['watoom-learning-config-sha256']=sha(config);atomic(stage/'manifests.json',prepared)
 env={**os.environ,'ANSIBLE_CONFIG':str(repo/'ansible/ansible.cfg'),'ANSIBLE_ROLES_PATH':str(repo/'ansible/roles')}
 with (out/'apply.log').open('w') as log:r=subprocess.run(['ansible-playbook','-i',str(repo/'ansible/inventories/homelab/hosts.yml'),str(repo/'ansible/playbooks/watoom-code-self-learning-stage.yml'),'-c','local'],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=90)
 if r.returncode:raise RuntimeError('Isolated production-role rollout failed')
 release(lambda p:m.request(p),lambda p,b:m.request(p,b),json.loads(checkpoint.read_text())['owner'])
 directory=stage/'workspace/role-acceptance';directory.mkdir(exist_ok=True);os.chown(directory,1001,1001)
 with (out/'native-role.log').open('w') as log:r=subprocess.run(['python3',str(source/'runtime_validation.py'),'--evidence',str(out),'--namespace',a.namespace,'--agent','watoom-workflow','--model','watoom/swift-qwen38-coder','--directory','/workspace/role-acceptance','--database',str(stage/'state/application.sqlite'),'--learning-root',str(stage/'state'),'--evaluations',str(stage/'evaluations'),'--approved-state',str(checkpoint)],stdout=log,stderr=subprocess.STDOUT,timeout=240)
 if r.returncode:raise RuntimeError('Production workflow prompt/guard failed isolated native learning acceptance')
except Exception as e:error=str(e)
finally:
 (stage/'manifests.json').write_bytes(before_manifest);os.chmod(stage/'manifests.json',0o600);update(phase='CUTOVER_FAILED',critical_failure='Temporary production-role staging exercise complete'+(': '+error if error else ''),grace_until=0)
deadline=time.monotonic()+180
while time.monotonic()<deadline:
 s=json.loads(checkpoint.read_text())
 if s['phase']=='ROLLED_BACK':
  assert sha(config)==sha(prior);after=controller.call('status');report={'status':'FAIL' if error else 'PASS','agent':'watoom-workflow','source_prompt_sha256':hashlib.sha256(agent['system'].encode()).hexdigest(),'installed_guard_sha256':sha(guardhost/'index.js'),'real_model':'watoom/swift-qwen38-coder','controller_generation_unchanged':gpu.get('generation')==after.get('generation'),'model_swaps':0,'automatic_staging_restoration':'PASS','seconds':time.monotonic()-start,'evidence':str(out),'error':error};atomic(root/'native-tests/production-role-staging.json',report);print(json.dumps(report));raise SystemExit(1 if error else 0)
 if s['phase']=='BLOCKED_RECOVERY':raise RuntimeError(s.get('blocker'))
 time.sleep(1)
raise RuntimeError('Role fixture restoration could not be verified; independent controller retains its checkpoint')
