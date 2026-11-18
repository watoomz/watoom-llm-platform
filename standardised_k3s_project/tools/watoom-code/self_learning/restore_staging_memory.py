#!/usr/bin/env python3
"""Independent staging-only memory availability watchdog."""
import argparse,pathlib,json,subprocess,os
p=argparse.ArgumentParser();p.add_argument('--checkpoint',type=pathlib.Path,required=True);a=p.parse_args();f=a.checkpoint
if f.is_symlink() or f.stat().st_uid!=0 or f.stat().st_mode&0o022:raise PermissionError('Private operator checkpoint required')
s=json.loads(f.read_text())
if not s['namespace'].startswith('watoom-code-learning-') or s['deployment']!='learning-memory':raise ValueError('Staging-only target')
d=json.loads(subprocess.check_output(['kubectl','-n',s['namespace'],'get','deploy','learning-memory','-o','json'],timeout=20))
if d['metadata']['uid']!=s['uid']:raise ValueError('Memory deployment identity changed')
subprocess.run(['kubectl','-n',s['namespace'],'scale','deploy/learning-memory','--replicas=1'],check=True,timeout=20,capture_output=True)
subprocess.run(['kubectl','-n',s['namespace'],'rollout','status','deploy/learning-memory','--timeout=150s'],check=True,timeout=160,capture_output=True)
print('STAGING_MEMORY_RESTORED')
