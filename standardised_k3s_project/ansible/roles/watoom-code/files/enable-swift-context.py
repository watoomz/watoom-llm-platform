#!/usr/bin/env python3
import json,os,pathlib,sys,tempfile
context=int(sys.argv[2]) if len(sys.argv)>2 else 100000
if not 4096 <= context <= 131072:raise ValueError("Application context outside supported backend capacity")
p=pathlib.Path(sys.argv[1]);before=p.read_bytes();data=json.loads(before)
limit=data["providers"]["watoom"]["models"]["swift-qwen38-coder"]["limit"]
if limit.get("context")==context:print("UNCHANGED");sys.exit(0)
limit["context"]=context
st=p.stat();fd,tmp=tempfile.mkstemp(prefix=".swift-context-",dir=p.parent)
try:
 with os.fdopen(fd,"w") as f:
  os.fchmod(f.fileno(),st.st_mode&0o777);os.fchown(f.fileno(),st.st_uid,st.st_gid)
  json.dump(data,f,indent=2);f.write("\n");f.flush();os.fsync(f.fileno())
 assert p.read_bytes()==before,"Concurrent configuration edit"
 os.replace(tmp,p)
finally:
 if os.path.exists(tmp):os.unlink(tmp)
print("CHANGED")
