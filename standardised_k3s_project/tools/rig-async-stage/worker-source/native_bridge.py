"""Root-side native capture adapter. Admission proof stays in the original bridge."""
import hashlib,json,os,pathlib,shutil,sqlite3,subprocess,sys

STATE=pathlib.Path('/data/ai/helper-scripts/state/workstation-render-stage')
PROGRAM=pathlib.Path('/data/ai/helper-scripts/workstation-render-stage/source')
PROJECT=pathlib.Path('/data/ai/projects/images/workstation-render-stage')
USER='watoom-render-stage'

def enqueue(request,manifest):
    process=subprocess.run(['runuser','-u',USER,'--','python3',str(PROGRAM/'broker.py'),'--root',str(STATE),'--project',str(PROJECT),'--admit-native'],input=json.dumps({'manifest':manifest,'native':request}),capture_output=True,text=True,timeout=180)
    if process.returncode:raise ValueError('Workstation admission failed: '+process.stdout[-400:]+process.stderr[-200:])
    return json.loads(process.stdout)['job']

def row(job):
    with sqlite3.connect('file:'+str(STATE/'queue.sqlite')+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row;value=db.execute('select id,state,error,receipt,native,storage from jobs where id=?',(job,)).fetchone()
        return dict(value) if value else None

def directory(root,parts):
    parent=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in parts:
            try:os.mkdir(part,0o755,dir_fd=parent)
            except FileExistsError:pass
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent);os.close(parent);parent=child
        return parent
    except BaseException:os.close(parent);raise

def transfer(source,destination,name,expected=None):
    import re,stat
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',name) or pathlib.Path(name).suffix not in ('.json','.log','.blend','.png','.mp4'):raise ValueError('Unexpected artifact')
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=source)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size>2*1024**3:raise ValueError('Artifact budget')
        with os.fdopen(fd,'rb',closefd=False) as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest();stream.seek(0)
        if expected and sha!=expected:raise ValueError('Worker artifact changed')
        try:target=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644,dir_fd=destination)
        except FileExistsError:
            old=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=destination)
            with os.fdopen(old,'rb') as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest()!=sha:raise ValueError('Existing artifact differs; reconcile')
        else:
            with os.fdopen(target,'wb') as stream:
                copied=hashlib.sha256()
                while data:=os.read(fd,1024*1024):stream.write(data);copied.update(data)
                stream.flush();os.fsync(stream.fileno())
                if copied.hexdigest()!=sha:raise ValueError('Artifact changed while copying; reconcile retained output')
        return {'sha256':sha,'bytes':info.st_size}
    finally:os.close(fd)

def complete(request,job,report,output):
    value=row(job)
    if not value or json.loads(value['native'])!=request:raise ValueError('Native admission binding mismatch')
    if value['state'] not in ('COMPLETED_VISUAL_REVIEW_PENDING','FAILED','RECONCILIATION_REQUIRED'):return None
    report.mkdir(parents=True,exist_ok=True)
    destination=directory(request['project'],['.opencode','captures',request['job']]);source=directory(pathlib.Path('/data/ai/helper-scripts/workstation-transfer') if value['storage']=='sftp-v1' else STATE,['uploads' if value['storage']=='sftp-v1' else 'outputs',job])
    try:
        if value['state']!='COMPLETED_VISUAL_REVIEW_PENDING':
            result={'status':'FAIL','worker':'workstation','error':value['error'],'manifest_sha256':request['manifest_sha256'],'output':str(output),'requires_visual_review':True}
            files=[]
            for name in os.listdir(source):
                if pathlib.Path(name).suffix not in ('.json','.log','.blend','.png','.mp4'):continue
                metadata=transfer(source,destination,name);files.append(dict(path=str(output/name),**metadata))
            result['outputs']=files
        else:
            receipt=json.loads(value['receipt']);evidence=receipt['evidence']
            if evidence.get('platform')!='Windows' or evidence.get('memory_limit_verified') is not True:raise ValueError('Windows boundary evidence missing')
            expected=hashlib.sha256((PROGRAM/'stage_renderer.py').read_bytes()).hexdigest()
            if evidence.get('renderer_sha256')!=expected:raise ValueError('Unpinned workstation renderer')
            expected=hashlib.sha256((PROGRAM/'renderer-provenance.json').read_bytes()).hexdigest()
            if evidence.get('runtime_manifest_sha256')!=expected:raise ValueError('Unpinned workstation helper bundle')
            manifest=json.loads((pathlib.Path(request['project'])/'.opencode/capture-jobs'/request['job']/'request.json').read_text())
            with open(manifest['source'],'rb') as stream:source_hash=hashlib.file_digest(stream,'sha256').hexdigest()
            if source_hash!=manifest['source_sha256'] or receipt['source_sha256']!=source_hash:raise ValueError('Original source changed')
            files=[]
            for name,sha in receipt['files'].items():
                metadata=transfer(source,destination,name,sha);files.append(dict(path=str(output/name),**metadata))
            result=dict(evidence,worker='workstation',source=manifest['source'],source_sha256=source_hash,source_unchanged=True,manifest_sha256=request['manifest_sha256'],output=str(output),requires_visual_review=evidence.get('status')!='PASS')
            if evidence.get('prepared_source'):result['prepared_source']=str(output/'posed.blend')
            result['outputs']=files
        path=report/'result.json';path.write_text(json.dumps(result,indent=2));path.chmod(0o644)
        return result
    finally:os.close(source);os.close(destination)

def completion_message(request,completed):
    return 'Your existing external Blender capture '+request['job']+' finished on the Windows workstation with trusted bridge status '+completed['status']+'. Read '+str(pathlib.Path(request['project'])/'.opencode/asset-capture-requests'/(request['request_id']+'.status.json'))+' and its root-owned receipt. Do not submit a duplicate. Render output requires actual pixel review; retain original source. This notification belongs only to existing request '+request['request_id']+'.'

def dispatch(m,request,manifest,publish,info):
    from asset_capture_bridge import PRIVATE,REPORTS,cancelled
    prior=PRIVATE/(request['request_id']+'.json');previous=json.loads(prior.read_text()) if prior.exists() else {}
    job=previous.get('external_job')
    if not job:
        job=enqueue(request,manifest)
        publish(request,'QUEUED',worker='workstation',external_job=job,reason='Windows worker admitted the same native request; do not resubmit')
    value=row(job)
    if not value:raise ValueError('Workstation queue identity missing')
    if cancelled(request['session_id'],database=getattr(m,'database','/data/ai/watoom-code/application.sqlite'),active_sessions=m.request('/api/session/active').get('data',{})) and value['state']=='QUEUED':
        process=subprocess.run(['runuser','-u',USER,'--','python3',str(PROGRAM/'broker.py'),'--root',str(STATE),'--project',str(PROJECT),'--cancel-native'],input=json.dumps({'job':job,'native':request}),capture_output=True,text=True,timeout=30)
        if process.returncode:raise ValueError('Native cancellation requires reconciliation')
        value=row(job)
    if value['state']=='CANCELLED':
        publish(request,'CANCELLED',worker='workstation',external_job=job,reason='Session interrupted before worker claim; no launch')
        return True
    if value['state'] in ('QUEUED','CLAIMED','PAUSED'):
        publish(request,'PAUSED' if value['state']=='PAUSED' else 'QUEUED' if value['state']=='QUEUED' else 'RUNNING',worker='workstation',external_job=job)
        return True
    out=pathlib.Path(request['project'])/'.opencode/captures'/request['job']
    # The request owns its fresh output directory; an unrelated preexisting output is rejected.
    marker=REPORTS/(request['request_id']+'.workstation.json')
    if out.exists() and not marker.exists():raise ValueError('Existing capture output; reconcile instead of replay')
    marker.write_text(json.dumps({'external_job':job,'output':str(out)}))
    report=REPORTS/request['request_id']
    result=complete(request,job,report,out)
    if result is None:return True
    summary={key:result[key] for key in ('status','worker','platform','source_unchanged','memory_limit_verified','memory_limit_bytes','images','output','engine','prepared_source','pose_status','requires_visual_review','error','rig_adapter_id','rig_adapter_compatible','rig_fingerprint') if key in result}
    completed=publish(request,'COMPLETED' if result['status'] in ('PASS','CAPTURED_VISUAL_REVIEW_PENDING','PREPARED_REVIEW_PENDING') else 'FAILED',worker='workstation',external_job=job,worker_result=summary,receipt=str(report/'result.json'))
    coordinator=request['session_id'];current=info
    for _ in range(12):
        if not current.get('parentID'):break
        coordinator=current['parentID'];current=m.request('/api/session/'+coordinator).get('data',{})
        if current.get('location',{}).get('directory')!=request['project']:raise ValueError('Parent project mismatch')
    if not cancelled(coordinator,database=getattr(m,'database','/data/ai/watoom-code/application.sqlite'),active_sessions=m.request('/api/session/active').get('data',{})):
        from completion_outbox import enqueue as enqueue_completion
        enqueue_completion(request,coordinator,completion_message(request,completed),kind='blender',application={'namespace':m.ns,'name':m.name})
    return True
