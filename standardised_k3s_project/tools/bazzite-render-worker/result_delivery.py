"""Idempotent receipt collection. Network retries never launch or replay a render."""
from pathlib import Path
import json,hashlib,os,re,time,fcntl

def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def atomic(path,value):
 path=Path(path);temporary=path.with_name('.'+path.name+'.tmp')
 with temporary.open('w') as f:json.dump(value,f,sort_keys=True);f.flush();os.fsync(f.fileno())
 os.replace(temporary,path);fd=os.open(path.parent,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
def validate(receipt,job,source):
 if receipt.get('schema')!=1 or receipt.get('job')!=job or receipt.get('source_fingerprint')!=source or receipt.get('status') not in ('COMPLETED','FAILED'):raise ValueError('Receipt identity/terminal status mismatch')
 files=receipt.get('files')
 if not isinstance(files,dict) or not 1<=len(files)<=128:raise ValueError('Artifact count')
 total=0
 for name,v in files.items():
  if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',name) or name in ('receipt.json','delivery.json') or not isinstance(v,dict) or set(v)!={'sha256','size'} or not re.fullmatch('[a-f0-9]{64}',v['sha256']) or type(v['size'])!=int or not 0<=v['size']<=2*1024**3:raise ValueError('Invalid artifact metadata')
  total+=v['size']
 if total>4*1024**3:raise ValueError('Total artifact budget')
 return files
class Receiver:
 def __init__(self,destination,fetch):self.root=Path(destination);self.root.mkdir(parents=True,exist_ok=True);self.fetch=fetch
 def collect(self,receipt,job,source):
  fd=os.open(self.root/'.delivery.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
  try:
   fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
   return self._collect(receipt,job,source)
  finally:os.close(fd)
 def _collect(self,receipt,job,source):
  files=validate(receipt,job,source);canonical=json.dumps(receipt,sort_keys=True,separators=(',',':'));identity=hashlib.sha256(canonical.encode()).hexdigest();marker=self.root/'delivery.json'
  if marker.exists():
   saved=json.loads(marker.read_text())
   if saved['receipt_sha256']!=identity:raise ValueError('Terminal receipt changed; reconcile, never overwrite')
  for name,v in files.items():
   final=self.root/name;partial=self.root/(name+'.part')
   if final.is_symlink() or partial.is_symlink():raise ValueError('Indirect artifact')
   if final.exists():
    if final.stat().st_size!=v['size'] or sha(final)!=v['sha256']:raise ValueError('Accepted artifact changed')
    continue
   if partial.exists() and partial.stat().st_size>v['size']:partial.rename(partial.with_name(partial.name+'.bad-'+str(time.time_ns())))
   try:self.fetch(name,partial)
   except Exception:
    atomic(marker,{'job':job,'receipt_sha256':identity,'state':'RECONNECTING','execution_replay':False});raise
   if not partial.is_file() or partial.stat().st_size!=v['size'] or sha(partial)!=v['sha256']:
    if partial.exists():partial.rename(partial.with_name(partial.name+'.bad-'+str(time.time_ns())))
    atomic(marker,{'job':job,'receipt_sha256':identity,'state':'RECONNECTING','execution_replay':False});raise ValueError('Artifact hash/size mismatch; retransfer only')
   with partial.open('rb') as f:os.fsync(f.fileno())
   os.replace(partial,final)
  atomic(self.root/'receipt.json',receipt);atomic(marker,{'job':job,'receipt_sha256':identity,'state':'VERIFIED','execution_replay':False,'ack_id':'ack_'+identity})
  return json.loads(marker.read_text())
