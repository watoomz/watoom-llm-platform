"""Reviewed quiescence/barrier checks. No replica mutation is performed here."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
from datetime import datetime, timezone
from controller import State
from durable_store import DurableStore
from g3h_service import atomic, process_identity


def k(*args):
    result=subprocess.run(['kubectl',*args],capture_output=True,text=True,timeout=45)
    if result.returncode:raise RuntimeError('kubectl gate failed: '+result.stderr[-1000:])
    return result.stdout


def models():
    return {x['metadata']['name']:x for x in json.loads(k('-n','llama-cpp','get','deploy','-o','json'))['items']
            if x['metadata']['name'].startswith('llama-cpp-')}


def quiescent(config):
    job_root=Path('/data/ai/llama-mesh/jobs')
    for state in ('pending','running'):
        if any(p.is_dir() for p in (job_root/state).iterdir()):raise RuntimeError('queue is not idle')
    pods=json.loads(k('-n','llama-cpp','get','pods','-l','app=llm-router','-o','json'))['items']
    if pods:raise RuntimeError('legacy router pods have not retired')
    for directory in Path('/proc').iterdir():
        if not directory.name.isdigit():continue
        try:args=(directory/'cmdline').read_bytes().decode(errors='replace').split('\0')
        except (FileNotFoundError,PermissionError,ProcessLookupError):continue
        if any(Path(arg).name=='llama_mesh_pipeline.py' for arg in args) and any(arg in ('worker','recover','recover-queue') for arg in args):
            raise RuntimeError('legacy worker/recovery process remains active')
    for name in ('watoom-opencode-mesh-bridge','watoom-llama-mesh-recovery'):
        result=subprocess.run(['systemctl','is-active',name],capture_output=True,text=True)
        if result.stdout.strip() in ('active','activating','deactivating'):raise RuntimeError('legacy service remains active: '+name)


def validate_policy(config, evidence):
    policy=json.loads(k('get','validatingadmissionpolicy','watoom-gpu-exclusive-writer','-o','json'))
    binding=json.loads(k('get','validatingadmissionpolicybinding','watoom-gpu-exclusive-writer','-o','json'))
    warnings=policy.get('status',{}).get('typeChecking',{}).get('expressionWarnings',[])
    if warnings:raise RuntimeError('admission CEL type warnings: '+str(warnings))
    if binding['spec'].get('validationActions')!=['Deny']:raise RuntimeError('admission binding is not enforcing')
    checks=[]
    for name,obj in models().items():
        # Actual server dry-run: no model replicas change, even for the negative probe.
        desired=1-obj['spec']['replicas'] if obj['spec']['replicas'] in (0,1) else 0
        patch=json.dumps({'spec':{'replicas':desired}})
        for subresource in (False,True):
            cmd=['kubectl','-n','llama-cpp','patch','deployment',name,'--type=merge','-p',patch,'--dry-run=server']
            if subresource:cmd+=['--subresource=scale']
            result=subprocess.run(cmd,capture_output=True,text=True,timeout=45)
            expected='GPU scale subresource is retired' if subresource else 'Only the GPU controller'
            if result.returncode==0 or expected not in result.stderr:
                raise RuntimeError('active admission denial not demonstrated for '+name+' '+str(subresource))
            checks.append({'name':name,'scale_subresource':subresource,'denied':True})
    atomic(Path(evidence)/'policy-live-check.json',{'checked_at':time.time(),'policy_uid':policy['metadata']['uid'],'checks':checks})


def barrier(config,evidence):
    quiescent(config)
    check=json.loads((Path(evidence)/'policy-live-check.json').read_text())
    if time.time()-check['checked_at']>300:raise RuntimeError('admission check is stale')
    before=models();results={}
    proof=Path(evidence)/'cutover-barrier.json'
    for name,obj in sorted(before.items()):
        nonce=uuid.uuid4().hex
        intent={'uid':obj['metadata']['uid'],'before_version':obj['metadata']['resourceVersion'],'nonce':nonce,'status':'pending'}
        results[name]=intent;atomic(proof,{'status':'in-progress','models':results,'time':time.time()})
        annotations=dict(obj['metadata'].get('annotations') or {})
        annotations['watoom.io/gpu-cutover-barrier']=nonce
        ops=[{'op':'test','path':'/metadata/uid','value':intent['uid']},
             {'op':'test','path':'/metadata/resourceVersion','value':intent['before_version']},
             {'op':'add','path':'/metadata/annotations','value':annotations}]
        result=json.loads(k('-n','llama-cpp','patch','deployment',name,'--type=json','-p',json.dumps(ops),'-o','json'))
        if result['metadata']['uid']!=intent['uid'] or result['metadata']['resourceVersion']==intent['before_version'] or result['metadata']['annotations'].get('watoom.io/gpu-cutover-barrier')!=nonce:
            raise RuntimeError('invalid barrier acknowledgement')
        intent.update(status='acknowledged',after_version=result['metadata']['resourceVersion'])
        atomic(proof,{'status':'in-progress','models':results,'time':time.time()})
    # G3H_POST_BARRIER_SPEC_REPLICA_CHECK_V1
    # Compare every acknowledged Deployment's desired replicas and protected spec.
    # Ignore metadata annotations/resourceVersion mutated by the barrier itself.
    after=models()
    if set(before)!=set(after):raise RuntimeError('GPU deployment inventory changed during barrier')
    for name,original in before.items():
        current=after[name]
        if current['metadata']['uid']!=original['metadata']['uid']:
            raise RuntimeError('GPU deployment UID changed during barrier: '+name)
        if current['spec'].get('replicas',1)!=original['spec'].get('replicas',1):
            raise RuntimeError('GPU replica drift during barrier: '+name)
        oldspec={k:v for k,v in original['spec'].items() if k!='replicas'}
        newspec={k:v for k,v in current['spec'].items() if k!='replicas'}
        if oldspec!=newspec:
            raise RuntimeError('GPU protected spec drift during barrier: '+name)
    for name,obj in after.items():
        if obj['metadata']['uid']!=results[name]['uid']:raise RuntimeError('GPU deployment recreated')
    atomic(proof,{'status':'complete','models':results,'time':time.time()})
    print('RESULT=ALL_GPU_STORAGE_BARRIERS_ACKNOWLEDGED')


def initialize(config,evidence):
    quiescent(config)
    proof=json.loads((Path(evidence)/'cutover-barrier.json').read_text())
    if proof['status']!='complete' or time.time()-proof['time']>600:raise RuntimeError('complete fresh barriers required')
    inventory=models()
    if set(inventory)!=set(proof['models']):raise RuntimeError('GPU inventory changed')
    for name,obj in inventory.items():
        if obj['metadata']['uid']!=proof['models'][name]['uid']:raise RuntimeError('GPU identity changed')
        if name not in (config['primary'],config['mesh']) and obj['spec']['replicas']!=0:
            raise RuntimeError('unexpected other GPU model; do not reclaim it')
    for name,identity in config['deployment_identity'].items():
        obj=inventory[name];spec=dict(obj['spec']);spec.pop('replicas',None)
        digest=hashlib.sha256(json.dumps(spec,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if obj['metadata']['uid']!=identity['uid'] or digest!=identity['spec_sha256']:raise RuntimeError('protected model spec changed')
    root=Path(config['state_root']);root.mkdir(mode=0o700,parents=True,exist_ok=True)
    if (root/'state.json').exists():raise RuntimeError('refuse to overwrite existing durable ownership')
    atomic(root/'cutover-proof.json',proof)
    baseline=inventory[config['primary']]['spec']['replicas']==1 and inventory[config['mesh']]['spec']['replicas']==0
    if baseline:
        DurableStore(root/'state.json').save(State())
        print('RESULT=CONTROLLER_INITIALIZED_QWEN_READY')
    else:
        # The cutover operator is a real process identity; recovery is permitted
        # only AFTER this initializer exits and verified old-writer barriers exist.
        job=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
        atomic(root/'worker.json',{'job':job,'pid':os.getpid(),'start':process_identity(os.getpid())})
        DurableStore(root/'state.json').save(State('recovery-required',job,1,True))
        print('RESULT=CONTROLLER_INITIALIZED_RECOVERY_REQUIRED JOB='+job)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('policy-check','barrier','initialize'))
    parser.add_argument('--config',required=True)
    parser.add_argument('--evidence',required=True)
    args=parser.parse_args();config=json.loads(Path(args.config).read_text())
    Path(args.evidence).mkdir(mode=0o700,parents=True,exist_ok=True)
    if args.action=='policy-check':validate_policy(config,args.evidence)
    elif args.action=='barrier':barrier(config,args.evidence)
    else:initialize(config,args.evidence)
