"""Fixed Godot operations inside the inherited Windows Job Object; source is a copy."""
import pathlib,json,hashlib,subprocess,sys,zipfile,stat,re,time,os,shutil
from windows_job import current_limit
CAPTURES={
 'capture':('.opencode/validation/p6-env-capture/p6_env_capture.tscn','.opencode/captures/p6-asset-review',['terrain-wild.png','meadow-tree.png','tree-closeup.png']),
 'capture-p7':('.opencode/validation/p7-poo-capture/p7_poo_capture.tscn','.opencode/captures/p7-poo',['ability-'+str(i)+'-'+n+'.png' for i,n in enumerate(['normal','explosive','rapid_fire','mega','sticky','scatter','precision','stink_bomb'])])}
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def unpack(archive,project):
 project.mkdir(exist_ok=False);count=0;total=0
 with zipfile.ZipFile(archive) as z:
  seen=set()
  for i in z.infolist():
   name=i.filename;parts=pathlib.PurePosixPath(name).parts;lower=name.casefold()
   if i.is_dir():continue
   if not parts or name.startswith(('/',chr(92))) or '..' in parts or chr(92) in name or ':' in name or lower in seen or stat.S_ISLNK(i.external_attr>>16):raise ValueError('Unsafe snapshot member')
   if any(x.endswith((' ','.')) or x.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{n}' for n in range(1,10)],*[f'LPT{n}' for n in range(1,10)]} for x in parts):raise ValueError('Windows reserved snapshot path')
   if parts[0] in ('.git','.godot'):raise ValueError('Snapshot contains live/cache state')
   count+=1;total+=i.file_size
   if count>20001 or total>2*1024**3:raise ValueError('Snapshot expansion budget')
   seen.add(lower);target=project.joinpath(*parts)
   if not target.resolve().is_relative_to(project.resolve()):raise ValueError('Snapshot escape')
   target.parent.mkdir(parents=True,exist_ok=True)
   with z.open(i) as src,target.open('xb') as dst:shutil.copyfileobj(src,dst)
 manifest=json.loads((project/'.rig-input-manifest.json').read_text())
 if {n.casefold() for n in manifest['files']}!=seen-{'.rig-input-manifest.json'}:raise ValueError('Snapshot closure mismatch')
 for name,digest in manifest['files'].items():
  if sha(project.joinpath(*pathlib.PurePosixPath(name).parts))!=digest:raise ValueError('Snapshot file hash mismatch')
 return manifest

def execute(plan):
 out=plan.parent;v=json.loads(plan.read_text());spec=v['manifest'];engine=pathlib.Path(v['godot']);profile=json.loads(pathlib.Path(__file__).with_name('game-runtime-provenance.json').read_text());limits=current_limit()
 actual={n:sha(engine.parent/n) for n in profile['files']}
 if actual!=profile['files']:raise ValueError('Godot engine changed')
 archive=pathlib.Path(spec['source']);assert sha(archive)==spec['source_sha256'];project=out/'project';meta=unpack(archive,project);assert meta['source_fingerprint']==spec['source_fingerprint'];deadline=time.monotonic()+850
 logs=[]
 def godot(args,limit=600):
  remaining=min(limit,max(1,int(deadline-time.monotonic())))
  r=subprocess.run([str(engine),*args],cwd=project,capture_output=True,text=True,errors='replace',timeout=remaining,creationflags=0x08000000)
  logs.append(r.stdout+r.stderr);(out/'godot.log').write_text('\n'.join(logs),encoding='utf-8');return r
 version=godot(['--version'],20).stdout.strip();assert version=='4.7.2.stable.official.ed1daf0bf',version
 base=['--path',str(project),'--audio-driver','Dummy','--rendering-method','gl_compatibility','--rendering-driver','opengl3']
 imported=godot(['--headless',*base,'--editor','--import'],240)
 if imported.returncode:raise RuntimeError('Godot snapshot import failed')
 summary=None;images=[];operation=spec['operation'];code=0
 if operation=='regression':
  if not (project/'scripts/test_runner.gd').is_file():raise ValueError('Existing scripts/test_runner.gd required')
  r=godot(['--headless',*base,'-s','res://scripts/test_runner.gd']);code=r.returncode
  rows=re.findall(r'^passed=(\d+) failed=(\d+) total=(\d+)$',r.stdout,re.M)
  if rows:summary=dict(zip(('passed','failed','total'),map(int,rows[-1])))
  if not summary or summary['failed'] or summary['total']<1 or summary['passed']!=summary['total']:code=1
 elif operation in CAPTURES or operation=='capture-scene':
  # capture-scene's deadline_sec (manifest-declared, up to 1080s like Bazzite/local) is passed straight to
  # godot() as a wish, not a guarantee: godot()'s own "remaining" clamp against the single overall Windows Job
  # Object deadline (850s here, under the platform's documented 900s boundary) still applies underneath it.
  if operation=='capture-scene':
   scene,directory,names=spec['scene'],spec['output_directory'],spec['images']
   wish=spec.get('deadline_sec',300)
  else:
   scene,directory,names=CAPTURES[operation]
   wish=300
  if not (project/scene).is_file():raise ValueError('Existing capture scene required')
  r=godot([*base,'--position','-32000,-32000','res://'+scene],wish);code=r.returncode
  for name in names:
   f=project/directory/name
   if not f.is_file():raise ValueError('Expected capture image missing: '+name)
   shutil.copy2(f,out/name);images.append(name)
  if operation=='capture-p7' and len({sha(out/n) for n in images})==1:raise ValueError('Identical ability frames are not valid evidence')
 elif operation!='import':raise ValueError('Unsupported operation; no arbitrary commands')
 errors=[line[:500] for line in '\n'.join(logs).splitlines() if line.startswith(('SCRIPT ERROR:','ERROR:'))]
 limits=current_limit()
 evidence={**limits,'platform':'Windows','engine':version,'engine_files':actual,'runner_sha256':sha(pathlib.Path(__file__)),'operation':operation,'source_sha256':spec['source_sha256'],'source_fingerprint':spec['source_fingerprint'],'source_unchanged':sha(archive)==spec['source_sha256'],'status':'FAIL' if code or errors else 'CAPTURED_VISUAL_REVIEW_PENDING' if images else 'PASS','summary':summary,'runtime_errors':errors[:20],'images':images,'files':images+['godot.log'],'visual_acceptance':False,'snapshot_only':True}
 (out/'worker.json').write_text(json.dumps(evidence,indent=2));return 1 if evidence['status']=='FAIL' else 0
if __name__=='__main__':
 try:sys.exit(execute(pathlib.Path(sys.argv[1])))
 except Exception as e:
  pathlib.Path(sys.argv[1]).parent.joinpath('runner-error.log').write_text(str(e));raise
