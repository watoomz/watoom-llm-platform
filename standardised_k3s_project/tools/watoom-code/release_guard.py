"""Release admission protocol shared by maintained deployment helpers.

No endpoint fallback: old applications without a durable guard are never promoted.
The owner token must be retained in private recovery evidence after acquisition.
"""
import secrets
import sqlite3,json,contextlib,os
class UnsafeRelease(RuntimeError):
    pass
def validate(value, held):
    data=value.get("data") if isinstance(value,dict) else None
    if not isinstance(data,dict) or data.get("version")!=1 or data.get("supported") is not True or data.get("held") is not held or data.get("leases")!=0:
        raise UnsafeRelease("Persistent native admission guard unavailable or execution not idle")
    return data
def active_clear(value):
    if not isinstance(value,dict) or set(value)!={"data"} or value["data"]!={}:
        raise UnsafeRelease("Native executions active or status contract invalid")
def acquire(get,post,save_owner,clearance):
    # These checks do not establish the fence. Atomic native acquire does.
    active_clear(get("/api/session/active"))
    validate(get("/api/session/deployment-guard"),False)
    clearance()
    owner=secrets.token_hex(32)
    save_owner(owner) # fsync owner evidence before acquiring a persistent fence
    validate(post("/api/session/deployment-guard",{"action":"acquire","owner":owner}),True)
    try:
        # Race winner either owns a work lease (acquire refuses) or sees the fence.
        validate(get("/api/session/deployment-guard"),True)
        active_clear(get("/api/session/active"))
        clearance()
    except BaseException:
        validate(post("/api/session/deployment-guard",{"action":"release","owner":owner}),False)
        raise
    return owner
def runtime(get,expected_image,actual_image):
    if actual_image!=expected_image:
        raise UnsafeRelease("Running immutable digest mismatch")
    validate(get("/api/session/deployment-guard"),True)
    active_clear(get("/api/session/active"))
    info=get("/api/info")
    if not isinstance(info,dict) or not isinstance(info.get("version"),str):
        raise UnsafeRelease("Authenticated application readiness failed")
def release(get,post,owner):
    validate(get("/api/session/deployment-guard"),True)
    validate(post("/api/session/deployment-guard",{"action":"release","owner":owner}),False)

def durable_clearance(path):
    with sqlite3.connect("file:"+str(path)+"?mode=ro",uri=True,timeout=5) as db:
        db.execute("BEGIN")
        tables={name for (name,) in db.execute("select name from sqlite_master where type='table'")}
        # session_pending was dropped by OpenCode v2.2.5 (pending input moved to session_inbox); check it where it still exists.
        checks={table:db.execute("select count(*) from "+table).fetchone()[0] for table in ("session_pending","session_inbox") if table in tables}
        if "job" in tables:checks["running_jobs"]=db.execute("select count(*) from job where status='running'").fetchone()[0]
        checks["execution_claims"]=db.execute("select count(*) from session_v2 where time_suspended is not null").fetchone()[0]
        checks["background_jobs"]=sum(json.loads(value).get("status")=="running" for (value,) in db.execute("select value from kv where key like 'job.background/%'"))
        jobs=db.execute("select phase,specialist_body,generation from _watoom_specialist_job").fetchall()
        checks["unsettled_specialists"]=sum(phase not in ("completed","failed","uncertain") for phase,_,_ in jobs)
        checks["unreconciled_gpu_ownership"]=sum(phase=="uncertain" and (generation is not None or json.loads(body).get("execution")!="cpu") for phase,body,generation in jobs)
    if any(checks.values()):raise UnsafeRelease("Durable execution clearance failed: "+json.dumps(checks,sort_keys=True))
    return checks


def snapshot_database(source, destination):
    """Complete a readable standalone SQLite snapshot before recording checksums."""
    with contextlib.closing(sqlite3.connect("file:"+str(source)+"?mode=ro",uri=True,timeout=5)) as original,contextlib.closing(sqlite3.connect(destination)) as snapshot:
        original.backup(snapshot)
        if snapshot.execute("pragma integrity_check").fetchone()[0]!="ok":raise UnsafeRelease("Database snapshot integrity failed")
        if snapshot.execute("pragma wal_checkpoint(truncate)").fetchone()[0]!=0:raise UnsafeRelease("Database snapshot checkpoint busy")
    for path in [destination,destination.parent]:
        fd=os.open(path,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
