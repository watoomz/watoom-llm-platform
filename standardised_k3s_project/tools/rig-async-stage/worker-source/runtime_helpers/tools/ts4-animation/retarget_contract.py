import re,json
from pathlib import Path
SCHEMA='watoom.ts4.retarget.v1'
PROFILE_DIR=Path(__file__).resolve().parents[2]/'ansible/roles/watoom-code/files/skills/human-pose-agent/references/adapters'
RUNTIME_PROFILE_DIR=Path('/data/ai/watoom-code/config/skills/human-pose-agent/references/adapters')
def profile_path(profile_id):
 if not isinstance(profile_id,str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,95}',profile_id):raise ValueError('Invalid retarget profile id')
 for folder in (PROFILE_DIR,RUNTIME_PROFILE_DIR):
  path=folder/(profile_id+'.json')
  if path.is_symlink():raise ValueError('Symlink profile forbidden')
  if path.exists():return path
 raise ValueError('Unknown retarget profile')
def load_profile(profile_id,armature):
 if not isinstance(profile_id,str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,95}',profile_id):raise ValueError('Invalid retarget profile id')
 if profile_id=='ts4-af-shadowheart-mhx-v1':
  if armature!='Shadowheart':raise ValueError('Unqualified retarget armature')
  return None
 path=profile_path(profile_id)
 if path.is_symlink() or not path.is_file() or path.stat().st_size>1024*1024:raise ValueError('Unknown or oversized retarget profile')
 profile=json.loads(path.read_text())
 if profile.get('id')!=profile_id or profile.get('armature')!=armature:raise ValueError('Retarget profile identity mismatch')
 if type(profile.get('bone_count'))!=int or not 1<=profile['bone_count']<=4096:raise ValueError('Invalid profile bone count')
 bones=profile.get('bones');switches=profile.get('switches');drivers=profile.get('drivers')
 if not isinstance(bones,list) or not bones or not isinstance(switches,dict) or not switches or not isinstance(drivers,list):raise ValueError('Rig fingerprint data required')
 if any(not isinstance(b,dict) or not isinstance(b.get('name'),str) or not {'name','parent','rest','lock_rotation','lock_location','rotation_mode','constraints'}<=set(b) for b in bones):raise ValueError('Incomplete rig fingerprint')
 names={b['name'] for b in bones}
 if len(names)!=len(bones) or any(not isinstance(v,str) or not v for v in switches.values()):raise ValueError('Invalid rig fingerprint')
 cfg=profile.get('retarget',{})
 if not isinstance(cfg,dict) or set(cfg)!={'mapping','scope'}:raise ValueError('Explicit retarget mapping and scope required')
 mapping=cfg['mapping']
 if not isinstance(mapping,dict) or not 1<=len(mapping)<=128:raise ValueError('Invalid retarget mapping')
 if any(not isinstance(k,str) or not re.fullmatch(r'b__[A-Za-z0-9_]+__',k) or not isinstance(v,str) or v not in names for k,v in mapping.items()):raise ValueError('Unfingerprinted retarget control')
 if len(set(mapping.values()))!=len(mapping):raise ValueError('Duplicate retarget controls')
 source_names={b['name'] for b in json.loads(Path(__file__).with_name('source-rig-af-v1.json').read_text())['rig']['bones']}
 if set(mapping)-source_names:raise ValueError('Unknown source skeleton bone')
 if mapping.get('b__ROOT_bind__')!='hip' or mapping.get('b__Head__')!='neckhead':raise ValueError('Current engine requires hip and neckhead root/head mappings')
 if not isinstance(cfg['scope'],str) or not 1<=len(cfg['scope'])<=2048:raise ValueError('Retarget limitations required')
 return profile
def validate(plan):
 if not isinstance(plan,dict) or set(plan)!={'schema','armature','clip','clip_sha256','profile','start_tick','end_tick','root_motion'}:raise ValueError('Exact retarget plan fields required')
 if plan['schema']!=SCHEMA:raise ValueError('Unqualified retarget schema')
 load_profile(plan['profile'],plan['armature'])
 if not isinstance(plan['clip'],str) or not Path(plan['clip']).is_absolute() or not re.fullmatch('[a-f0-9]{64}',plan['clip_sha256']):raise ValueError('Absolute pinned binary clip required')
 if any(type(plan[k])!=int for k in ['start_tick','end_tick']) or not 0<=plan['start_tick']<plan['end_tick']<=10000 or plan['end_tick']-plan['start_tick']>119:raise ValueError('Retarget range must be 2..120 frames')
 if plan['root_motion'] not in ['in-place','scaled']:raise ValueError('Unsupported root motion')
 return plan
