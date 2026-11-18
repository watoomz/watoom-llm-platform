#!/usr/bin/env python3
"""Suspend only the legacy canary after draining its existing application services."""
import argparse,json,pathlib,subprocess,time,secrets,os,sys
from release_guard import UnsafeRelease,active_clear
from maintenance_guard import run
NS='opencode';NAME='opencode-v2-canary'
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--evidence',required=True,type=pathlib.Path);ap.add_argument('--i-approve',action='store_true');a=ap.parse_args()
 print('RISK: stops the idle legacy OpenCode canary only. Existing service routes are temporarily drained, then restored; production, inference and persistent data are preserved.',flush=True)
 if not a.i_approve:raise UnsafeRelease('--i-approve required')
 out=a.evidence.resolve()
 if not out.is_relative_to(pathlib.Path('/data/ai/helper-scripts/reports')):raise UnsafeRelease('Evidence must remain in helper reports')
 out.mkdir(mode=0o700,parents=True,exist_ok=False)
 def save(name,value):
  p=out/name;p.write_text(json.dumps(value,indent=2));p.chmod(0o600)
 def kub(*args):return json.loads(run(['kubectl','-n',NS,*args,'-o','json']))
 d=kub('get','deployment',NAME);save('deployment-before.json',d)
 if d['spec'].get('replicas')==0:
  result={'status':'PASS','changed':False,'namespace':NS,'deployment':NAME,'replicas':0};save('result.json',result);print(json.dumps(result));return
 if d['spec'].get('replicas')!=1:raise UnsafeRelease('Expected one legacy canary replica')
 if any(x['spec']['scaleTargetRef'].get('name')==NAME for x in kub('get','hpa')['items']):raise UnsafeRelease('Canary autoscaler must be resolved in IaC first')
 pods=[p for p in kub('get','pods','-l','app='+NAME)['items'] if not p['metadata'].get('deletionTimestamp') and p['status'].get('phase')=='Running']
 if len(pods)!=1:raise UnsafeRelease('Canary pod identity ambiguous')
 pod=pods[0];save('pod-before.json',pod)
 # Refuse administrative bypasses rather than stopping somebody's tunnel.
 for proc in pathlib.Path('/proc').iterdir():
  if not proc.name.isdigit():continue
  try:argv=proc.joinpath('cmdline').read_bytes().split(bytes([0]))
  except OSError:continue
  if b'port-forward' in argv and b'opencode' in argv:raise UnsafeRelease('Legacy namespace port-forward is active; nothing stopped')
 probe_code="""import os,json,pathlib,urllib.request,base64
h={'Authorization':'Basic '+base64.b64encode((os.environ.get('OPENCODE_SERVER_USERNAME','opencode')+':'+os.environ['OPENCODE_SERVER_PASSWORD']).encode()).decode(),'Connection':'close'}
with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:4096/api/session/active',headers=h),timeout=10) as f:active=json.load(f)
unknown=[]
for p in pathlib.Path('/proc').iterdir():
 if not p.name.isdigit() or int(p.name) in [1,os.getpid()]:continue
 try:
  args=[x.decode() for x in (p/'cmdline').read_bytes().split(bytes([0])) if x];stat=(p/'stat').read_text().split()
  if args and not (stat[3]=='1' and args[0]=='/usr/local/lib/node_modules/@opencode/cli/bin/opencode.exe' and 'serve' in args):unknown.append({'pid':p.name,'executable':args[0]})
 except OSError:pass
connections=0
for table in ['tcp','tcp6']:
 for line in pathlib.Path('/proc/net/'+table).read_text().splitlines()[1:]:
  x=line.split()
  if int(x[1].split(':')[1],16)==4096 and x[3] in ['01','03','08']:connections+=1
print(json.dumps({'active':active,'unknown_processes':unknown,'connections':connections}))
"""
 def probe():
  current=kub('get','pod',pod['metadata']['name'])
  if current['metadata']['uid']!=pod['metadata']['uid']:raise UnsafeRelease('Canary identity changed')
  state=json.loads(run(['kubectl','-n',NS,'exec',pod['metadata']['name'],'-c','opencode','--','python3','-c',probe_code]))
  active_clear(state['active'])
  if state['unknown_processes']:raise UnsafeRelease('Canary has active child work; nothing stopped')
  return state
 probe()
 services=[s for s in kub('get','services')['items'] if s['spec'].get('selector') and all(pod['metadata']['labels'].get(k)==v for k,v in s['spec']['selector'].items())]
 if not services or any(s['spec'].get('type')!='ClusterIP' for s in services):raise UnsafeRelease('Expected internal legacy application services')
 save('services-before.json',services);fences=[]
 try:
  for service in services:
   selector={'watoom-canary-suspension':secrets.token_hex(16)}
   entry={'name':service['metadata']['name'],'uid':service['metadata']['uid'],'before':service['spec']['selector'],'held':selector}
   fences.append(entry);save('service-fences.private.json',fences)
   ops=[{'op':'test','path':'/metadata/uid','value':entry['uid']},{'op':'test','path':'/spec/selector','value':entry['before']},{'op':'replace','path':'/spec/selector','value':selector}]
   run(['kubectl','-n',NS,'patch','service',entry['name'],'--type=json','-p',json.dumps(ops)])
  deadline=time.monotonic()+45;quiet=0
  while time.monotonic()<deadline:
   state=probe();save('last-drain.json',state)
   drained=True
   for entry in fences:
    actual=kub('get','service',entry['name'])
    if actual['metadata']['uid']!=entry['uid'] or actual['spec']['selector']!=entry['held']:raise UnsafeRelease('Service fence changed')
    slices=kub('get','endpointslices','-l','kubernetes.io/service-name='+entry['name'])
    drained=drained and not any(s.get('endpoints') for s in slices['items'])
   quiet=quiet+1 if drained and state['connections']==0 else 0
   if quiet>=3:break
   time.sleep(.5)
  else:raise UnsafeRelease('Canary connections did not drain; nothing stopped')
  latest=kub('get','deployment',NAME)
  if latest['metadata']['uid']!=d['metadata']['uid']:raise UnsafeRelease('Deployment identity changed')
  probe()
  run(['kubectl','-n',NS,'scale','deployment/'+NAME,'--replicas=0','--current-replicas=1','--resource-version='+latest['metadata']['resourceVersion']])
  deadline=time.monotonic()+90
  while time.monotonic()<deadline:
   if not kub('get','pods','-l','app='+NAME)['items']:break
   time.sleep(1)
  else:raise UnsafeRelease('Canary termination did not converge; evidence retained')
 finally:
  for entry in reversed(fences):
   current=kub('get','service',entry['name'])
   if current['spec']['selector']==entry['before']:continue
   if current['metadata']['uid']!=entry['uid'] or current['spec']['selector']!=entry['held']:raise UnsafeRelease('Refusing to overwrite concurrent service change; recovery snapshot retained')
   run(['kubectl','-n',NS,'patch','service',entry['name'],'--type=json','-p',json.dumps([{'op':'test','path':'/spec/selector','value':entry['held']},{'op':'replace','path':'/spec/selector','value':entry['before']}])])
 final=kub('get','deployment',NAME);save('deployment-after.json',final)
 if final['spec'].get('replicas')!=0:raise UnsafeRelease('Canary replicas did not remain zero')
 for service in services:
  slices=kub('get','endpointslices','-l','kubernetes.io/service-name='+service['metadata']['name'])
  if any(s.get('endpoints') for s in slices['items']):raise UnsafeRelease('Canary endpoint remains')
 result={'status':'PASS','changed':True,'namespace':NS,'deployment':NAME,'replicas':0,'pods':0,'service_endpoints':0,'service_selectors_restored':True,'active_work_interrupted':False,'persistent_data_preserved':True};save('result.json',result);print(json.dumps(result))
if __name__=='__main__':main()
