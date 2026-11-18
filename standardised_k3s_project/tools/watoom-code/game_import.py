#!/usr/bin/env python3
"""Operator-only bounded import; never runs inside the application cgroup."""
from worker_directories import prepare_worker_directories
import argparse,hashlib,json,pathlib,subprocess,time,os
from game_validation import GODOT,GODOT_SHA,manifest,atomic,godot_errors,import_failure_reason,godot_hints
p=argparse.ArgumentParser();p.add_argument('--project',type=pathlib.Path,required=True);p.add_argument('--evidence',type=pathlib.Path,required=True);p.add_argument('--i-approve',action='store_true');a=p.parse_args()
project=a.project.resolve(strict=True)
if not a.i_approve or a.project.is_symlink() or not project.is_relative_to('/data/ai/projects/games') or not (project/'project.godot').is_file():raise ValueError('Approved existing game project required')
if hashlib.sha256(GODOT.read_bytes()).hexdigest()!=GODOT_SHA:raise ValueError('Pinned engine changed')
available=int(next(x.split()[1] for x in pathlib.Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
if available<5*1024**3:raise RuntimeError('3GiB worker plus 2GiB reserve unavailable')
# Reject indirect project resources using maintained manifest validation.
before={k:v for k,v in manifest(project).items() if not k.endswith('.import')}
prepare_worker_directories(project)
a.evidence.mkdir(parents=True,exist_ok=False);os.chmod(a.evidence,0o750)
# Mount a worker-only configuration to serialize resource imports. The live project
# and its request fingerprint remain unchanged; cache updates are the only outputs.
config_text=(project/'project.godot').read_text()
if '[editor]' in config_text:
 raise ValueError('Existing editor settings require explicit merge before serialized import')
worker_config=a.evidence/'worker-project.godot'
worker_config.write_text(config_text+'\n[editor]\nimport/use_multiple_threads=false\n')
os.chmod(worker_config,0o644)
unit='watoom-godot-import-'+str(time.time_ns());atomic(a.evidence/'prepared.json',{'unit':unit,'project':str(project),'source_manifest':before,'memory_limit':'3GiB'})
#  RuntimeMaxSec/timeout: a large project (hundreds of source GLBs re-importing on first touch) can run well
#  past 5 minutes even on the dedicated worker; 1800s still fits comfortably inside the service's own
#  TimeoutStartSec=60min, and the Python timeout keeps its ~30s margin over the unit's own kill.
cmd=['systemd-run','--quiet','--wait','--collect','--unit='+unit,'-p','MemoryMax=3G','-p','MemorySwapMax=0','-p','CPUQuota=200%','-p','TasksMax=128','-p','RuntimeMaxSec=1800','-p','TimeoutStopSec=10','-p','KillMode=control-group','-p','NoNewPrivileges=yes','-p','PrivateNetwork=yes','-p','PrivateDevices=yes','-p','PrivateTmp=yes','-p','ProtectSystem=strict','-p','ProtectHome=yes','-p','ReadWritePaths='+str(project),'-p','BindReadOnlyPaths='+str(worker_config)+':'+str(project/'project.godot'),'--setenv=HOME=/tmp','--','/usr/sbin/setpriv','--reuid=1009','--regid=1009','--clear-groups','--bounding-set=-all','--',str(GODOT),'--headless','--path',str(project),'--editor','--import']
with (a.evidence/'import.log').open('w') as log:r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=1830)
journal=subprocess.run(['journalctl','-u',unit,'--no-pager','-o','cat','-n','200'],capture_output=True,text=True,timeout=15)
(a.evidence/'unit-journal.log').write_text(journal.stdout)
text=(a.evidence/'import.log').read_text(errors='replace')+'\n'+journal.stdout
failure_reason='oom-kill' if 'oom-kill' in text or 'OOM killer' in text else ('worker-exit' if r.returncode else None)
after={k:v for k,v in manifest(project).items() if not k.endswith('.import')};errors=godot_errors(text)
changes={'changed':sorted(k for k in set(before)|set(after) if before.get(k)!=after.get(k))[:50],'note':'import changed source files (e.g. Godot .uid files or re-saved resources). Commit or fix these, then request a new import.'} if before!=after else None
if failure_reason is None and (changes or errors):failure_reason=import_failure_reason(errors,changes,True,True)
receipt={'status':'PASS' if r.returncode==0 and before==after and not errors else 'FAIL','unit':unit,'exit':r.returncode,'failure_reason':failure_reason,'log_tail':text.splitlines()[-40:],'source_unchanged':before==after,'source_changes_by_import':changes,'errors':errors[:20],'hints':godot_hints(errors),'memory_limit':'3GiB','import_threads':1,'worker_config_sha256':hashlib.sha256(worker_config.read_bytes()).hexdigest(),'scope':'import only; no rendering or gameplay acceptance'}
if receipt['status']!='PASS':
 stage,code=('reconcile','source_changed') if changes else ('run','oom') if 'oom' in str(failure_reason).lower() else ('run','script_error') if errors else ('run','worker_error')
 receipt.update(failure_stage=stage,failure_code=code)
atomic(a.evidence/'result.json',receipt)
target=project/'.opencode/validation/operator-godot';target.mkdir(parents=True,exist_ok=True);out=target/(unit+'.json');out.write_text(json.dumps(receipt,indent=2));os.chmod(out,0o644);print(json.dumps(receipt));raise SystemExit(0 if receipt['status']=='PASS' else 1)
