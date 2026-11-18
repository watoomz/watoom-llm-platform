"""Reconcile exact session claims from a proven terminated application process."""
import datetime

def restart_time(pod):
    containers=[x for x in pod['status']['containerStatuses'] if x['name']=='app']
    if len(containers)!=1:raise ValueError('Expected one application container')
    c=containers[0];old=c.get('lastState',{}).get('terminated',{});new=c.get('state',{}).get('running',{})
    if c['restartCount']<1 or old.get('reason')!='OOMKilled' or old.get('exitCode')!=137 or not new.get('startedAt'):raise ValueError('Proven OOM restart required')
    parse=lambda x:int(datetime.datetime.fromisoformat(x.replace('Z','+00:00')).timestamp()*1000)
    if parse(old['finishedAt'])>parse(new['startedAt']):raise ValueError('Inconsistent restart timeline')
    return parse(old['finishedAt']),c['containerID']

def validate(db,expected,root,terminated_at):
    fields=('id','parent_id','time_suspended','time_updated')
    if not isinstance(expected,list) or not 1<=len(expected)<=16 or any(set(x)!=set(fields) for x in expected):raise ValueError('Exact bounded claim set required')
    actual=[dict(zip(fields,row)) for row in db.execute('SELECT id,parent_id,time_suspended,time_updated FROM session_v2 WHERE time_suspended IS NOT NULL')]
    if sorted(actual,key=lambda x:x['id'])!=sorted(expected,key=lambda x:x['id']):raise ValueError('Claim identity changed')
    tree={x[0] for x in db.execute('WITH RECURSIVE tree(id) AS (SELECT id FROM session_v2 WHERE id=? UNION ALL SELECT s.id FROM session_v2 s JOIN tree t ON s.parent_id=t.id) SELECT id FROM tree',(root,))}
    roots=[x for x in expected if x['id']==root and x['parent_id'] is None]
    if len(roots)!=1 or any(x['id'] not in tree for x in expected):raise ValueError('Claims must belong to the exact selected root tree')
    if any(x['time_suspended']>=terminated_at or x['time_updated']>=terminated_at for x in expected):raise ValueError('Newer work must not be reconciled')
    return expected

def reconcile(db,expected,root,terminated_at,now):
    db.execute('BEGIN IMMEDIATE')
    try:
        validate(db,expected,root,terminated_at)
        for x in expected:
            count=db.execute("UPDATE session_v2 SET time_suspended=NULL,resume_attempts=0,time_idle=?,idle_outcome='interrupted' WHERE id=? AND time_suspended=? AND time_updated=?",(now,x['id'],x['time_suspended'],x['time_updated'])).rowcount
            if count!=1:raise ValueError('Concurrent session change')
        db.commit()
    except BaseException:db.rollback();raise
    return len(expected)
