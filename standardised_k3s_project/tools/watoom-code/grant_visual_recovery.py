"""Create one audited, exact-child recovery grant under an owned native release fence.
This changes no session counters/receipts and never grants visual acceptance.
"""
from pathlib import Path
import os,json,sqlite3,hashlib,secrets,re,tempfile

def grant(config,database,parent,guard_sha,evidence,maintenance):
 if os.geteuid()!=0:raise PermissionError('Operator only')
 g=maintenance.request('/api/session/deployment-guard').get('data',{})
 if not g.get('held') or g.get('leases')!=0 or maintenance.request('/api/session/active')!={'data':{}}:raise ValueError('Native idle release fence required')
 config=Path(config);database=Path(database);evidence=Path(evidence);before=config.read_bytes();cfg=json.loads(before)
 entries=[x for x in cfg['plugins'] if isinstance(x,dict) and x.get('package','').endswith('/coordinator-guard-'+guard_sha)]
 if len(entries)!=1:raise ValueError('Reviewed immutable guard version not selected')
 entry=entries[0];installed=config.parent/entry['package'].removeprefix('/config/')/'index.js'
 if hashlib.sha256(installed.read_bytes()).hexdigest()!=guard_sha:raise ValueError('Installed guard hash mismatch')
 prefix='plugin:'+'watoom.coordinator-guard'.encode('utf-16-be').hex()+':session/'
 with sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True) as db:
  def state(sid):
   row=db.execute('select value from kv where key=?',(prefix+sid,)).fetchone()
   if not row:raise ValueError('Missing native guard state')
   return json.loads(row[0])
  owner=state(parent);child=owner.get('child')
  if not owner.get('childReviewBlocked') or not child:raise ValueError('No blocked exact-child visual review')
  child_state=state(child);visual=child_state.get('pendingVisual') or {}
  a=db.execute('select directory from session_v2 where id=?',(parent,)).fetchone();z=db.execute('select parent_id,directory from session_v2 where id=?',(child,)).fetchone()
  if not a or not z or z!=(parent,a[0]):raise ValueError('Native child/project relationship mismatch')
  if visual.get('reviewMode')!='isolated-image-v2' or visual.get('presentationEvidence')!='exact-image-request-successful-response' or visual.get('presentedBy') not in entry['options'].get('verifiedVisionModels',[]):raise ValueError('Verified pixel presentation required')
  image=Path(visual['path'])
  if image.is_symlink() or image.resolve()!=image or hashlib.sha256(image.read_bytes()).hexdigest()!=visual.get('sha256'):raise ValueError('Pending image changed')
 evidence.mkdir(parents=True,exist_ok=True,mode=0o700);record=evidence/'visual-recovery-grant.private.json'
 if record.exists():
  permit=json.loads(record.read_text())
  if permit['parentSessionID']!=parent or permit['childSessionID']!=child or permit['image_sha256']!=visual['sha256'] or permit['nonce'] in owner.get('consumedRecoveryGrants',[]):raise ValueError('Recovery already consumed or identity changed; no fresh retry')
 else:
  permit={'parentSessionID':parent,'childSessionID':child,'image_sha256':visual['sha256'],'nonce':secrets.token_hex(32)}
  with record.open('x') as f:os.fchmod(f.fileno(),0o600);json.dump(permit,f,indent=2);f.flush();os.fsync(f.fileno())
 permits=entry['options'].setdefault('visualRecoveryGrants',[])
 if permit not in permits:permits.append(permit)
 mode=config.stat();fd,tmp=tempfile.mkstemp(prefix='.visual-recovery-',dir=config.parent)
 try:
  with os.fdopen(fd,'w') as f:os.fchmod(f.fileno(),mode.st_mode&0o777);os.fchown(f.fileno(),mode.st_uid,mode.st_gid);json.dump(cfg,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
  if config.read_bytes()!=before:raise ValueError('Concurrent configuration edit')
  os.replace(tmp,config)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
 return {'parent':parent,'child':child,'image_sha256':visual['sha256'],'oneUse':True}
