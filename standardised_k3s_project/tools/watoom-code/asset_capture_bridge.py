"""Native declarative capture bridge, dispatched under the existing worker lock."""
import json,pathlib,hashlib,os,stat,secrets,subprocess,sys,re,sqlite3,time
from asset_capture_contract import native_proof,contained
from bazzite_wait import bazzite_wait,wait_reason
CONFIG=pathlib.Path('/etc/watoom-asset-capture.json')
PRIVATE=pathlib.Path('/data/ai/private/asset-capture')
REPORTS=pathlib.Path('/data/ai/helper-scripts/reports/asset-capture')
def identity(v):return hashlib.sha256(json.dumps([v[k] for k in ('project','job','manifest_sha256','session_id','message_id','call_id')],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def publish(v,status,**extra):
 value={k:v[k] for k in ('request_id','project','job','manifest_sha256')};value.update(status=status,**extra)
 temporary=PRIVATE/(v['request_id']+'.tmp');temporary.write_text(json.dumps(value,indent=2));temporary.replace(PRIVATE/(v['request_id']+'.json'))
 parent=os.open(v['project'],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:
  for component in ('.opencode','asset-capture-requests'):
   child=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent);os.close(parent);parent=child
  name='.'+secrets.token_hex(12)+'.tmp';fd=os.open(name,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o644,dir_fd=parent)
  with os.fdopen(fd,'w') as f:json.dump(value,f,indent=2)
  os.replace(name,v['request_id']+'.status.json',src_dir_fd=parent,dst_dir_fd=parent)
 finally:os.close(parent)
 return value

def cancelled(session,database="/data/ai/watoom-code/application.sqlite",active_sessions=()):
 with sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True) as db:
  for _ in range(12):
   row=db.execute('select parent_id,idle_outcome from session_v2 where id=?',(session,)).fetchone()
   if not row or (row[1]=='interrupted' and session not in active_sessions):return True
   if not row[0]:return False
   session=row[0]
 return True

def dispatch(m):
 if not CONFIG.exists():return False
 cfg=json.loads(CONFIG.read_text());PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700);REPORTS.mkdir(parents=True,exist_ok=True)
 active=subprocess.check_output(['systemctl','list-units','--state=running','--no-legend','--plain','watoom-blender-capture-*'],text=True)
 if active.strip():return True
 for name in cfg['projects']:
  p=pathlib.Path(name);folder=p/'.opencode/asset-capture-requests'
  if not folder.is_dir() or folder.resolve()!=folder:continue
  for path in sorted(folder.glob('*.json'))[:512]:
   if not re.fullmatch('[a-f0-9]{64}',path.stem) or path.is_symlink() or path.stat().st_size>16384:continue
   validated=False
   try:
    v=json.loads(path.read_text())
    if v.get('project')!=name or v.get('request_id')!=path.stem or identity(v)!=path.stem or v.get('agent') not in ('watoom-workflow','watoom-builder'):continue
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}',v.get('job','')):continue
    validated=True
    prior=PRIVATE/(v['request_id']+'.json')
    if prior.exists():
     status=json.loads(prior.read_text())['status']
     if status=='RUNNING' and json.loads(prior.read_text()).get('worker')!='workstation':publish(v,'RECONCILIATION_REQUIRED',reason='Dispatcher restarted; inspect existing receipt, never replay');continue
     if status not in ('QUEUED','WAITING_FOR_HEADROOM') and not (status=='RUNNING' and json.loads(prior.read_text()).get('worker')=='workstation'):continue
    admitted_workstation=prior.exists() and json.loads(prior.read_text()).get('worker')=='workstation'
    info=m.request('/api/session/'+v['session_id']).get('data',{})
    if info.get('location',{}).get('directory')!=name or info.get('agent')!=v['agent'] or (info.get('idleOutcome')=='interrupted' and not admitted_workstation):continue
    if not admitted_workstation and cancelled(v['session_id'],active_sessions=m.request('/api/session/active').get('data',{})):publish(v,'CANCELLED',reason='Request session or parent interrupted; no launch');continue
    msg=m.request('/api/session/'+v['session_id']+'/message/'+v['message_id']).get('data',{})
    if not native_proof(msg,v):continue
    mf=contained(p/'.opencode/capture-jobs'/v['job']/'request.json',[name])
    if mf.stat().st_size>65536 or hashlib.sha256(mf.read_bytes()).hexdigest()!=v['manifest_sha256']:publish(v,'STALE_REQUEST',reason='Manifest changed; fresh job required');return True
    prior_doc=json.loads(prior.read_text()) if prior.exists() else {}
    now=time.time();since,rig_eligible=bazzite_wait(prior_doc,now)
    # Owner policy (2026-11-07): Bazzite first; the rig only after Bazzite has been unavailable for 10 minutes; never this server.
    def to_rig():
     sys.path.insert(0,'/data/ai/helper-scripts/workstation-render-stage/source')
     from native_bridge import dispatch as dispatch_workstation
     return dispatch_workstation(m,v,json.loads(mf.read_text()),publish,info)
    if prior_doc.get('worker')=='workstation':return to_rig()
    out=REPORTS/v['request_id']
    if out.exists():publish(v,'RECONCILIATION_REQUIRED',reason='Prior evidence exists; inspect, no replay');return True
    publish(v,'RUNNING',memory_limit=4294967296,worker='bazzite')
    cmd=[sys.executable,str(pathlib.Path(__file__).with_name('asset_capture_bazzite.py')),'--project',name,'--job',v['job'],'--evidence',str(out),'--i-approve','--expected-manifest-sha256',v['manifest_sha256']]
    with (REPORTS/(v['request_id']+'.log')).open('w') as log:r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=1150)
    if r.returncode==75 and not out.exists():
     # Bazzite did not start the job (nothing ran there)
     if cfg.get('workstation_enabled') and rig_eligible:return to_rig()
     publish(v,'QUEUED',reason=wait_reason(since,rig_eligible,time.time()),waiting_since=since,rig_eligible=rig_eligible);return True
    receipt=json.loads((out/'result.json').read_text()) if (out/'result.json').is_file() else {'status':'FAIL'}
    summary={k:receipt[k] for k in ('status','source_unchanged','cgroup_limit_verified','cgroup_memory_max','memory_limit','images','output','engine','prepared_source','pose_status','requires_visual_review','error','rig_adapter_id','rig_adapter_compatible','rig_fingerprint') if k in receipt}
    completed=publish(v,'COMPLETED' if r.returncode==0 and receipt.get('cgroup_limit_verified') and receipt.get('manifest_sha256')==v['manifest_sha256'] else 'FAILED',worker_result=summary,receipt=str(out/'result.json'))
    coordinator=v['session_id'];current=info
    for _ in range(12):
     if not current.get('parentID'):break
     coordinator=current['parentID'];current=m.request('/api/session/'+coordinator).get('data',{})
     if current.get('location',{}).get('directory')!=name:raise ValueError('Parent project mismatch')
    if not cancelled(coordinator,active_sessions=m.request('/api/session/active').get('data',{})):
     m.request('/api/session/'+coordinator+'/prompt',{'text':'Your existing external Blender capture '+v['job']+' finished with trusted bridge status '+completed['status']+'. Read '+str(folder/(v['request_id']+'.status.json'))+' and its root-owned receipt. Do not submit a duplicate. Render output still requires actual pixel review before visual acceptance; retain original source. This notification belongs only to the existing request '+v['request_id']+'.','resume':True})
    return True
   except Exception as e:
    if validated:publish(v,'RECONCILIATION_REQUIRED',reason=str(e)[:400])
    return True
 return False
