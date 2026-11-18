#!/usr/bin/env python3
"""Isolated logical AgentMemory restore probe; no production writes."""
import pathlib,json,subprocess,secrets,time,os
os.umask(0o077)
root=pathlib.Path('/data/ai/helper-scripts/watoom-self-learning-20261023T000524Z');out=root/'restore-test';out.mkdir(exist_ok=True)
ns='watoom-code-learning-20261023'
def run(args,data=None,timeout=60):
 r=subprocess.run(args,input=data,capture_output=True,timeout=timeout)
 if r.returncode:raise RuntimeError(r.stderr.decode()[-500:])
 return r.stdout
def atomic(name,value):
 p=out/name;t=p.with_suffix('.tmp')
 with t.open('w') as f:json.dump(value,f,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(t,p)
backup=json.loads((root/'baseline/agentmemory-export.json').read_text())
assert backup.get('version') and 'error' not in backup
deploys=json.loads((root/'baseline/deployments.json').read_text())['items']
image=next(x for x in deploys if x['metadata']['name']=='agentmemory')['spec']['template']['spec']['containers'][0]['image']
assert '@sha256:' in image
secretfile=out/'probe-secret'
if not secretfile.exists():secretfile.write_text(secrets.token_hex(32))
secret=secretfile.read_text()
namespace={'apiVersion':'v1','kind':'Namespace','metadata':{'name':ns,'labels':{'watoom-owner':'self-learning-restore'}}}
container={'name':'memory','image':image,'env':[{'name':'AGENTMEMORY_DATA_DIR','value':'/data'},{'name':'AGENTMEMORY_SECRET','value':secret},{'name':'AGENTMEMORY_AUTO_COMPRESS','value':'false'},{'name':'AGENTMEMORY_INJECT_CONTEXT','value':'false'}],'resources':{'requests':{'cpu':'25m','memory':'128Mi'},'limits':{'cpu':'1','memory':'1Gi'}},'securityContext':{'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}},'volumeMounts':[{'name':'data','mountPath':'/data'}],'readinessProbe':{'httpGet':{'path':'/agentmemory/livez','port':3111},'initialDelaySeconds':5,'periodSeconds':3,'failureThreshold':30}}
pod={'apiVersion':'v1','kind':'Pod','metadata':{'name':'memory-restore','namespace':ns,'labels':{'app':'memory-restore','watoom-owner':'self-learning-restore'}},'spec':{'automountServiceAccountToken':False,'restartPolicy':'Never','containers':[container],'volumes':[{'name':'data','emptyDir':{}}]}}
atomic('restore-pod.json',pod)
run(['kubectl','apply','-f','-'],json.dumps(namespace).encode())
old=run(['kubectl','-n',ns,'get','pod','memory-restore','--ignore-not-found','-o','json'])
if not old.strip():run(['kubectl','apply','-f','-'],json.dumps(pod).encode())
else:
 old=json.loads(old)
 assert old['metadata']['labels'].get('watoom-owner')=='self-learning-restore' and old['spec']['containers'][0]['image']==image
run(['kubectl','-n',ns,'wait','--for=condition=Ready','pod/memory-restore','--timeout=120s'],timeout=130)
code="""let b='';for await(const x of process.stdin)b+=x;let v=JSON.parse(b);let r=await fetch('http://127.0.0.1:3111/agentmemory/'+v.route,{method:v.route==='export'?'GET':'POST',headers:{authorization:'Bearer '+process.env.AGENTMEMORY_SECRET,'content-type':'application/json'},body:v.route==='export'?undefined:JSON.stringify(v.body),signal:AbortSignal.timeout(45000)});if(!r.ok)throw Error('HTTP '+r.status);process.stdout.write(await r.text());"""
def api(route,body=None):return json.loads(run(['kubectl','-n',ns,'exec','-i','memory-restore','--','node','--input-type=module','-e',code],json.dumps({'route':route,'body':body}).encode()))
start=time.monotonic()
result=api('import',{'exportData':backup,'strategy':'merge'});atomic('import-result.json',result)
assert result.get('success') is True,'Import not acknowledged'
restored=api('export');atomic('restored-export.json',restored)
failures=[];counts={}
for key,value in backup.items():
 if key in ('exportedAt','accessLogs','pagination','version'):continue
 if isinstance(value,list):
  original={str(x.get('id')):x for x in value};got={str(x.get('id')):x for x in restored.get(key,[])}
  counts[key]={'original':len(value),'restored':len(got)}
  if not original.keys()<=got.keys():failures.append(key+':missing IDs')
  if key=='memories':
   for ident,m in original.items():
    if got.get(ident,{}).get('content')!=m.get('content'):failures.append('memory-content:'+ident)
 elif isinstance(value,dict) and value and value!=restored.get(key):failures.append(key+':different')
report={'status':'FAIL' if failures else 'PASS','counts':counts,'failures':failures,'seconds':time.monotonic()-start,'image':image,'namespace':ns,'production_mutated':False,'scope':'logical restore only'}
atomic('restore-result.json',report);print(json.dumps(report));raise SystemExit(bool(failures))
