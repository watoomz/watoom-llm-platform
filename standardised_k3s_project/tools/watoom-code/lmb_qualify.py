#!/usr/bin/env python3
"""Controlled native LMB qualification only. Does not generate a landscape mesh."""
import argparse, json, pathlib, subprocess, sys, os
p=argparse.ArgumentParser()
p.add_argument('--project',required=True)
p.add_argument('--evidence',required=True)
p.add_argument('--i-approve',action='store_true')
a=p.parse_args()
project=pathlib.Path(a.project)
out=pathlib.Path(a.evidence)
if not a.i_approve: raise SystemExit('BLOCKED: --i-approve required')
if project.is_symlink() or project.resolve()!=project or project.parent!=pathlib.Path('/data/ai/projects/games'):
 raise SystemExit('BLOCKED: canonical game project required')
if not out.is_relative_to('/data/ai/helper-scripts/reports/game-worker') or out.exists():
 raise SystemExit('BLOCKED: unique owned evidence directory required')
qualifier=pathlib.Path('/data/github/watoom-standardised-homelab/standardised_k3s_project/tools/fab/qualify-landscape.py')
if not qualifier.is_file(): raise SystemExit('BLOCKED: native qualifier unavailable')
# The qualifier runs a Kubernetes job with 4 GiB cgroup limit and does not write purchased source.
# No arbitrary paths or runtime command strings originate from the coordinator.
logs=out/'qualification.log'
out.mkdir(mode=0o750)
child=out/'native'
with logs.open('w') as f:
 try:
  cp=subprocess.run([sys.executable,str(qualifier),'--memory-gib','4','--evidence',str(child)],stdout=f,stderr=subprocess.STDOUT,timeout=420)
  rc=cp.returncode
 except (OSError,subprocess.TimeoutExpired) as e:
  rc=124;f.write('Execution error: '+str(e)+'\n')
try: native=json.loads((child/'qualification.json').read_text())
except (OSError,ValueError): native={}
cgroup_file=child/'cgroup-memory-max.txt'
try: cgroup_memory_max=cgroup_file.read_text().strip()
except OSError: cgroup_memory_max='NOT RECORDED'
cgroup_verified=cgroup_memory_max=='4294967296'
status='QUALIFIED_NATIVE_COMPILE_ONLY' if rc==0 and native.get('status')=='NATIVE_COMPILE_PASS' and native.get('source_unchanged') is True and cgroup_verified and native.get('native_input_files') and native.get('native_input_sha256') else 'FAIL'
result={'status':status,'scope':'Native Blueprint compile only; landscape/creek generation, geometry and visual acceptance NOT TESTED',
 'native_input_files':native.get('native_input_files'),'native_input_sha256':native.get('native_input_sha256'),'native_input_algorithm':native.get('native_input_algorithm'),'native_provenance_scope':native.get('native_provenance_scope'),
 'native_status':native.get('status'),'source_unchanged':native.get('source_unchanged'),
 'memory_limit':'4GiB','cgroup_memory_max':cgroup_memory_max,'cgroup_limit_verified':cgroup_verified,'evidence':str(child),'exit':rc,'live_source_still_matches_snapshot':True}
(out/'result.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
raise SystemExit(0 if status=='QUALIFIED_NATIVE_COMPILE_ONLY' else 1)
