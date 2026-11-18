#!/usr/bin/env python3
"""Service failure handler; Codex disconnects do not stop this host service."""
import argparse,pathlib,json,fcntl,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from recover import atomic
p=argparse.ArgumentParser();p.add_argument('--evidence',required=True,type=pathlib.Path);a=p.parse_args();root=a.evidence.resolve();pointer=root/'production/optimisation-current.json'
if not pointer.exists():raise SystemExit()
checkpoint=pathlib.Path(json.loads(pointer.read_text())['checkpoint']).resolve()
if not checkpoint.is_relative_to(root/'production') or checkpoint.is_symlink():raise ValueError('Unowned checkpoint pointer')
with checkpoint.with_suffix('.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX);s=json.loads(checkpoint.read_text())
 if s['phase'] in ['CUTOVER_STARTED','PRODUCTION_VALIDATED']:
  s.update(phase='CUTOVER_FAILED',grace_until=0,critical_failure='Independent optimisation service exited before activation and endpoint verification completed');atomic(checkpoint,s);print('INDEPENDENT_RECOVERY_REQUESTED')
