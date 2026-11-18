#!/usr/bin/env python3
import argparse,pathlib,json,sqlite3,subprocess,time,sys,hashlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
from maintenance_guard import Maintenance
from release_guard import active_clear
from recover import atomic
p=argparse.ArgumentParser();p.add_argument('--evidence',required=True,type=pathlib.Path);p.add_argument('--namespace',required=True);a=p.parse_args()
if not a.namespace.startswith('watoom-code-learning-'):raise ValueError('Isolated controls only')
root=a.evidence;stage=root/'staging';m=Maintenance(a.namespace,'learning-app',root,True,True)
def states():
 with sqlite3.connect('file:'+str(stage/'state/application.sqlite')+'?mode=ro',uri=True) as c:return [json.loads(x[0]) for x in c.execute('select value from kv where key like ?',('%learning/v1/%',))]
def skill():return next(k for s in states() for k in s['skills'].values() if k['id']==ident)
ident=next(k['id'] for s in states() for k in s['skills'].values() if k['state']=='active')
path=stage/'state/skills'/pathlib.Path(skill()['path']).name;original=hashlib.sha256(path.read_bytes()).hexdigest()
def wait(fn,seconds=60):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  try:
   value=fn()
   if value:return value
  except Exception:pass
  time.sleep(1)
 raise RuntimeError('Control test deadline exceeded')
def action(name):
 r=subprocess.run(['python3',str(pathlib.Path(__file__).with_name('manage.py')),'--evidence',str(root),'--action',name,'--id',ident],capture_output=True,text=True,timeout=20)
 if r.returncode:raise RuntimeError(r.stderr)
 return json.loads(r.stdout)
active_clear(m.request('/api/session/active'));start=time.monotonic()
disabled=action('disable');wait(lambda:skill()['state']=='disabled')
wait(lambda:all(k['id']!=ident for k in m.request('/api/skill?location%5Bdirectory%5D=%2Fworkspace')['data']))
enabled=action('enable');wait(lambda:skill()['state']=='active')
wait(lambda:any(k['id']==ident for k in m.request('/api/skill?location%5Bdirectory%5D=%2Fworkspace')['data']))
scope='/workspace/isolation-check';(stage/'workspace/isolation-check').mkdir(exist_ok=True)
other=m.request('/api/session',{'title':'Project isolation acceptance','agent':'learning-fixture','location':{'directory':scope}})['data']
# A location-specific registry must not expose another directory's generated Skill.
other_response=m.request('/api/skill?location%5Bdirectory%5D=%2Fworkspace%2Fisolation-check');assert other_response['location']['directory']==scope,'Wrong native location response';other_skills=other_response['data']
assert all(k['id']!=ident for k in other_skills),'Cross-project native Skill exposure'
before=len(next(s for s in states() if ident in s['skills'])['events'])
pod=m.pod();restart=pod['status']['containerStatuses'][0]['restartCount']
container=pod['status']['containerStatuses'][0]['containerID'].removeprefix('containerd://')
if len(container)!=64 or any(c not in '0123456789abcdef' for c in container):raise ValueError('Unexpected staging container identity')
r=subprocess.run(['crictl','stop','--timeout','5',container],capture_output=True,timeout=20)
if r.returncode:raise RuntimeError(r.stderr.decode())
wait(lambda:m.pod()['status']['containerStatuses'][0]['restartCount']>restart,90)
wait(lambda:bool(m.request('/api/info').get('version')),90)
# Warm the location and wait for actual learned-Skill readiness, not TCP alone.
m.request('/api/session',{'title':'Post-termination readiness','agent':'learning-fixture','location':{'directory':'/workspace'}})
wait(lambda:any(k['id']==ident for k in m.request('/api/skill?location%5Bdirectory%5D=%2Fworkspace')['data']),60)
assert skill()['state']=='active' and hashlib.sha256(path.read_bytes()).hexdigest()==original
after=len(next(s for s in states() if ident in s['skills'])['events']);assert before==after,'Restart duplicated learning'
report={'status':'PASS','disable':'PASS','enable':'PASS','native_project_isolation':'PASS','process_termination':'PASS','restart_persistence':'PASS','duplicate_events_after_restart':after-before,'artifact_unchanged':True,'seconds':time.monotonic()-start,'operations':[disabled,enabled]}
atomic(root/'native-tests/operator-and-restart.json',report);print(json.dumps(report))
