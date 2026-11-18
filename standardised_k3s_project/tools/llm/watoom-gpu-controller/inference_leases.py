"""Durable request accounting. Uncertain completion blocks GPU changes."""
import json,secrets,urllib.request
from controller import Conflict,Unsafe
def leases(root):
 path=root/"inference-leases.json"
 if not path.exists():return {}
 doc=json.loads(path.read_text())
 if doc.get("version")!=1 or not isinstance(doc.get("leases"),dict):raise Unsafe("Corrupt request accounting")
 return doc["leases"]
def idle(runtime,name):
 try:
  base=runtime.c["urls"][name]
  diffusion=runtime.c.get("backend_types",{}).get(name)=="sdxl"
  headers={}
  if name.startswith("llama-cpp-mm-"):
   from pathlib import Path
   key_file=runtime.c.get("managed_auth_file")
   if key_file!="/data/ai/private/model-manager/backend-key":return False
   headers["Authorization"]="Bearer "+Path(key_file).read_text().strip()
  request=urllib.request.Request(base+("/status" if diffusion else "/slots"),headers=headers)
  with urllib.request.urlopen(request,timeout=10) as res:doc=json.load(res)
  if diffusion:return doc.get("active")==0
  return isinstance(doc,list) and all(slot.get("is_processing") is False for slot in doc)
 except Exception:return False
def handle(runtime,request,pid,atomic):
 runtime.store._check();items=leases(runtime.root);action=request["action"]
 if action=="begin-inference":
  name=request["deployment"]
  runtime.request_model(request,pid)
  start=runtime.identity(pid)
  if start is None:raise Unsafe("Router owner disappeared")
  token=secrets.token_hex(32)
  items[token]={"deployment":name,"pid":pid,"start":start,"completed":False}
  atomic(runtime.root/"inference-leases.json",{"version":1,"leases":items})
  return {"lease":token,"allowed":True}
 if action=="end-inference":
  token=request["lease"];entry=items.get(token)
  if not entry or entry["pid"]!=pid or entry["start"]!=runtime.identity(pid):raise Unsafe("Request owner mismatch")
  entry["completed"]=True
  # A closed HTTP stream alone does not prove the backend has cancelled its work.
  for name in {v["deployment"] for v in items.values()}:
   if idle(runtime,name):
    items={k:v for k,v in items.items() if not (v["deployment"]==name and v["completed"])}
  atomic(runtime.root/"inference-leases.json",{"version":1,"leases":items})
  return {"released":token not in items}
 raise Unsafe("Unknown inference action")

def proven_stopped(runtime,name):
 """No scaling: require pinned zero-replica identity and actual pod absence."""
 try:
  obj=runtime.actuator._get(name) # Includes the production deployment identity check.
  if obj["spec"]["replicas"]!=0 or obj.get("status",{}).get("replicas",0)!=0:return False
  return runtime.actuator.probe(name,"stopped") is True
 except Exception:return False

def prune(runtime,atomic):
 runtime.store._check();items=leases(runtime.root);changed=False
 for name in {entry["deployment"] for entry in items.values()}:
  stopped=any(e["deployment"]==name and e["completed"] for e in items.values()) and proven_stopped(runtime,name)
  backend_idle=False if stopped else idle(runtime,name)
  if not stopped and not backend_idle:continue
  for token,entry in list(items.items()):
   if entry["deployment"]==name and (entry["completed"] or (backend_idle and runtime.identity(entry["pid"])!=entry["start"])):
    del items[token];changed=True
 if changed:atomic(runtime.root/"inference-leases.json",{"version":1,"leases":items})
 return items
