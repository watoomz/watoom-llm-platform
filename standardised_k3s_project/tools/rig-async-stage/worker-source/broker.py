"""Restricted staging spool; stdin JSON over a forced-command SSH key."""
import argparse, base64, hashlib, json, os, pathlib, re, secrets, sqlite3, sys, time

def digest(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def write(path, value):
    temporary = path.with_name('.' + path.name + '.' + secrets.token_hex(6))
    with temporary.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)

def validate(value, project, roots=None):
    roots=roots or [str(project/'assets')]
    if value.get('kind')=='godot':
        from game_contract import validate_game
        return validate_game(value,roots)
    from asset_capture_contract import manifest
    manifest(value,roots)
    source=pathlib.Path(value['source'])
    if digest(source)!=value['source_sha256']:raise ValueError('Source hash mismatch')
    return source

class Broker:
    def __init__(self, root, project):
        self.root=pathlib.Path(root);self.project=pathlib.Path(project)
        self.db=sqlite3.connect(self.root/'queue.sqlite',timeout=10)
        self.db.row_factory=sqlite3.Row
        self.db.execute('pragma journal_mode=WAL')
        self.db.execute('create table if not exists jobs (id text primary key, manifest text not null, state text not null, token text, worker text, expires real, error text, receipt text)')
        self.db.execute('create table if not exists workers (id text primary key, seen real not null, status text not null)')
        columns={row[1] for row in self.db.execute('pragma table_info(jobs)')}
        for name in ('inputs','roots','native','storage'):
            if name not in columns:self.db.execute('alter table jobs add column '+name+' text')
        self.db.execute('create table if not exists submissions (name text primary key, id text not null, manifest text not null)')
        self.db.execute('create table if not exists metadata (key text primary key, value text not null)')
        if not self.db.execute("select 1 from metadata where key='legacy-bindings-v1'").fetchone():
            for path in (self.project/'incoming').glob('*/request.json'):
                try:
                    raw=json.dumps(json.loads(path.read_text()),sort_keys=True,separators=(',',':'));identity=hashlib.sha256(raw.encode()).hexdigest()
                    if self.db.execute('select 1 from jobs where id=?',(identity,)).fetchone():self.db.execute('insert or ignore into submissions values(?,?,?)',(path.parent.name,identity,raw))
                except (OSError,ValueError):pass
            self.db.execute("insert into metadata values('legacy-bindings-v1','done')")
        self.db.commit()
    def privileged(self,operation,**values):
        import socket
        channel=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);channel.settimeout(180)
        try:
            channel.connect('/run/watoom-workstation-inputs.sock');stream=channel.makefile('rwb')
            stream.write(json.dumps({'op':operation,**values}).encode()+b'\n');stream.flush();result=json.loads(stream.readline(800000))
            if not result['ok']:raise ValueError(result['error'])
            return result['inputs']
        finally:channel.close()
    def admit(self,value,roots,native=None,submission=None):
        from package_inputs import initial
        raw=json.dumps(value,sort_keys=True,separators=(',',':'))
        if submission:
            bound=self.db.execute('select id,manifest from submissions where name=?',(submission,)).fetchone()
            if bound:
                if bound['manifest']!=raw:raise ValueError('Admitted request is immutable; use a fresh job directory')
                return bound['id']
        namespace=native['request_id'] if native else submission
        identity=hashlib.sha256(json.dumps([namespace,raw],separators=(',',':')).encode()).hexdigest()
        if self.db.execute('select 1 from jobs where id=?',(identity,)).fetchone():return identity
        if self.root==pathlib.Path('/data/ai/helper-scripts/state/workstation-render-stage'):inputs=self.privileged('initial',manifest=value)
        else:
            validate(value,self.project,roots);inputs=initial(self.root,value,roots)
        with self.db:
            self.db.execute('begin immediate')
            if submission:
                current=self.db.execute('select id,manifest from submissions where name=?',(submission,)).fetchone()
                if current:
                    if current['manifest']!=raw:raise ValueError('Admitted request changed during snapshot; use a fresh directory')
                    return current['id']
            self.db.execute("insert or ignore into jobs(id,manifest,state,inputs,roots,native) values(?,?,'QUEUED',?,?,?)",(identity,raw,json.dumps(inputs),json.dumps(roots),json.dumps(native)))
            if submission:self.db.execute('insert or ignore into submissions values(?,?,?)',(submission,identity,raw))
        return identity
    def expire(self):
        self.db.execute("update jobs set state='RECONCILIATION_REQUIRED',error='Worker lease expired; do not replay' where state='CLAIMED' and expires<?",(time.time(),))
    def scan(self):
        with self.db:self.expire()
        for path in sorted((self.project/'incoming').glob('*/request.json')):
            try:
                if path.is_symlink() or path.parent.is_symlink() or path.stat().st_size>65536:raise ValueError('Indirect/oversize request')
                value=json.loads(path.read_text())
                cfgpath=pathlib.Path('/etc/watoom-asset-capture.json')
                cfg=json.loads(cfgpath.read_text()) if cfgpath.exists() else {}
                roots=[str(self.project/'assets')]+cfg.get('source_roots',[])+cfg.get('projects',[])
                identity=self.admit(value,roots,submission=path.parent.name)
                row=self.db.execute('select id,state,error,receipt from jobs where id=?',(identity,)).fetchone()
                public=dict(row);public['receipt']=json.loads(public['receipt']) if public['receipt'] else None
                write(self.project/'status'/(identity+'.json'),public)
                write(self.project/'status'/(path.parent.name+'.json'),public)
            except (ValueError,OSError,KeyError,TypeError) as error:
                write(self.project/'status'/(path.parent.name+'.json'),{'state':'REJECTED','error':str(error)[:300]})
        counts={row[0]:row[1] for row in self.db.execute('select state,count(*) from jobs group by state')}
        workers=[{'id':row['id'],'lastSeen':row['seen'],'online':time.time()-row['seen']<90,'lastOperation':row['status']} for row in self.db.execute('select * from workers')]
        write(self.project/'status/worker-status.json',{'schema':'watoom.workstation-stage.health.v1','sampledAt':time.time(),'workers':workers,'jobs':counts,'automatic_replay':False})
    def operation(self, request, worker):
        op=request.get('op')
        self.db.execute('begin immediate')
        try:
            self.expire()
            self.db.execute('insert or replace into workers values(?,?,?)',(worker,time.time(),op or 'unknown'))
            if op=='claim':
                active=self.db.execute("select id from jobs where state in ('CLAIMED','RECONCILIATION_REQUIRED')").fetchone()
                row=None if active else self.db.execute("select * from jobs where state='QUEUED' and (? is null or id=?) and (?=0 or native is not null and native!='null') and coalesce(json_extract(manifest,'$.kind'),'blender')=? order by rowid limit 1",(request.get('only_job'),request.get('only_job'),int(bool(request.get('native_only'))),request.get('job_kind','blender'))).fetchone()
                if not row:result={'job':None}
                else:
                    token=secrets.token_hex(32)
                    if self.root==pathlib.Path('/data/ai/helper-scripts/state/workstation-render-stage'):
                        try:inputs=self.privileged('initial',manifest=json.loads(row['manifest']))
                        except ValueError as error:
                            self.db.execute("update jobs set state='FAILED',error=? where id=?",('Input validation changed before claim: '+str(error)[:300],row['id']))
                            self.db.commit();return {'job':None,'rejected':row['id'],'reason':'Input changed or became invalid; no render launched'}
                        self.db.execute('update jobs set inputs=?,storage=? where id=?',(json.dumps(inputs),'sftp-v1',row['id']))
                        upload=pathlib.Path('/data/ai/helper-scripts/workstation-transfer/uploads')/row['id'];upload.mkdir(mode=0o2770,exist_ok=True);os.chmod(upload,0o2770)
                    self.db.execute("update jobs set state='CLAIMED',worker=?,token=?,expires=? where id=?",(worker,token,time.time()+90,row['id']))
                    result={'job':row['id'],'token':token,'manifest':json.loads(row['manifest']),'source_size':(self.root/'blobs'/json.loads(row['manifest'])['source_sha256']).stat().st_size,'inputs':inputs if self.root==pathlib.Path('/data/ai/helper-scripts/state/workstation-render-stage') else json.loads(row['inputs']) if row['inputs'] else []}
            elif op=='hello':result={'stage':True,'worker':worker}
            else:
                row=self.db.execute('select * from jobs where id=?',(request.get('job'),)).fetchone()
                if not row or row['state'] not in ('CLAIMED','PAUSED') or row['worker']!=worker or not secrets.compare_digest(row['token'],request.get('token','')):
                    raise ValueError('Claim unavailable; reconcile instead of replaying')
                if row['state']=='PAUSED' and op!='resume':raise ValueError('Job paused; explicit resume required')
                if op=='resume' and row['state']!='PAUSED':raise ValueError('Only paused claims can resume')
                spec=json.loads(row['manifest']);out=(pathlib.Path('/data/ai/helper-scripts/workstation-transfer/uploads')/row['id']) if row['storage']=='sftp-v1' else self.root/'outputs'/row['id'];out.mkdir(mode=0o2770,exist_ok=True)
                if row['storage']=='sftp-v1' and op in ('fetch','upload'):raise ValueError('SFTP is required for file payloads; SSH control carries metadata only')
                if op=='pause':
                    self.db.execute("update jobs set state='PAUSED',expires=null,error=? where id=?",(request.get('error','Operator pause')[:400],row['id']));result={'state':'PAUSED'}
                elif op=='resume':
                    # A user-authorized restart gets a clean upload target; retain
                    # any partial attempt instead of resuming stale output bytes.
                    if out.exists():out.rename(out.with_name(out.name+'.paused-'+str(time.time_ns())))
                    out.mkdir(mode=0o2770);os.chmod(out,0o2770)
                    self.db.execute("update jobs set state='QUEUED',token=null,expires=null,error=null where id=?",(row['id'],));result={'state':'QUEUED','explicit_resume':True}
                elif op=='heartbeat':
                    self.db.execute('update jobs set expires=? where id=?',(time.time()+90,row['id']));result={'alive':True}
                elif op=='dependencies':
                    from package_inputs import snapshot,unique,expand
                    requests=request['paths']
                    if not isinstance(requests,list) or len(requests)>512:raise ValueError('Dependency list budget')
                    inputs=json.loads(row['inputs']) if row['inputs'] else []
                    roots=json.loads(row['roots']) if row['roots'] else [str(self.project/'assets')]
                    if self.root==pathlib.Path('/data/ai/helper-scripts/state/workstation-render-stage'):
                        inputs+=self.privileged('dependencies',job=row['id'],paths=requests)
                    else:
                        for item in requests:
                            if not isinstance(item,dict) or set(item)!={'path','kind'} or item['kind'] not in ('file','tiled','sequence','library'):raise ValueError('Invalid dependency metadata')
                            paths=expand(item['path'],item['kind'])
                            if not paths:raise ValueError('Missing dependency')
                            for path in paths:inputs.append(snapshot(self.root,path,roots))
                    inputs=unique(inputs);self.db.execute('update jobs set inputs=? where id=?',(json.dumps(inputs),row['id']))
                    result={'inputs':inputs}
                elif op=='fetch':
                    offset=request['offset']
                    if type(offset)!=int or offset<0:raise ValueError('Invalid offset')
                    fileid=request.get('file',spec['source_sha256'])
                    allowed={x['id'] for x in json.loads(row['inputs'])} if row['inputs'] else {spec['source_sha256']}
                    if fileid not in allowed:raise ValueError('Input not declared for this claim')
                    with (self.root/'blobs'/fileid).open('rb') as stream:stream.seek(offset);data=stream.read(512*1024)
                    result={'data':base64.b64encode(data).decode(),'offset':offset}
                elif op=='upload_status':
                    result={'files':{p.name:p.stat().st_size for p in out.iterdir() if p.is_file() and not p.is_symlink()}}
                elif op=='upload':
                    name=request['name']
                    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',name) or pathlib.Path(name).suffix not in ('.png','.mp4','.blend','.json','.log'):raise ValueError('Output name forbidden')
                    data=base64.b64decode(request['data'],validate=True);target=out/name
                    if target.is_symlink() or len(data)>512*1024 or type(request['offset'])!=int:raise ValueError('Upload budget')
                    size=target.stat().st_size if target.exists() else 0
                    if size!=request['offset'] or size+len(data)>2*1024**3:raise ValueError('Nonsequential/oversize upload')
                    if sum(p.stat().st_size for p in out.iterdir())+len(data)>4*1024**3:raise ValueError('Job output budget')
                    with target.open('ab') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
                    result={'offset':size+len(data)}
                elif op in ('complete','failed','uncertain'):
                    if op=='complete':
                        self.privileged('initial',manifest=spec) if self.root==pathlib.Path('/data/ai/helper-scripts/state/workstation-render-stage') else validate(spec,self.project,json.loads(row['roots']) if row['roots'] else None)
                        files=request['files']
                        if not isinstance(files,dict) or not 1<=len(files)<=128 or any(not re.fullmatch('[a-f0-9]{64}',v) or (out/k).parent!=out or not (out/k).is_file() or digest(out/k)!=v for k,v in files.items()):raise ValueError('Output hash verification failed')
                        if spec.get('kind')=='godot':
                            from game_contract import verify_evidence
                            evidence=json.loads((out/'worker.json').read_text());verify_evidence(spec,evidence,files,out)
                        else:
                            evidence=json.loads((out/'worker.json').read_text())
                            if evidence.get('source_sha256')!=spec['source_sha256'] or evidence.get('platform')!='Windows' or evidence.get('memory_limit_verified') is not True or evidence.get('engine')!='5.2.1 LTS':raise ValueError('Worker receipt mismatch')
                            if evidence.get('status') not in ('PASS','PREPARED_REVIEW_PENDING','CAPTURED_VISUAL_REVIEW_PENDING'):raise ValueError('Worker did not succeed')
                            if spec['mode'] not in ('inspect','pose-inspect','pose-prepare'):
                                import struct
                                images=evidence.get('images',[]);count=1 if spec['mode']=='still' else spec.get('frames',[1,1])[1]-spec.get('frames',[1,1])[0]+1
                                if len(images)!=count or any(name not in files for name in images):raise ValueError('Rendered frames missing')
                                for name in images:
                                    header=(out/name).read_bytes()[:24]
                                    if header[:8]!=bytes([137,80,78,71,13,10,26,10]) or list(struct.unpack('>II',header[16:24]))!=spec.get('resolution',[768,1024]):raise ValueError('Invalid rendered PNG')
                            if spec['mode']=='pose-prepare' and 'posed.blend' not in files:raise ValueError('Prepared blend missing')
                            if spec.get('output_format')=='mp4' and 'capture.mp4' not in files:raise ValueError('MP4 missing')
                        state='COMPLETED_VISUAL_REVIEW_PENDING'
                        receipt={'schema':'watoom.workstation-stage.receipt.v1','job':row['id'],'worker':worker,'files':files,'source_sha256':spec['source_sha256'],'platform':'Windows','evidence':evidence,'visual_acceptance':False,'source_unchanged':True,'finishedAt':time.time()}
                        write(out/'receipt.json',receipt)
                        self.db.execute('update jobs set receipt=? where id=?',(json.dumps(receipt),row['id']))
                        public=self.project/'results'/row['id'];public.mkdir(exist_ok=True)
                        import shutil
                        for name in files:shutil.copyfile(out/name,public/name)
                        write(public/'receipt.json',receipt)
                    else:
                        state='FAILED' if op=='failed' else 'RECONCILIATION_REQUIRED'
                        files=request.get('files',{})
                        if not isinstance(files,dict) or len(files)>128:raise ValueError('Diagnostic artifact budget')
                        public=self.project/'results'/row['id'];public.mkdir(exist_ok=True)
                        for name,sha in files.items():
                            file=out/name
                            if file.parent!=out or not file.is_file() or file.is_symlink() or digest(file)!=sha:raise ValueError('Diagnostic hash mismatch')
                            import shutil
                            shutil.copy2(file,public/name)
                        receipt={'schema':'watoom.workstation-stage.receipt.v1','job':row['id'],'worker':worker,'status':state,'source_sha256':spec['source_sha256'],'files':files,'error':request.get('error',''),'visual_acceptance':False}
                        write(public/'receipt.json',receipt)
                        self.db.execute('update jobs set receipt=? where id=?',(json.dumps(receipt),row['id']))
                    self.db.execute('update jobs set state=?,error=?,token=null where id=?',(state,request.get('error','')[:400],row['id']))
                    result={'state':state}
                else:raise ValueError('Operation forbidden')
            self.db.commit();return result
        except BaseException:self.db.rollback();raise

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--project',required=True);p.add_argument('--scan',action='store_true');p.add_argument('--admit-native',action='store_true');p.add_argument('--cancel-native',action='store_true');p.add_argument('--admit-game-native',action='store_true');p.add_argument('--worker',default='rig-stage');args=p.parse_args()
    broker=Broker(args.root,args.project)
    try:
        if args.admit_game_native:
            value=json.loads(sys.stdin.buffer.read(100000));cfg=json.loads(pathlib.Path('/etc/watoom-rig-async-stage.json').read_text())
            if not cfg.get('enabled') or value['native']['project'] not in cfg['projects'] or value['manifest'].get('kind')!='godot':raise ValueError('RIG game staging route not enabled/authorized')
            identity=broker.admit(value['manifest'],cfg['projects'],value['native']);print(json.dumps({'job':identity}))
        elif args.admit_native:
            value=json.loads(sys.stdin.buffer.read(100000));cfg=json.loads(pathlib.Path('/etc/watoom-asset-capture.json').read_text())
            if value['native']['project'] not in cfg['projects']:
                stage=json.loads(pathlib.Path('/etc/watoom-rig-async-stage.json').read_text())
                if not stage.get('enabled') or value['native']['project'] not in stage['projects']:raise ValueError('Native project not authorized')
            identity=broker.admit(value['manifest'],cfg['source_roots']+[value['native']['project']],value['native'])
            print(json.dumps({'job':identity}))
        elif args.cancel_native:
            value=json.loads(sys.stdin.buffer.read(100000))
            broker.db.execute('begin immediate')
            row=broker.db.execute('select state,native from jobs where id=?',(value['job'],)).fetchone()
            if not row or json.loads(row['native'])!=value['native']:raise ValueError('Native cancellation binding mismatch')
            if row['state']=='QUEUED':broker.db.execute("update jobs set state='CANCELLED',error='Native session interrupted before claim' where id=?",(value['job'],))
            broker.db.commit();print(json.dumps({'state':'CANCELLED' if row['state']=='QUEUED' else row['state']}))
        elif args.scan:broker.scan()
        else:
            for raw in iter(sys.stdin.buffer.readline,b''):
                try:
                    if len(raw)>=800000:raise ValueError('Protocol request too large')
                    response={'ok':True,'result':broker.operation(json.loads(raw),args.worker)}
                except Exception as error:response={'ok':False,'error':str(error)[:500]}
                print(json.dumps(response),flush=True)

    except Exception as error:
        print(json.dumps({'ok':False,'error':str(error)[:500]}));sys.exit(1)
    finally:broker.db.close()
if __name__=='__main__':main()
