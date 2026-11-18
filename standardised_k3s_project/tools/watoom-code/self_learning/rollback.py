#!/usr/bin/env python3
"""Request supported restoration from the independently scheduled recovery controller."""
import argparse,pathlib,json,time,fcntl,subprocess,os
from recover import atomic
p=argparse.ArgumentParser();p.add_argument('--evidence',required=True,type=pathlib.Path);p.add_argument('--wait',action='store_true');a=p.parse_args();checkpoint=a.evidence/'production/recovery-state.json'
if not checkpoint.exists():raise SystemExit('No production release exists to restore')
plan=json.loads((a.evidence/'production/plan.json').read_text());repo=pathlib.Path(__file__).resolve().parents[3]
env={**os.environ,'ANSIBLE_CONFIG':str(repo/'ansible/ansible.cfg'),'ANSIBLE_ROLES_PATH':str(repo/'ansible/roles')}
values={'watoom_learning_root':str(a.evidence/'production'),'watoom_learning_controller_script':plan['controller_script'],'watoom_learning_recovery_checkpoint':str(checkpoint)}
with (a.evidence/'production/explicit-rollback-controller.log').open('w') as log:
 result=subprocess.run(['ansible-playbook','-i',str(repo/'ansible/inventories/homelab/hosts.yml'),str(repo/'ansible/playbooks/watoom-code-self-learning-controller.yml'),'-c','local','-e',json.dumps(values)],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=90)
if result.returncode:raise SystemExit('Failed to arm the exact requested rollback checkpoint; existing controller unchanged')
with checkpoint.with_suffix('.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX);s=json.loads(checkpoint.read_text())
 if not s.get('production_approved'):raise PermissionError('Unapproved restoration target')
 if s['phase']=='ROLLED_BACK':print('ALREADY_ROLLED_BACK');raise SystemExit()
 if s['phase']=='BLOCKED_RECOVERY':raise SystemExit('BLOCKED_RECOVERY: '+s.get('blocker','Inspect preserved evidence'))
 s.update(phase='CUTOVER_FAILED',critical_failure='Explicit operator rollback request',grace_until=0);atomic(checkpoint,s)
print('ROLLBACK_QUEUED',flush=True)
if a.wait:
 deadline=time.monotonic()+960
 while time.monotonic()<deadline:
  s=json.loads(checkpoint.read_text())
  if s['phase']=='ROLLED_BACK':print('ROLLED_BACK_VERIFIED');raise SystemExit()
  if s['phase']=='BLOCKED_RECOVERY':raise SystemExit('BLOCKED_RECOVERY: '+s.get('blocker',''))
  time.sleep(3)
 raise SystemExit('Restoration verification timed out; independent controller remains armed')
