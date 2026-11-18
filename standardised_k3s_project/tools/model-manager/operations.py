"""Serialized managed artifact installation/removal, preserving shared references."""
import contextlib,hashlib,json,os,time,secrets,shutil
from pathlib import Path
from file_lock import lock_file
from download import fetch,safe_path,digest
from store import model_identity
from settings import validate
from gguf_header import context_limit
class Blocked(ValueError):pass
class Operations:
 def __init__(self,store,root,broker,downloader=fetch,metadata_reader=context_limit):
  self.store=store;self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
  self.broker=broker;self.downloader=downloader;self.metadata_reader=metadata_reader
 @contextlib.contextmanager
 def exclusive(self):
  with (Path(self.store.path).parent/"operations.lock").open("a") as f:
   lock_file(f);yield
 def install(self,selection,progress=lambda n:None,cancel=lambda:False):
  with self.exclusive():
   if cancel():raise Blocked("Cancelled; no files changed")
   identity=model_identity(selection)
   existing=self.store.db.execute("SELECT record FROM models WHERE id=?",(identity,)).fetchone()
   if existing:
    record=json.loads(existing[0])
    if record.get("registered"):
     record.pop("registration_error",None)
     with self.store.db:self.store.db.execute("UPDATE models SET record=? WHERE id=?",(json.dumps(record),identity))
     return record
    outcome=self.broker("register",record);record.update(outcome)
    if record.get("registered"):record.pop("registration_error",None)
    with self.store.db:self.store.db.execute("UPDATE models SET record=? WHERE id=?",(json.dumps(record),identity))
    return record
   kind=selection["kind"];validate(selection["settings"],kind,max_context=selection.get("max_context"))
   if kind in ("lora","diffusion-checkpoint"):
    base=selection.get("base_install")
    row=self.store.db.execute("SELECT record FROM models WHERE id=?",(base,)).fetchone()
    if not row:raise Blocked("An installed compatible base selection is required")
    base_record=json.loads(row[0])
    if base_record["kind"]!="diffusion-pipeline" or (selection.get("base_repository") and base_record["repository"]!=selection.get("base_repository")):raise Blocked("Base identity does not match adapter")
   else:base_record=None
   required=sum(item["size"] for item in selection["files"])
   if shutil.disk_usage(self.root).free<required+3*1024**3:raise Blocked("Selection plus disk reserve exceeds available storage")
   artifacts=[];total=0
   category={"gguf":"gguf","lora":"loras","diffusion-checkpoint":"diffusion","diffusion-pipeline":"diffusion"}[kind]
   target=self.root/category/"model-manager"/identity
   for item in selection["files"]:
    aid=hashlib.sha256((selection["repository"]+"@"+selection["revision"]+"/"+item["path"]).encode()).hexdigest()
    prior=self.store.db.execute("SELECT path,bytes,digest FROM artifacts WHERE id=?",(aid,)).fetchone()
    if prior:
     path=Path(prior[0])
     if not path.exists() or path.is_symlink() or path.stat().st_size!=prior[1] or digest(path)!=prior[2]:raise Blocked("Shared artifact missing or changed; retained for investigation")
     result={"path":prior[0],"bytes":prior[1],"sha256":prior[2]}
     if kind=="diffusion-pipeline":
      destination=safe_path(target,item["path"]);destination.parent.mkdir(parents=True,exist_ok=True)
      if destination.exists():
       if destination.stat().st_size!=prior[1] or digest(destination)!=prior[2]:raise Blocked("Dependency link changed")
      else:os.link(path,destination,follow_symlinks=False)
      if destination!=path:
       artifacts.append((aid,result))
       aid=hashlib.sha256((aid+"@"+str(destination)).encode()).hexdigest()
       result={**result,"path":str(destination)}
    else:
     result=self.downloader(target,selection["repository"],selection["revision"],item,progress=lambda n:progress(total+n),cancel=cancel)
    total+=result["bytes"];progress(total)
    artifacts.append((aid,result))
   record={"id":identity,"revision":selection["revision"],"repository":selection["repository"],"kind":kind,"settings":selection["settings"],"artifacts":[a for a,_ in artifacts],"downloaded":True,"configured":False,"registered":False,"tested":False,"protected":False,"installation_epoch":secrets.token_hex(16),"max_context":selection.get("max_context")}
   if kind=="diffusion-pipeline":record["base_path"]=str(target)
   if base_record:
    record["dependencies"]=[base_record["id"]];record["artifacts"]+=base_record["artifacts"];record["base_path"]=base_record["base_path"]
   with self.store.db:
    for aid,item in artifacts:
     self.store.db.execute("INSERT OR IGNORE INTO artifacts VALUES(?,?,?,?)",(aid,item["path"],item["bytes"],item["sha256"]))
    self.store.db.execute("INSERT INTO models VALUES(?,?,?)",(identity,record["revision"],json.dumps(record)))
    for aid in record["artifacts"]:self.store.db.execute("INSERT INTO refs VALUES(?,?)",(identity,aid))
   # Real registration broker; failure leaves truthful downloaded-only recovery record.
   try:
    if kind=="gguf":
     detected=self.metadata_reader(artifacts[0][1]["path"])
     if detected:
      record["max_context"]=min(record.get("max_context") or detected,detected)
      record["context_limit_source"]="GGUF header"
      validate(record["settings"],kind,max_context=record["max_context"])
      with self.store.db:self.store.db.execute("UPDATE models SET record=? WHERE id=?",(json.dumps(record),identity))
    outcome=self.broker("register",record)
    record.update(outcome)
    if outcome.get("registered") is not True:raise Blocked("Registration not verified")
   except Exception as e:
    record["registration_error"]=type(e).__name__+": "+str(e)[:200]
   with self.store.db:self.store.db.execute("UPDATE models SET record=? WHERE id=?",(json.dumps(record),identity))
   return record
 def generate(self,identity,revision,prompt,settings=None,negative_prompt=None,progress=None):
  with self.exclusive():
   row=self.store.db.execute("SELECT record FROM models WHERE id=?",(identity,)).fetchone()
   if not row:raise Blocked("Unknown installation")
   record=json.loads(row[0])
   if record["revision"]!=revision or not record.get("registered"):raise Blocked("Stale or unregistered installation")
   request={"prompt":prompt,**({"settings":settings} if settings is not None else {})}
   if negative_prompt is not None:
    from settings import validate_negative_prompt
    request["negative_prompt"]=validate_negative_prompt(negative_prompt)
   result=self.broker("generate",record,request,progress=progress) if progress else self.broker("generate",record,request)
   if not result.get("tested"):raise Blocked("Generation not verified")
   record["tested"]=True;record.pop("registration_error",None)
   with self.store.db:self.store.db.execute("UPDATE models SET record=? WHERE id=?",(json.dumps(record),identity))
   return result
 def plan_remove(self,identity,revision):
  row=self.store.db.execute("SELECT record FROM models WHERE id=?",(identity,)).fetchone()
  if not row:raise Blocked("Unknown installation")
  record=json.loads(row[0])
  if record["revision"]!=revision:raise Blocked("Stale revision")
  if record.get("protected"):raise Blocked("Recovery installation is protected")
  for row in self.store.db.execute("SELECT record FROM models WHERE id<>?",(identity,)):
   if identity in json.loads(row[0]).get("dependencies",[]):raise Blocked("Another installation depends on this model")
  artifacts=self.store.reclaimable(identity)
  plan={"id":identity,"revision":revision,"resources":record.get("resources",[]),"paths":[x[1] for x in artifacts],"bytes":sum(x[2] for x in artifacts),"keep_files_default":True,"installation_epoch":record.get("installation_epoch"),"immediate_reclaimable_bytes":0,"deletion_policy":"Quarantine with verified recovery receipt; no automatic purge"}
  plan["confirmation"]=hashlib.sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest()
  return plan
 def remove(self,identity,revision,delete=False,confirmation=None,job_id=None):
  with self.exclusive():
   destination=Path(self.store.path).parent/"removals";destination.mkdir(exist_ok=True)
   receipt_path=destination/((job_id or identity)+".json")
   if receipt_path.exists():
    previous=json.loads(receipt_path.read_text())
    if previous["plan"]["confirmation"]!=confirmation:raise Blocked("Removal receipt identity mismatch")
    with self.store.db:
     self.store.db.execute("DELETE FROM refs WHERE model=?",(identity,))
     self.store.db.execute("DELETE FROM models WHERE id=?",(identity,))
    return previous
   plan=self.plan_remove(identity,revision)
   if confirmation!=plan["confirmation"]:raise Blocked("Fresh identity/path-scoped removal confirmation required")
   row=self.store.db.execute("SELECT record FROM models WHERE id=?",(identity,)).fetchone();record=json.loads(row[0])
   if record.get("registered"):
    result=self.broker("retire",record)
    if result.get("retired") is not True:raise Blocked("Retirement not verified")
   # Move only immutable unreferenced owned files to quarantine; no reclaimed-byte claim.
   record["registered"]=False;record["removal_phase"]="retired-files-pending"
   with self.store.db:self.store.db.execute("UPDATE models SET record=? WHERE id=?",(json.dumps(record),identity))
   moved=[]
   if delete:
    quarantine=self.root/"quarantine"/"model-manager"/identity;quarantine.mkdir(parents=True,exist_ok=True)
    for name in plan["paths"]:
     source=Path(name)
     if not source.is_relative_to(self.root) or source.is_symlink():raise Blocked("Artifact escapes managed storage")
     relative=source.relative_to(self.root);safe_path(self.root,str(relative))
     known=self.store.db.execute("SELECT digest,bytes FROM artifacts WHERE path=?",(str(source),)).fetchone()
     if source.exists() and (not known or source.stat().st_size!=known[1] or digest(source)!=known[0]):raise Blocked("Artifact changed since installation; retained")
     target=safe_path(quarantine,str(relative));target.parent.mkdir(parents=True,exist_ok=True)
     if source.exists():os.rename(source,target)
     if target.exists():
      if not known or target.stat().st_size!=known[1] or digest(target)!=known[0]:raise Blocked("Quarantine receipt integrity mismatch")
      moved.append({"original":str(source),"quarantine":str(target)})
   receipt={"retired":True,"files":"quarantined" if delete else "retained","actual_reclaimed_bytes":0,"moved":moved,"at":time.time(),"plan":plan}
   temporary=receipt_path.with_suffix(".tmp")
   with temporary.open("w") as output:
    json.dump(receipt,output,indent=2);output.flush();os.fsync(output.fileno())
   os.replace(temporary,receipt_path)
   with self.store.db:
    self.store.db.execute("DELETE FROM refs WHERE model=?",(identity,))
    self.store.db.execute("DELETE FROM models WHERE id=?",(identity,))
    if delete:
     for aid in record["artifacts"]:
      self.store.db.execute("DELETE FROM artifacts WHERE id=? AND NOT EXISTS(SELECT 1 FROM refs WHERE artifact=?)",(aid,aid))
   return receipt
