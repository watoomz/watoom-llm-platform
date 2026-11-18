#!/usr/bin/env python3
"""Operator stop/reconciliation only; never resumes prompts or engine work."""
import argparse,json,pathlib,sqlite3,os,time
from maintenance_guard import Maintenance
import release_guard,restarted_claims

def main():
    p=argparse.ArgumentParser();p.add_argument('--root-session',required=True);p.add_argument('--claims',required=True,type=pathlib.Path);p.add_argument('--evidence',required=True,type=pathlib.Path);p.add_argument('--i-approve',action='store_true');a=p.parse_args()
    if not a.i_approve:raise RuntimeError('--i-approve required')
    out=a.evidence.resolve();out.mkdir(parents=True,exist_ok=False,mode=0o700);expected=json.loads(a.claims.read_text());dbpath=pathlib.Path('/data/ai/watoom-code/application.sqlite');m=Maintenance('watoom-code','watoom-code',out,True,True)
    pod=m.pod();terminated,identity=restarted_claims.restart_time(pod);(out/'restart-proof.json').write_text(json.dumps(pod['status']['containerStatuses'],indent=2))
    def clearance():
        release_guard.active_clear(m.request('/api/session/active'))
        if restarted_claims.restart_time(m.pod())!=(terminated,identity):raise RuntimeError('Application identity changed')
        if any(j.get('status',{}).get('active') for j in m.kub('get','jobs')['items']):raise RuntimeError('Worker active')
        for process in pathlib.Path('/proc').iterdir():
            if not process.name.isdigit():continue
            try:exe=(process/'exe').resolve().name.lower()
            except OSError:continue
            if exe.startswith(('blender','unrealeditor','godot')):raise RuntimeError('Engine process active')
        with sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True) as db:restarted_claims.validate(db,expected,a.root_session,terminated)
        try:release_guard.durable_clearance(dbpath)
        except release_guard.UnsafeRelease as e:
            prefix='Durable execution clearance failed: '
            if not str(e).startswith(prefix):raise
            gates=json.loads(str(e)[len(prefix):])
            if gates.pop('execution_claims')!=len(expected) or any(gates.values()):raise RuntimeError('Other durable work present')
        else:raise RuntimeError('Expected claims disappeared')
    def save(owner):
        f=out/'owner.private';f.write_text(owner);f.chmod(0o600)
        with f.open('rb') as stream:os.fsync(stream.fileno())
    owner=release_guard.acquire(m.request,lambda path,body:m.request(path,body),save,clearance)
    try:
        clearance();release_guard.snapshot_database(dbpath,out/'application-before.private.sqlite')
        with sqlite3.connect(dbpath,timeout=5) as db:count=restarted_claims.reconcile(db,expected,a.root_session,terminated,int(time.time()*1000))
        result=dict(status='PASS',changed_rows=count,scope='exact OOM-interrupted session tree; history preserved',job_resumed=False,clearance=release_guard.durable_clearance(dbpath));(out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
    finally:release_guard.release(m.request,lambda path,body:m.request(path,body),owner)
if __name__=='__main__':main()
