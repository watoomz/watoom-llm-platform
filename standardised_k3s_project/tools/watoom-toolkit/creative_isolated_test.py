#!/usr/bin/env python3
"""One owned bounded CPU worker exercises maintained creative code against read-only library sources."""
import argparse,json,pathlib,secrets,subprocess,os
p=argparse.ArgumentParser();p.add_argument('--evidence',required=True,type=pathlib.Path);p.add_argument('--operation',required=True,choices=['inspect','optimize','world','character','material']);p.add_argument('--asset-id',required=True);p.add_argument('--additional-asset-id',action='append',default=[]);p.add_argument('--seed',type=int,default=42);p.add_argument('--parameters',default='{}');a=p.parse_args()
import asset_catalog,creative
root=pathlib.Path(__file__).parent;r=a.evidence
catalog=asset_catalog.Catalog('/assets',r/'catalog-test-state/catalog.json')
sources=[]
for ref in [a.asset_id,*a.additional_asset_id]:
 metadata=dict(catalog.load()['records'][ref]);path=asset_catalog.safe(pathlib.Path('/data/ai/assets'),metadata['path']);assert path.stat().st_mtime_ns==metadata['mtime_ns'] and path.stat().st_size==metadata['bytes'];metadata['sha256']=asset_catalog.checksum(path);metadata['checksum_state']='VERIFIED';sources.append({'path':'/assets/'+metadata['path'],'reference':metadata})
token=secrets.token_hex(8);name='creative-'+a.operation+'-'+token
output=r/name;output.mkdir();os.chown(output,1010,1009);output.chmod(0o770)
request={'task':'3d-creative','operation':a.operation,'asset_id':a.asset_id,'asset_ids':a.additional_asset_id,'seed':a.seed,'parameters':json.loads(a.parameters),'sources':sources,'input':sources[0]['path'],'output':'/job/artifacts','job_id':token}
creative.validate({k:v for k,v in request.items() if k not in ['sources','input','output','job_id']})
cm={'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':name,'namespace':'watoom-code'},'data':{f.name:f.read_text() for f in root.iterdir() if f.suffix in ['.py','.gd'] and not f.name.startswith('test_') and f.stat().st_size<150000}}
job={'apiVersion':'batch/v1','kind':'Job','metadata':{'name':name,'namespace':'watoom-code','labels':{'watoom-test-owner':'creative-pipelines-20261017'}},'spec':{'backoffLimit':0,'activeDeadlineSeconds':180,'template':{'metadata':{'labels':{'watoom-test-owner':'creative-pipelines-20261017'}},'spec':{'restartPolicy':'Never','automountServiceAccountToken':False,'securityContext':{'runAsUser':1010,'runAsGroup':1009,'runAsNonRoot':True,'fsGroup':1009},'containers':[{'name':'worker','image':'127.0.0.1:5000/watoom-toolkit@sha256:2a12a7ddbab49fdb4c17db85b074b644a6cc97bc27ff1ce5069beeefd04baca3','command':['blender','--factory-startup','--disable-autoexec','--background','--threads','1','--python-exit-code','1','--python','/opt/watoom/creative_blender.py','--',json.dumps(request)],'env':[{'name':'HOME','value':'/home/toolkit'},{'name':'OPENBLAS_NUM_THREADS','value':'1'},{'name':'OMP_NUM_THREADS','value':'1'}],'securityContext':{'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']},'seccompProfile':{'type':'RuntimeDefault'}},'resources':{'limits':{'cpu':'1','memory':'2Gi'},'requests':{'cpu':'100m','memory':'128Mi'}},'volumeMounts':[{'name':'library','mountPath':'/assets','readOnly':True},{'name':'code','mountPath':'/opt/watoom','readOnly':True},{'name':'output','mountPath':'/job'},{'name':'tmp','mountPath':'/tmp'},{'name':'home','mountPath':'/home/toolkit'}]}],'volumes':[{'name':'library','hostPath':{'path':'/data/ai/assets','type':'Directory'}},{'name':'code','configMap':{'name':name}},{'name':'output','hostPath':{'path':str(output),'type':'Directory'}},{'name':'tmp','emptyDir':{'sizeLimit':'256Mi'}},{'name':'home','emptyDir':{'sizeLimit':'64Mi'}}]}}}}
(output/'request.private.json').write_text(json.dumps(request,indent=2));(output/'job.json').write_text(json.dumps(job,indent=2))
for obj in [cm,job]:subprocess.run(['kubectl','apply','-f','-'],input=json.dumps(obj).encode(),check=True,capture_output=True)
import time
deadline=time.monotonic()+195
while time.monotonic()<deadline:
 current=json.loads(subprocess.check_output(['kubectl','-n','watoom-code','get','job',name,'-o','json']))
 if current.get('status',{}).get('succeeded')==1 or current.get('status',{}).get('failed'):break
 time.sleep(2)
logs=subprocess.check_output(['kubectl','-n','watoom-code','logs','job/'+name],text=True)
(output/'worker.log').write_text(logs)
if current.get('status',{}).get('succeeded')!=1:raise RuntimeError('Owned creative job failed; inspect '+str(output)+'\n'+logs[-2000:])
manifest=json.loads((output/'artifacts/manifest.json').read_text())
assert manifest['status']=='PASS' and manifest['creative']['source_hashes_unchanged'] is True and manifest['godot_acceptance']['status']=='PASS'
for item in manifest['outputs']:assert asset_catalog.checksum(output/'artifacts'/item['path'])==item['sha256']
assert set(creative.names(request))==set([item['path'] for item in manifest['outputs']]+['manifest.json'])
(r/('latest-'+a.operation+'.txt')).write_text(str(output)+'\n')
print(json.dumps({'status':'PASS','operation':a.operation,'evidence':str(output),'godot':manifest['godot_acceptance'],'source_unchanged':True,'artifact_sha256':asset_catalog.checksum(output/'artifacts/asset.glb')}))
