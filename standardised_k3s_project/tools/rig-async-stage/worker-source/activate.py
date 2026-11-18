"""Scoped RIG capture activation using the existing native release fence."""
import argparse,json,pathlib,sys,os,subprocess

def main():
 p=argparse.ArgumentParser();p.add_argument('--iac-root',required=True,type=pathlib.Path);p.add_argument('--evidence',required=True,type=pathlib.Path);p.add_argument('--previous',required=True,type=pathlib.Path);p.add_argument('--i-approve',action='store_true');a=p.parse_args()
 if not a.i_approve:raise RuntimeError('Explicit operator approval required')
 root=a.iac_root.resolve();out=a.evidence.resolve();out.mkdir(mode=0o700,parents=True,exist_ok=False)
 sys.path.insert(0,str(root/'tools/watoom-code'))
 import release_guard
 from maintenance_guard import Maintenance
 from skills_release import NativeRelease
 m=Maintenance('watoom-code','watoom-code',out,True,True);get=m.request
 names=['asset-image-clip-capture','workstation-render-stage'];release=NativeRelease(root,out,names,previous=a.previous,provenance=[])
 before=get('/api/skill?directory=/data/ai/projects/images')['data'];deployment=m.kub('get','deploy','watoom-code')
 config=pathlib.Path('/data/ai/watoom-code/config/opencode.json');worker=pathlib.Path('/etc/watoom-asset-capture.json')
 config_before=config.read_bytes();worker_before=worker.read_bytes();(out/'opencode-before.private.json').write_bytes(config_before);(out/'worker-before.json').write_bytes(worker_before)
 def clearance():
  release_guard.active_clear(get('/api/session/active'));release_guard.durable_clearance(pathlib.Path('/data/ai/watoom-code/application.sqlite'))
  if any(j.get('status',{}).get('active') for j in m.kub('get','jobs')['items']):raise RuntimeError('Active native job')
  import sqlite3
  with sqlite3.connect('file:/data/ai/helper-scripts/state/workstation-render-stage/queue.sqlite?mode=ro',uri=True) as db:
   if db.execute("select 1 from jobs where state in ('CLAIMED','RECONCILIATION_REQUIRED')").fetchone():raise RuntimeError('External worker needs reconciliation')
 def save(owner):
  p=out/'guard-owner.private';p.write_text(owner);p.chmod(0o600)
  with p.open('rb') as stream:os.fsync(stream.fileno())
 owner=release_guard.acquire(get,lambda p,b:m.request(p,b),save,clearance);healthy=True
 try:
  release_guard.snapshot_database(pathlib.Path('/data/ai/watoom-code/application.sqlite'),out/'application-before.private.sqlite')
  healthy=False;release.apply()
  command=['ansible-playbook','-i','inventories/homelab/hosts.yml','playbooks/watoom-code-workstation-capture.yml','-e','watoom_render_routing_guard_held=true']
  env=dict(os.environ,ANSIBLE_CONFIG=str(root/'ansible/ansible.cfg'),ANSIBLE_ROLES_PATH=str(root/'ansible/roles'))
  for attempt in ('apply','repeat'):
   result=subprocess.run(command,cwd=root/'ansible',env=env,capture_output=True,text=True,timeout=360);(out/('ansible-'+attempt+'.log')).write_text(result.stdout+result.stderr)
   if result.returncode or attempt=='repeat' and 'changed=0' not in result.stdout:raise RuntimeError('Scoped activation '+attempt+' failed; inspect retained evidence')
  verification=release.verify(get,[s['id'] for s in before])
  if not json.loads(worker.read_text()).get('workstation_enabled'):raise RuntimeError('RIG routing flag not enabled')
  if m.kub('get','deploy','watoom-code')['spec']!=deployment['spec']:raise RuntimeError('Application deployment changed unexpectedly')
  result={'status':'PASS','skills':verification,'native_route':'RIG enabled for new requests','application_restarted':False,'repeat_apply':'UNCHANGED','paused_manual_jobs':'preserved; native-only claim filter','visual_acceptance':'required separately'};(out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result));healthy=True
 except BaseException:
  worker.write_bytes(worker_before)
  # Admission excludes concurrent config writers; retain changed config as evidence.
  (out/'opencode-failed.private.json').write_bytes(config.read_bytes());config.write_bytes(config_before)
  release.rollback();healthy=True;raise
 finally:
  if healthy:release_guard.release(get,lambda p,b:m.request(p,b),owner)
if __name__=='__main__':main()
