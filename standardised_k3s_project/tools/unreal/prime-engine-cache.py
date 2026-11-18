#!/usr/bin/env python3
"""Prime one isolated file DDC from accepted engine cache entries, without replacing live entries."""
import argparse,pathlib,os,re,time,shutil,json,tempfile
ap=argparse.ArgumentParser();ap.add_argument("--source",required=True,type=pathlib.Path);ap.add_argument("--target",required=True,type=pathlib.Path);ap.add_argument("--receipt",required=True,type=pathlib.Path);a=ap.parse_args()
source=a.source.resolve(strict=True);target=a.target.resolve(strict=True)
if source==target or not source.is_relative_to("/data/ai/builds") or not target.is_relative_to("/data/ai/builds"):
 raise ValueError("Distinct isolated build cache roots required")
started=time.monotonic();used=0;copied=0;skipped=0;stopped=None
for tree in ("Content","Buckets"):
 for parent,dirs,files in os.walk(source/tree,followlinks=False):
  pattern="[A-Za-z][A-Za-z0-9_]{0,63}" if tree=="Buckets" and pathlib.Path(parent)==source/tree else "[a-f0-9]{2}"
  dirs[:]=[name for name in dirs if re.fullmatch(pattern,name) and not (pathlib.Path(parent)/name).is_symlink()]
  for name in files:
   if not re.fullmatch("[a-f0-9]{36}\\.udd",name):continue
   incoming=pathlib.Path(parent)/name
   if incoming.is_symlink() or not incoming.is_file():continue
   size=incoming.stat().st_size
   if time.monotonic()-started>120 or copied+skipped>=20000 or used+size>512*1024**2:
    stopped="bounded_cache_checkpoint";break
   destination=target/incoming.relative_to(source)
   if not destination.parent.resolve().is_relative_to(target):raise ValueError("Cache target escapes isolated root")
   if destination.exists():skipped+=1;continue
   missing=[];directory=destination.parent
   while not directory.exists():missing.append(directory);directory=directory.parent
   if directory.is_symlink():raise ValueError("Target cache parent symlink")
   for directory in reversed(missing):
    directory.mkdir(mode=0o755);os.chown(directory,1009,1009)
   fd,temporary=tempfile.mkstemp(prefix=".prime-",dir=destination.parent)
   try:
    before=incoming.stat()
    with os.fdopen(fd,"wb") as output,incoming.open("rb") as read:
     os.fchown(output.fileno(),1009,1009);os.fchmod(output.fileno(),0o644)
     shutil.copyfileobj(read,output,1024*1024)
    after=incoming.stat()
    if (after.st_size,after.st_mtime_ns)!=(before.st_size,before.st_mtime_ns):raise RuntimeError("Accepted cache entry changed while reading")
    try:os.link(temporary,destination,follow_symlinks=False);copied+=1;used+=size
    except FileExistsError:skipped+=1
   finally:os.unlink(temporary)
  if stopped:break
 if stopped:break
a.receipt.write_text(json.dumps({"status":"CHECKPOINT" if stopped else "PASS","reason":stopped,"source":str(source),"target":str(target),"copied":copied,"skipped":skipped,"bytes":used,"seconds":round(time.monotonic()-started,2),"source_modified":False,"existing_target_entries_overwritten":False},indent=2))
print(a.receipt.read_text())
