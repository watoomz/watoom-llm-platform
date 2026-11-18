import json,time
from pathlib import Path
from file_lock import lock_file
from operations import Operations
from admission_errors import AdmissionBusy
class Worker:
 def __init__(self,store,operations,paused=lambda:False):self.store=store;self.operations=operations;self.stopping=False;self.paused=paused
 def once(self):
  if self.paused():return False
  jobs=[j for j in self.store.jobs() if j["state"] in ("QUEUED","WAITING_NATIVE_IDLE","DOWNLOADING","REMOVING","GENERATING","CANCEL_REQUESTED")]
  if not jobs:return False
  job=jobs[-1];selection=json.loads(job["selection"])
  if job["state"]=="CANCEL_REQUESTED":
   self.store.transition(job["id"],"CANCELLED");return True
  try:
   if selection.get("operation")=="generate":
    if job["state"]=="GENERATING":raise ValueError("Interrupted generation: explicit retry required after ownership reconciliation")
    self.store.transition(job["id"],"GENERATING")
    result=self.operations.generate(selection["id"],selection["revision"],selection["prompt"],**({"settings":selection["settings"]} if "settings" in selection else {}),**({"negative_prompt":selection["negative_prompt"]} if "negative_prompt" in selection else {}),progress=lambda stage:self.store.set_stage(job["id"],stage))
    self.store.save_result(job["id"],result);self.store.transition(job["id"],"GENERATION_VERIFIED");return True
   if selection.get("operation")=="remove":
    self.store.transition(job["id"],"REMOVING")
    receipt=self.operations.remove(selection["id"],selection["revision"],selection.get("delete",False),selection["confirmation"],job_id=job["id"])
    self.store.transition(job["id"],"REMOVED_FILES_QUARANTINED" if receipt["files"]=="quarantined" else "REMOVED_FILES_RETAINED")
    return True
   self.store.transition(job["id"],"DOWNLOADING")
   record=self.operations.install(selection,lambda n:self.store.transition(job["id"],"DOWNLOADING",n),lambda:self.store.cancelled(job["id"]))
   self.store.transition(job["id"],"REGISTERED_NOT_TESTED" if record.get("registered") else "DOWNLOADED_REGISTRATION_FAILED",sum(x["size"] for x in selection["files"]),None if record.get("registered") else record.get("registration_error"))
  except AdmissionBusy as e:
   if selection.get("operation")=="generate":
    self.store.transition(job["id"],"WAITING_NATIVE_IDLE",error=str(e)[:200]);return False
   self.store.transition(job["id"],"FAILED",error=str(e)[:200])
  except Exception as e:self.store.transition(job["id"],"CANCELLED" if self.store.cancelled(job["id"]) else "FAILED",error=type(e).__name__+": "+str(e)[:200])
  return True
 def run(self):
  with Path(str(self.store.path)+".worker.lock").open("a") as lock:
   lock_file(lock) # One queue consumer across processes and overlapping pod lifetimes.
   while not self.stopping:
    if not self.once():time.sleep(1)
