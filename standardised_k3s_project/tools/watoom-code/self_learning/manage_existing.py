#!/usr/bin/env python3
"""Review native existing-Skill state or submit a root-owned independent evaluator report."""
import argparse,pathlib,sqlite3,json,secrets,os
from recover import atomic
p=argparse.ArgumentParser();p.add_argument('--evidence',required=True,type=pathlib.Path);p.add_argument('--runtime',choices=['staging','production'],default='staging');p.add_argument('--action',choices=['status','baseline','compare','regression'],default='status');p.add_argument('--id');p.add_argument('--report',type=pathlib.Path);p.add_argument('--scope-hash');a=p.parse_args()
root=a.evidence.resolve();plan=json.loads((root/'production/plan.json').read_text()) if a.runtime=='production' else None
database=pathlib.Path('/data/ai/watoom-code/application.sqlite') if plan else root/'staging/state/application.sqlite';evaluations=pathlib.Path(plan['evaluations']) if plan else root/'staging/evaluations'
with sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True) as db:rows=[(key,json.loads(value)) for key,value in db.execute('select key,value from kv where key like ?',('%optimisation/v1/%',))]
if a.action=='status':print(json.dumps([{'scope_hash':key.split('/')[-1],**s} for key,s in rows],indent=2));raise SystemExit()
if os.geteuid()!=0:raise PermissionError('Independent evaluator inputs must be operator-owned')
if not a.report or a.report.is_symlink() or a.report.stat().st_uid!=0 or a.report.stat().st_mode&0o022:raise PermissionError('Protected root-owned evaluator report required')
report=json.loads(a.report.read_text());scope=report.pop('scope');import hashlib
scopehash=hashlib.sha256(json.dumps(scope,separators=(',',':')).encode()).hexdigest()
if not any(key.endswith('/'+scopehash) for key,s in rows):raise ValueError('Exact native project/agent scope required')
request=secrets.token_hex(16);value={'kind':'existing-skill-'+a.action,'id':a.id,'scope':scope,'request':request,'report':report}
if a.action=='regression':value['receipt']=report['receipt']
file=evaluations/('existing-'+request+'.json');atomic(file,value);os.chmod(file,0o644);print(json.dumps({'queued':value['kind'],'request':request,'activation':'No hot replacement. Qualified revisions require the idle deployment controller and an immutable configuration selection.'}))
