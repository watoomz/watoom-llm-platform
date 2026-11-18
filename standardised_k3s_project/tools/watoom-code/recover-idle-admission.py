import pathlib,sys,json,subprocess,os,secrets,time,hashlib
import argparse
p=argparse.ArgumentParser();p.add_argument('--evidence',required=True,type=pathlib.Path);p.add_argument('--i-approve',action='store_true');p.add_argument('--playbook',default='watoom-code-read-access.yml',choices=['watoom-code-read-access.yml','watoom-code-coordinator-guard.yml','watoom-code-guard-knowledge.yml']);a=p.parse_args()
if os.geteuid()!=0 or not a.i_approve:raise PermissionError('Root operator and explicit --i-approve required')
os.umask(0o077)
R=pathlib.Path(__file__).resolve().parents[2];O=a.evidence.resolve();O.mkdir(parents=True,exist_ok=False,mode=0o700);sys.path.insert(0,str(R/'tools/watoom-code'))
from maintenance_guard import Maintenance
import release_guard
m=Maintenance('watoom-code','watoom-code',O,True,True);D=pathlib.Path('/data/ai/watoom-code/application.sqlite');fence=D.parent/'watoom-release-guard.json';owner=secrets.token_hex(32)
assert not m.request('/api/session/active')['data'];assert m.request('/api/session/deployment-guard')['data']['held']==False;release_guard.durable_clearance(D)
state=json.loads(pathlib.Path('/data/ai/helper-scripts/state/gpu-controller/state.json').read_text());leases=json.loads(pathlib.Path('/data/ai/helper-scripts/state/gpu-controller/inference-leases.json').read_text());assert not state['owner'] and not state['uncertain'] and not leases['leases']
release_guard.snapshot_database(D,O/'pre-recovery.private.sqlite');(O/'recovery-owner.private').write_text(owner)
def run(args,timeout=150):
 p=subprocess.run(args,cwd=R,env={**os.environ,'ANSIBLE_CONFIG':str(R/'ansible/ansible.cfg'),'ANSIBLE_ROLES_PATH':str(R/'ansible/roles')},capture_output=True,text=True,timeout=timeout)
 with (O/'recovery.log').open('a') as f:f.write(p.stdout+p.stderr)
 if p.returncode:raise RuntimeError('Command failed; inspect recovery.log')
def scale(n):run(['kubectl','-n','watoom-code','scale','deployment/watoom-code','--replicas='+str(n)])
# Existing ingress/service maintenance fence prevents new admission during retirement.
stopped=False;installed=False
try:
 m.begin()
 for _ in range(10):
  try:m.verify_closed();break
  except Exception:time.sleep(1)
 else:raise RuntimeError('Maintenance fence did not close')
 assert not m.request('/api/session/active')['data'];release_guard.durable_clearance(D)
 scale(0);stopped=True
 run(['kubectl','-n','watoom-code','wait','--for=delete','pod','-l','app=watoom-code','--timeout=90s'],100)
 # Recheck after the old process has gone; never discard input or claims.
 release_guard.durable_clearance(D);assert not fence.exists()
 fd=os.open(fence,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 try:os.fchown(fd,1001,1001);os.write(fd,json.dumps({'version':1,'owner':owner}).encode());os.fsync(fd)
 finally:os.close(fd)
 # Durable native fence exists before any replacement process starts.
 run(['ansible-playbook','-i','ansible/inventories/homelab/hosts.yml','ansible/playbooks/'+a.playbook,'--connection','local','--limit','watoom-homelab','-e','watoom_coordinator_release_guard_held=true']);installed=True
 scale(1);run(['kubectl','-n','watoom-code','rollout','status','deployment/watoom-code','--timeout=120s'],130)
 release_guard.validate(m.request('/api/session/deployment-guard'),True);release_guard.durable_clearance(D)
 digest=hashlib.sha256((R/'ansible/roles/watoom-code/files/coordinator-guard/index.js').read_bytes()).hexdigest();config=json.loads((D.parent/'config/opencode.json').read_text());assert any(isinstance(p,dict) and p.get('package','').endswith('coordinator-guard-'+digest) for p in config['plugins'])
 roles=None
 for _ in range(30):
  try:roles=m.request('/api/agent')['data'];break
  except Exception:time.sleep(2)  # the app answers 503 for a few seconds after a restart
 assert roles is not None;assert all('Shell reads are an approved alternative' in a['system'] for a in roles if a['id'] in ['watoom-critic','watoom-investigator'])
 release_guard.release(m.request,lambda p,b:m.request(p,b),owner);m.release()
 (O/'activation.json').write_text(json.dumps({'status':'PASS','guard_sha256':digest,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip(),'database_preserved':True,'activation':'LIVE'},indent=2));print('ACTIVATED '+digest)
except BaseException:
 # Preserve an owned persistent fence/evidence on partial activation; do not delete provenance.
 if stopped:scale(1)
 m.release();raise
