"""Install pinned independent upstream projects (Git or owner-requested archive); never execute template code."""
from pathlib import Path
import json,subprocess,hashlib,os,re,time,uuid
from archive import extract,sha
BASE=Path(__file__).parent;spec=json.loads((BASE/'sources.json').read_text());root=Path(spec['root']);root.mkdir(parents=True,exist_ok=True)
if root.resolve()!=root:raise ValueError('Indirect template root')
meta=root/'.catalogue';meta.mkdir(exist_ok=True);(meta/'records').mkdir(exist_ok=True)
def command(args,cwd=None,timeout=600):
 r=subprocess.run(args,cwd=cwd,capture_output=True,text=True,timeout=timeout,env={**os.environ,'GIT_TERMINAL_PROMPT':'0'})
 if r.returncode:raise RuntimeError('Command failed '+args[0]+': '+r.stderr[-600:])
 return r.stdout.strip()
def git(args,cwd=None,timeout=600):return command(['git','-c','core.hooksPath=/dev/null','-c','protocol.file.allow=never',*args],cwd,timeout)
installed=[]
for source in spec['templates']:
 ident=source['id'];target=root/source['category']/ident;record=meta/'records'/(ident+'.json')
 if target.exists():
  if target.is_symlink() or not record.exists():raise ValueError('Existing untracked target protected: '+str(target))
  previous=json.loads(record.read_text())
  if 'archive_sha256' in source:
   files=json.loads((meta/'records'/(ident+'.files.json')).read_text());now={}
   for f in target.rglob('*'):
    if f.is_file() and '.godot' not in f.relative_to(target).parts:now[f.relative_to(target).as_posix()]=sha(f)
   if previous['archive_sha256']!=source['archive_sha256'] or now!=files:raise ValueError('Existing template has changes: '+str(target))
  else:
   actual=git(['rev-parse','HEAD'],target)
   if actual!=previous['commit'] or git(['status','--porcelain'],target):raise ValueError('Existing template has changes: '+str(target))
  installed.append(previous);print('RETAINED '+ident,flush=True);continue
 target.parent.mkdir(exist_ok=True)
 if target.parent.resolve()!=target.parent:raise ValueError('Indirect category')
 incoming=root/'.incoming';incoming.mkdir(exist_ok=True);stage=incoming/(ident+'-'+uuid.uuid4().hex[:12]);stage.mkdir()
 if 'archive_sha256' in source:
  downloads=root/'.downloads'/ident;archive=downloads/source['archive_name']
  if archive.is_symlink() or not archive.is_file():raise ValueError('Download the pinned archive first: '+str(archive))
  digest=sha(archive)
  if digest!=source['archive_sha256']:raise ValueError('Archive hash differs from pinned source: '+digest)
  print('EXTRACTING '+ident,flush=True);extract(archive,stage);commit=None;pointers=[];manifest={}
 else:
  ref=source['ref']
  if ref=='HEAD':
   line=git(['ls-remote',source['repository'],'HEAD']).splitlines()
   if len(line)!=1:raise ValueError('Ambiguous upstream HEAD')
   ref=line[0].split()[0]
  print('FETCHING '+ident,flush=True)
  git(['init','--quiet'],stage);git(['remote','add','origin',source['repository']],stage);git(['fetch','--depth=1','origin',ref],stage);git(['-c','advice.detachedHead=false','checkout','--detach','FETCH_HEAD'],stage)
  commit=git(['rev-parse','HEAD'],stage)
  if not re.fullmatch('[a-f0-9]{40}',commit):raise ValueError('Invalid source commit')
  git(['submodule','update','--init','--recursive','--depth=1'],stage)
  tracked=git(['ls-files','-z'],stage).split('\0');pointers=[];manifest={}
  for name in filter(None,tracked):
   f=stage/name
   if f.is_symlink() and not f.resolve().is_relative_to(stage):raise ValueError('Upstream symlink escapes project: '+name)
   if f.is_file() and not f.is_symlink():
    with f.open('rb') as stream:
     prefix=stream.read(150)
    if prefix.startswith(b'version https://git-lfs.github.com/spec/v1'):pointers.append(name)
  if pointers:git(['lfs','pull'],stage)
 projects=[];licenses=[];file_count=0;byte_count=0
 for directory,dirs,files in os.walk(stage):
  dirs[:]=[n for n in dirs if n not in {'.git','.godot'}]
  for name in files:
   f=Path(directory)/name
   if f.is_symlink():
    if not f.resolve().is_relative_to(stage):raise ValueError('Indirect project dependency')
    continue
   relative=f.relative_to(stage).as_posix();file_count+=1;byte_count+=f.stat().st_size
   with f.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
   manifest[relative]=sha
   if name=='project.godot':projects.append(relative)
   if name.lower().startswith(('license','licence','copying','notice')):licenses.append(relative)
 for name in pointers:
  if (stage/name).read_bytes().startswith(b'version https://git-lfs.github.com/spec/v1'):raise ValueError('Unresolved Git LFS content')
 if not projects:raise ValueError('No Godot project found')
 if not licenses:raise ValueError('No retained license notice found')
 os.rename(stage,target)
 project_files=sorted(projects);primary='project.godot' if 'project.godot' in projects else project_files[0] if len(projects)==1 else None
 features=[]
 if primary:
  text=(target/primary).read_text(errors='replace');features=re.findall(r'config/features=(.*)',text)
 data={**source,'path':str(target),'commit':commit,'requested_ref':source.get('ref'),'installed_at':time.time(),'project_files':project_files,'project_root':str((target/primary).parent) if primary else None,'config_features':features,'license':source.get('license','MIT (repository; retain bundled third-party notices)'),'license_files':sorted(licenses),'file_count':file_count,'bytes':byte_count,'tree_manifest_sha256':hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest(),'runtime_validation':'NOT_TESTED','validation':'Pinned commit, clean checkout, project.godot, license notices, dependency/LFS and contained paths inspected; no engine or template script executed.'}
 if commit is None:
  data.update(archive_name=archive.name,archive_bytes=archive.stat().st_size,validation='Pinned archive SHA-256, contained/non-colliding paths, complete extraction, project.godot and licence notices inspected; no engine or template script executed.')
 (meta/'records'/(ident+'.files.json')).write_text(json.dumps(manifest,indent=2)+'\n');record.write_text(json.dumps(data,indent=2)+'\n');installed.append(data);print('INSTALLED '+ident+' '+(commit or source.get('archive_sha256'))+' '+str(file_count)+' files',flush=True)
catalogue={'schema':'watoom.game-template-catalogue.v1','root':str(root),'generated_at':time.time(),'templates':installed};temporary=root/'.catalogue.json.tmp';temporary.write_text(json.dumps(catalogue,indent=2)+'\n');os.replace(temporary,root/'catalogue.json')
print('CATALOGUE_INSTALLED '+str(len(installed)),flush=True)
