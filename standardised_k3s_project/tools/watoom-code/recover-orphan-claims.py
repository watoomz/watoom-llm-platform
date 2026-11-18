#!/usr/bin/env python3
"""Bounded multi-child extension of recover-orphan-claim.py; preserves history."""
import argparse,json,pathlib,sqlite3,sys,os
from maintenance_guard import Maintenance
import release_guard,orphan_claims

def main():
    p=argparse.ArgumentParser();p.add_argument('--claims',required=True,type=pathlib.Path);p.add_argument('--evidence',required=True,type=pathlib.Path);p.add_argument('--i-approve',action='store_true');a=p.parse_args()
    if not a.i_approve:raise RuntimeError('--i-approve required')
    expected=json.loads(a.claims.read_text());out=a.evidence.resolve();out.mkdir(parents=True,exist_ok=False,mode=0o700)
    dbpath=pathlib.Path('/data/ai/watoom-code/application.sqlite');m=Maintenance('watoom-code','watoom-code',out,True,True)
    def clearance():
        release_guard.active_clear(m.request('/api/session/active'))
        if any(j.get('status',{}).get('active') for j in m.kub('get','jobs')['items']):raise RuntimeError('Active worker job')
        with sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True) as db:orphan_claims.validate(db,expected)
        try:release_guard.durable_clearance(dbpath)
        except release_guard.UnsafeRelease as error:
            prefix='Durable execution clearance failed: '
            if not str(error).startswith(prefix):raise
            gates=json.loads(str(error)[len(prefix):])
            if gates.pop('execution_claims')!=len(expected) or any(gates.values()):raise RuntimeError('Other durable work present')
        else:raise RuntimeError('Expected claims disappeared')
    def save(owner):
        file=out/'owner.private';file.write_text(owner);file.chmod(0o600)
        with file.open('rb') as f:os.fsync(f.fileno())
    owner=release_guard.acquire(m.request,lambda path,body:m.request(path,body),save,clearance)
    try:
        clearance();release_guard.snapshot_database(dbpath,out/'application-before.private.sqlite')
        (out/'claims-before.json').write_text(json.dumps(expected,indent=2))
        with sqlite3.connect(dbpath,timeout=5) as db:count=orphan_claims.reconcile(db,expected)
        result=dict(status='PASS',changed_rows=count,history_preserved=True,scope='exact interrupted-parent child claims only',clearance=release_guard.durable_clearance(dbpath))
        (out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
    finally:release_guard.release(m.request,lambda path,body:m.request(path,body),owner)

if __name__=='__main__':main()
