"""Project-neutral declarative capture contract; no caller shell or engine arguments."""
import pathlib,json,hashlib,re

def load(project,job):
 project=pathlib.Path(project)
 if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}',job):raise ValueError('Invalid capture job')
 path=project/'.opencode/capture-jobs'/job/'request.json'
 if path.is_symlink() or path.resolve()!=path or path.stat().st_size>32768:raise ValueError('Indirect/oversize capture manifest')
 raw=path.read_bytes();v=json.loads(raw)
 if set(v)-{'deadline_sec'}!={'schema','scene','inputs','output_directory','images'} or v['schema']!=1:raise ValueError('Invalid declarative capture schema')
 # Bounded so the run, its 30s grace and the bridge fit the worker unit's 20 min start limit.
 deadline=v.get('deadline_sec',600)
 if isinstance(deadline,bool) or not isinstance(deadline,(int,float)) or deadline!=int(deadline) or not 60<=deadline<=1080:raise ValueError('deadline_sec must be an integer 60-1080')
 deadline=int(deadline)
 def relative(s,field):
  if not isinstance(s,str) or not re.fullmatch('[A-Za-z0-9_./-]+',s) or s.startswith('/') or '..' in pathlib.PurePosixPath(s).parts or str(pathlib.PurePosixPath(s))!=s:
   raise ValueError(field+' '+json.dumps(s)+' is not a normalised project-relative path: letters, digits and _ . / - only, no leading or trailing slash, no // and no .. segments')
  return s
 scene=relative(v['scene'],'scene');directory=relative(v['output_directory'],'output_directory')
 if not scene.endswith('.tscn') or not directory.startswith('.opencode/captures/'):raise ValueError('scene must be a .tscn file and output_directory must be under .opencode/captures/')
 if not isinstance(v['inputs'],list) or not 1<=len(v['inputs'])<=128 or scene not in v['inputs'] or len(set(v['inputs']))!=len(v['inputs']):raise ValueError('Capture inputs required')
 if not isinstance(v['images'],list) or not 1<=len(v['images'])<=32 or len(set(v['images']))!=len(v['images']) or any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,100}\.png',n) for n in v['images']):raise ValueError('Expected PNG names required')
 rows=[]
 for name in sorted(v['inputs']):
  f=project/relative(name,'inputs entry')
  if f.resolve()!=f or not f.is_file() or f.is_symlink() or f.stat().st_size>64*1024**2:raise ValueError('Unsafe capture input')
  rows.append([name,hashlib.sha256(f.read_bytes()).hexdigest()])
 sha=hashlib.sha256(json.dumps([hashlib.sha256(raw).hexdigest(),rows],separators=(',',':')).encode()).hexdigest()
 return {**v,'directory':directory,'names':v['images'],'deadline_sec':deadline,'memory_gib':4,'capture_spec_sha256':sha}
def revision(project,job,base):
 return hashlib.sha256(json.dumps([base,load(project,job)['capture_spec_sha256']],separators=(',',':')).encode()).hexdigest()
