"""Declarative asset capture contract shared by the operator and tests."""
import hashlib,json,math,pathlib,re
from pose_preparation_contract import preparation
MODES={'inspect','still','turntable','animation','pose-inspect','pose-prepare'}

def sha(path):
 h=hashlib.sha256()
 with pathlib.Path(path).open('rb') as f:
  for block in iter(lambda:f.read(1048576),b''):h.update(block)
 return h.hexdigest()

def contained(path,roots,exists=True):
 p=pathlib.Path(path)
 if not p.is_absolute() or p.is_symlink() or p.resolve(strict=exists)!=p or not any(p.is_relative_to(pathlib.Path(x)) for x in roots):raise ValueError('Indirect or out-of-scope path')
 if exists and not p.is_file():raise ValueError('Regular input required')
 return p

def manifest(value,roots):
 if not isinstance(value,dict) or set(value)-{'schema','mode','source','source_sha256','visibility','camera','lighting','resolution','samples','frames','fps','action','armature','pose','output_format','source_asset_id','modifiers','preparation','loop_action'}:raise ValueError('Unsupported capture fields; scripts/commands are forbidden')
 if value.get('schema')!=1 or value.get('mode') not in MODES:raise ValueError('Unsupported capture mode')
 p=contained(value['source'],roots)
 if p.suffix.lower() not in {'.blend','.glb','.gltf'} or p.stat().st_size>1024**3:raise ValueError('Unsupported/oversize source')
 if not re.fullmatch('[a-f0-9]{64}',value.get('source_sha256','')):raise ValueError('Source SHA-256 required')
 def names(values):
  if not isinstance(values,list) or len(values)>256 or any(not isinstance(x,str) or not 1<=len(x)<=256 for x in values) or len(set(values))!=len(values):raise ValueError('Invalid explicit object names')
 visibility=value.get('visibility',{})
 if not isinstance(visibility,dict) or set(visibility)-{'show','hide'}:raise ValueError('Invalid visibility edits')
 for v in visibility.values():names(v)
 if set(visibility.get('show',[]))&set(visibility.get('hide',[])):raise ValueError('Conflicting visibility')
 camera=value.get('camera',{})
 if not isinstance(camera,dict) or set(camera)-{'view','framing','margin','preserve'}:raise ValueError('Invalid camera settings')
 if camera.get('view','front') not in {'front','three-quarter','side','back'} or camera.get('framing','full') not in {'full'}:raise ValueError('Unsupported view/framing')
 if not isinstance(camera.get('margin',1.15),(int,float)) or not 1<=camera.get('margin',1.15)<=2:raise ValueError('Invalid camera margin')
 if value.get('lighting','studio') not in {'studio','preserve'}:raise ValueError('Unsupported lighting')
 resolution=value.get('resolution',[768,1024])
 if not isinstance(resolution,list) or len(resolution)!=2 or any(type(x)!=int or not 64<=x<=2048 for x in resolution):raise ValueError('Resolution budget exceeded')
 if type(value.get('samples',24))!=int or not 1<=value.get('samples',24)<=64:raise ValueError('Sample budget exceeded')
 frames=value.get('frames',[1,1])
 if not isinstance(frames,list) or len(frames)!=2 or any(type(x)!=int for x in frames) or not 0<=frames[1]-frames[0]<=119 or not -10000<=frames[0]<=frames[1]<=10000:raise ValueError('Frame budget exceeded')
 if resolution[0]*resolution[1]*(frames[1]-frames[0]+1)>128*1024**2:raise ValueError('Total frame pixel budget exceeded')
 if type(value.get('fps',24))!=int or not 1<=value.get('fps',24)<=60:raise ValueError('FPS budget exceeded')
 if value.get('output_format','png') not in {'png','mp4'}:raise ValueError('Unsupported output format')
 if not isinstance(value.get('pose',[]),list):raise ValueError('Pose list required')
 if value.get('mode')=='still' and value.get('output_format')=='mp4':raise ValueError('Still capture requires PNG')
 if value.get('output_format')=='mp4' and (any(x%2 for x in resolution) or frames[1]<=frames[0]):raise ValueError('MP4 requires even dimensions and at least two frames')
 for item in value.get('pose',[]):
  if not isinstance(item,dict):raise ValueError('Pose entries must be objects')
  if set(item)!={'armature','bone','rotation_euler'} or not all(isinstance(item[k],str) and 0<len(item[k])<256 for k in ('armature','bone')):raise ValueError('Invalid pose selector')
  angles=item['rotation_euler']
  if not isinstance(angles,list) or len(angles)!=3 or any(not isinstance(x,(int,float)) or not math.isfinite(x) or abs(x)>math.pi for x in angles):raise ValueError('Invalid pose angles')
 if len(value.get('pose',[]))>128:raise ValueError('Pose budget exceeded')
 if any(k in value and (not isinstance(value[k],str) or not 1<=len(value[k])<=256) for k in ('action','armature')):raise ValueError('Invalid Action selector')
 edits=value.get('modifiers',[])
 if not isinstance(edits,list) or len(edits)>64:raise ValueError('Modifier edit budget')
 for edit in edits:
  if not isinstance(edit,dict) or set(edit)!={'object','name','enabled'} or type(edit['enabled'])!=bool or any(not isinstance(edit[k],str) or not 1<=len(edit[k])<=256 for k in ('object','name')):raise ValueError('Invalid modifier edit')
 if value.get('action') and not value.get('armature'):raise ValueError('Action owner required')
 if 'loop_action' in value:
  if type(value['loop_action'])!=bool or value['mode']!='animation' or not value.get('action') or value.get('pose'):raise ValueError('Action looping requires animation/explicit Action and no pose overrides')
 preparation(value)
 if value.get('preparation',{}).get('method')=='ts4-retarget':
  plan=value['preparation']['plan'];clip=contained(plan['clip'],roots)
  if clip.suffix.lower() not in {'.clip','.resource'} or clip.stat().st_size>64*1024**2 or sha(clip)!=plan['clip_sha256']:raise ValueError('Pinned TS4 clip input mismatch/budget')
 return value

def native_proof(message,request):
 for part in message.get('content',[]):
  state=part.get('state',{});md=state.get('metadata',{}) or {}
  if part.get('type')=='tool' and part.get('name')=='watoom_asset_capture' and part.get('id')==request['call_id'] and state.get('status')=='completed' and state.get('input')=={'action':'request','job':request['job']} and all(md.get(k)==request[k] for k in ('request_id','project','job','manifest_sha256')):return True
 return False
