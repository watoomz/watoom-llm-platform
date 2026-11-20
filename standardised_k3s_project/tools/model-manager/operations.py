"""Serialized managed artifact installation/removal, preserving shared references."""
import contextlib,hashlib,json,os,time,secrets,shutil
from pathlib import Path
from file_lock import lock_file
from download import fetch,safe_path,digest
from store import model_identity
from settings import validate
from gguf_header import inspect as gguf_inspect
LLM_KINDS=("gguf","gguf-lora")
class Blocked(ValueError):pass
class Operations:
 def __init__(self,store,root,broker,downloader=fetch,metadata_reader=gguf_inspect):
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
   kind=selection["kind"]
   # MTP is provisionally allowed for a published MTP file; the downloaded header decides before registration.
   validate(selection["settings"],kind,capabilities={"mtp":True,"vision":True},max_context=selection.get("max_context"))
   if kind in ("lora","diffusion-checkpoint","gguf-lora"):
    base=selection.get("base_install")
    row=self.store.db.execute("SELECT record FROM models WHERE id=?",(base,)).fetchone()
    if not row:raise Blocked("An installed compatible base selection is required")
    base_record=json.loads(row[0])
    expected="gguf" if kind=="gguf-lora" else "diffusion-pipeline"
    if base_record["kind"]!=expected or (selection.get("base_repository") and base_record["repository"]!=selection.get("base_repository")):raise Blocked("Base identity does not match adapter")
   else:base_record=None
   required=sum(item["size"] for item in selection["files"])
   artifacts=[];total=0
   category={"gguf":"gguf","gguf-lora":"loras","lora":"loras","diffusion-checkpoint":"diffusion","diffusion-pipeline":"diffusion"}[kind]
   target=self.root/category/"model-manager"/identity
   # self.root itself can be a small container-local overlay with only the per-category
   # subdirectory bind-mounted onto the real storage; check free space where files actually
   # land, not at self.root, or a real large volume gets wrongly reported as full.
   target.parent.mkdir(parents=True,exist_ok=True)
   if shutil.disk_usage(target.parent).free<required+3*1024**3:raise Blocked("Selection plus disk reserve exceeds available storage")
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
   record={"id":identity,"revision":selection["revision"],"repository":selection["repository"],"kind":kind,"settings":selection["settings"],"artifacts":[a for a,_ in artifacts],"downloaded":True,"configured":False,"registered":False,"tested":False,"protected":False,"installation_epoch":secrets.token_hex(16),"max_context":selection.get("max_context"),"description":selection.get("description")}
   if kind=="diffusion-pipeline":record["base_path"]=str(target)
   projector_name=selection["settings"].get("projector")
   projector=next(((aid,item) for aid,item in artifacts if projector_name and Path(item["path"]).name==Path(projector_name).name),None)
   if projector_name and not projector:raise Blocked("Projector was not downloaded")
   if projector:record["artifacts"].remove(projector[0])
   if base_record:
    record["dependencies"]=[base_record["id"]];record["artifacts"]+=base_record["artifacts"]
    if "base_path" in base_record:record["base_path"]=base_record["base_path"]
   # The projector is always the last artifact, so the model (and a LoRA's base) keep their positions.
   if projector:record["artifacts"].append(projector[0])
   with self.store.db:
    for aid,item in artifacts:
     self.store.db.execute("INSERT OR IGNORE INTO artifacts VALUES(?,?,?,?)",(aid,item["path"],item["bytes"],item["sha256"]))
    self.store.db.execute("INSERT INTO models VALUES(?,?,?)",(identity,record["revision"],json.dumps(record)))
    for aid in record["artifacts"]:self.store.db.execute("INSERT INTO refs VALUES(?,?)",(identity,aid))
   # Real registration broker; failure leaves truthful downloaded-only recovery record.
   try:
    if kind in LLM_KINDS:
     # For a LoRA the served model is the base: its header gives the context limit and any MTP head.
     model_path=artifacts[0][1]["path"] if kind=="gguf" else self.base_model_path(base_record)
     header=self.metadata_reader(model_path)
     if isinstance(header,int) or header is None:header={"context_length":header,"nextn_predict_layers":0}
     detected=header.get("context_length")
     if detected:
      record["max_context"]=min(record.get("max_context") or detected,detected)
      record["context_limit_source"]="GGUF header"
     record["capabilities"]={"mtp":(header.get("nextn_predict_layers") or 0)>0,"vision":False}
     if projector:
      vision=self.metadata_reader(projector[1]["path"])
      if not isinstance(vision,dict) or vision.get("type")!="mmproj" or not vision.get("vision_encoder") or vision.get("projection_dim")!=header.get("embedding_length"):raise Blocked("Projector does not match the model (mmproj vision encoder, projection_dim == embedding_length)")
      record["capabilities"]["vision"]=True
     # Smaller models get more context: context_auto raises (never lowers) the chosen context to what fits on the GPU.
     from settings import fit_context
     weights=sum(item["bytes"] for aid,item in artifacts if not (projector and aid==projector[0]))+(sum(row[0] for row in self.store.db.execute("SELECT bytes FROM artifacts WHERE id IN (%s)"%",".join("?"*len(base_record["artifacts"])),base_record["artifacts"])) if base_record else 0)
     settings=record["settings"]
     fit=fit_context(header,weights,settings.get("cache_k","q4_0"),settings.get("cache_v","q4_0")) if isinstance(header,dict) and header.get("block_count") else None
     if fit:
      record["context_fit"]=fit
      if settings.get("context_auto") and fit>settings.get("context",0):settings["context"]=min(fit,record.get("max_context") or fit)
     # A projector on the GPU counts against the cap; when it does not fit beside the context it encodes on the CPU.
     if projector and settings.get("projector_gpu"):
      from settings import fits_on_gpu
      if fits_on_gpu(header,weights+projector[1]["bytes"],settings.get("context",0),settings.get("cache_k","q4_0"),settings.get("cache_v","q4_0")) is False:
       settings["projector_gpu"]=False;record["projector_note"]="Projector moved to the CPU: it does not fit beside the context in 18 GiB"
     if kind=="gguf-lora":
      adapter=self.metadata_reader(artifacts[0][1]["path"])
      if isinstance(adapter,dict) and (adapter.get("type")!="adapter" or adapter.get("architecture")!=header.get("architecture")):raise Blocked("Adapter does not match the base model architecture")
     validate(record["settings"],kind,capabilities=record["capabilities"],max_context=record.get("max_context"))
     with self.store.db:self.store.db.execute("UPDATE models SET record=? WHERE id=?",(json.dumps(record),identity))
    outcome=self.broker("register",record)
    record.update(outcome)
    if outcome.get("registered") is not True:raise Blocked("Registration not verified")
   except Exception as e:
    record["registration_error"]=type(e).__name__+": "+str(e)[:200]
   with self.store.db:self.store.db.execute("UPDATE models SET record=? WHERE id=?",(json.dumps(record),identity))
   return record
 def base_model_path(self,base_record):
  row=self.store.db.execute("SELECT path FROM artifacts WHERE id=?",(base_record["artifacts"][0],)).fetchone()
  if not row:raise Blocked("Base model artifact missing")
  return row[0]
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
 # Runtime settings a re-registration may change (reasoning; Swift's KV types and batch sizes, T-0123) while keeping the identity (and so the mm-* name that sessions and tickets
 # use). The identity hashes the install selection; the original values are kept in record["reregistered_from"].
 REREGISTER_OVERRIDES=("reasoning","reasoning_effort","chat_template","temperature","top_p","top_k","min_p","presence_penalty","repeat_penalty","cache_k","cache_v","batch","ubatch","speculation","draft_count")
 def reregister(self,identity,revision,overrides=None):
  """Retire and register again with the current broker workload (e.g. --metrics added after install), files kept.
  The broker refuses while the GPU controller has an owner and retire refuses a running deployment (T-0123)."""
  overrides=dict(overrides or {})
  if any(k not in self.REREGISTER_OVERRIDES for k in overrides):raise Blocked("Only %s may change on re-registration"%", ".join(self.REREGISTER_OVERRIDES))
  with self.exclusive():
   row=self.store.db.execute("SELECT record FROM models WHERE id=?",(identity,)).fetchone()
   if not row:raise Blocked("Unknown installation")
   record=json.loads(row[0])
   if record["revision"]!=revision:raise Blocked("Stale revision")
   if record.get("protected"):raise Blocked("Recovery installation is protected")
   if record["kind"] not in LLM_KINDS:raise Blocked("Re-registration is for llama.cpp models")
   # Re-prove header facts: models installed before capability detection (e.g. mm-73306b) carry no MTP proof, so
   # matching Swift's draft-mtp would otherwise be refused although the GGUF has the head.
   artifacts=[self.store.db.execute("SELECT path FROM artifacts WHERE id=?",(a,)).fetchone()[0] for a in record["artifacts"]]
   header=self.metadata_reader(artifacts[0] if record["kind"]=="gguf" else artifacts[1])   # a LoRA's artifacts are [adapter, base...]
   if isinstance(header,dict):
    record["capabilities"]={**(record.get("capabilities") or {"vision":False}),"mtp":(header.get("nextn_predict_layers") or 0)>0}
   settings={**record["settings"],**overrides}
   validate(settings,record["kind"],capabilities=record.get("capabilities"),max_context=record.get("max_context"))
   if record.get("registered"):
    result=self.broker("retire",record)
    if result.get("retired") is not True:raise Blocked("Retirement not verified")
   elif record.get("controller_identity"):
    # An interrupted reregister saves the record unregistered while the broker still holds the prior registration
    # (register then fails "Prior registered configuration differs"): retire that leftover; no receipt = nothing to do.
    try:
     result=self.broker("retire",record)
    except Exception as e:
     if "installation receipt required" not in str(e):raise
    else:
     if result.get("retired") is not True:raise Blocked("Retirement not verified")
   changed={k:record["settings"].get(k) for k,v in overrides.items() if record["settings"].get(k)!=v}
   if changed:record["reregistered_from"]={**changed,**record.get("reregistered_from",{})}
   record.update(settings=settings,registered=False,configured=False)
   record.pop("registration_error",None)
   # Saved before register: the broker reads the record from the catalogue, and a failed register leaves a truthful
   # unregistered record that a second reregister call completes.
   with self.store.db:self.store.db.execute("UPDATE models SET record=? WHERE id=?",(json.dumps(record),identity))
   try:
    outcome=self.broker("register",record)
    record.update(outcome)
    if outcome.get("registered") is not True:raise Blocked("Registration not verified")
   except Exception as e:
    record["registration_error"]=type(e).__name__+": "+str(e)[:200]
   with self.store.db:self.store.db.execute("UPDATE models SET record=? WHERE id=?",(json.dumps(record),identity))
   return record
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
    for name in plan["paths"]:
     source=Path(name)
     if not source.is_relative_to(self.root) or source.is_symlink():raise Blocked("Artifact escapes managed storage")
     relative=source.relative_to(self.root);safe_path(self.root,str(relative))
     known=self.store.db.execute("SELECT digest,bytes FROM artifacts WHERE path=?",(str(source),)).fetchone()
     if source.exists() and (not known or source.stat().st_size!=known[1] or digest(source)!=known[0]):raise Blocked("Artifact changed since installation; retained")
     # Quarantine inside the same <category>/model-manager mount as the file: in the pod only those directories are
     # bind-mounted on the real storage, so a quarantine elsewhere is another filesystem (rename -> EXDEV, 2026-11-19).
     if len(relative.parts)<3 or relative.parts[1]!="model-manager":raise Blocked("Artifact outside a managed category")
     quarantine=self.root/relative.parts[0]/"model-manager"/".quarantine"/identity
     target=safe_path(quarantine,str(Path(*relative.parts[2:])));target.parent.mkdir(parents=True,exist_ok=True)
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
