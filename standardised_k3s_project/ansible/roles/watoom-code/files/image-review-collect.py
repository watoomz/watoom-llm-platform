#!/usr/bin/env python3
"""Copy stable project capture images into the owner-requested common review tree."""
from pathlib import Path
import os,json,hashlib,shutil,tempfile,fcntl,stat
ROOT=Path('/data/ai/projects/images/review')
SOURCES=[Path('/data/ai/projects'),Path('/data/ai/watoom-code/generated')]
SKIP={'.git','.godot','node_modules','__pycache__','.venv','toolchain','toolchains','vendor'}
KINDS={'renders','render','captures','screenshots','previews','preview','validation','engine-validation'}
EXT={'.png','.jpg','.jpeg','.webp','.gif'}

def open_dir_nofollow(parent_fd,name,create=False):
 """Open `name` strictly inside the directory held open at `parent_fd`, by file descriptor, never by
 re-resolving a path string. O_NOFOLLOW makes the kernel refuse a symlink at this exact segment, and
 operating by dir_fd from here on means a later swap of `name` cannot redirect an already-open fd: every
 write below still targets the inode that was open and verified, not whatever `name` currently points to.
 This is what actually closes the gap a check-then-act Path.is_symlink() check cannot: that check and the
 later open/rename are two separate syscalls on a path string, and the owner of the parent directory (the
 review root is 1001-owned, mode 0775, so the project/model that writes captures also owns it) can swap a
 real directory for a symlink in the window between them."""
 flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW
 try:
  return os.open(name,flags,dir_fd=parent_fd)
 except FileNotFoundError:
  if not create:raise
  try:
   os.mkdir(name,0o755,dir_fd=parent_fd)
  except FileExistsError:
   pass  # lost a create race with another run of this same script; the entry exists now, open it below
  return os.open(name,flags,dir_fd=parent_fd)
 except NotADirectoryError:
  raise RuntimeError('Review target %r is not a real directory (symlink or file planted where a directory was expected)'%(name,))

def mkdirs_nofollow(parts):
 """Walk ROOT's already-real path down through `parts`, refusing to follow or silently create through any
 symlink, and return the fd of the leaf directory (caller must os.close it)."""
 fd=os.open(str(ROOT),os.O_RDONLY|os.O_DIRECTORY)
 try:
  for part in parts:
   nxt=open_dir_nofollow(fd,part,create=True)
   os.close(fd)
   fd=nxt
  return fd
 except Exception:
  os.close(fd)
  raise

def run():
 ROOT.mkdir(parents=True,exist_ok=True)
 if ROOT.is_symlink():raise RuntimeError('Review root must be a real directory')
 copied=0
 for source in SOURCES:
  if not source.exists():continue
  for directory,dirs,files in os.walk(source,followlinks=False):
   here=Path(directory)
   dirs[:]=[d for d in dirs if d not in SKIP and not (here/d).is_symlink() and not (here/d).resolve().is_relative_to(ROOT.parent)]
   if source.name!='generated' and not ({x.lower() for x in here.parts}&KINDS):continue
   for name in files:
    p=here/name
    if p.suffix.lower() not in EXT or p.is_symlink():continue
    st=p.stat()
    if not st.st_size:continue
    # Projects may still be writing captures; only publish an unchanged read.
    hasher=hashlib.sha256()
    with p.open('rb') as stream:
     for chunk in iter(lambda:stream.read(1048576),b''):hasher.update(chunk)
    after=p.stat()
    if (st.st_size,st.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):continue
    digest=hasher.hexdigest()
    relative=p.relative_to(source)
    leaf_name=p.stem+'--'+digest[:16]+p.suffix.lower()
    dir_fd=mkdirs_nofollow(('projects',*relative.parent.parts))
    try:
     try:
      target_stat=os.stat(leaf_name,dir_fd=dir_fd,follow_symlinks=False)
      if stat.S_ISLNK(target_stat.st_mode):raise RuntimeError('Review target symlink rejected')
      continue  # already published (exists and is a real file)
     except FileNotFoundError:
      pass
     fd,tmp=tempfile.mkstemp(dir='/proc/self/fd/%d'%dir_fd,prefix='.capture-')
     try:
      with os.fdopen(fd,'wb') as f, p.open('rb') as source_file:
       shutil.copyfileobj(source_file,f,1048576);f.flush();os.fsync(f.fileno());os.fchmod(f.fileno(),0o644)
      final=p.stat()
      with open(tmp,'rb') as verify:
       if hashlib.file_digest(verify,'sha256').hexdigest()!=digest or (final.st_size,final.st_mtime_ns)!=(st.st_size,st.st_mtime_ns):continue
      os.rename(os.path.basename(tmp),leaf_name,src_dir_fd=dir_fd,dst_dir_fd=dir_fd)
     finally:
      if os.path.exists(tmp):os.unlink(tmp)
     meta={'source_path':str(p),'sha256':digest,'bytes':st.st_size,'source_mtime_ns':st.st_mtime_ns,'capture_kind':'project_capture_copy'}
     with open('/proc/self/fd/%d/%s.json'%(dir_fd,leaf_name),'w') as mf:mf.write(json.dumps(meta,indent=2)+'\n')
     copied+=1
    finally:
     os.close(dir_fd)
 print(json.dumps({'copied':copied,'review_root':str(ROOT)}))
if __name__=='__main__':
 lock=Path('/data/ai/helper-scripts/state/image-review-collector.lock');lock.parent.mkdir(parents=True,exist_ok=True)
 with lock.open('a') as f:
  try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:raise SystemExit(0)
  run()
