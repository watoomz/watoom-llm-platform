#!/usr/bin/env python3
"""Restartable serial backfill of exact dummy symbols in the accepted overlay only."""
import argparse,fcntl,hashlib,json,os,pathlib,subprocess,time,re
ap=argparse.ArgumentParser();ap.add_argument("--evidence",required=True,type=pathlib.Path);ap.add_argument("--engine-root",type=pathlib.Path,default=pathlib.Path("/data/ai/builds/unreal-recovery-20261016T213935Z/source"));ap.add_argument("--baseline-root",type=pathlib.Path);ap.add_argument("--selection",type=pathlib.Path);ap.add_argument("--capacity-status",type=pathlib.Path);ap.add_argument("--budget-hours",type=int,choices=[4,12],default=12);a=ap.parse_args()
out=a.evidence.resolve();assert out.is_relative_to(pathlib.Path("/data/ai/helper-scripts/reports"));out.mkdir(mode=0o700,exist_ok=True)
# One owner across fresh evidence directories.
lock=pathlib.Path("/data/ai/helper-scripts/reports/unreal-symbol-backfill.lock").open("a");fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
root=a.engine_root.resolve();assert root.is_relative_to(pathlib.Path("/data/ai"))
helper=pathlib.Path(__file__).with_name("check-crash-symbols.py")
prior_path=out/"symbol-coverage.json"
prior=json.loads(prior_path.read_text()) if prior_path.exists() else {}
results={};started=time.monotonic()-prior.get("elapsed_seconds",0)
def verified_crt_only_stub(binary):
 debug=binary.with_suffix(".debug")
 if binary.stat().st_size>16384 or not debug.is_file() or debug.stat().st_size>262144:return None
 def run(*args):return subprocess.check_output(list(args),text=True,timeout=20)
 def buildid(p):
  import re
  match=re.search(r"Build ID: ([a-fA-F0-9]+)",run("readelf","-n",str(p)))
  return match[1] if match else None
 identity=buildid(binary)
 if not identity or identity!=buildid(debug):return None
 dwarf=run("readelf","--debug-dump=info",str(debug))
 if "DW_TAG_compile_unit" not in dwarf or "DW_TAG_subprogram" in dwarf:return None
 crt={"deregister_tm_clones","register_tm_clones","__do_global_dtors_aux","frame_dummy","__do_global_ctors_aux","_init","_fini"}
 functions=[]
 for line in run("readelf","-sW",str(debug)).splitlines():
  fields=line.split()
  if len(fields)>=8 and fields[3]=="FUNC" and fields[6]!="UND":
   if fields[7] not in crt or fields[2]!="0":return None
   functions.append(fields[7])
 if not functions:return None
 return {"status":"NOT_APPLICABLE_CRT_ONLY_STUB","build_id":identity,"binary_sha256":hashlib.sha256(binary.read_bytes()).hexdigest(),"debug_sha256":hashlib.sha256(debug.read_bytes()).hexdigest(),"defined_functions":functions,"dwarf_subprograms":0,"scope":"Matching debug has no module subprograms; only zero-size CRT stubs. No FILE/FUNC records fabricated, placeholder preserved. Not full line-symbol acceptance."}

def save(status,**extra):
 value=dict(status=status,pid=os.getpid(),results=results,elapsed_seconds=round(time.monotonic()-started),**extra)
 temp=out/"symbol-coverage.new";temp.write_text(json.dumps(value,indent=2));os.replace(temp,out/"symbol-coverage.json")
def available():return int(next(x.split()[1] for x in pathlib.Path("/proc/meminfo").read_text().splitlines() if x.startswith("MemAvailable:")))*1024
modules=[]
if a.selection:
 deadline=time.monotonic()+900
 while not a.selection.exists() and time.monotonic()<deadline:
  save("WAITING_SELECTION_INVENTORY");time.sleep(10)
 if not a.selection.exists():save("BLOCKED_TIME_BUDGET",reason="Inventory did not settle within15min");raise SystemExit(2)
 inventory=json.loads(a.selection.read_text())
 assert pathlib.Path(inventory["root"]).resolve()==root
 modules=[root/x["module"] for x in inventory["changed"]]
for directory,dirs,files in (() if a.selection else os.walk(root/"Engine",followlinks=False)):
 # Debug sidecars are installed only in Binaries/Linux; avoid source/intermediate trees.
 dirs[:]=[d for d in dirs if d not in ("Intermediate","Source","Content","DerivedDataCache","Saved","Extras","Documentation")]
 if pathlib.Path(directory).parts[-2:]!=("Binaries","Linux"):continue
 for name in files:
  if not name.endswith(".debug"):continue
  debug=pathlib.Path(directory)/name
  binary=next((p for p in [debug.with_suffix(".so"),debug.with_suffix("")] if p.is_file()),None)
  if binary is not None:modules.append(binary)
if a.baseline_root:
 baseline=a.baseline_root.resolve()
 def bid(p):
  if not p.is_file():return None
  value=subprocess.check_output(["readelf","-n",str(p)],text=True,timeout=20)
  m=re.search(r"Build ID: ([a-fA-F0-9]+)",value);return m[1].lower() if m else None
 if a.selection:
  inventory=json.loads(a.selection.read_text());assert pathlib.Path(inventory["root"]).resolve()==root and pathlib.Path(inventory["baseline"]).resolve()==baseline
  selected={x["module"] for x in inventory["changed"]}
 else:
  selected={str(p.relative_to(root)) for p in modules if bid(p)!=bid(baseline/p.relative_to(root))}
 unchanged=inventory.get("unchanged_matching_build_ids",0) if a.selection else len(modules)-len(selected)
 modules=[p for p in modules if str(p.relative_to(root)) in selected]
else:unchanged=0
save("INVENTORY_COMPLETE",total=len(modules),unchanged_build_ids_preserved=unchanged)
if a.capacity_status:
 deadline=time.monotonic()+3600
 while time.monotonic()<deadline:
  capacity=json.loads(a.capacity_status.read_text()) if a.capacity_status.exists() else {}
  if capacity.get("status")=="CAPACITY_LENT":break
  save("WAITING_GUARDED_CAPACITY",total=len(modules));time.sleep(10)
 else:save("BLOCKED_TIME_BUDGET",reason="No guarded capacity within1h");raise SystemExit(2)

for binary in modules:
 relative=str(binary.relative_to(root));sym=binary.with_suffix(".sym")
 if not a.baseline_root and sym.is_file() and sym.stat().st_size>100:
  results[relative]={"status":"PRESERVED_EXISTING_SYMBOLS","bytes":sym.stat().st_size};continue
 if not sym.is_file() or sym.is_symlink() or (not a.baseline_root and (not 0<sym.stat().st_size<=100 or sym.read_bytes().replace(b"DummySyms",b"").strip())):
  results[relative]={"status":"NOT_TESTED_NO_EXACT_PLACEHOLDER"};continue
 stub=verified_crt_only_stub(binary)
 if stub:
  results[relative]=stub;save("RUNNING",total=len(modules));continue
 evidence=out/("module-"+hashlib.sha256(relative.encode()).hexdigest()[:16])
 if (evidence/"placeholder-backfill.json").exists():
  results[relative]={"status":"PASS","evidence":str(evidence)};continue
 if evidence.exists():
  results[relative]={"status":"BLOCKED_PRIOR_ATTEMPT","evidence":str(evidence)};continue
 while available()<=8*1024**3 and time.monotonic()-started<a.budget_hours*3600:
  save("WAITING_FOR_HEADROOM",current=relative,total=len(modules));time.sleep(15)
 if time.monotonic()-started>=a.budget_hours*3600:
  save("BLOCKED_TIME_BUDGET",total=len(modules));raise SystemExit(2)
 save("RUNNING",current=relative,total=len(modules))
 with (out/"coordinator.private.log").open("ab") as log:
  result=subprocess.run(["python3",str(helper),"--evidence",str(evidence),"--module",relative,"--memory-gib","6","--seconds","300","--engine-root",str(root),"--install-verified"]+(["--replace-stale-from",str(a.baseline_root.resolve())] if a.baseline_root else []),stdout=log,stderr=subprocess.STDOUT,timeout=420)
 results[relative]={"status":"PASS" if result.returncode==0 else "FAIL","evidence":str(evidence)}
 if result.returncode:
  save("BLOCKED_MODULE_FAILURE",current=relative,total=len(modules));raise SystemExit(2)
save("COMPLETE",total=len(modules),unchanged_build_ids_preserved=unchanged,scope="Selected changed matching-debug modules recertified; baseline-proven stale symbols backed up before atomic replacement. Unchanged build IDs preserved. Modules without debug sidecars excluded.")
