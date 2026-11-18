"""Operator-only same-identity repair from recorded native tool evidence; never submit a new job."""
import argparse,sqlite3,json,pathlib,hashlib,os,time,fcntl
from game_worker_bridge import request_identity,native_proof,fingerprint

def _restore(project,ident,database,evidence):
 if os.geteuid()!=0:raise PermissionError('Operator only')
 project=pathlib.Path(project);evidence=pathlib.Path(evidence)
 if project.parent!=pathlib.Path('/data/ai/projects/games') or project.resolve()!=project:raise ValueError('Canonical game project required')
 if len(ident)!=64 or any(c not in '0123456789abcdef' for c in ident):raise ValueError('Invalid request identity')
 path=project/'.opencode/worker-requests'/(ident+'.json')
 if path.is_symlink() or path.parent.resolve()!=path.parent:raise ValueError('Indirect protocol path')
 with sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True) as db:
  candidates=[]
  for sid,agent,mid,raw in db.execute('select s.id,s.agent,m.id,m.data from session_message m join session_v2 s on s.id=m.session_id where s.directory=?',(str(project),)):
   for call in json.loads(raw).get('content',[]):
    st=call.get('state',{});meta=st.get('metadata',{});inp=st.get('input',{})
    if call.get('type')!='tool' or call.get('name')!='watoom_game_worker' or meta.get('request_id')!=ident or inp.get('action')!='request':continue
    req=dict(schema=1,request_id=ident,project=str(project),operation=inp['operation'],job=inp['job'],source_fingerprint=meta['source_fingerprint'],session_id=sid,message_id=mid,call_id=call['id'],agent=agent,created_at=call['time'].get('ran',call['time']['created']))
    if request_identity(req)!=ident or not native_proof(json.loads(raw),req):raise ValueError('Native provenance mismatch')
    candidates.append(req)
 if len(candidates)!=1:raise ValueError('Exactly one recorded native admission required')
 req=candidates[0]
 if fingerprint(project)!=req['source_fingerprint']:raise ValueError('Source changed: do not revive stale request')
 private=pathlib.Path('/data/ai/private/game-worker')/(ident+'.json')
 if private.exists() and json.loads(private.read_text()).get('status') not in ['QUEUED','WAITING_FOR_HEADROOM']:raise ValueError('Existing execution/terminal evidence: reconcile instead of replay')
 if (pathlib.Path('/data/ai/helper-scripts/reports/game-worker')/ident).exists():raise ValueError('Prior execution evidence exists: no replay')
 evidence.mkdir(parents=True,exist_ok=True,mode=0o700)
 backup=evidence/(ident+'.before.json')
 with backup.open('xb') as f:f.write(path.read_bytes());f.flush();os.fsync(f.fileno())
 backup.chmod(0o600)
 temporary=path.with_name('.'+ident+'.operator-repair');fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o644)
 with os.fdopen(fd,'w') as f:json.dump(req,f,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(temporary,path)
 record={'request_id':ident,'same_native_identity':True,'no_prior_execution':True,'source_matches':True,'restored_from_message':req['message_id'],'restored_call':req['call_id'],'backup':str(backup)}
 (evidence/'repair-result.json').write_text(json.dumps(record,indent=2));return record
def restore(project,ident,database,evidence):
 with pathlib.Path('/data/ai/private/game-worker/worker.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  return _restore(project,ident,database,evidence)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--project',required=True);p.add_argument('--request-id',required=True);p.add_argument('--database',required=True);p.add_argument('--evidence',required=True);a=p.parse_args();print(json.dumps(restore(a.project,a.request_id,a.database,a.evidence)))
