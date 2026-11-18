"""Fixed TS4 parent-local Action importer / MHX rest-space rotation retargeter."""
import bpy,json,math,hashlib,sys,importlib.util
from pathlib import Path
from mathutils import Matrix,Quaternion,Vector,Euler
from bisect import bisect_right
sys.path.insert(0,str(Path(__file__).parent))
from codec import decode
from retarget_contract import validate,load_profile,profile_path
ROOT=Path(__file__).resolve().parents[2]
ADAPTER=ROOT/'ansible/roles/watoom-code/files/skills/human-pose-agent/scripts/rig_adapter.py'
PROFILE=Path(__file__).with_name('source-rig-af-v1.json')
MAPPING={'b__ROOT_bind__':'hip','b__Spine0__':'spine','b__Spine2__':'chest','b__Head__':'neckhead'}
for side in ['L','R']:
 for src,dst in [('UpperArm','upper_arm'),('Forearm','forearm'),('Hand','hand'),('Thigh','thigh'),('Calf','shin'),('Foot','foot'),('Toe','toe')]:MAPPING[f'b__{side}_{src}__']=f'{dst}.fk.{side}'
def fnv(name):
 value=0x811c9dc5
 for byte in name.lower().encode():value=((value*0x01000193)&0xffffffff)^byte
 return f'{value:08X}'
def interpolate(track,tick,rotation=False):
 frames=track['frames'];times=[f['tick'] for f in frames];i=max(0,bisect_right(times,tick)-1);a=frames[i];b=frames[min(i+1,len(frames)-1)];weight=0 if a['tick']==b['tick'] else max(0,min(1,(tick-a['tick'])/(b['tick']-a['tick'])))
 if rotation:
  qa=Quaternion((a['values'][3],*a['values'][:3]));qb=Quaternion((b['values'][3],*b['values'][:3]))
  if abs(qa.magnitude-1)>.03 or abs(qb.magnitude-1)>.03:raise ValueError('Invalid source quaternion norm')
  return qa.normalized().slerp(qb.normalized(),weight)
 return Vector(a['values']).lerp(Vector(b['values']),weight)
def assign(rig,bone,matrix):
 kwargs={}
 if bone.parent:kwargs={'parent_matrix':bone.parent.matrix,'parent_matrix_local':bone.parent.bone.matrix_local}
 bone.matrix_basis=bone.bone.convert_local_to_pose(matrix,bone.bone.matrix_local,invert=True,**kwargs)
 rig.update_tag();bpy.context.view_layer.update()
def angle_error(a,b):
 # Quaternion signs represent the same rotation.
 return 2*math.acos(min(1.0,max(0.0,abs(a.normalized().dot(b.normalized())))))
def clamp_authored_limits(rig,bone):
 changes=[]
 # Only local, full-influence authored limits can be projected predictably.
 for c in bone.constraints:
  if c.mute or c.influence==0:continue
  if c.type!='LIMIT_ROTATION' or c.owner_space!='LOCAL' or abs(c.influence-1)>1e-6:continue
  if any(d.data_path.startswith(c.path_from_id()) for d in rig.animation_data.drivers):continue
  order=getattr(c,'euler_order','AUTO')
  if order=='AUTO':order=bone.rotation_mode if bone.rotation_mode in ['XYZ','XZY','YXZ','YZX','ZXY','ZYX'] else 'XYZ'
  q=bone.matrix_basis.to_quaternion();e=q.to_euler(order);before=list(e)
  for i,axis in enumerate('xyz'):
   if getattr(c,'use_limit_'+axis):
    e[i]=max(getattr(c,'min_'+axis),min(getattr(c,'max_'+axis),e[i]))
  if angle_error(q,e.to_quaternion())>1e-6:
   loc,_,scale=bone.matrix_basis.decompose()
   bone.matrix_basis=Matrix.LocRotScale(loc,e.to_quaternion(),scale)
   changes.append({'constraint':c.name,'order':order,'requested_local_euler':before,'applied_local_euler':list(e)})
 if changes:rig.update_tag();bpy.context.view_layer.update()
 return changes
def unconstrained_pose_rotation(bone):
 kwargs={}
 if bone.parent:kwargs={'parent_matrix':bone.parent.matrix,'parent_matrix_local':bone.parent.bone.matrix_local}
 return bone.bone.convert_local_to_pose(bone.matrix_basis,bone.bone.matrix_local,**kwargs).to_quaternion()
def prepare(plan,out):
 # Preserve a machine-readable reason even for early validation/decode failures.
 out=Path(out)
 try:return _prepare(plan,out)
 except Exception as exc:
  path=out/'retarget-diagnostics.json'
  details=json.loads(path.read_text()) if path.exists() else {}
  details.update(status='FAIL',error=str(exc),error_type=type(exc).__name__,profile=plan.get('profile'),requires_visual_review=True)
  path.write_text(json.dumps(details,indent=2))
  raise
def curves(action,rig):
 import bpy_extras.anim_utils
 bag=bpy_extras.anim_utils.action_get_channelbag_for_slot(action,rig.animation_data.action_slot)
 return list(bag.fcurves) if bag else []
def _prepare(plan,out):
 validate(plan);selected=load_profile(plan['profile'],plan['armature']);mapping=selected['retarget']['mapping'] if selected else MAPPING;out=Path(out);binary=Path(plan['clip']).read_bytes()
 if len(binary)>64*1024**2 or hashlib.sha256(binary).hexdigest()!=plan['clip_sha256']:raise ValueError('Pinned clip revision mismatch')
 doc=decode(binary)
 if plan['end_tick']>=doc['ticks']:raise ValueError('Clip range exceeds duration')
 fps=round(1/doc['tick_seconds'])
 if fps not in [24,25,30,60] or abs(fps*doc['tick_seconds']-1)>1e-5:raise ValueError('Unsupported tick rate')
 rows=json.loads(PROFILE.read_text())['rig']['bones'];source_names={fnv(b['name']):b['name'] for b in rows}
 if len(source_names)!=len(rows):raise ValueError('Source bone hash collision')
 tracks={};ignored=[]
 for track in doc['tracks']:
  name=source_names.get(track['bone_hash'])
  if name is None or track['semantic'] not in [1,2]:ignored.append({'hash':track['bone_hash'],'semantic':track['semantic'],'reason':'unknown source track'});continue
  if name not in mapping:ignored.append({'hash':track['bone_hash'],'bone':name,'semantic':track['semantic'],'reason':'source Action only; no dedicated target control'})
  tracks[(name,track['semantic'])]=track
 if not tracks:raise ValueError('No recognized TS4 skeleton tracks')
 rig=bpy.data.objects.get(plan['armature']);spec=importlib.util.spec_from_file_location('fixed_mhx_adapter',ADAPTER);adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
 profile=selected or json.loads(adapter.PROFILE.read_text());errors,fingerprint=adapter.profile_check(rig,profile)
 if errors:raise ValueError('; '.join(errors))
 if any(n not in rig.pose.bones for n in mapping.values()):raise ValueError('Mapped control absent')
 saved_constraints=adapter.constraint_state(rig);saved_drivers=adapter.driver_state(rig)
 rig.animation_data_create();rig.animation_data.action=None
 for nla in rig.animation_data.nla_tracks:nla.mute=True
 for bone in rig.pose.bones:bone.matrix_basis=Matrix.Identity(4)
 for key in profile['switches'].values():rig[key]=0.0
 rig.update_tag();bpy.context.view_layer.update()
 action=bpy.data.actions.new('TS4_Retarget_Shadowheart');rig.animation_data.action=action;action.use_fake_user=True
 data=bpy.data.armatures.new('TS4_Reference');source=bpy.data.objects.new('TS4_Imported_Source',data);bpy.context.scene.collection.objects.link(source);bpy.context.view_layer.objects.active=source;source.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
 for row in rows:
  b=data.edit_bones.new(row['name']);b.head=Matrix(row['rest']).translation;b.tail=b.head+Vector((0,0,.001));b.matrix=Matrix(row['rest']);b.length=.001
 for row in rows:
  if row['parent']:data.edit_bones[row['name']].parent=data.edit_bones[row['parent']]
 bpy.ops.object.mode_set(mode='OBJECT');source.animation_data_create();source.animation_data.action=bpy.data.actions.new('TS4_Imported_Source_Action');source.animation_data.action.use_fake_user=True
 rest={b['name']:Matrix(b['rest']) for b in rows};locals={b['name']:(rest[b['parent']].inverted()@rest[b['name']] if b['parent'] else rest[b['name']]) for b in rows}
 scale=rig.data.bones['hip'].matrix_local.translation.z/rest['b__ROOT_bind__'].translation.z
 samples=[];diagnostics=[];reference_root=None;previous={};start=plan['start_tick'];end=plan['end_tick'];scene=bpy.context.scene;scene.render.fps=fps;scene.frame_start=1;scene.frame_end=end-start+1
 for tick in range(start,end+1):
  frame=tick-start+1;scene.frame_set(frame);matrices={}
  for row in rows:
   name=row['name'];local=locals[name];location=interpolate(tracks[(name,1)],tick) if (name,1) in tracks else local.translation;rotation=interpolate(tracks[(name,2)],tick,True) if (name,2) in tracks else local.to_quaternion();matrix=Matrix.LocRotScale(location,rotation,Vector((1,1,1)));matrices[name]=matrices[row['parent']]@matrix if row['parent'] else matrix
   bone=source.pose.bones[name];kwargs={'parent_matrix':matrices[row['parent']],'parent_matrix_local':rest[row['parent']]} if row['parent'] else {};bone.matrix_basis=bone.bone.convert_local_to_pose(matrices[name],bone.bone.matrix_local,invert=True,**kwargs);bone.rotation_mode='QUATERNION';bone.keyframe_insert('location',frame=frame);bone.keyframe_insert('rotation_quaternion',frame=frame)
  if reference_root is None:reference_root=matrices['b__ROOT_bind__'].translation.copy()
  frame_errors=[]
  for name,target in mapping.items():
   bone=rig.pose.bones[target];delta=matrices[name].to_quaternion()@rest[name].to_quaternion().inverted();rotation=delta@bone.bone.matrix_local.to_quaternion();desired=bone.matrix.copy();desired=Matrix.LocRotScale(desired.translation,rotation,Vector((1,1,1)))
   if target=='hip' and plan['root_motion']=='scaled':desired.translation=bone.bone.matrix_local.translation+(matrices[name].translation-reference_root)*scale
   assign(rig,bone,desired)
   projected=clamp_authored_limits(rig,bone)
   expected=unconstrained_pose_rotation(bone) if projected else rotation
   if bone.rotation_mode=='QUATERNION':
    q=bone.rotation_quaternion
    if target in previous and q.dot(previous[target])<0:q.negate()
    previous[target]=q.copy();bone.rotation_quaternion=q;channel='rotation_quaternion'
   elif bone.rotation_mode in ['XYZ','XZY','YXZ','YZX','ZXY','ZYX']:
    e=bone.rotation_euler
    if target in previous:e.make_compatible(previous[target])
    previous[target]=e.copy();bone.rotation_euler=e;channel='rotation_euler'
   else:raise ValueError('Unqualified axis-angle control')
   bone.keyframe_insert(channel,frame=frame)
   if target=='hip':bone.keyframe_insert('location',frame=frame)
   angular=angle_error(bone.matrix.to_quaternion(),expected);frame_errors.append(angular)
   requested_error=angle_error(bone.matrix.to_quaternion(),rotation)
   if projected or angular>.03:
    diagnostics.append({'frame':frame,'source_tick':tick,'source_bone':name,'target_control':target,'requested_error_rad':requested_error,'residual_error_rad':angular,'clamped_limits':projected,'constraints':[{'name':c.name,'type':c.type,'space':c.owner_space,'influence':c.influence,'mute':c.mute} for c in bone.constraints]})
  for key in profile['switches'].values():rig.keyframe_insert(data_path='["'+key+'"]',frame=frame)
  samples.append({'frame':frame,'max_control_angle_error':max(frame_errors),'control_matrices':{n:[list(r) for r in rig.pose.bones[n].matrix] for n in mapping.values()},'head_matrix':[list(r) for r in rig.pose.bones['neckhead'].matrix],'deform_head_matrix':[list(r) for r in rig.pose.bones['head'].matrix] if 'head' in rig.pose.bones else None})
 diagnostic={'status':'LIMITED_REVIEW_PENDING' if diagnostics else 'PREPARED_REVIEW_PENDING','profile':plan['profile'],'rotation_tolerance_rad':.03,'events':diagnostics,'requires_visual_review':True}
 (out/'retarget-diagnostics.json').write_text(json.dumps(diagnostic,indent=2))
 failures=[d for d in diagnostics if d['residual_error_rad']>.03]
 if failures:
  first=failures[0]
  raise ValueError('Unresolved control rotation: '+first['target_control']+' at frame '+str(first['frame'])+' (residual '+format(first['residual_error_rad'],'.6f')+' rad); see retarget-diagnostics.json')
 for owner in [rig,source]:
  for fc in curves(owner.animation_data.action,owner):
   for key in fc.keyframe_points:key.interpolation='LINEAR'
 if adapter.constraint_state(rig)!=saved_constraints or adapter.driver_state(rig)!=saved_drivers:raise ValueError('Constraints or drivers changed')
 source.hide_render=True;source.hide_set(True);scene.frame_set(1)
 bpy.ops.wm.save_as_mainfile(filepath=str(out/'posed.blend'))
 bpy.ops.wm.open_mainfile(filepath=str(out/'posed.blend'),load_ui=False,use_scripts=False);rig=bpy.data.objects[plan['armature']];reopened=[]
 for sample in samples:
  scene=bpy.context.scene;scene.frame_set(sample['frame']);bpy.context.view_layer.update();actual=rig.pose.bones['neckhead'].matrix
  error=max(abs(rig.pose.bones[n].matrix[i][j]-expected[i][j]) for n,expected in sample['control_matrices'].items() for i in range(4) for j in range(4));reopened.append(error)
 if max(reopened)>1e-4:raise ValueError('Saved Action evaluation differs after reopening')
 result={'status':'PREPARED_REVIEW_PENDING','adapter':plan['profile'],'action':rig.animation_data.action.name,'source_action':'TS4_Imported_Source_Action','frames':[1,end-start+1],'fps':fps,'mapped_controls':mapping,'unmapped_source_tracks':ignored,'scope':selected['retarget']['scope'] if selected else 'Body rotations; optional root displacement. No finger/face, IK contacts, prop or clothing correction. Reference skeleton compatibility requires review.','source_clip_sha256':plan['clip_sha256'],'adapter_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'source_profile_sha256':hashlib.sha256(PROFILE.read_bytes()).hexdigest(),'target_profile_sha256':hashlib.sha256(profile_path(plan['profile']).read_bytes() if selected else adapter.PROFILE.read_bytes()).hexdigest(),'rig_fingerprint':fingerprint,'samples':samples,'constraint_limited':bool(diagnostics),'constraint_events':diagnostics,'saved_reopen_max_error':max(reopened),'requires_visual_review':True}
 (out/'retarget-evidence.json').write_text(json.dumps(result,indent=2));(out/'pose-validation.json').write_text(json.dumps({'status':'PREPARED_REVIEW_PENDING','retarget_evidence':'retarget-evidence.json','constraint_limited':bool(diagnostics),'diagnostics':'retarget-diagnostics.json','warning':'Authored joint limits changed requested motion; review actual output' if diagnostics else None}));return result
