#!/usr/bin/env python3
import pathlib,json,sqlite3,subprocess,time,urllib.parse,argparse
p=argparse.ArgumentParser();p.add_argument('--evidence',type=pathlib.Path,default='/data/ai/helper-scripts/watoom-self-learning-20261023T000524Z');p.add_argument('--namespace',default='watoom-code-learning-20261023');a=p.parse_args();root=a.evidence;stage=root/'staging';ns=a.namespace
if not ns.startswith('watoom-code-learning-'):raise ValueError('Staging-only acceptance')
code="""import os,urllib.request,base64,json,sys
v=json.load(sys.stdin);h={'Authorization':'Basic '+base64.b64encode(('opencode:'+os.environ['OPENCODE_PASSWORD']).encode()).decode(),'Content-Type':'application/json'}
r=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:4096'+v['path'],headers=h,data=json.dumps(v['body']).encode() if v.get('body') is not None else None),timeout=15);sys.stdout.buffer.write(r.read())
"""
def api(path,body=None):
 r=subprocess.run(['kubectl','-n',ns,'exec','-i','deploy/learning-app','--','python3','-c',code],input=json.dumps({'path':path,'body':body}).encode(),capture_output=True,timeout=30)
 if r.returncode:raise RuntimeError(r.stderr.decode()[-1200:])
 return json.loads(r.stdout)
s=api('/api/session',{'title':'Fresh session learned procedure retrieval','agent':'learning-fixture','location':{'directory':'/workspace'}})['data'];sid=s['id']
activation_start=time.monotonic();activation_deadline=activation_start+45
while True:
 skills=api('/api/skill?location%5Bdirectory%5D=%2Fworkspace')['data'];learned=[k for k in skills if k['id'].startswith('learned-')]
 if learned:break
 if time.monotonic()>activation_deadline:raise RuntimeError('Evaluated candidate did not register within45s')
 time.sleep(.5)
activation_seconds=time.monotonic()-activation_start
start=time.monotonic();api('/api/session/'+sid+'/prompt',{'text':'RETRIEVE the relevant learned sort fixture procedure, apply it, and verify persisted output.'})
deadline=time.monotonic()+40
while sid in api('/api/session/active')['data']:
 if time.monotonic()>deadline:raise RuntimeError('Fresh-session replay timed out')
 time.sleep(.5)
with sqlite3.connect('file:'+str(stage/'state/application.sqlite')+'?mode=ro',uri=True) as c:
 messages=[json.loads(x[0]) for x in c.execute('select data from session_message where session_id=? and type=? order by seq',(sid,'assistant'))]
 tools=[x for m in messages for x in m.get('content',[]) if x.get('type')=='tool']
 assert all(t['state']['status']=='completed' for t in tools),tools
 assert any(t['name']=='skill' and t['state']['input']['id']==learned[0]['id'] for t in tools),'Native skill tool not used'
 assert any(t['name']=='watoom_learning_fixture' for t in tools),'Learned procedure not applied'
 states=[json.loads(x[0]) for x in c.execute('select value from kv where key like ?',('%learning/v1/%',))]
 state=next(s for s in states if learned[0]['id'] in s['skills'])
assert json.loads((stage/'state/fixture-result.json').read_text())==[1,2,3]
metrics=[json.loads(line) for line in (stage/'state/provider-metrics.jsonl').read_text().splitlines()]
report={'status':'PASS','session':sid,'seconds':time.monotonic()-start,'activation_seconds':activation_seconds,'native_skill':learned[0]['id'],'completed_tools':[t['name'] for t in tools],'memory_deliveries':{q:sum(x['state']==q for x in state['outbox'].values()) for q in ['queued','sending','uncertain','delivered']},'context_bytes_accumulated':state['metrics']['contextBytes'],'metadata_injection_observed':any(x['metadata_present'] for x in metrics),'token_usage':'NOT_MEASURED_CPU_FIXTURE_PROVIDER','gpu_inference_requests':0,'efficiency_improvement':'NOT_CLAIMED'}
(root/'native-tests/end-to-end.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
