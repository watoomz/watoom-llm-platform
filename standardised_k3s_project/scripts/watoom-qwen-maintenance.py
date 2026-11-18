#!/usr/bin/env python3
"""Guarded host-side single-model reasoning upgrade; no inference-agent dependency.
Usage: --check (read only), --apply --approve-downtime (explicit maintenance).
Resumption is a durable outbox, never a fabricated/unauthorized OpenCode API call.
"""
import argparse, copy, datetime, fcntl, hashlib, json, os, pathlib, subprocess, sys, time, traceback

NAME='llama-cpp-swift-qwen38-coder'
ROOT=pathlib.Path('/data/ai/projects/homelab/homelab-llm/standardised_k3s_project')
SOURCE=ROOT/'manifests/10-infrastructure/llm/llama-cpp-swift-qwen38.yml'
BASE=pathlib.Path('/data/ai/helper-scripts')
CONFIG=BASE/'config/gpu-controller.json'
STATE=BASE/'state/gpu-controller'
OUT=pathlib.Path('/data/ai/artifacts/qwen-reasoning-maintenance')
UNIT='watoom-gpu-controller.service'

class Blocked(RuntimeError): pass

def cmd(args, timeout=30, ok=True):
    p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if ok and p.returncode: raise Blocked(f'command failed: {args[0]} {args[1:]}: {p.stderr.strip()[-1000:]}')
    return p

def load(path): return json.loads(path.read_text())
def kub(): return load_stdout(['kubectl','-n','llama-cpp','get','deployment',NAME,'-o','json'])
def load_stdout(args): return json.loads(cmd(args).stdout)
def digest(obj):
    spec=copy.deepcopy(obj['spec']);spec.pop('replicas',None)
    return hashlib.sha256(json.dumps(spec,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def server(obj):
    xs=obj['spec']['template']['spec']['containers']
    matches=[(i,x) for i,x in enumerate(xs) if x.get('name')=='llama-server']
    if len(matches)!=1: raise Blocked('exactly one llama-server container required')
    return matches[0]

def reason_args(args):
    def value(k):
        indices=[i for i,v in enumerate(args) if v==k]
        if len(indices)>1: raise Blocked('duplicate '+k)
        if not indices:return None
        i=indices[0]
        if i+1>=len(args):raise Blocked('no value for '+k)
        return args[i+1]
    return value('--reasoning'),value('--reasoning-effort')

def staged():
    # Read only flags in source; reject ambiguous / noncanonical stage. No broad manifest apply.
    text=SOURCE.read_text()
    import re
    found=re.search(r'(?m)^\s*-\s*[\'\"]?--reasoning[\'\"]?\s*\n\s*-\s*[\'\"]?on[\'\"]?\s*\n\s*-\s*[\'\"]?--reasoning-effort[\'\"]?\s*\n\s*-\s*[\'\"]?low[\'\"]?\s*$',text)
    if not found: raise Blocked('source manifest does not unambiguously contain --reasoning on --reasoning-effort low')
    return hashlib.sha256(SOURCE.read_bytes()).hexdigest()

def ready_gate():
    staged()
    cfg=load(CONFIG);state=load(STATE/'state.json');lease=load(STATE/'inference-leases.json')
    live=kub();uid=live['metadata']['uid'];known=cfg.get('deployment_identity',{}).get(NAME)
    if known!={'uid':uid,'spec_sha256':digest(live)}:raise Blocked('approved UID/spec digest mismatch')
    if (state.get('phase'),state.get('owner'),state.get('uncertain'))!=('qwen-ready',None,False):raise Blocked('controller not qwen-ready/unowned/certain')
    leases=lease.get('leases')
    if not isinstance(leases,(dict,list)) or len(leases):raise Blocked('active or unknown inference leases')
    if live['spec'].get('replicas')!=1 or live.get('status',{}).get('readyReplicas')!=1:raise Blocked('primary must have exactly one ready replica')
    if cmd(['systemctl','is-active','--quiet',UNIT],ok=False).returncode:raise Blocked('GPU controller service not active')
    ix,c=server(live);args=c.get('args')
    if not isinstance(args,list):raise Blocked('llama-server args missing')
    reasoning,effort=reason_args(args)
    if reasoning!='on':raise Blocked('live reasoning must already be on')
    # Require no pending controller intents; acknowledged records can remain.
    intents=STATE/'intents'
    if intents.exists():
        for p in intents.glob('*.json'):
            if load(p).get('status')!='acknowledged':raise Blocked('pending controller mutation intent')
    return cfg,state,live,ix,args,effort

def atomic_json(path,obj):
    raw=(json.dumps(obj,sort_keys=True,indent=2)+'\n').encode()
    temp=path.with_name(path.name+'.maintenance-tmp-'+str(os.getpid()))
    mode=(path.stat().st_mode&0o777) if path.exists() else 0o600
    fd=os.open(temp,os.O_CREAT|os.O_EXCL|os.O_WRONLY,mode)
    try:
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.chmod(temp,mode);os.replace(temp,path)
        d=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(d)
        finally:os.close(d)
    finally:
        if temp.exists():temp.unlink()

def patch_args(live,index,old,new):
    # Kubernetes JSON patch CAS against resourceVersion + UID. Only args touched.
    operations=[{'op':'test','path':'/metadata/uid','value':live['metadata']['uid']},
                {'op':'test','path':'/metadata/resourceVersion','value':live['metadata']['resourceVersion']},
                {'op':'test','path':f'/spec/template/spec/containers/{index}/args','value':old},
                {'op':'replace','path':f'/spec/template/spec/containers/{index}/args','value':new}]
    return cmd(['kubectl','-n','llama-cpp','patch','deployment',NAME,'--type=json','-p',json.dumps(operations)],timeout=45)

def await_rollout(seconds):
    r=cmd(['kubectl','-n','llama-cpp','rollout','status','deployment/'+NAME,'--timeout='+str(seconds)+'s'],timeout=seconds+30,ok=False)
    if r.returncode:raise Blocked('rollout failure: '+r.stderr[-1000:])
    live=kub()
    if live.get('status',{}).get('readyReplicas')!=1:raise Blocked('new deployment not ready')
    return live

def record(path,obj):atomic_json(path,obj)

def main():
    p=argparse.ArgumentParser()
    mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--check',action='store_true');mode.add_argument('--apply',action='store_true')
    p.add_argument('--approve-downtime',action='store_true')
    p.add_argument('--session-id',help='Existing OpenCode session id, stored in handoff; optional')
    p.add_argument('--timeout',type=int,default=480)
    a=p.parse_args()
    if a.apply and not a.approve_downtime:raise Blocked('explicit --approve-downtime required')
    if os.geteuid()!=0:raise Blocked('run as root on homelab host')
    OUT.mkdir(parents=True,exist_ok=True);os.chmod(OUT,0o700)
    with (OUT/'maintenance.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        cfg,state,live,ix,args,effort=ready_gate()
        print('PREFLIGHT=PASS\nLIVE_EFFORT='+str(effort))
        if a.check:return
        if effort=='low':print('RESULT=ALREADY_LOW');return
        if effort is not None:raise Blocked('unknown current effort '+str(effort))
        # Record recovery data before any mutation, durable even if process dies.
        stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        folder=OUT/('run-'+stamp+'-'+str(os.getpid()));folder.mkdir(mode=0o700)
        record(folder/'deployment.before.json',live)
        record(folder/'controller-config.before.json',cfg)
        record(folder/'controller-state.before.json',state)
        handoff={'status':'checkpointed','session_id':a.session_id,'project':str(ROOT.parent),
                 'message':'The Swift Qwen deployment was restarted for reasoning_effort=low. Reconcile any interrupted tool calls before continuing. Preserve dirty work.',
                 'resume_delivery':'pending: integrate with verified OpenCode API; never auto-run unknown session commands'}
        record(folder/'resume-outbox.json',handoff)
        print('RECOVERY_DIR='+str(folder),flush=True)
        # Recheck before stopping controller. Controller remains stopped for the entire spec+identity transaction.
        stopped=False; changed=False; approved=False
        try:
            ready_gate()
            cmd(['systemctl','stop',UNIT],timeout=40);stopped=True
            if cmd(['systemctl','is-active','--quiet',UNIT],ok=False).returncode==0:raise Blocked('controller still active')
            # Recheck static gates with controller stopped, fail if requests/leases appeared.
            state2=load(STATE/'state.json');lease2=load(STATE/'inference-leases.json')
            if state2!=state or len(lease2.get('leases',[])):raise Blocked('state or leases changed during stop')
            current=kub()
            if current['metadata']['uid']!=live['metadata']['uid'] or digest(current)!=digest(live):raise Blocked('deployment changed during maintenance')
            j,c=server(current);old=c.get('args',[])
            if old!=args:raise Blocked('args changed during maintenance')
            new=list(old);at=new.index('--reasoning')+1;new[at]='on';new+=['--reasoning-effort','low']
            patch_args(current,j,old,new);changed=True
            rolled=await_rollout(a.timeout)
            newargs=server(rolled)[1]['args']
            if reason_args(newargs)!=('on','low'):raise Blocked('live reasoning flags mismatch after rollout')
            cfg2=load(CONFIG)
            if cfg2!=cfg:raise Blocked('controller config changed during maintenance')
            state2=load(STATE/'state.json');lease2=load(STATE/'inference-leases.json')
            if state2!=state or len(lease2.get('leases',[])):raise Blocked('controller state/leases changed during rollout')
            updated=copy.deepcopy(cfg);updated['deployment_identity'][NAME]={'uid':rolled['metadata']['uid'],'spec_sha256':digest(rolled)}
            atomic_json(CONFIG,updated);approved=True
            record(folder/'deployment.after.json',rolled)
            record(folder/'controller-config.after.json',updated)
            handoff['status']='model-ready-awaiting-resume';record(folder/'resume-outbox.json',handoff)
        except BaseException as exc:
            print('APPLY_ERROR='+str(exc),file=sys.stderr,flush=True)
            if changed:
                try:
                    actual=kub();j,c=server(actual)
                    # Preserve other modifications: rollback only if args still match our change.
                    expected=args+['--reasoning-effort','low']
                    if c.get('args')!=expected or actual['metadata']['uid']!=live['metadata']['uid']:
                        raise Blocked('unexpected live changes; manual recovery required')
                    patch_args(actual,j,expected,args)
                    oldlive=await_rollout(a.timeout)
                    if approved:
                        nowcfg=load(CONFIG)
                        if nowcfg['deployment_identity'][NAME]['spec_sha256']!=digest(actual):raise Blocked('approval changed; manual recovery required')
                        atomic_json(CONFIG,cfg)
                    if digest(oldlive)!=digest(live):raise Blocked('rollback does not match original spec; manual recovery required')
                    print('ROLLBACK=PASS',flush=True)
                except BaseException as rollback_err:
                    print('ROLLBACK=FAILED '+str(rollback_err),file=sys.stderr,flush=True)
                    handoff['status']='manual-recovery-required';record(folder/'resume-outbox.json',handoff)
                    # Do not restart controller when identity is inconsistent.
                    raise
            handoff['status']='rolled-back' if changed else 'not-applied';record(folder/'resume-outbox.json',handoff)
            raise
        finally:
            # Restart only when approved config matches actual live spec.
            if stopped:
                try:
                    actual=kub();match=load(CONFIG)['deployment_identity'][NAME]=={'uid':actual['metadata']['uid'],'spec_sha256':digest(actual)}
                    if match:
                        cmd(['systemctl','start',UNIT],timeout=50)
                        print('GPU_CONTROLLER_RESTARTED=YES',flush=True)
                    else:print('GPU_CONTROLLER_RESTARTED=NO IDENTITY_MISMATCH',file=sys.stderr,flush=True)
                except Exception as err:print('GPU_CONTROLLER_RESTART_FAILED='+str(err),file=sys.stderr,flush=True)
        print('RESULT=DEPLOYED\nRESUME_HANDOFF='+str(folder/'resume-outbox.json'))
        print('AUTO_RESUME=NOT_CONFIGURED (requires verified WatooM-Code session API adapter)')

if __name__=='__main__':
    try:main()
    except BaseException as e:
        print('RESULT=FAILED: '+str(e),file=sys.stderr)
        sys.exit(2)
