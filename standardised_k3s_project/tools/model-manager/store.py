"""Single durable queue/catalog, revision-scoped overrides and dependency references."""
import sqlite3,json,hashlib,time,threading
def model_identity(selection):
    return hashlib.sha256(json.dumps({k:v for k,v in selection.items() if k!="max_context"},sort_keys=True).encode()).hexdigest()
class Store:
    def __init__(self,path):
        self.path=path; self.local=threading.local()
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,selection TEXT NOT NULL,state TEXT NOT NULL,progress INTEGER NOT NULL DEFAULT 0,error TEXT,updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS models(id TEXT PRIMARY KEY,revision TEXT NOT NULL,record TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY,path TEXT UNIQUE NOT NULL,bytes INTEGER NOT NULL,digest TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS refs(model TEXT NOT NULL,artifact TEXT NOT NULL,PRIMARY KEY(model,artifact));
        CREATE TABLE IF NOT EXISTS overrides(identity TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS image_requests(request_id TEXT PRIMARY KEY,digest TEXT NOT NULL,job_id TEXT NOT NULL);
        """)
        self.db.execute("CREATE TABLE IF NOT EXISTS image_request_sessions(job_id TEXT PRIMARY KEY,session_id TEXT NOT NULL)")
        self.db.execute("CREATE INDEX IF NOT EXISTS image_request_sessions_owner ON image_request_sessions(session_id)")
        columns={row[1] for row in self.db.execute("PRAGMA table_info(jobs)")}
        if "created" not in columns:
            self.db.execute("ALTER TABLE jobs ADD COLUMN created REAL")
            self.db.execute("UPDATE jobs SET created=updated")
        if "result" not in columns:self.db.execute("ALTER TABLE jobs ADD COLUMN result TEXT")
        if "stage" not in columns:self.db.execute("ALTER TABLE jobs ADD COLUMN stage TEXT")
        # Normalize obsolete failure text only after recorded successful registration;
        # never promote downloaded/unconfigured records or erase failed job history.
        self.db.execute("UPDATE models SET record=json_remove(record,'$.registration_error') WHERE json_extract(record,'$.registered')=1 AND json_extract(record,'$.configured')=1")
        self.db.execute("UPDATE jobs SET error=NULL WHERE state='REGISTERED_NOT_TESTED'")
        self.db.commit()
    @property
    def db(self):
        if not hasattr(self.local,"db"):
            self.local.db=sqlite3.connect(self.path,timeout=30)
            self.local.db.execute("PRAGMA foreign_keys=ON")
        return self.local.db
    def close(self):
        connection=getattr(self.local,"db",None)
        if connection is not None:connection.close();del self.local.db
    def enqueue(self,selection):
        raw=json.dumps(selection,sort_keys=True,separators=(",",":")); key=hashlib.sha256(raw.encode()).hexdigest()
        with self.db: self.db.execute("INSERT OR IGNORE INTO jobs(id,selection,state,updated,created) VALUES(?,?,?,?,?)",(key,raw,"QUEUED",time.time(),time.time()))
        if not selection.get("operation"):
            row=self.db.execute("SELECT state FROM jobs WHERE id=?",(key,)).fetchone()
            installed=self.db.execute("SELECT 1 FROM models WHERE id=?",(model_identity(selection),)).fetchone()
            if row and row[0] in ("REGISTERED_NOT_TESTED","DOWNLOADED_REGISTRATION_FAILED") and not installed:
                with self.db:self.db.execute("UPDATE jobs SET state='QUEUED',progress=0,error=NULL,result=NULL,created=?,updated=? WHERE id=?",(time.time(),time.time(),key))
        return key
    def jobs(self):
        result=[]
        for row in self.db.execute("SELECT id,selection,state,progress,error,updated,created,stage FROM jobs ORDER BY updated DESC"):
            item=dict(zip(("id","selection","state","progress","error","updated","created","stage"),row))
            item["average_bytes_per_second"]=item["progress"]/max(1,item["updated"]-item["created"])
            result.append(item)
        return result
    def transition(self,key,state,progress=0,error=None):
        if state=="DOWNLOADING" and self.cancelled(key):return
        with self.db: self.db.execute("UPDATE jobs SET state=?,progress=?,error=?,stage=NULL,updated=? WHERE id=?",(state,progress,error,time.time(),key))
    def set_stage(self,key,stage):
        # Only a running generation carries a stage; never resurrect a finished or cancelled job.
        with self.db: self.db.execute("UPDATE jobs SET stage=?,updated=? WHERE id=? AND state='GENERATING'",(stage,time.time(),key))
    def cancel(self,key):
        with self.db:self.db.execute("UPDATE jobs SET state=CASE WHEN state IN ('QUEUED','WAITING_NATIVE_IDLE') THEN 'CANCELLED' ELSE 'CANCEL_REQUESTED' END,updated=strftime('%s','now') WHERE id=? AND state IN ('QUEUED','WAITING_NATIVE_IDLE','DOWNLOADING')",(key,))
    def cancelled(self,key):
        row=self.db.execute("SELECT state FROM jobs WHERE id=?",(key,)).fetchone()
        return not row or row[0] in ("CANCEL_REQUESTED","CANCELLED")
    def retry(self,key):
        with self.db:self.db.execute("UPDATE jobs SET state='QUEUED',error=NULL WHERE id=? AND state IN ('FAILED','CANCELLED','DOWNLOADED_REGISTRATION_FAILED')",(key,))
    def save_result(self,key,result):
        with self.db:self.db.execute("UPDATE jobs SET result=? WHERE id=?",(json.dumps(result),key))
    def result(self,key):
        row=self.db.execute("SELECT result FROM jobs WHERE id=?",(key,)).fetchone()
        return json.loads(row[0]) if row and row[0] else None
    def save_overrides(self,identity,value):
        with self.db: self.db.execute("INSERT OR REPLACE INTO overrides VALUES(?,?)",(identity,json.dumps(value)))
    def overrides(self,identity):
        row=self.db.execute("SELECT value FROM overrides WHERE identity=?",(identity,)).fetchone()
        return json.loads(row[0]) if row else {}
    def reclaimable(self,model):
        return list(self.db.execute("SELECT a.id,a.path,a.bytes FROM artifacts a JOIN refs r ON a.id=r.artifact WHERE r.model=? AND NOT EXISTS(SELECT 1 FROM refs x WHERE x.artifact=a.id AND x.model<>?)",(model,model)))
