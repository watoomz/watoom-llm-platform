"""One-slot outbound workstation stage worker; claims are never blindly replayed."""
import argparse, base64, hashlib, json, os, pathlib, subprocess, threading, time
from windows_job import run
from pause_control import control,check,PauseRequested

def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def save(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2));os.replace(temp,path)

class Worker:
    def __init__(self,config):
        self.channel=None;self.channel_lock=threading.Lock()
        source=pathlib.Path(__file__).resolve().parent
        provenance=json.loads((source/'renderer-provenance.json').read_text())
        if not provenance.get('outputs'):raise RuntimeError('Runtime bundle lacks output hashes')
        for name,expected in provenance['outputs'].items():
            path=source/name
            if not path.resolve().is_relative_to(source) or digest(path)!=expected:raise RuntimeError('Runtime helper hash changed: '+name)
        self.execution=hashlib.sha256(json.dumps({'files':{str(f.relative_to(source)):digest(f) for f in sorted(source.rglob('*')) if f.is_file() and f.suffix in ('.py','.json') and '__pycache__' not in f.parts},'device':config.get('device'),'blender':digest(pathlib.Path(config['blender']))},sort_keys=True).encode()).hexdigest()
        self.config=config;self.root=pathlib.Path(config['root']);self.root.mkdir(exist_ok=True)
    def rpc(self,operation,claim=None,**values):
        request={'op':operation,**values}
        if claim:request.update(job=claim['job'],token=claim['token'])
        c=self.config
        import queue
        with self.channel_lock:
            if self.channel is None or self.channel.poll() is not None:
                self.replies=queue.Queue();replies=self.replies
                self.channel=subprocess.Popen([c['ssh'],'-T','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=10','-i',c['key'],'-l',c['user'],c['host']],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1,creationflags=0x08000000)
                stream=self.channel.stdout
                def receive():
                    try:
                        for line in stream:replies.put(line)
                    finally:replies.put(None)
                threading.Thread(target=receive,daemon=True).start()
            try:
                self.channel.stdin.write(json.dumps(request)+'\n');self.channel.stdin.flush()
                raw=self.replies.get(timeout=180 if operation in ('claim','dependencies','complete') else 30)
                if raw is None:raise RuntimeError('Worker transport channel closed')
                response=json.loads(raw)
            except BaseException:
                self.channel.kill();self.channel=None;raise
            if not response['ok']:raise RuntimeError(response['error'])
            return response['result']
    def sftp(self,lines,out):
        import uuid
        batch=out/('.sftp-'+uuid.uuid4().hex+'.batch');batch.write_text('\n'.join(lines)+'\n',encoding='utf-8')
        c=self.config
        try:
            for attempt in range(3):
                if attempt:
                    # Retry file transport only; Blender is never rerun here.
                    current=self.rpc('upload_status',self.transfer_claim)['files'] if any(line.startswith(('put ','reput ')) for line in lines) else {}
                    import shlex
                    retried=[]
                    for line in lines:
                        if line.startswith(('put ','reput ')):
                            parts=shlex.split(line);name=pathlib.PurePosixPath(parts[2]).name
                            line=('reput' if name in current else 'put')+' '+self.quote(parts[1])+' '+self.quote(parts[2])
                        retried.append(line)
                    batch.write_text('\n'.join(retried)+'\n',encoding='utf-8');time.sleep(attempt*2)
                result=subprocess.run([c.get('sftp','C:/Windows/System32/OpenSSH/sftp.exe'),'-b',str(batch),'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-i',c['sftp_key'],c.get('sftp_user','watoom-render-transfer')+'@'+c['host']],capture_output=True,text=True,timeout=c.get('transfer_timeout',3600),creationflags=0x08000000)
                with (out/'transfer.log').open('a',encoding='utf-8') as log:log.write(result.stdout+result.stderr)
                if result.returncode==0:return
            raise RuntimeError('SFTP transfer failed after three transport attempts; inspect transfer.log: '+result.stderr[-250:])
        finally:batch.unlink(missing_ok=True)
    def quote(self,value):
        value=str(value).replace('\\','/')
        if any(c in value for c in ('\n','\r','\0')):raise ValueError('Control character in transfer path')
        return '"'+value.replace('"','\\"')+'"'
    def once(self):
        if control(self.config):return
        paused_job=None
        journal=self.root/'active.private.json'
        resume=None
        if journal.exists():
            old=json.loads(journal.read_text())
            if old['phase']=='FETCHING' and old.get('claim',{}).get('job')==self.config.get('resume_fetch_job'):
                if old.get('execution')!=self.execution:raise RuntimeError('Execution scripts/profile changed; resume validation invalidated, reconcile this claim')
                resume=old['claim'];self.rpc('heartbeat',resume)
            elif old['phase']=='PAUSED':
                if old.get('execution')!=self.execution:raise RuntimeError('Paused runtime changed; operator reconciliation required')
                self.rpc('resume',old['claim']);paused_job=old['claim']['job']
                import shutil
                oldout=self.root/'jobs'/paused_job;archive=oldout/('paused-attempt-'+str(time.time_ns()));archive.mkdir()
                for item in list(oldout.iterdir()):
                    if item.is_file():shutil.move(str(item),str(archive/item.name))
            elif old['phase'] not in ('DONE','FAILED','RECONCILIATION_REQUIRED'):
                self.rpc('uncertain',old['claim'],error='Worker restarted during '+old['phase']+'; operator reconciliation required')
                save(journal,{'phase':'RECONCILIATION_REQUIRED','job':old['claim']['job']})
                return
        claim=resume or self.rpc('claim',only_job=paused_job or self.config.get('only_job'),native_only=self.config.get('native_only',True),job_kind='blender')
        if not claim.get('job'):return
        self.transfer_claim=claim
        out=self.root/'jobs'/claim['job'];out.mkdir(parents=True,exist_ok=bool(resume or paused_job))
        save(journal,{'phase':'FETCHING','claim':claim,'execution':self.execution})
        stopped=threading.Event();health={'last':time.monotonic()}
        def beat():
            while not stopped.wait(15):
                try:self.rpc('heartbeat',claim);health['last']=time.monotonic()
                except Exception:pass
        thread=threading.Thread(target=beat,daemon=True);thread.start()
        def valid():
            check(self.config)
            if time.monotonic()-health['last']>65:raise RuntimeError('Lease heartbeat lost; render stopped for reconciliation')
        terminal_sent=False
        try:
            import copy,re,posixpath
            spec=copy.deepcopy(claim['manifest']);mapping={};inputs=claim.get('inputs',[])
            if not inputs:inputs=[{'id':spec['source_sha256'],'sha256':spec['source_sha256'],'original':spec['source'],'relative':'inputs/source'+pathlib.Path(spec['source']).suffix,'size':claim['source_size']}]
            def transfer(items):
                pending=[];commands=[]
                for item in items:
                    if item['original'] in mapping:continue
                    relative=pathlib.PurePosixPath(item['relative'])
                    if relative.is_absolute() or '..' in relative.parts:raise ValueError('Indirect input path')
                    file=out/pathlib.Path(*relative.parts)
                    if not file.resolve().is_relative_to(out.resolve()):raise ValueError('Input path escaped')
                    file.parent.mkdir(parents=True,exist_ok=True)
                    if not re.fullmatch('[a-f0-9]{64}',item['id']):raise ValueError('Invalid content id')
                    if file.exists() and file.stat().st_size>item['size']:raise ValueError('Resume file exceeds input size')
                    if file.exists() and file.stat().st_size==item['size'] and digest(file)!=item['sha256']:
                        file.rename(file.with_name(file.name+'.corrupt-'+str(time.time_ns())))
                    if not file.exists() or file.stat().st_size!=item['size']:
                        commands.append('reget '+self.quote('/payloads/inputs/'+item['id'])+' '+self.quote(file))
                    pending.append((item,file))
                if commands:self.sftp(commands,out)
                for item,file in pending:
                    valid()
                    if digest(file)!=item['sha256']:raise ValueError('Transferred input hash mismatch')
                    mapping[item['original']]=str(file)
            transfer(inputs)
            original_source=spec['source'];source=pathlib.Path(mapping[original_source]);spec['source']=str(source)
            if spec.get('preparation',{}).get('method')=='ts4-retarget':
                plan=spec['preparation']['plan'];plan['clip']=mapping[plan['clip']]
            request={'manifest':spec,'source_roots':[str(out)],'device':self.config.get('device','CPU'),'original_source':original_source,'original_source_sha256':claim['manifest']['source_sha256'],'dependency_map':mapping,'ffmpeg':self.config.get('ffmpeg')}
            plan=out/'plan.json';save(plan,request)
            command=[self.config['blender'],'--background','--factory-startup','--disable-autoexec','--threads','4','--python-exit-code','1','--python']
            if source.suffix.lower()=='.blend':
                for iteration in range(12):
                    code=run(command+[str(pathlib.Path(__file__).with_name('portable_inputs.py')),'--',str(plan)],out,timeout=120,heartbeat=valid)
                    if code:raise RuntimeError('Dependency inspection failed; exit '+str(code))
                    deps=json.loads((out/'dependencies.json').read_text())
                    pending=[item for item in deps if item['path'] not in mapping]
                    if not pending:break
                    inputs=self.rpc('dependencies',claim,paths=pending)['inputs'];transfer(inputs)
                    for item in pending:
                        if item['kind']=='tiled' and '<UDIM>' in item['path']:
                            import fnmatch
                            matches=[v for k,v in mapping.items() if fnmatch.fnmatch(k,item['path'].replace('<UDIM>','[0-9][0-9][0-9][0-9]'))]
                            if matches:mapping[item['path']]=str(pathlib.Path(matches[0]).parent/pathlib.PurePosixPath(item['path']).name)
                    save(plan,request)
                else:raise ValueError('Dependency graph did not converge')
            else:
                from portable_package import rebase
                source=rebase(source,original_source,mapping,out);spec['source']=str(source);spec['source_sha256']=digest(source)
            from asset_capture_contract import manifest
            manifest(spec,[str(out)]);save(plan,request)
            save(journal,{'phase':'RENDERING','claim':claim})
            code=run(command+[str(pathlib.Path(__file__).with_name('stage_renderer.py')),'--',str(plan)],out,timeout=900,heartbeat=valid)
            if any(digest(pathlib.Path(mapping[item['original']]))!=item['sha256'] for item in inputs):raise RuntimeError('Source/dependency snapshot changed')
            evidence=json.loads((out/'worker.json').read_text()) if (out/'worker.json').is_file() else {'files':[]}
            save(journal,{'phase':'UPLOADING','claim':claim})
            if code:
                names=[p.name for p in out.iterdir() if p.is_file() and p.suffix in ('.json','.log','.blend','.png','.mp4')]
            else:
                if not evidence.get('memory_limit_verified'):raise RuntimeError('Windows resource boundary not verified')
                names=list(dict.fromkeys(evidence['files']+['worker.json']+(['blender.log'] if (out/'blender.log').is_file() and (out/'blender.log').stat().st_size else [])))
            files={};commands=[];remote=self.rpc('upload_status',claim)['files']
            for name in names:
                valid();file=out/name
                if file.parent!=out or file.stat().st_size>2*1024**3:raise ValueError('Output budget')
                files[name]=digest(file)
                if name in remote and remote[name]>file.stat().st_size:raise ValueError('Remote output exceeds local size; reconcile')
                commands.append(('reput ' if name in remote else 'put ')+self.quote(file)+' '+self.quote('/payloads/uploads/'+claim['job']+'/'+name))
            if commands:self.sftp(commands,out)
            if code:
                self.rpc('failed',claim,error='Blender exit '+str(code),files=files)
                terminal_sent=True
                raise RuntimeError('Blender failed; diagnostic artifacts retained; exit '+str(code))
            result=self.rpc('complete',claim,files=files)
            save(journal,{'phase':'DONE','job':claim['job'],'result':result});save(out/'result.json',result)
        except PauseRequested as error:
            self.rpc('pause',claim,error=str(error))
            save(journal,{'phase':'PAUSED','claim':claim,'execution':self.execution,'error':str(error)})
            return
        except Exception as error:
            uncertain=time.monotonic()-health['last']>65
            try:
                if not terminal_sent:self.rpc('uncertain' if uncertain else 'failed',claim,error=str(error))
            except Exception:uncertain=True
            save(journal,{'phase':'RECONCILIATION_REQUIRED' if uncertain else 'FAILED','job':claim['job'],'error':str(error)})
            raise
        finally:stopped.set();thread.join(timeout=26)

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--once',action='store_true');args=p.parse_args()
    worker=Worker(json.loads(pathlib.Path(args.config).read_text()))
    import msvcrt
    lock=(worker.root/'worker.lock').open('a+b');lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
    msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    while True:
        try:
            worker.rpc('hello');worker.once();save(worker.root/'health.json',{'status':'paused' if control(worker.config) else 'online','seenAt':time.time()})
        except Exception as error:
            save(worker.root/'health.json',{'status':'error','seenAt':time.time(),'error':str(error)[:500]})
            if args.once:raise
        if args.once:break
        time.sleep(10)
if __name__=='__main__':main()
