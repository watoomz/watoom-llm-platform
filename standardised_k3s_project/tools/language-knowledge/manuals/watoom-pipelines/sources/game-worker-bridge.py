#!/usr/bin/env python3
"""Validate native worker requests and dispatch fixed operator-owned helpers.

Terminal worker results retain their existing status and fields, with bounded failure_stage/failure_code metadata.
Raw subprocess argv representations are converted to a short human sentence; no receipt is replayed during reconciliation.
"""
import pathlib,json,hashlib,os,fcntl,subprocess,time,sys,re,stat,secrets
import contextlib
from contextlib import contextmanager
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from maintenance_guard import Maintenance
from game_validation import atomic
from lmb_provenance import ALGORITHM, receipt_report
import datetime
CONFIG=pathlib.Path('/etc/watoom-game-worker.json')
RIG_CONFIG=pathlib.Path('/etc/watoom-rig-async-stage.json')
PRIVATE=pathlib.Path('/data/ai/private/game-worker')
REPORTS=pathlib.Path('/data/ai/helper-scripts/reports/game-worker')
OPERATIONS={'regression':'game_validation.py','import':'game_import.py','capture':'game_capture.py','capture-scene':'game_capture.py','capture-p7':'game_capture.py','poo-vfx-inspect':'../fab/inspect-poo-vfx.py','poo-vfx-export':'../fab/export-poo-vfx.py','lmb-qualify':'lmb_qualify.py','unreal-export':'game_unreal_export.py','blender':'game_blender.py','terrain-export':'game_terrain_export.py'}
def canonical(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))
def fingerprint(project):
 rows=[]
 for root,dirs,files in os.walk(project,followlinks=False):
  for name in list(dirs)+files:
   p=pathlib.Path(root)/name
   if p.is_symlink():raise ValueError('Source symlink refused')
  dirs[:]=[x for x in dirs if x not in {'.godot','.opencode','.git','magpie-final'}]
  for name in files:
   if name.endswith('.import'):continue
   p=pathlib.Path(root)/name;s=p.stat()
   if not stat.S_ISREG(s.st_mode):continue
   rows.append([str(p.relative_to(project)),str(s.st_size),str(s.st_mtime_ns)])
   if len(rows)>20000:raise ValueError('Source limit')
 for name in ['.opencode/validation/p6-env-capture/p6_env_capture.gd','.opencode/validation/p6-env-capture/p6_env_capture.tscn','.opencode/validation/p7-poo-capture/p7_poo_capture.gd','.opencode/validation/p7-poo-capture/p7_poo_capture.tscn']:
  p=project/name
  if p.is_symlink():raise ValueError('Indirect capture source')
  if p.parent.exists() and p.parent.resolve()!=p.parent:raise ValueError('Indirect capture source')
  if p.exists():
   if p.resolve()!=p or p.is_symlink() or not p.is_file():raise ValueError('Indirect capture source')
   s=p.stat();rows.append([name,str(s.st_size),str(s.st_mtime_ns)])
 rows.append(['.watoom-worker-contract','cache-mount-v1','0'])
 rows.sort(key=lambda x:x[0].encode());return hashlib.sha256(canonical(rows).encode()).hexdigest()
def request_fingerprint(project,v):
 if v['operation']=='capture-scene':
  from capture_spec import revision
  return revision(project,v['job'],fingerprint(project))
 if v['operation']=='unreal-export':
  import unreal_export_spec
  return unreal_export_spec.revision(project,v['job'])
 if v['operation']=='blender':
  import blender_job_spec
  return blender_job_spec.revision(project,v['job'])
 if v['operation']=='terrain-export':
  import terrain_spec
  return terrain_spec.revision(project,v['job'])
 return fingerprint(project)
def checked_fingerprint(project,v):
 """The request's current source fingerprint, or (None, reason) when its declared inputs are invalid.
 A bad manifest fails only its own request with a reason the agent can act on; it must not stop the dispatcher."""
 try:return request_fingerprint(project,v),None
 except (ValueError,OSError,KeyError,TypeError) as e:
  where={'capture-scene':' in .opencode/capture-jobs/'+v['job']+'/request.json','unreal-export':' in .opencode/unreal-export-jobs/'+v['job']+'/request.json','blender':' in .opencode/blender-jobs/'+v['job']+'/request.json','terrain-export':' in .opencode/terrain-jobs/'+v['job']+'/request.json'}.get(v['operation'],'')
  return None,'Invalid request'+where+': '+str(e)+'. No worker launched; fix it and submit a new job name.'
def request_identity(v):
 return hashlib.sha256(canonical([v['project'],v['operation'],v['source_fingerprint'],v['session_id'],v['message_id'],v['call_id']]).encode()).hexdigest()

def failure_metadata(receipt=None, error=None, returncode=None, timed_out=False):
 """Map existing worker signals to bounded machine-readable failure fields."""
 r=receipt if isinstance(receipt,dict) else {}; text=' '.join(str(x or '') for x in (r.get('failure_reason'),r.get('error'),r.get('reason'),error)).lower()
 if error is not None:
  timed_out=timed_out or isinstance(error,subprocess.TimeoutExpired)
  returncode=returncode if returncode is not None else getattr(error,'returncode',None)
 if r.get('source_changes_by_import'): return 'reconcile','source_changed'
 if timed_out or r.get('timed_out') or 'timed out' in text or 'deadline exceeded' in text: return 'run','timeout'
 if r.get('is_oom') or r.get('oom') or 'out of memory' in text or 'memory limit' in text or returncode==137: return 'run','oom'
 if returncode==255: return 'stage','unreachable'
 if 'not_started' in text or 'not staged' in text or 'image missing' in text or returncode==75: return 'stage','not_staged'
 if 'pull_failed' in text or 'pull failed' in text: return 'pull','worker_error'
 if 'script raised' in text or 'godot errors' in text or 'read-only file system' in text or 'script reported' in text: return 'run','script_error'
 if 'source changed' in text or 'source_changes_by_import' in text: return 'reconcile','source_changed'
 if error is not None: return 'reconcile','unknown'
 if returncode not in (None,0): return 'run','worker_error'
 return None,None

def human_failure(reason, code):
 text=str(reason or '').strip()
 if text.startswith("Command '[") or text.startswith('Command "['):
  return 'Worker command failed (%s).' % code
 return (text[:450] if text else 'Worker failed (%s).' % code)
def native_proof(message,v):
 for p in message.get('content',[]):
  if p.get('type')!='tool' or p.get('name')!='watoom_game_worker' or p.get('id')!=v['call_id']:continue
  s=p.get('state',{});i=s.get('input',{});md=s.get('metadata',{}) or {}
  if s.get('status')=='completed' and i=={'action':'request','operation':v['operation'],'job':v['job']} and all(md.get(k)==v[k] for k in ['request_id','project','operation','source_fingerprint','job']):return True
 return False
def publish(v,status,**extra):
 public={k:v[k] for k in ['request_id','project','operation','source_fingerprint','job']};public.update(status=status,**extra)
 # Only root-owned, regular, non-writable-by-others status files are trusted by the native tool.
 private=PRIVATE/(v['request_id']+'.json');atomic(private,public)
 parent=os.open(v['project'],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:
  for component in ['.opencode','worker-requests']:
   child=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent);os.close(parent);parent=child
  temporary='.'+v['request_id']+'.'+secrets.token_hex(8)+'.tmp'
  fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o644,dir_fd=parent)
  with os.fdopen(fd,'w') as f:json.dump(public,f,indent=2);f.flush();os.fsync(f.fileno())
  os.replace(temporary,v['request_id']+'.status.json',src_dir_fd=parent,dst_dir_fd=parent)
 finally:os.close(parent)
 return public
def project_safe(path):
 p=pathlib.Path(path)
 return p.is_dir() and not p.is_symlink() and str(p.resolve())==str(p) and p.parent==pathlib.Path('/data/ai/projects/games')
def read_request(path,project):
 try:
  fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
  with os.fdopen(fd,'r') as f:
   st=os.fstat(f.fileno())
   if not stat.S_ISREG(st.st_mode) or st.st_size>16384:return None
   v=json.load(f)
  if not isinstance(v,dict) or v.get('project')!=str(project) or v.get('operation') not in OPERATIONS or v.get('agent') not in ['watoom-workflow','watoom-builder']:return None
  if not all(isinstance(v.get(k),str) and re.fullmatch('[A-Za-z0-9_-]{1,128}',v[k]) for k in ['session_id','message_id','call_id','job']):return None
  if not re.fullmatch('[a-f0-9]{64}',v.get('source_fingerprint','')):return None
  if v.get('request_id')!=path.stem or request_identity(v)!=path.stem:return None
  return v
 except (OSError,ValueError,TypeError,KeyError):return None

def cpu_client():
 sys.path.insert(0,'/data/ai/helper-scripts/gpu-controller')
 from client import GPUClient
 return GPUClient('/data/ai/helper-scripts/state/gpu-controller-private/worker.sock',timeout=1500)

from bazzite_wait import RIG_AFTER_SEC,bazzite_wait,wait_reason
def rig_retry_hint(project,operation,failure_code):
 """Owner policy (2026-11-09): a Bazzite run that timed out on a rig-enrolled operation, for a rig-enrolled
 project, should be retried on the rig -- the rig has a real GPU, Bazzite's capture path is software-rendered
 (llvmpipe). The rig is a separate, isolated application with its own queue and database (see
 tools/rig-async-stage/README.md); this bridge never writes into that queue directly. Instead, on exactly this
 condition, the existing per-job resume prompt gets one extra sentence telling the agent to resubmit via
 watoom_rig_game_job itself -- never silently, and never when the operation or project is not actually
 enrolled there, so the suggestion is never a dead end."""
 if failure_code!='timeout':return ''
 try:
  rig=json.loads(RIG_CONFIG.read_text())
 except (OSError, ValueError):
  return ''
 if not rig.get('enabled') or operation not in rig.get('operations',[]) or str(project) not in rig.get('projects',[]):return ''
 return (' This operation (%s) timed out on Bazzite (software-rendered, no real GPU) and this project is enrolled '
         'on the rig, which has a real GPU. Resubmit the SAME job name via watoom_rig_game_job instead of retrying '
         'Bazzite again.') % operation
def local_route_blocked(operation,remote,evidence_exists,cfg):
 """True when a request must wait (QUEUED) instead of taking the local route, which parks the production model.
 unreal-export and terrain-export route themselves (always Bazzite, never parks inference); existing evidence
 goes to reconciliation, not a launch."""
 return remote is None and operation not in ('unreal-export','terrain-export') and not evidence_exists and not cfg.get('local_fallback',False)
@contextmanager
def reserve_headroom(m, worker_gib=3):
 required=(worker_gib+2)*1024**3
 mem=int(next(x.split()[1] for x in pathlib.Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
 if mem>=required:
  yield True;return
 # Do not evict inference or interrupt any native session. The controller independently
 # checks actual backend idleness and leases under its ownership lock.
 if m.request('/api/session/active').get('data',{}):
  yield False;return
 client=cpu_client();generation=None
 try:
  generation=client.call('begin',job='game-worker')['generation']
  client.call('park-cpu',job='game-worker',generation=generation)
  mem=int(next(x.split()[1] for x in pathlib.Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
  yield mem>=required
 finally:
  if generation is not None:
   client.call('restore',job='game-worker',generation=generation)

def recover_cpu():
 # ExecStopPost: ownership recovery is allowed only after the recorded process died.
 client=cpu_client();state=client.call('status')
 if state.get('owner')=='game-worker':
  client.call('recover',job='game-worker',generation=state['generation'])


def main():
 if os.geteuid()!=0:raise PermissionError('Operator only')
 cfg=json.loads(CONFIG.read_text());PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700);REPORTS.mkdir(parents=True,exist_ok=True)
 lock=(PRIVATE/'worker.lock').open('a')
 # The rig async bridge shares this lock. Its reconcile pass holds it for a few seconds, so wait briefly
 # rather than lose the whole poll; a lock still busy after 15s (a running job) skips this poll.
 deadline=time.time()+15
 while True:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
  except BlockingIOError:
   if time.time()>deadline:print('worker lock busy; skipping this poll',flush=True);return
   time.sleep(0.5)
 m=Maintenance('watoom-code','watoom-code',REPORTS,True,True)
 # No new worker starts during a native deployment fence or another operator Godot run.
 if m.request('/api/session/deployment-guard').get('data',{}).get('held'):return
 running=subprocess.check_output(['systemctl','list-units','--state=running','--no-legend','--plain','watoom-godot-*'],text=True)
 if running.strip():return
 from asset_capture_bridge import dispatch
 if dispatch(m):return
 for name in cfg['projects']:
  if not project_safe(name):continue
  project=pathlib.Path(name);folder=project/'.opencode/worker-requests'
  if not folder.is_dir() or folder.is_symlink() or folder.resolve()!=folder:continue
  for path in sorted(folder.glob('*.json')):
   if len(path.stem)!=64 or path.is_symlink() or not path.is_file() or path.stat().st_size>16384:continue
   v=read_request(path,project)
   if v is None:continue
   ident=v['request_id']
   prior=PRIVATE/(ident+'.json');old=None
   if prior.exists():
    old=json.loads(prior.read_text())
    if old['status']=='RUNNING':
     publish(v,'RECONCILIATION_REQUIRED',reason='Dispatcher restarted after a running request; existing evidence must be reconciled, no replay',failure_stage='run',failure_code='worker_error')
     continue
    if old['status'] not in ['QUEUED','WAITING_FOR_HEADROOM']:continue
   try:info=m.request('/api/session/'+v['session_id']).get('data',{})
   except Exception:continue
   if info.get('location',{}).get('directory')!=name or info.get('agent')!=v['agent']:continue
   try:msg=m.request('/api/session/'+v['session_id']+'/message/'+v['message_id']).get('data',{})
   except Exception:continue
   if not native_proof(msg,v):continue
   coordinator=v['session_id'];current=info
   for _ in range(12):
    if not current.get('parentID'):break
    coordinator=current['parentID'];current=m.request('/api/session/'+coordinator).get('data',{})
    if current.get('location',{}).get('directory')!=name:raise ValueError('Parent project mismatch')
   current_fingerprint,invalid=checked_fingerprint(project,v)
   if invalid:
    publish(v,'FAILED',reason=invalid,failure_stage='request',failure_code='unknown');continue
   if current_fingerprint!=v['source_fingerprint']:
    result=publish(v,'STALE_REQUEST',reason='Source changed before dispatch; request a fresh revision, no worker launched',failure_stage='request',failure_code='source_changed')
   else:
    p85_capture=v['operation']=='capture' and v['job'].startswith('p85-')
    worker_gib=4 if v['operation'] in ['regression','lmb-qualify','capture-scene'] or p85_capture else 3
    if v['operation']=='blender':
     import blender_job_spec
     worker_gib=blender_job_spec.load(project,v['job'])['memory_gib']
    out=REPORTS/ident
    remote=None
    # Bazzite first for the configured operations: no homelab RAM is needed, so no headroom wait.
    # game_bazzite.py exits NOT_STARTED (75) before launching anything; only then does the local route run.
    if v['operation'] in cfg.get('bazzite_operations',[]) and not out.exists():
     publish(v,'RUNNING',coordinator_session=coordinator,evidence_id=ident,worker='bazzite')
     execution_started_at=datetime.datetime.now(datetime.timezone.utc).isoformat()
     if v['operation']=='blender':cmd=[sys.executable,str(pathlib.Path(__file__).parent/'blender_bazzite.py'),'--project',name,'--evidence',str(out),'--i-approve','--blender-job',v['job']]
     else:cmd=[sys.executable,str(pathlib.Path(__file__).parent/'game_bazzite.py'),'--operation',v['operation'],'--project',name,'--evidence',str(out),'--i-approve']
     if v['operation']=='capture-p7':cmd+=['--profile','p7']
     if v['operation']=='capture-scene':cmd+=['--capture-job',v['job']]
     elif p85_capture:cmd+=['--profile','p85']
     t_remote=time.time()
     try:
      remote=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=2700 if v['operation']=='blender' else 2400);(REPORTS/(ident+'.operator.log')).write_text(remote.stdout)
      # no evidence folder = nothing was launched there (NOT_STARTED removes its own)
      if not out.exists():remote=None
     except Exception as e:
      remote=e
     if remote is None and time.time()-t_remote>240:
      # keep this oneshot poll inside its 20-minute limit: retry on the next poll
      now=time.time();since,eligible=bazzite_wait(old,now)
      publish(v,'QUEUED',reason=wait_reason(since,eligible,now),waiting_since=since,rig_eligible=eligible);continue
    if local_route_blocked(v['operation'],remote,out.exists(),cfg):
      # Owner policy (2026-11-07): heavy work runs on Bazzite, else the rig, never on this server. The local route calls
      # reserve_headroom(), which parks the production model through the GPU controller (agents then get 503s).
      now=time.time();since,eligible=bazzite_wait(old,now)
      publish(v,'QUEUED',reason=wait_reason(since,eligible,now),waiting_since=since,rig_eligible=eligible);continue
    # unreal-export: export_pack.py picks Bazzite or the local Job and checks local RAM itself, so never park inference for it
    with (reserve_headroom(m,worker_gib) if remote is None and v['operation'] not in ('unreal-export','terrain-export') else contextlib.nullcontext(True)) as available:
     if not available:publish(v,'WAITING_FOR_HEADROOM',required=str(worker_gib)+'GiB worker plus2GiB reserve; active inference is never interrupted');continue
     if remote is None and out.exists():
      result=publish(v,'RECONCILIATION_REQUIRED',reason='Prior owned evidence exists without terminal bridge status; never replay blindly',failure_stage='reconcile',failure_code='unknown')
     else:
      if remote is None:
       publish(v,'RUNNING',coordinator_session=coordinator,evidence_id=ident)
       helper=pathlib.Path(__file__).parent/OPERATIONS[v['operation']]
       cmd=[sys.executable,str(helper),'--project',name,'--evidence',str(out),'--i-approve']
       if v['operation']=='regression':cmd+=['--memory-gib',str(worker_gib)]
       if v['operation']=='capture-p7':cmd+=['--profile','p7']
       if v['operation']=='capture-scene':cmd+=['--capture-job',v['job']]
       elif v['operation']=='unreal-export':cmd+=['--export-job',v['job']]
       elif v['operation']=='blender':cmd+=['--blender-job',v['job']]
       elif v['operation']=='terrain-export':cmd+=['--terrain-job',v['job']]
       elif p85_capture:cmd+=['--profile','p85']
      try:
       if isinstance(remote,Exception):raise remote
       if remote is not None:
        r=remote
       else:
        execution_started_at=datetime.datetime.now(datetime.timezone.utc).isoformat()
        # import: a large project (hundreds of source GLBs re-importing on first touch) needs more than 900s;
        # keep it above game_import.py's own internal budget (systemd RuntimeMaxSec=1800 + its 1830s wrapper).
        # terrain-export: deadline_sec can be up to 1800, plus its own poll budget (deadline+180) and two
        # remote directory-hash passes; generous margin, still well inside the service's own TimeoutStartSec=60min.
        r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=1150 if v['operation'] in ['capture-scene','unreal-export','blender'] else 1900 if v['operation']=='import' else 3300 if v['operation']=='terrain-export' else 900);(REPORTS/(ident+'.operator.log')).write_text(r.stdout)
       receipt=json.loads((out/'result.json').read_text()) if (out/'result.json').is_file() else {'status':'FAIL','failure_reason':'Helper did not produce result: '+(([l for l in (r.stdout or '').splitlines() if l.strip()] or ['no output'])[-1])[:300]}
       if v['operation']=='lmb-qualify':
        identity_check=receipt_report(receipt,v)
        if identity_check['errors']:raise ValueError('Native receipt identity/provenance mismatch: '+str(identity_check['errors']))
        receipt.update({k:v[k] for k in ['request_id','project','job','operation','source_fingerprint']})
        receipt.update(source_fingerprint_algorithm=ALGORITHM,executed_at=execution_started_at,receipt_path=str(out/'result.json'))
        atomic(out/'result.json',receipt)
        (out/'result.json').chmod(0o644)
       same=request_fingerprint(project,v)==v['source_fingerprint'] and receipt.get('live_source_still_matches_snapshot',True)
       terminal='COMPLETED' if same and r.returncode==0 else 'STALE_RESULT' if not same else 'FAILED'
       # Publish bounded actual result fields, no arbitrary raw logs or prompt content.
       failure_stage,failure_code=failure_metadata(receipt,returncode=r.returncode)
       if terminal!='COMPLETED' and not same and failure_code is None:failure_stage,failure_code='reconcile','source_changed'
       summary={k:receipt[k] for k in ['status','failure_reason','profile','scene','summary','runtime_error_count','errors','images','memory_limit','cgroup_memory_max','cgroup_limit_verified','source_unchanged','failed_tests','runtime_error_examples','scope','engine','class_counts','loaded','assets','godot_adaptation_confirmed','native_status','source_fingerprint_algorithm','native_input_sha256','native_input_algorithm','receipt_path','executed_at','timed_out','elapsed_sec','deadline_sec','counts','exported','export_directory','source_changes_by_import','export_status','backend','backend_fallback_reason','artifact_directory','traceback','script_result','outputs','output_directory','exit','script','hints','manifest'] if k in receipt}
       if isinstance(summary.get('failure_reason'),str) and summary['failure_reason'].startswith("Command '["):
        summary['failure_reason']=human_failure(summary['failure_reason'],failure_code or 'unknown')
       if failure_stage:summary.update(failure_stage=failure_stage,failure_code=failure_code)
       app_receipt=receipt.get('app_receipt')
       if not app_receipt:
        candidates=list((project/'.opencode/validation/operator-godot').glob('*'+str(receipt.get('unit','missing'))+'*.json'));app_receipt=str(candidates[0]) if candidates else None
       if v['operation']=='lmb-qualify' and (out/'result.json').is_file():
        app_receipt=str(out/'result.json')
       result=publish(v,terminal,worker_result=summary,receipt=app_receipt,evidence_id=ident,source_matches=same)
      except Exception as e:
       failure_stage,failure_code=failure_metadata(error=e)
       result=publish(v,'RECONCILIATION_REQUIRED',reason=human_failure(e,failure_code),failure_stage=failure_stage,failure_code=failure_code,evidence_id=ident)
   m.request('/api/session/'+coordinator+'/prompt',{'text':'Bounded external '+({'unreal-export':'Unreal','blender':'Blender'}.get(v['operation'],'Godot'))+' '+v['operation']+' request '+ident+' finished with bridge status '+result['status']+'. Read the root-owned status '+str(folder/(ident+'.status.json'))+' and referenced actual receipt; match source revision before acceptance. This is the existing request from '+v['session_id']+'; do not duplicate/replay it. A worker PASS is technical evidence only; visual criteria remain separate. If failed/stale, inspect exact evidence and repair the remaining bounded package before requesting a new revision. Continue existing project scope and preserve guards.'+rig_retry_hint(project,v['operation'],failure_code),'resume':True})
   return
if __name__=='__main__':
 if sys.argv[1:]==['--recover-cpu']:recover_cpu()
 else:main()
