#!/usr/bin/env python3
"""Operator-authorized exact orphan-claim repair under native admission fencing."""
import argparse,pathlib,sqlite3,json,subprocess,base64,urllib.request,secrets,os,sys
import release_guard
p=argparse.ArgumentParser()
p.add_argument('--session',required=True);p.add_argument('--expected-suspended',required=True,type=int)
p.add_argument('--evidence',required=True,type=pathlib.Path);p.add_argument('--i-approve',action='store_true')
a=p.parse_args()
print('RISK: clears one idle suspended child execution claim; session history is preserved. Requires a native admission fence and a consistent database snapshot.',flush=True)
if not a.i_approve:sys.exit('BLOCKED: --i-approve required')
out=a.evidence.resolve();out.mkdir(mode=0o700,parents=True,exist_ok=False);out.chmod(0o700)
dbpath=pathlib.Path('/data/ai/watoom-code/application.sqlite')
def kub(*args):return json.loads(subprocess.check_output(['kubectl','-n','watoom-code',*args,'-o','json']))
deploy=kub('get','deploy','watoom-code')
env=next(c for c in deploy['spec']['template']['spec']['containers'] if c['name']=='app')['env']
ref=next(x for x in env if x['name']=='OPENCODE_PASSWORD')['valueFrom']['secretKeyRef']
pw=base64.b64decode(kub('get','secret',ref['name'])['data'][ref['key']])
auth='Basic '+base64.b64encode(b'opencode:'+pw).decode()
ip=kub('get','svc','watoom-code')['spec']['clusterIP']
def api(path,body=None):
 h={'Authorization':auth,'Content-Type':'application/json'}
 r=urllib.request.Request('http://'+ip+':4096'+path,headers=h,data=None if body is None else json.dumps(body).encode())
 with urllib.request.urlopen(r,timeout=15) as response:return json.load(response)
release_guard.active_clear(api('/api/session/active'))
release_guard.validate(api('/api/session/deployment-guard'),False)
owner=secrets.token_hex(32)
f=out/'owner.private.json';f.write_text(json.dumps({'owner':owner,'deployment_uid':deploy['metadata']['uid']}));f.chmod(0o600)
fd=os.open(f,os.O_RDONLY);os.fsync(fd);os.close(fd)
held=False
try:
 release_guard.validate(api('/api/session/deployment-guard',{'action':'acquire','owner':owner}),True);held=True
 release_guard.active_clear(api('/api/session/active'))
 with sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True) as db:
  db.row_factory=sqlite3.Row
  claims=[dict(x) for x in db.execute('SELECT id,parent_id,time_suspended,resume_attempts,time_updated FROM session_v2 WHERE time_suspended IS NOT NULL')]
  if len(claims)!=1 or claims[0]['id']!=a.session or claims[0]['time_suspended']!=a.expected_suspended or not claims[0]['parent_id']:raise RuntimeError('Claim identity changed or is not an orphan child')
 before=claims[0];(out/'claim-before.private.json').write_text(json.dumps(before,indent=2))
 # Every independent durable gate must already be clear.
 try:release_guard.durable_clearance(dbpath)
 except release_guard.UnsafeRelease as error:
  prefix='Durable execution clearance failed: '
  if not str(error).startswith(prefix):raise
  gates=json.loads(str(error)[len(prefix):])
  if gates.pop('execution_claims')!=1 or any(gates.values()):raise RuntimeError('Other durable work is present')
 else:raise RuntimeError('Expected claim disappeared')
 release_guard.snapshot_database(dbpath,out/'application-before.private.sqlite')
 (out/'application-before.private.sqlite').chmod(0o600)
 with sqlite3.connect(dbpath,timeout=5) as db:
  db.execute('BEGIN IMMEDIATE')
  row=db.execute('UPDATE session_v2 SET time_suspended=NULL,resume_attempts=0 WHERE id=? AND parent_id=? AND time_suspended=? AND time_updated=?',(a.session,before['parent_id'],a.expected_suspended,before['time_updated']))
  if row.rowcount!=1:raise RuntimeError('Concurrent claim change; transaction rolled back')
 release_guard.durable_clearance(dbpath)
 (out/'result.json').write_text(json.dumps({'status':'PASS','changed_rows':1,'history_preserved':True,'scope':'time_suspended and resume_attempts only','clearance':release_guard.durable_clearance(dbpath)},indent=2))
 print('PASS: exact orphan claim released; durable execution clearance is zero.',flush=True)
finally:
 if held:release_guard.release(lambda path:api(path),lambda path,body:api(path,body),owner)
