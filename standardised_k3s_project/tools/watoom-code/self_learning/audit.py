#!/usr/bin/env python3
"""Targeted read-only runtime audit; reports stay in the private run directory."""
import argparse,pathlib,json,subprocess,hashlib,zipfile,sys,time,tarfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
from maintenance_guard import Maintenance
from recover import atomic
p=argparse.ArgumentParser();p.add_argument('--evidence',required=True,type=pathlib.Path);p.add_argument('--namespace',required=True);p.add_argument('--allow-absent-staging',action='store_true');a=p.parse_args()
root=a.evidence.resolve();checks=[]
def record(name,status,evidence):checks.append({'id':name,'status':status,'evidence':evidence})
def kub(ns,*args):return json.loads(subprocess.check_output(['kubectl','--request-timeout=10s','-n',ns,*args,'-o','json'],timeout=20))
archive=pathlib.Path('/data/ai/helper-scripts/WatooM_Self_Learning_Research_Audit_Implementation.zip')
with zipfile.ZipFile(archive) as z:record('PACKAGE_INTEGRITY','PASS' if z.testzip() is None else 'FAIL',{'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'files':z.namelist()})
baseline=json.loads((root/'baseline/deployments.json').read_text())['items']
for name in ['watoom-code','agentmemory']:
 old=next(x for x in baseline if x['metadata']['name']==name);live=kub('watoom-code','get','deploy',name)
 same=old['metadata']['uid']==live['metadata']['uid'] and [c['image'] for c in old['spec']['template']['spec']['containers']]==[c['image'] for c in live['spec']['template']['spec']['containers']]
 record('PRODUCTION_'+name,'PASS' if same and live.get('status',{}).get('readyReplicas')==1 else 'FAIL',{'same_uid_and_images':same,'ready':live.get('status',{}).get('readyReplicas'),'images':[c['image'] for c in live['spec']['template']['spec']['containers']]})
with tarfile.open(root/'baseline/configuration.tar.gz') as tar:before=tar.extractfile('config/opencode.json').read()
current=pathlib.Path('/data/ai/watoom-code/config/opencode.json').read_bytes()
record('PRODUCTION_CONFIG_PRESERVED','PASS' if current==before else 'WARN',{'baseline_sha256':hashlib.sha256(before).hexdigest(),'current_sha256':hashlib.sha256(current).hexdigest()})
try:
 m=Maintenance('watoom-code','watoom-code',root,True,True);info=m.request('/api/info');guard=m.request('/api/session/deployment-guard');active=m.request('/api/session/active')
 record('PRODUCTION_AUTHENTICATED_HEALTH','PASS',{'version':info.get('version'),'deployment_guard':guard,'active_sessions':len(active.get('data',{}))})
except Exception as e:record('PRODUCTION_AUTHENTICATED_HEALTH','FAIL',{'error':str(e)[:300]})
old=json.loads((root/'baseline/inference.json').read_text());live=kub('llama-cpp','get','deploy',old['metadata']['name'])
record('SELECTED_INFERENCE_PRESERVED','PASS' if old['spec']==live['spec'] and live.get('status',{}).get('readyReplicas',0)>=old['spec'].get('replicas',1) else 'WARN',{'same_spec':old['spec']==live['spec'],'ready':live.get('status',{}).get('readyReplicas')})
stage_present=subprocess.run(['kubectl','get','namespace',a.namespace,'--ignore-not-found','-o','name'],capture_output=True,text=True,check=True).stdout.strip()
if not stage_present and not a.allow_absent_staging:raise RuntimeError('Expected staging namespace missing')
for name in (['learning-app','learning-memory'] if stage_present else []):
 live=kub(a.namespace,'get','deploy',name);s=live['spec']['template']['spec'];paths=[v['hostPath']['path'] for v in s.get('volumes',[]) if 'hostPath' in v]
 safe=s.get('automountServiceAccountToken') is False and all(str(root/'staging') in path for path in paths) and all(not any('gpu' in k.lower() for k in c.get('resources',{}).get('limits',{})) for c in s['containers'])
 record('ISOLATION_'+name,'PASS' if safe else 'FAIL',{'token_automount':s.get('automountServiceAccountToken'),'host_paths':paths,'gpu_resources':False,'ready':live.get('status',{}).get('readyReplicas')})
r=subprocess.run(['kubectl','auth','can-i','patch','deployments','-n','watoom-code','--as=system:serviceaccount:'+a.namespace+':default'],capture_output=True,text=True,timeout=20)
record('STAGING_PRODUCTION_RBAC','PASS' if r.stdout.strip()=='no' else 'FAIL',{'can_patch_production':r.stdout.strip()})
report={'time':time.time(),'checks':checks,'result':'PASS' if all(x['status']=='PASS' for x in checks) else 'PARTIAL'}
atomic(root/'runtime-audit.json',report);print(json.dumps({'result':report['result'],'checks':[{k:x[k] for k in ['id','status']} for x in checks]}))

if report["result"]!="PASS":raise SystemExit(1)
