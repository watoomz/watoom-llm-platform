#!/usr/bin/env python3
"""Expire only one owned staging fixture, never a later run or production."""
import pathlib,json,argparse,fcntl,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from recover import atomic
p=argparse.ArgumentParser();p.add_argument('--input',required=True,type=pathlib.Path);a=p.parse_args();marker=json.loads(a.input.read_text());path=pathlib.Path(marker['checkpoint'])
with path.with_suffix('.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX);s=json.loads(path.read_text())
 if s.get('production_approved') or not s['namespace'].startswith('watoom-code-learning-'):raise ValueError('Staging-only expiry')
 if s.get('recovery_nonce')==marker['nonce'] and s['phase'] in ['CUTOVER_STARTED','PRODUCTION_VALIDATED']:
  s.update(phase='CUTOVER_FAILED',critical_failure='Owned temporary Skill revision fixture expired; restore its baseline',grace_until=0);atomic(path,s)
