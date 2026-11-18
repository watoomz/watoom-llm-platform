"""Exact cancellation reconciliation; never infer clearance from idle alone."""
import json

def validate(db,expected):
    if not isinstance(expected,list) or not 1<=len(expected)<=16:raise ValueError('Select 1..16 exact orphan claims')
    fields=('id','parent_id','time_suspended','time_updated')
    if any(set(x)!=set(fields) for x in expected) or len({x['id'] for x in expected})!=len(expected):raise ValueError('Invalid expected claim set')
    rows=db.execute('SELECT s.id,s.parent_id,s.time_suspended,s.time_updated,p.time_idle,p.idle_outcome FROM session_v2 s LEFT JOIN session_v2 p ON p.id=s.parent_id WHERE s.time_suspended IS NOT NULL').fetchall()
    actual=[dict(zip(fields,row[:4])) for row in rows]
    if sorted(actual,key=lambda x:x['id'])!=sorted(expected,key=lambda x:x['id']):raise ValueError('Exact orphan claim set changed')
    if any(not row[1] or row[4] is None or row[5]!='interrupted' for row in rows):raise ValueError('Each owner parent must be interrupted and idle')
    return actual

def reconcile(db,expected):
    db.execute('BEGIN IMMEDIATE')
    try:
        validate(db,expected)
        for row in expected:
            changed=db.execute('UPDATE session_v2 SET time_suspended=NULL,resume_attempts=0 WHERE id=? AND parent_id=? AND time_suspended=? AND time_updated=?',(row['id'],row['parent_id'],row['time_suspended'],row['time_updated'])).rowcount
            if changed!=1:raise ValueError('Concurrent claim change')
        db.commit()
    except BaseException:
        db.rollback();raise
    return len(expected)
