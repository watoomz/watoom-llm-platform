"""Fixed staged Godot operations, independent of Blender capture schemas."""
import pathlib,re,hashlib,json
OPS={'import','regression','capture','capture-p7','capture-scene'}
# capture-scene carries its own declarative job (dispatcher.py reads it via capture_spec.load() on the live
# project before freezing, the same way the Linux bridge does) instead of using a fixed built-in scene.
CAPTURE_SCENE_EXTRA={'job','scene','output_directory','images','deadline_sec'}
def validate_game(v,projects):
 base={'kind','mode','project','operation','source','source_sha256','source_fingerprint'}
 required=base|CAPTURE_SCENE_EXTRA if v.get('operation')=='capture-scene' else base
 if set(v)!=required or v['kind']!='godot' or v['mode']!='game' or v['operation'] not in OPS:raise ValueError('Invalid staged game manifest')
 if v['operation']=='capture-scene':
  if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}',v['job']):raise ValueError('Invalid capture-scene job')
  if not isinstance(v['scene'],str) or not v['scene'].endswith('.tscn') or v['scene'].startswith('/') or '..' in pathlib.PurePosixPath(v['scene']).parts:raise ValueError('Invalid capture-scene scene')
  if not isinstance(v['output_directory'],str) or not v['output_directory'].startswith('.opencode/captures/'):raise ValueError('Invalid capture-scene output_directory')
  if not isinstance(v['images'],list) or not 1<=len(v['images'])<=32 or any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,100}\.png',n) for n in v['images']) or len(set(v['images']))!=len(v['images']):raise ValueError('Invalid capture-scene images')
  if not isinstance(v['deadline_sec'],int) or isinstance(v['deadline_sec'],bool) or not 60<=v['deadline_sec']<=1080:raise ValueError('Invalid capture-scene deadline_sec')
 if v['project'] not in projects:raise ValueError('Game project not authorized')
 for key in ('source_sha256','source_fingerprint'):
  if not re.fullmatch(r'[a-f0-9]{64}',v[key]):raise ValueError('Invalid game identity')
 source=pathlib.Path(v['source']);expected=pathlib.Path(v['project'])/'.opencode/rig-job-snapshots'
 if source.parent!=expected or not re.fullmatch(r'[a-f0-9]{64}\.zip',source.name) or source.is_symlink() or source.resolve()!=source or not source.is_file() or source.stat().st_size>2*1024**3:raise ValueError('Invalid frozen game input')
 with source.open('rb') as f:
  if hashlib.file_digest(f,'sha256').hexdigest()!=v['source_sha256']:raise ValueError('Game archive changed')
 return source

def verify_evidence(spec,v,files,out):
 profile=json.loads(pathlib.Path(__file__).with_name('game-runtime-provenance.json').read_text())
 if v.get('source_sha256')!=spec['source_sha256'] or v.get('source_fingerprint')!=spec['source_fingerprint'] or v.get('operation')!=spec['operation']:raise ValueError('Game receipt revision mismatch')
 if v.get('platform')!='Windows' or v.get('memory_limit_verified') is not True or v.get('memory_limit_bytes')!=8*1024**3:raise ValueError('Game Windows boundary missing')
 if v.get('engine')!='4.7.2.stable.official.ed1daf0bf' or v.get('engine_files')!=profile['files']:raise ValueError('Unpinned Godot engine')
 if v.get('runner_sha256')!=hashlib.sha256(pathlib.Path(__file__).with_name('game_runner.py').read_bytes()).hexdigest():raise ValueError('Unpinned game runner')
 if v.get('status') not in ('PASS','CAPTURED_VISUAL_REVIEW_PENDING') or v.get('runtime_errors'):raise ValueError('Game did not pass technical checks')
 if spec['operation']=='regression':
  s=v.get('summary') or {}
  if not s.get('total') or s.get('failed')!=0 or s.get('passed')!=s['total']:raise ValueError('Missing/pending game regression summary')
 if spec['operation'].startswith('capture'):
  import struct
  images=v.get('images',[])
  if not images or any(name not in files for name in images):raise ValueError('Game capture images missing')
  for name in images:
   with (out/name).open('rb') as f:h=f.read(24)
   if h[:8]!=bytes([137,80,78,71,13,10,26,10]) or min(struct.unpack('>II',h[16:24]))<16:raise ValueError('Invalid game PNG')
