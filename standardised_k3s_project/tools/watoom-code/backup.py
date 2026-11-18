#!/usr/bin/env python3
"""Consistent SQLite backups and configuration snapshots; never downgrade data.

Each run writes <dest>/<UTC stamp>/ with gzip'd online SQLite copies (application,
catalog, home/*.db), config and AgentMemory archives, the Deployment list and a
manifest (integrity_check, row counts, sha256). Older runs are pruned only after a
verified run, and a node-exporter textfile metric records the last success.
AgentMemory is a live non-SQLite store: its archive is best-effort file-consistent.
"""
import argparse,datetime,gzip,hashlib,json,pathlib,re,shutil,sqlite3,subprocess,tarfile,os
STAMP=re.compile(r'^\d{8}T\d{6}Z$')
def sha256(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(1<<20),b''):h.update(block)
 return h.hexdigest()
def copy_sqlite(source,target):
 target.parent.mkdir(parents=True,exist_ok=True)
 with sqlite3.connect('file:'+str(source)+'?mode=ro',uri=True) as src,sqlite3.connect(target) as dst:src.backup(dst)
 with sqlite3.connect(target) as db:
  db.execute('pragma journal_mode=delete')  # copy inherits WAL; leave no -wal/-shm beside the .gz
  check=db.execute('pragma integrity_check').fetchone()[0]
  tables=[t for (t,) in db.execute("select name from sqlite_master where type='table' and name in ('session_v2','session_message','project')")]
  counts={t:db.execute('select count(*) from "'+t+'"').fetchone()[0] for t in tables}
 if check!='ok':raise RuntimeError(f'{source}: integrity_check {check}')
 with open(target,'rb') as f,gzip.open(str(target)+'.gz','wb',compresslevel=6) as g:shutil.copyfileobj(f,g)
 target.unlink()
 return {'integrity':check,'rows':counts}
def write_metric(directory,stamp,size):
 # node-exporter runs as nobody: every level this creates must be traversable despite umask 077.
 for level in reversed([d for d in [directory,*directory.parents] if not d.exists()]):level.mkdir();level.chmod(0o755)
 tmp=directory/'.watoom-backup.prom.tmp'
 tmp.write_text('# HELP watoom_backup_last_success_timestamp_seconds Last verified WatooM-Code backup.\n'
  '# TYPE watoom_backup_last_success_timestamp_seconds gauge\n'
  f'watoom_backup_last_success_timestamp_seconds{{target="watoom-code"}} {stamp}\n'
  '# HELP watoom_backup_size_bytes Size of the last verified WatooM-Code backup.\n'
  '# TYPE watoom_backup_size_bytes gauge\n'
  f'watoom_backup_size_bytes{{target="watoom-code"}} {size}\n')
 tmp.chmod(0o644);tmp.replace(directory/'watoom-backup.prom')
def prune(dest,keep):
 runs=sorted(d for d in dest.iterdir() if d.is_dir() and STAMP.match(d.name) and (d/'manifest.json').is_file())
 for old in runs[:-keep]:shutil.rmtree(old)
def main():
 p=argparse.ArgumentParser();p.add_argument('--root',default='/data/ai/watoom-code');p.add_argument('--namespace',default='watoom-code')
 p.add_argument('--dest',default='/data/backups/watoom-code');p.add_argument('--keep',type=int,default=14);p.add_argument('--textfile-dir',default='/var/lib/node_exporter/textfile');a=p.parse_args()
 root=pathlib.Path(a.root).resolve()
 if root!=pathlib.Path('/data/ai/watoom-code'):raise SystemExit('Only the verified staging root is supported')
 if a.keep<1:raise SystemExit('--keep must be at least 1')
 os.umask(0o077);dest=pathlib.Path(a.dest);dest.mkdir(parents=True,exist_ok=True,mode=0o700)
 now=datetime.datetime.now(datetime.timezone.utc);out=dest/now.strftime('%Y%m%dT%H%M%SZ');out.mkdir()
 manifest={'created':now.isoformat(),'root':str(root),'sqlite':{},'archives':{},'files':{}}
 for source in [root/'application.sqlite',root/'catalog.sqlite',*(root/'home').rglob('*.db')]:
  if not source.is_file():continue
  manifest['sqlite'][str(source.relative_to(root))]=copy_sqlite(source,out/source.relative_to(root))
 if 'application.sqlite' not in manifest['sqlite']:raise RuntimeError('application.sqlite missing; refusing to report success')
 for name,path in [('config',root/'config'),('memory',root/'memory')]:
  if not path.is_dir():continue
  with tarfile.open(out/(name+'.tar.gz'),'w:gz') as tar:tar.add(path,arcname=name)
  manifest['archives'][name]='best-effort live file copy' if name=='memory' else 'snapshot'
 (out/'deployments.json').write_bytes(subprocess.check_output(['kubectl','-n',a.namespace,'get','deployments','-o','json']))
 for f in sorted(x for x in out.rglob('*') if x.is_file()):manifest['files'][str(f.relative_to(out))]=sha256(f)
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
 size=sum(f.stat().st_size for f in out.rglob('*') if f.is_file())
 prune(dest,a.keep)
 write_metric(pathlib.Path(a.textfile_dir),int(now.timestamp()),size)
 print(json.dumps({'backup':str(out),'bytes':size,'sqlite':manifest['sqlite']}))
if __name__=='__main__':main()
