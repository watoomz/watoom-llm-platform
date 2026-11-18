#!/usr/bin/env python3
"""Portable GLB/FBX/TGA export of a purchased Unreal pack in a bounded, isolated worker.

Backends (--backend, default auto):
  bazzite - the Bazzite worker (bazzite.py): the pack's Content is synced to its cache and verified file by file
            against the source hashes, then UnrealEditor-Cmd runs in rootless podman with no network, a read-only
            root, all capabilities dropped, the engine and Content read-only, inside a bounded systemd unit.
            Results are pulled back into --out. Keeps big exports off the homelab server's RAM.
  local   - a k8s Job on the homelab: Content and the engine are hostPath mounts, read-only.
  auto    - bazzite when its runtime is staged and it has the RAM and disk; otherwise local. Falls back only
            before the worker starts: a started export is never replayed.
Either way the pack's Content is hashed before and after; ue_export_assets.py runs inside UnrealEditor-Cmd and
writes exported/ plus native-result.json.

  sudo python3 /data/ai/watoom-code/config/skills/watoom-fab-owned-assets/scripts/unreal-export/export_pack.py --pack /data/ai/assets/fab/<pack> --root /Game/<Folder> --out /data/ai/artifacts/unreal-export/<name> \
      [--classes SkeletalMesh,AnimSequence] [--include Wolf,Deer] [--exclude /Demo/] [--max-assets 400] [--memory-gib 4] [--backend auto|bazzite|local]
"""
import argparse,hashlib,json,os,pathlib,shlex,shutil,subprocess,sys,time
NS='watoom-code'
ENGINE=pathlib.Path('/data/ai/toolchains/unreal/5.8.3/runtime-74dc43e1a653')
PACKS=pathlib.Path('/data/ai/assets/fab')
OUTS=pathlib.Path('/data/ai/artifacts/unreal-export')
HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
a=argparse.ArgumentParser()
a.add_argument('--pack',type=pathlib.Path,required=True);a.add_argument('--root',required=True);a.add_argument('--out',type=pathlib.Path,required=True)
a.add_argument('--classes',default='SkeletalMesh,AnimSequence,StaticMesh,Texture2D');a.add_argument('--include',default='');a.add_argument('--exclude',default='/Demo/,/Maps/,/Levels/')
a.add_argument('--max-assets',type=int,default=400);a.add_argument('--memory-gib',type=int,default=4);a.add_argument('--deadline',type=int,default=1200)
a.add_argument('--backend',choices=['auto','bazzite','local'],default='auto')
a.add_argument('--script',choices=['ue_export_assets.py','ue_metahuman.py','ue_export_datatables.py'],default='ue_export_assets.py',help='in-engine script to run')
a.add_argument('--reserve-gib',type=int,default=2,help='free RAM to leave beyond --memory-gib on the worker (default 2)')
a.add_argument('--full-editor',action='store_true',help='run UnrealEditor (Slate initialised, null renderer) instead of the UnrealEditor-Cmd commandlet; needed by editor-UI-backed calls such as MetaHuman geometry export')
a.add_argument('--accept-shutdown-crash',action='store_true',help='accept a pulled native-result.json that reports success even if the engine crashed while shutting down (recorded in result.json)')
a.add_argument('--plugins',default='',help='extra Unreal plugins to enable in the generated project, comma separated')
a.add_argument('--request-extra',default='{}',help='JSON object merged into request.json for the in-engine script')
args=a.parse_args()
if os.geteuid()!=0:raise SystemExit('Run as root: the Job needs kubectl and the output is chowned to the toolkit user')
pack=args.pack.resolve(strict=True);content=pack/'Content'
if args.pack.is_symlink() or pack.parent!=PACKS or not content.is_dir():raise SystemExit('Pack must be a directory directly under /data/ai/assets/fab with a Content folder')
if not args.root.startswith('/Game/') or '..' in args.root:raise SystemExit('--root must be a /Game/... path')
out=args.out.resolve()
if not out.is_relative_to(OUTS) or out.exists():raise SystemExit('--out must be a new directory under /data/ai/artifacts/unreal-export')
if not 0<=args.reserve_gib<=8 or not 2<=args.memory_gib<=12 or not 60<=args.deadline<=3600 or not 1<=args.max_assets<=2000:raise SystemExit('Out-of-range resource bounds')
image=subprocess.check_output(['kubectl','-n',NS,'get','deploy','watoom-toolkit','-o','jsonpath={.spec.template.spec.containers[0].image}'],text=True).strip()
if '@sha256:' not in image:raise SystemExit('Production toolkit image is not digest-pinned')
def hashes():return {str(x.relative_to(content)):hashlib.sha256(x.read_bytes()).hexdigest() for x in sorted(content.rglob('*')) if x.is_file()}
def local_mem():return int(next(x.split()[1] for x in pathlib.Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
need=(args.memory_gib+args.reserve_gib)*1024**3

# choose the backend before anything is written
backend=args.backend;fallback_reason=None;bz=None
if backend in ('auto','bazzite'):
 try:
  import bazzite as bz
  staged=bz.runtime_ready()
  if not staged:raise RuntimeError('runtime not staged on Bazzite (bazzite.py stage-runtime)')
  if staged[1].get('image')!=image:raise RuntimeError('Bazzite toolkit image differs from production; re-run bazzite.py stage-runtime')
  ram,disk=bz.free()
  if ram<need:raise RuntimeError('Bazzite has %.1f GiB free RAM, needs %d'%(ram/1024**3,args.memory_gib+args.reserve_gib))
  pack_bytes=sum(x.stat().st_size for x in content.rglob('*') if x.is_file())
  if disk<2*pack_bytes+20*1024**3:raise RuntimeError('Bazzite has %.1f GiB free disk'%(disk/1024**3))
  backend='bazzite'
 except Exception as e:
  if args.backend=='bazzite':raise SystemExit('Bazzite backend unavailable: %s'%e)
  backend='local';fallback_reason=str(e)[:300]
if backend=='local' and local_mem()<need:raise SystemExit('%d GiB limit plus 2 GiB reserve is not available (%.1f GiB free)'%(args.memory_gib,local_mem()/1024**3))

before=hashes()
OUTS.mkdir(parents=True,exist_ok=True);out.mkdir(mode=0o770)
(out/'source-hashes.json').write_text(json.dumps(before))
(out/'Inspection.uproject').write_text(json.dumps({'FileVersion':3,'EngineAssociation':'','Plugins':[{'Name':n,'Enabled':True} for n in ['PythonScriptPlugin','GLTFExporter',*[x for x in args.plugins.split(',') if x]]]}))
(out/'request.json').write_text(json.dumps({**json.loads(args.request_extra),**{'root':args.root,'classes':[c for c in args.classes.split(',') if c],'include':[i for i in args.include.split(',') if i],
 'exclude':[e for e in args.exclude.split(',') if e],'max_assets':args.max_assets}}))
shutil.copy2(HERE/args.script,out/args.script)
name='watoom-ue-export-'+hashlib.sha256(str(out).encode()).hexdigest()[:12]
budget=args.deadline-60
editor_cmd=['python3','-c',"import pathlib,subprocess,sys;pathlib.Path('/tmp/home').mkdir(exist_ok=True);sys.exit(subprocess.run(sys.argv[2:],timeout=int(sys.argv[1])).returncode)",str(budget),
 *(['/unreal-engine/Engine/Binaries/Linux/UnrealEditor','/job/Inspection.uproject','-ExecutePythonScript=/job/'+args.script,'-nosplash','-RenderOffScreen'] if args.full_editor else
   ['/unreal-engine/Engine/Binaries/Linux/UnrealEditor-Cmd','/job/Inspection.uproject','-run=PythonScript','-script=/job/'+args.script]),
 '-NullRHI','-unattended','-nosound','-nop4','-stdout','-ddc=NoZenLocalFallback','-LocalDataCachePath=/job/DerivedDataCache']
home_env={'HOME':'/tmp/home','XDG_CACHE_HOME':'/tmp/home/.cache','XDG_CONFIG_HOME':'/tmp/home/.config','XDG_DATA_HOME':'/tmp/home/.local/share',**({'SDL_VIDEODRIVER':'dummy','SDL_AUDIODRIVER':'dummy'} if args.full_editor else {})}
succeeded=False;extra={}

def run_local():
 job={'apiVersion':'batch/v1','kind':'Job','metadata':{'name':name,'namespace':NS,'labels':{'watoom-test-owner':'unreal-export'}},
  'spec':{'ttlSecondsAfterFinished':3600,'backoffLimit':0,'activeDeadlineSeconds':args.deadline,'template':{'spec':{
   'restartPolicy':'Never','automountServiceAccountToken':False,'enableServiceLinks':False,'activeDeadlineSeconds':args.deadline,
   'securityContext':{'runAsUser':1009,'runAsGroup':1009,'fsGroup':1009,'runAsNonRoot':True,'seccompProfile':{'type':'RuntimeDefault'}},
   'volumes':[{'name':'engine','hostPath':{'path':str(ENGINE),'type':'Directory'}},{'name':'tmp','emptyDir':{'sizeLimit':'2Gi'}},
    {'name':'job','hostPath':{'path':str(out),'type':'Directory'}},{'name':'content','hostPath':{'path':str(content),'type':'Directory'}}],
   'containers':[{'name':'unreal','image':image,'imagePullPolicy':'IfNotPresent',
    'securityContext':{'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}},
    'env':[{'name':k,'value':v} for k,v in home_env.items()],
    'resources':{'requests':{'cpu':'500m','memory':'1Gi'},'limits':{'cpu':'4','memory':'%dGi'%args.memory_gib}},
    'volumeMounts':[{'name':'engine','mountPath':'/unreal-engine','readOnly':True},{'name':'tmp','mountPath':'/tmp'},{'name':'job','mountPath':'/job'},{'name':'content','mountPath':'/job/Content','readOnly':True}],
    'command':editor_cmd}]}}}}
 for f in [out,*out.iterdir()]:os.chown(f,1009,1009)
 subprocess.run(['chcon','-R','-t','container_file_t',str(out)],check=True)
 (out/'job.json').write_text(json.dumps(job,indent=1))
 subprocess.run(['kubectl','create','-f',str(out/'job.json')],check=True,stdout=subprocess.DEVNULL)
 deadline=time.time()+args.deadline+120;status={}
 while time.time()<deadline:
  status=json.loads(subprocess.check_output(['kubectl','-n',NS,'get','job',name,'-o','json'])).get('status',{})
  if status.get('succeeded') or status.get('failed'):break
  time.sleep(10)
 logs=subprocess.run(['kubectl','-n',NS,'logs','job/'+name],capture_output=True,text=True)
 (out/'native.private.log').write_text(logs.stdout[-4_000_000:]+logs.stderr[-200_000:]);os.chmod(out/'native.private.log',0o600)
 return bool(status.get('succeeded'))

r_pack=None;r_job=None
def remote_hashes():
 r=bz.sh('cd ~/%s/Content && find . -type f -print0 | xargs -0r sha256sum'%r_pack,timeout=3600,check=True)
 return {l[66:].removeprefix('./'):l[:64] for l in r.stdout.splitlines() if len(l)>66}

def prepare_bazzite():
 """Sync + verify the pack and the job folder; returns the launch command. Starts nothing."""
 global r_pack,r_job
 r_pack='%s/%s'%(bz.R_PACKS,pack.name);r_job='%s/%s'%(bz.R_JOBS,name)
 tag=bz.runtime_ready()[1]['local_tag']
 home=bz.sh('printf %s "$HOME"',timeout=60,check=True).stdout.strip()
 if not home.startswith('/'):raise RuntimeError('cannot resolve the worker home')
 bz.sh('mkdir -p ~/%s/Content ~/%s'%(r_pack,r_job),timeout=60,check=True)
 r=bz.push(str(content)+'/','%s/Content/'%r_pack,['--delete'])
 if r.returncode:raise RuntimeError('pack sync failed: '+r.stderr[-500:])
 if remote_hashes()!=before:raise RuntimeError('pack on Bazzite does not match the source hashes')
 r=bz.push(str(out)+'/','%s/'%r_job)
 if r.returncode:raise RuntimeError('job push failed: '+r.stderr[-500:])
 podman=['podman','run','--rm','--name',name,'--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
  '--userns','keep-id:uid=1009,gid=1009','--memory','%dg'%args.memory_gib,'--memory-swap','%dg'%args.memory_gib,'--cpus','4','--pids-limit','4096',
  '--tmpfs','/tmp:rw,size=2g,mode=1777',*sum([['-e','%s=%s'%kv] for kv in home_env.items()],[]),
  '-v','%s/%s:/unreal-engine:ro,z'%(home,bz.R_ENGINE),'-v','%s/%s:/job:z'%(home,r_job),'-v','%s/%s/Content:/job/Content:ro,z'%(home,r_pack),
  tag,*editor_cmd]
 job_dir='%s/%s'%(home,r_job)
 script='%s > %s 2>&1; echo $? > %s'%(' '.join(shlex.quote(x) for x in podman),shlex.quote(job_dir+'/native.log'),shlex.quote(job_dir+'/exit_code'))
 unit=['systemd-run','--user','--unit='+name,'--collect',*bz.UNIT_LIMITS,'-p','RuntimeMaxSec=%d'%(args.deadline+60),'/bin/bash','-c',script]
 (out/'worker-command.json').write_text(json.dumps(unit,indent=1))
 return ' '.join(shlex.quote(x) for x in unit)

held=None
if backend=='bazzite':
 try:
  held=bz.inhibit(name,args.deadline+3600,'Unreal export '+name)
  launch=prepare_bazzite()
 except Exception as e:
  if held:bz.release(held)
  if args.backend=='bazzite':
   result={'status':'FAIL','reason':'Bazzite export did not start: %s'%str(e)[:300]}
   (out/'result.json').write_text(json.dumps(result,indent=2));print('@@JSON@@'+json.dumps(result));raise SystemExit(1)
  backend='local';fallback_reason='before start: '+str(e)[:300]
  if local_mem()<need:raise SystemExit('Bazzite failed before start (%s) and local RAM is short'%fallback_reason)
  succeeded=run_local()
 else:
  # from the launch on there is no fallback: a launch error may still have started the unit
  try:
   r=bz.sh(launch,timeout=120)
   extra['launch']='ok' if r.returncode==0 else 'error: '+r.stderr[-300:]
  except Exception as e:
   extra['launch']='uncertain: '+str(e)[:300]
  deadline=time.time()+args.deadline+180;code=None
  while time.time()<deadline:
   try:
    r=bz.sh('cat ~/%s/exit_code 2>/dev/null; systemctl --user is-active %s.service'%(r_job,name),timeout=60)
    lines=r.stdout.split()
    if lines and lines[0].lstrip('-').isdigit():code=int(lines[0]);break
    if lines and lines[-1] in ('inactive','failed'):break
   except Exception:
    pass
   time.sleep(15)
  r=bz.pull('%s/'%r_job,str(out)+'/',['--exclude=Content/','--exclude=DerivedDataCache/'])
  extra['pull_ok']=r.returncode==0
  log=out/'native.log'
  if log.exists():log.rename(out/'native.private.log');os.chmod(out/'native.private.log',0o600)
  succeeded=code==0 and extra['pull_ok']
  try:
   extra['worker_source_unchanged']=remote_hashes()==before
  except Exception:
   extra['worker_source_unchanged']=False
  if extra['pull_ok']:bz.sh('rm -rf ~/%s'%r_job,timeout=300)
  extra.update(worker='bazzite',exit_code=code)
  bz.release(held)
  for f in out.rglob('*'):os.chown(f,1009,1009)
  os.chown(out,1009,1009)
else:
 succeeded=run_local()

if not succeeded and args.accept_shutdown_crash and extra.get('pull_ok') and (out/'native-result.json').exists():
 try:
  native=json.loads((out/'native-result.json').read_text())
  if native.get('status') in ('METAHUMAN_PASS','PORTABLE_EXPORT_PASS') and not native.get('error'):
   succeeded=True;extra['shutdown_crash_accepted']=True
 except Exception:pass
unchanged=hashes()==before and extra.get('worker_source_unchanged',True)
result=json.loads((out/'native-result.json').read_text()) if (out/'native-result.json').exists() else {'status':'FAIL','reason':'Worker wrote no native-result.json'}
if not succeeded:result.update(status='FAIL',reason=result.get('reason') or 'Unreal worker did not finish successfully')
if not unchanged:result.update(status='FAIL',reason='Purchased source changed during export')
result.update(job=name,image=image,source_unchanged=unchanged,memory_limit_gib=args.memory_gib,backend=backend,**extra)
if fallback_reason:result['backend_fallback_reason']=fallback_reason
(out/'result.json').write_text(json.dumps(result,indent=2))
print('@@JSON@@'+json.dumps({k:result.get(k) for k in ('status','counts','reason','job','source_unchanged','backend')}))
raise SystemExit(0 if result['status'] in ('PORTABLE_EXPORT_PASS','PARTIAL_EXPORT','METAHUMAN_PASS','METAHUMAN_PARTIAL','PROBE_DONE') else 1)
