#!/usr/bin/env python3
import json,os,pathlib,sys,tempfile,re
p=pathlib.Path(sys.argv[1]);before=p.read_bytes();data=json.loads(before)
target=sys.argv[2] if len(sys.argv)>2 else "/config/watoom-tools/coordinator-guard"
pattern=r"/config/watoom-tools/coordinator-guard(?:-[a-f0-9]{64})?"
if not re.fullmatch(pattern,target):raise SystemExit("Invalid maintained guard package path")
data.setdefault("experimental",{})["subagent_depth"]=2
# Exact-image guard proof must see the original bytes, not a post-tool JPEG transcode.
# Existing dimensions/base64 limits remain enforced; preserve all other media settings.
data.setdefault("media",{}).setdefault("image",{})["auto_resize"]=False
plugins=data.setdefault("plugins",[]);updated=[];found=False;options={}
for value in plugins:
 package=value if isinstance(value,str) else value.get("package")
 if isinstance(package,str) and re.fullmatch(pattern,package):
  if isinstance(value,dict):options.update(value.get("options",{}))
  if not found:updated.append(None);found=True
 else:updated.append(value)
verified=set(options.get("verifiedVisionModels",[]));verified.update(["watoom/swift-qwen38-coder", "watoom/qwen38-uncensored-mtp", "watoom/tiel-coder-35b-a3b-mtp"])
options["verifiedVisionModels"]=sorted(verified)
entry={"package":target,"options":options}
if found:updated[updated.index(None)]=entry
else:updated.append(entry)
data["plugins"]=updated
# Qualified by paired opposite-colour image probes; backend uses a read-only projector.
models=data.setdefault("providers",{}).setdefault("watoom",{}).setdefault("models",{})
model=models.setdefault("qwen38-uncensored-mtp",{"modelID":"qwen38-uncensored-mtp","name":"Qwen3.8 Uncensored MTP","limit":{"context":100000,"output":4096}})
model["capabilities"]={**model.get("capabilities",{}),"tools":True,"input":["text","image"],"output":["text"]}
if json.loads(before)==data:print("UNCHANGED");sys.exit(0)
st=p.stat();fd,tmp=tempfile.mkstemp(prefix=".coordination-config-",dir=p.parent)
try:
 with os.fdopen(fd,"w") as f:
  os.fchmod(f.fileno(),st.st_mode&0o777);os.fchown(f.fileno(),st.st_uid,st.st_gid)
  json.dump(data,f,indent=2);f.write("\n");f.flush();os.fsync(f.fileno())
 assert p.read_bytes()==before,"Concurrent configuration edit"
 os.replace(tmp,p)
finally:
 if os.path.exists(tmp):os.unlink(tmp)
print("CHANGED")
