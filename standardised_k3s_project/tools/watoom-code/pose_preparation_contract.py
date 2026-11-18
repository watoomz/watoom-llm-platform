"""Fixed pose payload contract; no script paths or executable input."""
import math,json

def preparation(v):
 modes={'pose-inspect','pose-prepare'}
 if v['mode'] not in modes:
  if 'preparation' in v:raise ValueError('Preparation requires a pose mode')
  return
 if set(v)-{'schema','mode','source','source_sha256','source_asset_id','preparation'}:raise ValueError('Pose jobs accept source and fixed preparation only')
 if not v['source'].endswith('.blend'):raise ValueError('Pose helper requires .blend')
 if v['mode']=='pose-inspect':
  if 'preparation' in v:raise ValueError('Inspection cannot apply a pose')
  return
 cfg=v.get('preparation')
 if not isinstance(cfg,dict) or set(cfg)!={'method','plan'} or cfg['method'] not in {'auto','recipe','rig-adapter','ts4-retarget','retarget'}:raise ValueError('Fixed auto, recipe, rig-adapter, ts4-retarget or retarget method required')
 plan=cfg['plan']
 if not isinstance(plan,dict) or len(json.dumps(plan))>49152:raise ValueError('Pose plan budget')
 def finite(x,depth=0):
  if depth>12:raise ValueError('Pose plan depth budget')
  if isinstance(x,dict):
   if len(x)>256 or any(not isinstance(k,str) or len(k)>256 for k in x):raise ValueError('Pose map budget')
   for val in x.values():finite(val,depth+1)
  elif isinstance(x,list):
   if len(x)>256:raise ValueError('Pose array budget')
   for val in x:finite(val,depth+1)
  elif type(x) in (int,float):
   if not math.isfinite(x) or abs(x)>1000000:raise ValueError('Pose finite numeric budget')
  elif not isinstance(x,(str,bool,type(None))) or isinstance(x,str) and len(x)>1024:raise ValueError('Pose value budget')
 finite(plan)
 if cfg['method']=='retarget':
  # watoom.retarget.v3 (or an upgraded v2 plan): any TS4 skeleton or Blender Action onto any humanoid/quadruped armature.
  import sys,pathlib
  sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'ts4-animation'))
  from retarget_contract import validate_v3
  validate_v3(plan);return
 if not isinstance(plan.get('armature'),str) or not 1<=len(plan['armature'])<=256:raise ValueError('Exact armature required')
 if type(plan.get('frame',1))!=int or not -10000<=plan.get('frame',1)<=10000:raise ValueError('Pose frame budget')
 if cfg['method']=='ts4-retarget':
  import sys,pathlib
  sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'ts4-animation'))
  from retarget_contract import validate
  validate(plan);return
 if cfg['method']=='rig-adapter':
  from rig_pose_contract import validate
  validate(plan);return
 if cfg['method']=='recipe':
  if set(plan)-{'schema','armature','frame','calibration_verified','human_reviewed','poses'} or plan.get('schema')!='watoom.human_pose_recipe.v1':raise ValueError('Recipe schema')
  if plan.get('calibration_verified') is not True or plan.get('human_reviewed') is not True:raise ValueError('Actual calibration and human review required')
  poses=plan.get('poses')
  if not isinstance(poses,dict) or not 1<=len(poses)<=128:raise ValueError('Recipe bone budget')
  for channels in poses.values():
   if not isinstance(channels,dict) or not channels or set(channels)-{'rotation_quaternion','location'}:raise ValueError('Unsupported recipe channels')
   for key,size in [('rotation_quaternion',4),('location',3)]:
    if key in channels and (not isinstance(channels[key],list) or len(channels[key])!=size or any(type(n) not in (int,float) for n in channels[key])):raise ValueError('Invalid recipe vector')
 else:
  if set(plan)-{'schema','armature','frame','role_overrides','targets','settings'} or plan.get('schema')!='watoom.human_pose_auto_plan.v1':raise ValueError('Auto plan schema')
  targets=plan.get('targets');settings=plan.get('settings',{})
  if not isinstance(targets,dict) or not 1<=len(targets)<=8 or not isinstance(settings,dict):raise ValueError('Auto target budget')
  for target in targets.values():
   if not isinstance(target,dict) or set(target)-{'point','pole','orientation_world_quat'} or 'point' not in target:raise ValueError('Auto target fields')
   for key,vec in target.items():
    if not isinstance(vec,list) or len(vec)!=(4 if key=='orientation_world_quat' else 3) or any(type(n) not in (int,float) for n in vec):raise ValueError('Auto target vector')
  allowed={'world_up','iterations','endpoint_tolerance','ground_z','ground_penetration_tolerance','balance_margin','static_pose','check_mesh_collisions','max_collision_faces_per_mesh','full_body_passes','orientation_tolerance_rad','joint_limits','max_self_collision_candidates','limb_capsule_radius_factor','exclude_environment_objects'}
  if set(settings)-allowed:raise ValueError('Unsupported solver settings')
  for key,default,maximum in [('iterations',90,180),('full_body_passes',5,8),('max_collision_faces_per_mesh',60000,60000),('max_self_collision_candidates',100000,100000)]:
   val=settings.get(key,default)
   if type(val)!=int or not 1<=val<=maximum:raise ValueError('Solver work budget: '+key)
