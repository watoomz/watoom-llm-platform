#!/usr/bin/env python3
"""Read-only staging runtime acceptance; no production access or fixture substitution."""
import argparse,base64,hashlib,json,pathlib,sqlite3,subprocess,urllib.request,urllib.error
p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();out=pathlib.Path(a.output);checks={};namespace='watoom-code'
def kub(*args):return json.loads(subprocess.check_output(['kubectl','-n',namespace,*args,'-o','json']))
secret=kub('get','secret','watoom-code-auth')['data'];password=base64.b64decode(secret['OPENCODE_PASSWORD']).decode();token=base64.b64decode(secret['token']).decode()
def request(service,port,path,authorized=True):
 ip=kub('get','service',service)['spec']['clusterIP'];headers={}
 if authorized:headers['Authorization']=('Basic '+base64.b64encode(('opencode:'+password).encode()).decode()) if service=='watoom-code' else 'Bearer '+token
 try:
  with urllib.request.urlopen(urllib.request.Request('http://'+ip+':'+str(port)+path,headers=headers),timeout=15) as r:return r.status,r.read(),dict(r.headers)
 except urllib.error.HTTPError as e:return e.code,e.read(),{}
for name in ['watoom-code','agentmemory','watoom-toolkit']:
 d=kub('get','deployment',name);checks[name+'_ready']=d['status'].get('readyReplicas')==1
 checks[name+'_immutable']=all('@sha256:' in c['image'] for c in d['spec']['template']['spec']['containers'])
 checks[name+'_standard_selinux']=d['spec']['template']['spec'].get('securityContext',{}).get('seLinuxOptions',{}).get('type')!='spc_t'
checks['server']=request('watoom-code',4096,'/api/info')[0]==200
checks['auth_boundary']=request('watoom-code',4096,'/api/config',False)[0]==401
status,body,headers=request('watoom-code',4096,'/',False);checks['web_shell']=status==200 and b'<!doctype html' in body.lower()
status,body,_=request('watoom-code',4096,'/api/config/profiles');catalog=json.loads(body);checks['seven_profiles']=status==200 and len(catalog['profiles'])==7
status,body,_=request('watoom-code',4096,'/api/agent');agents={x['id'] for x in json.loads(body)['data']};checks['native_agents']={"watoom-workflow","watoom-builder","watoom-investigator","watoom-reviewer","watoom-kali"}.issubset(agents)
status,body,_=request('watoom-code',4096,'/api/plugin');plugins={x['id']:x['state']['status'] for x in json.loads(body)['data']}
for name in ['watoom.tool.specialist','watoom.tool.memory','watoom.tool.worker']:checks[name]=plugins.get(name)=='active'
status,body,_=request('watoom-toolkit',8879,'/api/catalog');toolkit=json.loads(body);checks['toolkit_local_only']=status==200 and all(x.get('backend') in ('blender-cpu','generic-specialist') and x.get('id')!='meshy' for x in toolkit['generators']);checks['paid_route_absent']=request('watoom-toolkit',8879,'/api/providers/meshy')[0]==404
checks['app_no_kubernetes_token']=kub('get','deployment','watoom-code')['spec']['template']['spec'].get('automountServiceAccountToken') is False
checks['controller_no_gpu']=all(c.get('resources',{}).get('limits',{}).get('nvidia.com/gpu',0)==0 for c in kub('get','deployment','watoom-toolkit')['spec']['template']['spec']['containers'])
root=pathlib.Path('/data/ai/watoom-code');database=root/'application.sqlite'
with sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True) as db:
 checks['workflow_checkpoint']=db.execute('SELECT count(*) FROM _watoom_checkpoint').fetchone()[0]>0
 rows=db.execute('SELECT * FROM _watoom_outbox').fetchall();checks['memory_observed']=any('observed' in row for row in rows)
checks['no_worker_leaks']=not kub('get','jobs','-l','app=watoom-toolkit-worker').get('items') and not kub('get','pods','-l','app=watoom-toolkit-worker').get('items')
result={'result':'PASS' if all(checks.values()) else 'FAIL','checks':checks};out.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2));raise SystemExit(0 if result['result']=='PASS' else 1)
