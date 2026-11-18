#!/usr/bin/env python3
"""Operator-owned bounded software-render capture of the existing P6 scene."""
from worker_directories import prepare_worker_directories
import argparse,pathlib,subprocess,hashlib,json,time,os
from game_validation import GODOT,GODOT_SHA,atomic,godot_errors,godot_hints,godot_output_tail
from capture_profiles import PROFILES,exit_evidence,frame_evidence_errors
p=argparse.ArgumentParser();p.add_argument('--project',type=pathlib.Path,required=True);p.add_argument('--evidence',type=pathlib.Path,required=True);p.add_argument('--i-approve',action='store_true');p.add_argument('--profile',choices=sorted(PROFILES),default='p6');p.add_argument('--capture-job');a=p.parse_args();profile=PROFILES[a.profile];
if a.capture_job:
 from capture_spec import load
 profile=load(a.project.resolve(strict=True),a.capture_job)
memory_gib=profile.get('memory_gib',3);deadline_sec=profile.get('deadline_sec',180);project=a.project.resolve(strict=True)
if not a.i_approve or a.project.is_symlink() or not project.is_relative_to('/data/ai/projects/games'):raise ValueError('Approved game project required')
scene=project/profile['scene']
if not scene.is_file() or scene.is_symlink():raise ValueError(('scene '+profile['scene']+' named in the capture-job manifest is not a regular file in the project' if a.capture_job else 'operation capture runs only the fixed '+profile['scene']+' scene, which this project does not have; for your own views use operation capture-scene with .opencode/capture-jobs/<job>/request.json'))
if hashlib.sha256(GODOT.read_bytes()).hexdigest()!=GODOT_SHA:raise ValueError('Engine identity mismatch')
mem=int(next(x.split()[1] for x in pathlib.Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
if mem<(memory_gib+2)*1024**3:raise RuntimeError(str(memory_gib)+'GiB worker plus 2GiB reserve unavailable')
prepare_worker_directories(project)
for name in ['.opencode/validation',profile['directory']]:
 d=project
 for component in pathlib.PurePosixPath(name).parts:
  d=d/component
  if not d.exists():d.mkdir(mode=0o775);os.chown(d,1009,1009)
  if d.is_symlink() or d.resolve()!=d or not d.is_dir():raise ValueError('Indirect output directory')

a.evidence.mkdir(parents=True,exist_ok=False);unit='watoom-godot-capture-'+str(time.time_ns());atomic(a.evidence/'prepared.json',{'unit':unit,'scene':str(scene)})
cmd=['systemd-run','--quiet','--wait','--collect','--unit='+unit,'-p','MemoryMax='+str(memory_gib)+'G','-p','MemorySwapMax=0','-p','CPUQuota=200%','-p','TasksMax=128','-p','RuntimeMaxSec='+str(deadline_sec),'-p','TimeoutStopSec=10','-p','KillMode=control-group','-p','NoNewPrivileges=yes','-p','PrivateNetwork=yes','-p','PrivateDevices=yes','-p','PrivateTmp=yes','-p','ProtectSystem=strict','-p','ProtectHome=yes','-p','ReadWritePaths='+str(project/'.godot')+' '+str(project/'.opencode'),'--setenv=HOME=/tmp','--setenv=LIBGL_ALWAYS_SOFTWARE=1','--setenv=GALLIUM_DRIVER=llvmpipe','--setenv=LP_NUM_THREADS=2','--setenv=__EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/50_mesa.json','--setenv=__GLX_VENDOR_LIBRARY_NAME=mesa','--','/usr/sbin/setpriv','--reuid=1009','--regid=1009','--clear-groups','--bounding-set=-all','--','/usr/sbin/xvfb-run','-e',str(project/'.opencode/validation/xvfb-worker.log'),'-a','-s','-screen 0 800x800x24',str(GODOT),'--path',str(project),'--audio-driver','Dummy','--rendering-driver','opengl3','res://'+profile['scene']]
start=time.time()
with (a.evidence/'capture.log').open('w') as log:
 try:returncode=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=deadline_sec+30).returncode
 except subprocess.TimeoutExpired:returncode=None
elapsed=time.time()-start
images=[]
for name in profile['names']:
 f=project/profile['directory']/name
 if f.is_file():
  import struct
  if f.is_symlink() or f.resolve()!=f or f.stat().st_size>128*1024**2:raise ValueError('Unsafe/oversize capture output')
  with f.open('rb') as image:header=image.read(24)
  if len(header)!=24 or header[:8]!=bytes([137,80,78,71,13,10,26,10]) or any(not 16<=x<=8192 for x in struct.unpack('>II',header[16:24])):raise ValueError('Invalid rendered PNG')
  images.append({'path':str(f),'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'fresh':f.stat().st_mtime>=start})
journal=subprocess.run(['journalctl','-u',unit,'--no-pager','-o','cat'],capture_output=True,text=True).stdout
with (a.evidence/'capture.log').open('a') as log:log.write(journal)
text=(a.evidence/'capture.log').read_text(errors='replace');errors=godot_errors(text);errors+=([x[:500] for x in text.splitlines() if 'Failed to set up mount namespacing' in x] or ['WORKER_NAMESPACE_SETUP_FAILED: Godot did not launch']) if returncode==226 else []
timed_out,exit_errors=exit_evidence(returncode,text,elapsed,deadline_sec,errors);errors=exit_errors+errors
errors+=frame_evidence_errors(a.profile,images);receipt={'profile':'declarative' if a.capture_job else a.profile,'scene':profile['scene'],'capture_spec_sha256':profile.get('capture_spec_sha256'),'status':'CAPTURED_VISUAL_REVIEW_PENDING' if returncode==0 and len(images)==len(profile['names']) and all(x['fresh'] for x in images) and not errors else 'FAIL','unit':unit,'exit':returncode,'timed_out':timed_out,'elapsed_sec':round(elapsed,1),'deadline_sec':deadline_sec,'images':images,'errors':errors[:20],'hints':godot_hints(errors),'output_tail':godot_output_tail(text),'gpu_used':False,'memory_limit':str(memory_gib)+'GiB'};atomic(a.evidence/'result.json',receipt)
target=project/'.opencode/validation/operator-godot';target.mkdir(parents=True,exist_ok=True);f=target/(unit+'.json');f.write_text(json.dumps(receipt,indent=2));os.chmod(f,0o644);print(json.dumps(receipt));raise SystemExit(0 if receipt['status']!='FAIL' else 1)
