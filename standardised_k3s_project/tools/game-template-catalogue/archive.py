"""Safe ZIP extraction shared by the Godot and Unreal installers; never executes archive content."""
import hashlib,re,stat,zipfile
from pathlib import Path,PurePosixPath

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def extract(archive,stage):
 """Extract into an existing empty stage; reject unsafe, linked or colliding paths. Returns the file manifest."""
 manifest=[]
 with zipfile.ZipFile(archive) as z:
  items=z.infolist();assert len(items)<100000 and sum(i.file_size for i in items)<20*1024**3
  seen=set()
  for i in items:
   name=i.filename.replace('\\','/');path=PurePosixPath(name)
   if path.is_absolute() or '..' in path.parts or re.match(r'^[A-Za-z]:',name) or not path.parts or '\x00' in name:raise ValueError('Unsafe archive path')
   if stat.S_ISLNK(i.external_attr>>16):raise ValueError('Archive symlink not permitted')
   key=str(path).casefold()
   if key in seen and not i.is_dir():raise ValueError('Duplicate/case-colliding archive path')
   seen.add(key)
   p=stage/str(path);assert p.resolve().is_relative_to(stage.resolve())
   if i.is_dir():p.mkdir(parents=True,exist_ok=True);continue
   p.parent.mkdir(parents=True,exist_ok=True)
   h=hashlib.sha256();size=0
   with z.open(i) as inp,p.open('xb') as out:
    for b in iter(lambda:inp.read(1024*1024),b''):out.write(b);h.update(b);size+=len(b)
   assert size==i.file_size
   p.chmod(0o644);manifest.append({'path':str(path),'bytes':size,'sha256':h.hexdigest()})
 return manifest
