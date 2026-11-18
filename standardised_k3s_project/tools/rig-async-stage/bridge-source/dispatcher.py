"""Opt-in staged dispatcher: admit all RIG work, deliver receipts without blocking inference."""
import pathlib,sys,os,json,hashlib,zipfile,shutil,stat,time,fcntl,subprocess
BASE=pathlib.Path(__file__).parent;sys.path.insert(0,str(BASE.parent/'worker-source'));sys.path.append('/data/github/watoom-standardised-homelab/standardised_k3s_project/tools/watoom-code')
from maintenance_guard import Maintenance
from game_worker_bridge import request_fingerprint
import capture_spec
from native_bridge import row,transfer,directory,STATE,PROGRAM,PROJECT,USER
from completion_outbox import enqueue,drain,atomic
CFG=pathlib.Path('/etc/watoom-rig-async-stage.json');PRIVATE=pathlib.Path('/data/ai/private/rig-async-stage');FOLDER='.opencode/rig-worker-requests'
def identity(v):return hashlib.sha256(json.dumps([v[k] for k in ('project','operation','source_fingerprint','session_id','message_id','call_id')]+['rig-stage'],separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def proof(message,v):
 for t in message.get('content',[]):
  s=t.get('state',{});md=s.get('metadata') or {}
  if t.get('type')=='tool' and t.get('name')=='watoom_rig_game_job' and t.get('id')==v['call_id'] and s.get('status')=='completed' and s.get('input')=={'action':'request','operation':v['operation'],'job':v['job']} and all(md.get(k)==v[k] for k in ('request_id','project','operation','source_fingerprint','job')):return True
 return False
def publish(v,status,**extra):
 d={k:v[k] for k in ('request_id','project','operation','job','source_fingerprint')};d.update(status=status,worker='rig-stage',**extra);atomic(PRIVATE/(v['request_id']+'.json'),d)
 root=directory(pathlib.Path(v['project']),['.opencode','rig-worker-requests'])
 try:
  name=v['request_id']+'.status.json';tmp='.'+name+'.'+str(time.time_ns());fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644,dir_fd=root)
  with os.fdopen(fd,'w') as f:json.dump(d,f,indent=2);f.flush();os.fsync(f.fileno())
  os.replace(tmp,name,src_dir_fd=root,dst_dir_fd=root)
 finally:os.close(root)
 return d

def freeze(v):
 project=pathlib.Path(v['project']);folder=project/'.opencode/rig-job-snapshots';folder.mkdir(exist_ok=True)
 if folder.is_symlink() or folder.resolve()!=folder:raise ValueError('Indirect snapshot folder')
 dest=folder/(v['request_id']+'.zip');marker=PRIVATE/(v['request_id']+'.snapshot.json')
 if marker.exists():
  meta=json.loads(marker.read_text())
  with dest.open('rb') as f:
   if hashlib.file_digest(f,'sha256').hexdigest()!=meta['source_sha256']:raise ValueError('Retained snapshot changed; reconcile')
  return meta
 if dest.exists():raise ValueError('Unbound snapshot exists; operator reconciliation required')
 # capture-scene's source_fingerprint is a combined project+manifest hash (capture_spec.revision), not the
 # plain project fingerprint; request_fingerprint() picks the right one per operation, same as the main bridge.
 if request_fingerprint(project,v)!=v['source_fingerprint']:raise ValueError('STALE_REQUEST: source changed before snapshot; no external job launched')
 files=[]
 for root,dirs,names in os.walk(project,followlinks=False):
  dirs[:]=[d for d in dirs if d not in {'.godot','.opencode','.git','magpie-final'}]
  for name in names:
   if not name.endswith('.import'):files.append(pathlib.Path(root)/name)
 for name in ('.opencode/validation/p6-env-capture/p6_env_capture.gd','.opencode/validation/p6-env-capture/p6_env_capture.tscn','.opencode/validation/p7-poo-capture/p7_poo_capture.gd','.opencode/validation/p7-poo-capture/p7_poo_capture.tscn'):
  f=project/name
  if f.exists():files.append(f)
 if len(files)>20000:raise ValueError('Source file budget')
 manifest={};total=0;seen=set();temp=dest.with_suffix('.zip.partial')
 try:
  with zipfile.ZipFile(temp,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as z:
   for f in sorted(files):
    name=f.relative_to(project).as_posix()
    if f.is_symlink() or f.resolve()!=f or name.casefold() in seen or name=='.rig-input-manifest.json':raise ValueError('Indirect/case-colliding snapshot input')
    seen.add(name.casefold());fd=os.open(f,os.O_RDONLY|os.O_NOFOLLOW);before=os.fstat(fd);total+=before.st_size
    if not stat.S_ISREG(before.st_mode) or total>2*1024**3:os.close(fd);raise ValueError('Snapshot source budget 2GiB')
    h=hashlib.sha256();zi=zipfile.ZipInfo(name);zi.compress_type=zipfile.ZIP_DEFLATED
    with os.fdopen(fd,'rb') as src,z.open(zi,'w') as out:
     while b:=src.read(1024*1024):h.update(b);out.write(b)
     after=os.fstat(src.fileno())
     if after.st_size!=before.st_size or after.st_mtime_ns!=before.st_mtime_ns:raise ValueError('Source changed during snapshot')
    manifest[name]=h.hexdigest()
   if request_fingerprint(project,v)!=v['source_fingerprint']:raise ValueError('STALE_REQUEST: source changed while snapshotting')
   z.writestr('.rig-input-manifest.json',json.dumps({'source_fingerprint':v['source_fingerprint'],'files':manifest},sort_keys=True))
  if temp.stat().st_size>2*1024**3:raise ValueError('Snapshot archive budget')
  with temp.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
  os.replace(temp,dest);os.chmod(dest,0o644);meta={'source':str(dest),'source_sha256':sha};atomic(marker,meta);return meta
 except BaseException:
  temp.unlink(missing_ok=True);raise

def notify(m,v,info,status):
 from asset_capture_bridge import cancelled
 coordinator=v['session_id'];current=info
 for _ in range(12):
  if not current.get('parentID'):break
  coordinator=current['parentID'];current=m.request('/api/session/'+coordinator).get('data',{})
  if current.get('location',{}).get('directory')!=v['project']:raise ValueError('Parent project mismatch')
 text='Existing queued RIG Godot '+v['operation']+' job '+v['job']+' finished with status '+status['status']+'. Read '+str(pathlib.Path(v['project'])/FOLDER/(v['request_id']+'.status.json'))+' and the referenced root-owned receipt. Do not submit a duplicate. Match the frozen source revision before acceptance; stale results are evidence for their original snapshot only. Review actual capture pixels separately. Continue independent project work and preserve the source.'
 enqueue(v,coordinator,text,kind='godot',application={'namespace':m.ns,'name':m.name})
def process(m,v):
 info=m.request('/api/session/'+v['session_id']).get('data',{})
 if info.get('location',{}).get('directory')!=v['project'] or info.get('agent')!=v['agent']:raise ValueError('Native session identity mismatch')
 old=PRIVATE/(v['request_id']+'.json');status=json.loads(old.read_text()) if old.exists() else {}
 if status.get('status') in ('COMPLETED','FAILED','STALE_RESULT','STALE_REQUEST','RECONCILIATION_REQUIRED','CANCELLED'):
  notify(m,v,info,status);return
 if not proof(m.request('/api/session/'+v['session_id']+'/message/'+v['message_id']).get('data',{}),v):return
 job=status.get('external_job')
 if not job:
  from asset_capture_bridge import cancelled
  if cancelled(v['session_id'],database=getattr(m,'database','/data/ai/watoom-code/application.sqlite'),active_sessions=m.request('/api/session/active').get('data',{})):publish(v,'CANCELLED',reason='Native session interrupted before admission');return
  inputs=freeze(v);spec={'kind':'godot','mode':'game','project':v['project'],'operation':v['operation'],'source_fingerprint':v['source_fingerprint'],**inputs}
  if v['operation']=='capture-scene':
   # capture-scene has no fixed built-in scene (unlike capture/capture-p7); the declarative job manifest,
   # already validated by capture_spec.load() when the coordinator admitted this request, carries scene/
   # output_directory/images/deadline_sec through to the Windows runner.
   job_spec=capture_spec.load(pathlib.Path(v['project']),v['job'])
   spec.update(job=v['job'],scene=job_spec['scene'],output_directory=job_spec['directory'],images=job_spec['names'],deadline_sec=job_spec['deadline_sec'])
  p=subprocess.run(['runuser','-u',USER,'--','python3',str(PROGRAM/'broker.py'),'--root',str(STATE),'--project',str(PROJECT),'--admit-game-native'],input=json.dumps({'native':v,'manifest':spec}),capture_output=True,text=True,timeout=180)
  if p.returncode:raise ValueError('Staged game admission: '+p.stderr[-300:])
  job=json.loads(p.stdout)['job'];status=publish(v,'QUEUED',external_job=job,inputs_frozen=True)
 q=row(job)
 if not q:raise ValueError('Admitted external identity missing')
 if q['state'] in ('QUEUED','CLAIMED','PAUSED'):
  publish(v,{'QUEUED':'QUEUED','CLAIMED':'RUNNING','PAUSED':'PAUSED'}[q['state']],external_job=job,inputs_frozen=True);return
 out=pathlib.Path(v['project'])/'.opencode/rig-job-results'/v['job'];dest=directory(pathlib.Path(v['project']),['.opencode','rig-job-results',v['job']]);source=directory(pathlib.Path('/data/ai/helper-scripts/workstation-transfer'),['uploads',job])
 try:
  receipt=json.loads(q['receipt']) if q['receipt'] else {};files={}
  for name,sha in receipt.get('files',{}).items():files[name]=transfer(source,dest,name,sha)
  same=request_fingerprint(pathlib.Path(v['project']),v)==v['source_fingerprint'];terminal='COMPLETED' if q['state']=='COMPLETED_VISUAL_REVIEW_PENDING' and same else 'STALE_RESULT' if q['state']=='COMPLETED_VISUAL_REVIEW_PENDING' else q['state'] if q['state'] in ('FAILED','CANCELLED','RECONCILIATION_REQUIRED') else 'RECONCILIATION_REQUIRED'
  result={'request_id':v['request_id'],'job':v['job'],'operation':v['operation'],'source_fingerprint':v['source_fingerprint'],'source_matches':same,'external_job':job,'worker_receipt':receipt,'files':files,'visual_acceptance':False};name='receipt.json'
  try:fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644,dir_fd=dest)
  except FileExistsError:
   fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=dest)
   with os.fdopen(fd) as f:prior=json.load(f)
   if any(prior.get(k)!=result[k] for k in ('request_id','external_job','source_fingerprint','files')):raise ValueError('Existing receipt identity differs; no overwrite')
  else:
   with os.fdopen(fd,'w') as f:json.dump(result,f,indent=2);f.flush();os.fsync(f.fileno())
 finally:os.close(source);os.close(dest)
 status=publish(v,terminal,external_job=job,inputs_frozen=True,source_matches=same,receipt=str(out/'receipt.json'),worker_result=receipt.get('evidence',{}));notify(m,v,info,status)
def repair_capture_notifications(m,cfg):
 from native_bridge import completion_message
 from asset_capture_contract import native_proof
 for project in set(json.loads(pathlib.Path('/etc/watoom-asset-capture.json').read_text())['projects'])|set(cfg['projects']):
  folder=pathlib.Path(project)/'.opencode/asset-capture-requests'
  if not folder.is_dir() or folder.resolve()!=folder:continue
  for path in sorted(folder.glob('*.json'))[:512]:
   if len(path.stem)!=64 or path.is_symlink():continue
   try:
    v=json.loads(path.read_text())
    if project not in cfg['projects'] and v.get('created_at',0)<cfg['activation_ms']:continue
    status=folder/(v['request_id']+'.status.json');st=status.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid!=0 or st.st_mode&0o022 or st.st_size>262144:continue
    d=json.loads(status.read_text())
    if d.get('worker')!='workstation' or d.get('status') not in ('COMPLETED','FAILED','RECONCILIATION_REQUIRED'):continue
    q=row(d['external_job'])
    if not q or json.loads(q['native'])!=v:continue
    info=m.request('/api/session/'+v['session_id']).get('data',{})
    if info.get('location',{}).get('directory')!=project:continue
    if not native_proof(m.request('/api/session/'+v['session_id']+'/message/'+v['message_id']).get('data',{}),v):continue
    coordinator=v['session_id'];current=info
    for _ in range(12):
     if not current.get('parentID'):break
     coordinator=current['parentID'];current=m.request('/api/session/'+coordinator).get('data',{})
     if current.get('location',{}).get('directory')!=project:raise ValueError('Parent project mismatch')
    enqueue(v,coordinator,completion_message(v,d),kind='blender',application={'namespace':m.ns,'name':m.name})
   except Exception:continue

def main():
 os.umask(0o077);cfg=json.loads(CFG.read_text())
 if not cfg.get('enabled'):return
 PRIVATE.mkdir(exist_ok=True,parents=True,mode=0o700);lock=open('/data/ai/private/game-worker/worker.lock','a')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:return
 app=cfg['application'];m=Maintenance(app['namespace'],app['name'],PRIVATE,True,True);m.database=app['database'];m.rig_projects=cfg['projects']
 if m.request('/api/session/deployment-guard')['data']['held']:return
 for name in cfg['projects']:
  project=pathlib.Path(name)
  if project.is_symlink() or project.resolve()!=project or project.parent!=pathlib.Path('/data/ai/projects/games'):continue
  folder=project/FOLDER
  if not folder.is_dir() or folder.is_symlink() or folder.resolve()!=folder:continue
  for path in sorted(folder.glob('*.json'))[:512]:
   if len(path.stem)!=64 or path.is_symlink() or path.stat().st_size>16384:continue
   v=json.loads(path.read_text())
   if v.get('request_id')!=path.stem or identity(v)!=path.stem or v.get('worker_target')!='rig-stage' or v.get('project')!=name or v.get('operation') not in ('import','regression','capture','capture-p7','capture-scene') or v.get('agent') not in ('watoom-workflow','watoom-builder'):continue
   try:
    info=m.request('/api/session/'+v['session_id']).get('data',{})
    message=m.request('/api/session/'+v['session_id']+'/message/'+v['message_id']).get('data',{})
   except Exception:continue
   if info.get('location',{}).get('directory')!=name or info.get('agent')!=v['agent'] or not proof(message,v):continue
   try:process(m,v)
   except Exception as e:
    s=publish(v,'STALE_REQUEST' if str(e).startswith('STALE_REQUEST:') else 'RECONCILIATION_REQUIRED',reason=str(e)[:500]);info=m.request('/api/session/'+v['session_id']).get('data',{});notify(m,v,info,s)
 # The candidate asset scan admits every RIG capture without waiting for one to finish.
 import importlib.util
 spec=importlib.util.spec_from_file_location('rig_asset_scan',BASE/'asset_capture_bridge.py');scan=importlib.util.module_from_spec(spec);spec.loader.exec_module(scan);scan.dispatch(m)
 repair_capture_notifications(m,cfg);drain(m)
 original=Maintenance('watoom-code','watoom-code',PRIVATE,True,True);scan.dispatch(original);repair_capture_notifications(original,cfg);drain(original)
if __name__=='__main__':main()
