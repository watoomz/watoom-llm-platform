import os,sqlite3,sys
from pathlib import Path
root=Path(sys.argv[1]); path=root/'catalog.sqlite'
if path.exists(): raise SystemExit(0)
with sqlite3.connect(path) as db:
 for sql in ["CREATE TABLE skills(id TEXT PRIMARY KEY,repo TEXT,path TEXT,name TEXT,description TEXT,sha256 TEXT,license TEXT,risk TEXT,validation TEXT)","CREATE TABLE sources(repo TEXT,commit_sha TEXT)","CREATE TABLE approvals(skill_id TEXT PRIMARY KEY,approved_sha TEXT,note TEXT,at TEXT)","CREATE TABLE approval_context(skill_id TEXT PRIMARY KEY,commit_sha TEXT,bundle_sha TEXT)","CREATE VIRTUAL TABLE skills_fts USING fts5(id UNINDEXED,name,description)"]: db.execute(sql)
os.chown(path,1001,1001);os.chmod(path,0o600)
