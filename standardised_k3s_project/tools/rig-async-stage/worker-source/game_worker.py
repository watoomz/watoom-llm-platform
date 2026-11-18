"""Separate staged Godot consumer sharing the RIG's single leased execution slot."""
import pathlib,json,hashlib,time,os,subprocess,threading,shutil,sys,argparse
from worker import Worker,digest,save
from windows_job import run
from pause_control import control,check,PauseRequested
class GameWorker(Worker):
 def once(self):
  if control(self.config):return
  journal=self.root/'active.private.json';paused=None
  if journal.exists():
   old=json.loads(journal.read_text())
   if old['phase']=='PAUSED':
    if old.get('execution')!=self.execution:raise RuntimeError('Paused runtime changed; reconcile instead of replay')
    self.rpc('resume',old['claim']);paused=old['claim']['job']
    out=self.root/'jobs'/paused;backup=out/('paused-attempt-'+str(time.time_ns()));backup.mkdir()
    for file in list(out.iterdir()):
     if file.name not in ('inputs',backup.name):shutil.move(str(file),str(backup/file.name))
   elif old['phase'] not in ('DONE','FAILED','RECONCILIATION_REQUIRED'):
    self.rpc('uncertain',old['claim'],error='Game worker restarted during '+old['phase']+'; no automatic replay');save(journal,{'phase':'RECONCILIATION_REQUIRED','claim':old['claim']});return
  claim=self.rpc('claim',job_kind='godot',native_only=True,only_job=paused or self.config.get('only_job'))
  if not claim.get('job'):return
  self.transfer_claim=claim;out=self.root/'jobs'/claim['job'];out.mkdir(parents=True,exist_ok=bool(paused));save(journal,{'phase':'FETCHING','claim':claim,'execution':self.execution})
  stop=threading.Event();health={'last':time.monotonic()}
  def beat():
   while not stop.wait(15):
    try:self.rpc('heartbeat',claim);health['last']=time.monotonic()
    except Exception:pass
  thread=threading.Thread(target=beat,daemon=True);thread.start()
  def valid():
   check(self.config)
   if time.monotonic()-health['last']>65:raise RuntimeError('Game worker lease lost; reconcile')
  try:
   spec=dict(claim['manifest']);assert spec['kind']=='godot';items=claim['inputs'];assert len(items)==1;item=items[0];rel=pathlib.PurePosixPath(item['relative']);assert not rel.is_absolute() and '..' not in rel.parts;file=out.joinpath(*rel.parts);file.parent.mkdir(parents=True,exist_ok=True)
   if file.exists() and file.stat().st_size>item['size']:raise ValueError('Input exceeds frozen size')
   self.sftp(['reget '+self.quote('/payloads/inputs/'+item['id'])+' '+self.quote(file)],out);valid()
   if digest(file)!=item['sha256']:raise ValueError('Game snapshot transfer hash mismatch')
   spec['source']=str(file);plan=out/'game-plan.json';save(plan,{'manifest':spec,'godot':self.config['godot']});save(journal,{'phase':'RUNNING','claim':claim,'execution':self.execution})
   code=run([sys.executable,str(pathlib.Path(__file__).with_name('game_runner.py')),str(plan)],out,timeout=900,heartbeat=valid);valid()
   if digest(file)!=item['sha256']:raise ValueError('Frozen game archive changed')
   names=[f.name for f in out.iterdir() if f.is_file() and f.suffix in ('.json','.log','.png')];files={n:digest(out/n) for n in names};save(journal,{'phase':'UPLOADING','claim':claim,'execution':self.execution});remote=self.rpc('upload_status',claim)['files']
   self.sftp([('reput ' if n in remote else 'put ')+self.quote(out/n)+' '+self.quote('/payloads/uploads/'+claim['job']+'/'+n) for n in names],out)
   result=self.rpc('failed' if code else 'complete',claim,files=files,**({'error':'Godot operation failed; diagnostic artifacts retained'} if code else {}));save(journal,{'phase':'FAILED' if code else 'DONE','job':claim['job'],'result':result})
  except PauseRequested as e:
   self.rpc('pause',claim,error=str(e));save(journal,{'phase':'PAUSED','claim':claim,'execution':self.execution,'error':str(e)})
  except Exception as e:
   uncertain=time.monotonic()-health['last']>65
   try:self.rpc('uncertain' if uncertain else 'failed',claim,error=str(e))
   except Exception:uncertain=True
   save(journal,{'phase':'RECONCILIATION_REQUIRED' if uncertain else 'FAILED','claim':claim,'error':str(e)});raise
  finally:stop.set();thread.join(timeout=26)
def main():
 p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--once',action='store_true');a=p.parse_args();w=GameWorker(json.loads(pathlib.Path(a.config).read_text()));profile=json.loads(pathlib.Path(__file__).with_name('game-runtime-provenance.json').read_text());engine=pathlib.Path(w.config['godot'])
 for n,h in profile['files'].items():
  if digest(engine.parent/n)!=h:raise RuntimeError('Game engine identity changed')
 w.execution=hashlib.sha256((w.execution+json.dumps(profile['files'],sort_keys=True)).encode()).hexdigest()
 import msvcrt
 lock=(w.root/'worker.lock').open('a+b');lock.write(b'0');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
 while True:
  try:w.rpc('hello');w.once();save(w.root/'health.json',{'status':'paused' if control(w.config) else 'online','seenAt':time.time()})
  except Exception as e:
   save(w.root/'health.json',{'status':'error','error':str(e)[:500],'seenAt':time.time()})
   if a.once:raise
  if a.once:break
  time.sleep(5)
if __name__=='__main__':main()
