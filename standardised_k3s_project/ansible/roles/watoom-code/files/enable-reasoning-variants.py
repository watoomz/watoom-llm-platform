#!/usr/bin/env python3
"""Set the GUI reasoning variants on the listed watoom models in place; other settings are kept."""
import json,os,pathlib,sys,tempfile
spec=json.loads(sys.argv[2])
models,variants=spec["models"],spec["variants"]
if not variants or any(set(v)-{"id","body","settings","headers"} or not isinstance(v.get("id"),str) for v in variants):raise ValueError("Invalid variant definition")
p=pathlib.Path(sys.argv[1]);before=p.read_bytes();data=json.loads(before)
catalog=data["providers"]["watoom"]["models"]
changed=False
for name in models:
 model=catalog.get(name)
 if model is None:continue  # not configured on this install
 if model.get("variants")!=variants:model["variants"]=variants;changed=True
if not changed:print("UNCHANGED");sys.exit(0)
st=p.stat();fd,tmp=tempfile.mkstemp(prefix=".reasoning-variants-",dir=p.parent)
try:
 with os.fdopen(fd,"w") as f:
  os.fchmod(f.fileno(),st.st_mode&0o777);os.fchown(f.fileno(),st.st_uid,st.st_gid)
  json.dump(data,f,indent=2);f.write("\n");f.flush();os.fsync(f.fileno())
 assert p.read_bytes()==before,"Concurrent configuration edit"
 os.replace(tmp,p)
finally:
 if os.path.exists(tmp):os.unlink(tmp)
print("CHANGED")
