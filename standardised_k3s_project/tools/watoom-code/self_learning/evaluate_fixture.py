#!/usr/bin/env python3
"""Evaluate only the registered deterministic sort fixture; no arbitrary candidate execution."""
import argparse,pathlib,json,sqlite3,subprocess,hashlib,time,os
p=argparse.ArgumentParser();p.add_argument('--evidence',required=True,type=pathlib.Path);p.add_argument('--namespace',required=True);a=p.parse_args()
root=a.evidence.resolve();stage=root/'staging';out=root/'native-tests'
if not a.namespace.startswith('watoom-code-learning-'):raise ValueError('Isolated evaluation only')
def state():
 with sqlite3.connect('file:'+str(stage/'state/application.sqlite')+'?mode=ro',uri=True) as c:
  rows=c.execute('select value from kv where key like ?',('%learning/v1/%',)).fetchall()
 return [json.loads(x[0]) for x in rows]
s=next(s for s in state() if any(k['state']=='candidate' for k in s['skills'].values()))
k=next(k for k in s['skills'].values() if k['state']=='candidate')
if k['policy']!='sort-fixture':raise ValueError('No independent evaluator registered for this workflow')
config=json.loads((stage/'config/opencode.json').read_text());policy=config['plugins'][0]['options']['policies'][0]
digest=hashlib.sha256(json.dumps(policy,separators=(',',':')).encode()).hexdigest()
assert digest==k['version']
path=stage/'state/skills'/pathlib.Path(k['path']).name
assert hashlib.sha256(path.read_bytes()).hexdigest()==k['sha256']
assert len(k['evidence'])==3 and all(s['events'][rid]['status']=='VERIFIED' for rid in k['evidence'])
parse=subprocess.run(['/data/ai/projects/llm/watoom-code/prompt-builder-20261020/toolchain/bun',str(out/'parse-skill.ts'),str(path)],capture_output=True,text=True,timeout=30)
assert parse.returncode==0,parse.stderr
parsed=json.loads(parse.stdout);assert parsed['_tag']=='Parsed' and parsed['skill']['id']==k['id']
(out/'native-parser-result.json').write_text(parse.stdout)
start=time.monotonic()
replay=subprocess.run(['python3',str(pathlib.Path(__file__).with_name('native_acceptance.py')),'--evidence',str(root),'--namespace',a.namespace,'--sessions','1'],capture_output=True,text=True,timeout=60)
assert replay.returncode==0,replay.stderr
sid=json.loads(next(line for line in replay.stdout.splitlines() if line.startswith('{')))['session']
with sqlite3.connect('file:'+str(stage/'state/application.sqlite')+'?mode=ro',uri=True) as c:
 messages=[json.loads(x[0]) for x in c.execute('select data from session_message where session_id=? and type=?',(sid,'assistant'))]
 tools=[x for m in messages for x in m.get('content',[]) if x.get('type')=='tool']
 assert len([t for t in tools if t['name']=='watoom_learning_fixture' and t['state']['status']=='completed'])==1
 assert not any(t['state']['status']=='error' for t in tools)
assert json.loads((stage/'state/fixture-result.json').read_text())==[1,2,3]
for section in ['Activation','Requirements and environment','Verified procedure','Validation','Recovery','Provenance and version','Safety']:assert '## '+section in parsed['skill']['content']
e={'id':k['id'],'scope':k['scope'],'candidateHash':k['sha256'],'policyDigest':digest,'correctness':True,'safety':True,'useful':True,'usefulness_basis':'Matches fixed fixture procedure; no efficiency improvement claimed','replayIDs':[sid],'replay_seconds':time.monotonic()-start,'evaluator':'fixed-sort-fixture-v1'}
dest=stage/'evaluations'/(k['id']+'.json');tmp=dest.with_suffix('.tmp')
with tmp.open('w') as f:json.dump(e,f,indent=2);f.flush();os.fsync(f.fileno())
os.chown(tmp,0,0);os.chmod(tmp,0o644);os.replace(tmp,dest)
(out/'evaluation-result.json').write_text(json.dumps(e,indent=2))
print(json.dumps({'candidate':k['id'],'native_parser':'PASS','independent_replay':'PASS','replay':sid,'attestation':str(dest)}))
