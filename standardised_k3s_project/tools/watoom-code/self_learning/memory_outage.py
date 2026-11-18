#!/usr/bin/env python3
import argparse,pathlib,json,subprocess,sqlite3,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
from maintenance_guard import Maintenance
from release_guard import active_clear
from recover import atomic
p=argparse.ArgumentParser();p.add_argument('--evidence',type=pathlib.Path,required=True);p.add_argument('--namespace',required=True);a=p.parse_args()
if not a.namespace.startswith('watoom-code-learning-'):raise ValueError('Staging-only outage')
root=a.evidence;stage=root/'staging';ns=a.namespace;m=Maintenance(ns,'learning-app',root,True,True)
active_clear(m.request('/api/session/active'))
mem=json.loads(subprocess.check_output(['kubectl','-n',ns,'get','deploy','learning-memory','-o','json'],timeout=20))
checkpoint=stage/'memory-pause.json';atomic(checkpoint,{'namespace':ns,'deployment':'learning-memory','uid':mem['metadata']['uid']})
restore=pathlib.Path(__file__).with_name('restore_staging_memory.py')
subprocess.run(['systemd-run','--quiet','--unit=watoom-learning-memory-backstop-'+str(time.time_ns()),'--on-active=60','/usr/bin/python3',str(restore),'--checkpoint',str(checkpoint)],check=True,capture_output=True,timeout=20)
start=time.monotonic()
def read():
 with sqlite3.connect('file:'+str(stage/'state/application.sqlite')+'?mode=ro',uri=True) as c:return [json.loads(x[0]) for x in c.execute('select value from kv where key like ?',('%learning/v1/%',))]
try:
 subprocess.run(['kubectl','-n',ns,'scale','deploy/learning-memory','--replicas=0'],check=True,capture_output=True,timeout=20)
 subprocess.run(['kubectl','-n',ns,'wait','--for=delete','pod','-l','app=learning-memory','--timeout=45s'],check=True,capture_output=True,timeout=50)
 r=subprocess.run(['python3',str(pathlib.Path(__file__).with_name('native_acceptance.py')),'--evidence',str(root),'--namespace',ns,'--sessions','1'],capture_output=True,text=True,timeout=60)
 if r.returncode:raise RuntimeError(r.stderr)
 sid=json.loads(next(x for x in r.stdout.splitlines() if x.startswith('{')))['session']
 selected=next(s for s in read() if any(e['session']==sid for e in s['events'].values()))
 eventid=next(k for k,e in selected['events'].items() if e['session']==sid and e['status']=='VERIFIED')
 pending=next(e for e in selected['outbox'].values() if e['envelope']['job']=='learning:'+eventid)
 assert pending['state']=='uncertain','Outage did not exercise uncertain delivery'
finally:
 subprocess.run(['python3',str(restore),'--checkpoint',str(checkpoint)],check=True,capture_output=True,timeout=180)
deadline=time.monotonic()+70
while True:
 selected=next(s for s in read() if eventid in s['events']);entry=next(e for e in selected['outbox'].values() if e['envelope']['job']=='learning:'+eventid)
 if entry['state']=='delivered':break
 if time.monotonic()>deadline:raise RuntimeError('Durable event did not recover to AgentMemory')
 time.sleep(1)
# Independently replay the installed idempotent API, then verify one unchanged record.
code="""import os,urllib.request,json,sys
v=json.load(sys.stdin);h={'Authorization':'Bearer '+os.environ['AGENTMEMORY_SECRET'],'Content-Type':'application/json'};url=os.environ['AGENTMEMORY_URL'].rstrip('/')
def call(path,body=None):
 r=urllib.request.urlopen(urllib.request.Request(url+path,headers=h,data=None if body is None else json.dumps(body).encode()),timeout=15);return json.load(r)
ident=v['id'];before=call('/agentmemory/memories/'+ident)['memory'];r=call('/agentmemory/import',{'strategy':'skip','exportData':{'version':'0.9.29','exportedAt':before['createdAt'],'sessions':[],'observations':{},'memories':[before],'summaries':[]}});after=call('/agentmemory/memories/'+ident)['memory'];all=call('/agentmemory/memories?agentId=learning-fixture&limit=5000')['memories'];assert before==after and sum(x['id']==ident for x in all)==1;print(json.dumps({'duplicate_count':1,'content_preserved':True,'skip_ack':r.get('success')}))
"""
r=subprocess.run(['kubectl','-n',ns,'exec','-i','deploy/learning-app','--','python3','-c',code],input=json.dumps({'id':entry['receipt']['memoryId']}).encode(),capture_output=True,timeout=40)
assert r.returncode==0,r.stderr.decode();duplicate=json.loads(r.stdout)
report={'status':'PASS','session':sid,'memory_unavailable':'EXERCISED','native_task_continued':True,'durable_outbox_recovered':True,'duplicate_prevention':duplicate,'seconds':time.monotonic()-start,'independent_restore_backstop':'ARMED'}
atomic(root/'native-tests/memory-outage.json',report);print(json.dumps(report))
