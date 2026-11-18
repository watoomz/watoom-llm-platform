"""Trusted Blender-side capture implementation; entered only inside the 4GiB unit."""
import sys,json,math,pathlib,time,subprocess
import bpy
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from mathutils import Vector

def cgroup():
 line=next(x for x in pathlib.Path('/proc/self/cgroup').read_text().splitlines() if x.startswith('0::'))
 root=pathlib.Path('/sys/fs/cgroup')/line[3:].lstrip('/')
 return root,(root/'memory.max').read_text().strip()

def bounds(objects):
 points=[];deps=bpy.context.evaluated_depsgraph_get()
 for obj in objects:
  evaluated=obj.evaluated_get(deps)
  points.extend(evaluated.matrix_world@Vector(corner) for corner in evaluated.bound_box)
 if not points:raise ValueError('No visible geometry in selected scene')
 low=Vector([min(v[i] for v in points) for i in range(3)]);high=Vector([max(v[i] for v in points) for i in range(3)])
 if not all(math.isfinite(x) for x in (*low,*high)):raise ValueError('Nonfinite scene bounds')
 return low,high

def aim(obj,target):obj.rotation_euler=(target-obj.location).to_track_quat('-Z','Y').to_euler()

def inventory():
 rows=[]
 for obj in bpy.context.scene.objects:
  row={'name':obj.name,'type':obj.type,'hide_render':obj.hide_render,'hide_viewport':obj.hide_viewport,'dimensions':list(obj.dimensions),'matrix_world':[list(row) for row in obj.matrix_world]}
  if obj.type=='MESH':row.update(vertices=len(obj.data.vertices),polygons=len(obj.data.polygons),materials=[s.material.name if s.material else None for s in obj.material_slots],modifiers=[{'type':m.type,'object':getattr(getattr(m,'object',None),'name',None),'name':m.name,'render':m.show_render,'viewport':m.show_viewport,'vertex_group':getattr(m,'vertex_group',None)} for m in obj.modifiers],uvs=[x.name for x in obj.data.uv_layers],shape_keys=[{'name':k.name,'value':k.value} for k in obj.data.shape_keys.key_blocks] if obj.data.shape_keys else [])
  if obj.type=='ARMATURE':
   details=[]
   for bone in list(obj.pose.bones)[:1024]:
    details.append({'name':bone.name,'parent':bone.parent.name if bone.parent else None,'deform':bone.bone.use_deform,'rotation_mode':bone.rotation_mode,'rotation_euler':list(bone.rotation_euler),'location':list(bone.location),'head':list(bone.head),'tail':list(bone.tail),'rest_matrix':[list(row) for row in bone.bone.matrix_local],'lock_rotation':list(bone.lock_rotation),'constraints':[{'name':c.name,'type':c.type,'influence':c.influence,'mute':c.mute,'target':getattr(getattr(c,'target',None),'name',None),'subtarget':getattr(c,'subtarget',None)} for c in bone.constraints]})
   row.update(bones=[b.name for b in obj.data.bones][:1024],bone_count=len(obj.data.bones),pose_bones=details,controls=[b.name for b in obj.pose.bones if not b.bone.use_deform][:512],custom_shapes=sorted({b.custom_shape.name for b in obj.pose.bones if b.custom_shape}),drivers=[{'path':d.data_path,'index':d.array_index,'muted':d.mute} for d in obj.animation_data.drivers] if obj.animation_data else [])
  rows.append(row)
 images=[{'name':x.name,'source':x.source,'path':bpy.path.abspath(x.filepath),'packed':bool(x.packed_file),'size':list(x.size)} for x in bpy.data.images]
 actions=[{'name':a.name,'frames':list(a.frame_range)} for a in bpy.data.actions]
 return dict(objects=rows,images=images,actions=actions,scene=bpy.context.scene.name,frame=bpy.context.scene.frame_current)

POSE_ACTIONS=set()
LOOP_CLOCK=None

def verify_pose(spec):
 for item in spec.get('pose',[]):
  bone=bpy.data.objects[item['armature']].pose.bones[item['bone']]
  if bone.rotation_mode!='XYZ' or any(abs(a-b)>1e-5 for a,b in zip(item['rotation_euler'],bone.rotation_euler)):raise ValueError('Rendered pose overridden by animation/driver: '+item['bone'])

def pose_frame(scene,spec,frame):
 """Evaluate authored animation first, then explicit pose overrides and proof."""
 output_frame=frame
 if LOOP_CLOCK:
  from animation_sampling import loop_frame
  frame=loop_frame(frame,**LOOP_CLOCK)
 whole=math.floor(frame);scene.frame_set(whole,subframe=frame-whole);bpy.context.view_layer.update()
 edits=spec.get('pose',[]);rigs={item['armature']:bpy.data.objects[item['armature']] for item in edits}
 before={}
 for name,rig in rigs.items():
  if rig.type!='ARMATURE':raise ValueError('Pose owner is not an armature: '+name)
  before[name]={b.name:tuple(v for row in b.matrix for v in row) for b in rig.pose.bones if b.bone.use_deform}
  if name not in POSE_ACTIONS:
   rig.animation_data_create()
   if rig.animation_data.action:rig.animation_data.action=rig.animation_data.action.copy()
   POSE_ACTIONS.add(name)
 controls=[]
 for item in edits:
  bone=rigs[item['armature']].pose.bones[item['bone']]
  controls.append({'armature':item['armature'],'bone':item['bone'],'requested':item['rotation_euler'],'before':list(bone.rotation_euler)})
  bone.rotation_mode='XYZ';bone.rotation_euler=item['rotation_euler']
  bone.keyframe_insert(data_path='rotation_euler',frame=frame,group='CapturePoseOverrides')
 bpy.context.view_layer.update()
 changed=0
 for rig_name,rig in rigs.items():
  for bone in rig.pose.bones:
   if bone.name in before[rig_name] and any(abs(a-b)>1e-6 for a,b in zip(before[rig_name][bone.name],(v for row in bone.matrix for v in row))):changed+=1
 for item in controls:
  bone=rigs[item['armature']].pose.bones[item['bone']];item['actual']=list(bone.rotation_euler)
  if any(abs(a-b)>1e-5 for a,b in zip(item['requested'],item['actual'])):raise ValueError('Pose channels overridden by rig/animation: '+item['bone'])
 requested_change=any(any(abs(a-b)>1e-5 for a,b in zip(item['requested'],item['before'])) for item in controls)
 if requested_change and not changed:raise ValueError('Pose controls did not change evaluated deform bones; inspect constraints/control mapping, no default-pose success')
 return {'frame':output_frame,'source_frame':frame,'controls':controls,'changed_deform_bones':changed,'requested_channel_change':requested_change,'visual_review_required':True}

def main():
 start=time.time();plan=pathlib.Path(sys.argv[sys.argv.index('--')+1]);out=plan.parent;request=json.loads(plan.read_text());spec=request['manifest']
 group,limit=cgroup()
 if limit!='4294967296':raise ValueError('Worker must be bounded at exactly 4GiB before opening any scene')
 if bpy.app.version[:3]!=(5,2,1):raise ValueError('Pinned Blender 5.2.1 required')
 source=pathlib.Path(spec['source'])
 if source.suffix.lower()=='.blend':bpy.ops.wm.open_mainfile(filepath=str(source),load_ui=False,use_scripts=False)
 else:
  bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False);bpy.ops.import_scene.gltf(filepath=str(source))
 if spec['mode'] in ('pose-inspect','pose-prepare'):
  from pose_preparation_worker import prepare
  try:prepare(out,spec,group,limit,start)
  except Exception as error:
   (out/'worker.json').write_text(json.dumps({'status':'FAIL','mode':spec['mode'],'cgroup_memory_max':int(limit),'engine':bpy.app.version_string,'error':str(error)[:500],'files':[x.name for x in out.iterdir() if x.is_file()]}));raise
  return
 scene=bpy.context.scene;data=inventory();(out/'inventory.json').write_text(json.dumps(data,indent=2))
 if spec['mode']=='inspect':
  (out/'worker.json').write_text(json.dumps({'status':'PASS','mode':'inspect','cgroup_memory_max':int(limit),'engine':bpy.app.version_string,'seconds':time.time()-start,'files':['inventory.json']},indent=2));return
 scene.render.use_simplify=True;scene.render.simplify_subdivision=1;scene.render.simplify_subdivision_render=1
 scene.cycles.max_subdivisions=1;scene.cycles.texture_limit_render='1024'
 for obj in scene.objects:
  for modifier in obj.modifiers:
   if modifier.type=='SUBSURF':modifier.levels=min(modifier.levels,1);modifier.render_levels=min(modifier.render_levels,1)
 vis=spec.get('visibility',{})
 for name in vis.get('hide',[]):bpy.data.objects[name].hide_render=True
 for name in vis.get('show',[]):
  obj=bpy.data.objects[name];obj.hide_render=False;obj.hide_viewport=False;obj.hide_set(False)
  for c in obj.users_collection:c.hide_render=False;c.hide_viewport=False
 targets={c for name in vis.get('show',[]) for c in bpy.data.objects[name].users_collection}
 def enable(layer):
  child=any([enable(x) for x in layer.children]);selected=layer.collection in targets or child
  if selected:layer.exclude=False;layer.hide_viewport=False
  return selected
 enable(bpy.context.view_layer.layer_collection)
 # Hide only proven bone-widget objects, not all meshes lacking material slots.
 widgets={b.custom_shape for obj in scene.objects if obj.type=='ARMATURE' for b in obj.pose.bones if b.custom_shape}
 for obj in widgets:obj.hide_render=True
 if spec.get('action'):
  rig=bpy.data.objects[spec['armature']];rig.animation_data_create();rig.animation_data.action=bpy.data.actions[spec['action']]
 for edit in spec.get('modifiers',[]):
  obj=bpy.data.objects[edit['object']];modifier=obj.modifiers[edit['name']]
  if modifier.type!='MASK':raise ValueError('Only existing clothing MASK modifiers may be toggled')
  paths={modifier.path_from_id(k) for k in ('show_render','show_viewport')}
  if obj.animation_data:
   for driver in obj.animation_data.drivers:
    if driver.data_path in paths:driver.mute=True
  modifier.show_render=edit['enabled'];modifier.show_viewport=edit['enabled']
 global LOOP_CLOCK
 LOOP_CLOCK=None
 if spec.get('loop_action'):
  action=bpy.data.actions[spec['action']];a,b=action.frame_range
  if b<=a:raise ValueError('Cannot loop empty/single-frame Action')
  LOOP_CLOCK={'output_start':spec.get('frames',[1,1])[0],'output_fps':spec.get('fps',24),'source_fps':scene.render.fps/scene.render.fps_base,'action_start':a,'action_end':b}
 frames=spec.get('frames',[1,1]);pose_evidence=[pose_frame(scene,spec,frames[0])]
 meshes=[x for x in scene.objects if x.type=='MESH' and not x.hide_render and x not in widgets]
 if not meshes:raise ValueError('No renderable meshes')
 roots=[pathlib.Path(x) for x in request['source_roots']]
 missing=[]
 for image in bpy.data.images:
  if image.source not in {'FILE','TILED','SEQUENCE'} or image.packed_file:continue
  path=pathlib.Path(bpy.path.abspath(image.filepath))
  if image.source=='TILED':
   candidates=list(path.parent.glob(path.name.replace('<UDIM>','[0-9][0-9][0-9][0-9]')))
  else:candidates=[path]
  if not candidates or any(not p.is_file() or not any(p.resolve().is_relative_to(r) for r in roots) for p in candidates):missing.append(image.name)
 if missing:raise ValueError('Missing or out-of-scope image dependencies: '+', '.join(missing[:12]))
 low,high=bounds(meshes)
 if spec['mode']=='animation':
  for frame in sorted({frames[0],(frames[0]+frames[1])//2,frames[1]}):
   pose_frame(scene,spec,frame);lo,hi=bounds(meshes);low=Vector([min(low[i],lo[i]) for i in range(3)]);high=Vector([max(high[i],hi[i]) for i in range(3)])
  pose_frame(scene,spec,frames[0])
 centre=(low+high)/2;size=high-low;camera_spec=spec.get('camera',{});resolution=spec.get('resolution',[768,1024]);aspect=resolution[0]/resolution[1]
 angle=math.radians({'front':-90,'three-quarter':-65,'side':0,'back':90}[camera_spec.get('view','front')])
 if camera_spec.get('preserve'):
  camera=scene.camera
  if not camera:raise ValueError('No authored camera to preserve')
 else:
  camera_data=bpy.data.cameras.new('CaptureCamera');camera=bpy.data.objects.new('CaptureCamera',camera_data);scene.collection.objects.link(camera);scene.camera=camera
  camera_data.type='ORTHO';camera_data.ortho_scale=max(size.z,max(size.x,size.y)/aspect)*camera_spec.get('margin',1.15)
  radius=max(size.length*2,1);camera.location=centre+Vector((math.cos(angle)*radius,math.sin(angle)*radius,size.z*0.06));aim(camera,centre)
 if spec.get('lighting','studio')=='studio':
  for obj in scene.objects:
   if obj.type=='LIGHT':obj.hide_render=True
  world=bpy.data.worlds.new('CaptureWorld');world.use_nodes=True;world.node_tree.nodes['Background'].inputs['Color'].default_value=(0.12,0.12,0.12,1);world.node_tree.nodes['Background'].inputs['Strength'].default_value=0.35;scene.world=world
  scale=max(size.length,0.5)
  for name,relative,power in [('Key',(-1.3,-1.8,1.6),500),('Fill',(1.4,-0.8,0.6),220),('Rim',(0.2,1.5,1.5),400)]:
   light=bpy.data.lights.new('Capture'+name,'AREA');light.energy=power*scale*scale;light.shape='DISK';light.size=scale;obj=bpy.data.objects.new(light.name,light);scene.collection.objects.link(obj);obj.location=centre+Vector(relative)*scale;aim(obj,centre)
 scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=spec.get('samples',24);scene.cycles.use_denoising=True
 scene.render.threads_mode='FIXED';scene.render.threads=2;scene.render.resolution_x=resolution[0];scene.render.resolution_y=resolution[1];scene.render.resolution_percentage=100
 scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA';scene.render.fps=spec.get('fps',24);scene.render.film_transparent=False
 # Authored subdivisions can otherwise exceed the external worker budget.
 scene.render.use_simplify=True;scene.render.simplify_subdivision_render=1
 (out/'prepared-inventory.json').write_text(json.dumps(inventory(),indent=2))
 images=[]
 if spec['mode']=='still':
  pose_evidence.append(pose_frame(scene,spec,frames[0]))
  scene.render.filepath=str(out/'capture.png');bpy.ops.render.render(write_still=True);verify_pose(spec);images=['capture.png']
 else:
  count=frames[1]-frames[0]+1
  for index,frame in enumerate(range(frames[0],frames[1]+1)):
   if spec['mode']=='animation':pose_evidence.append(pose_frame(scene,spec,frame))
   else:
    pose_evidence.append(pose_frame(scene,spec,frames[0]));orbit=angle+2*math.pi*index/max(count-1,1);radius=max(size.length*2,1);camera.location=centre+Vector((math.cos(orbit)*radius,math.sin(orbit)*radius,size.z*0.06));aim(camera,centre)
   filename='frame-'+str(index).zfill(4)+'.png';scene.render.filepath=str(out/filename);bpy.ops.render.render(write_still=True);verify_pose(spec);images.append(filename)
 if spec.get('output_format','png')=='mp4':
  if not request.get('ffmpeg'):raise ValueError('MP4 encoder not installed in worker')
  command=[request['ffmpeg'],'-nostdin','-v','error','-framerate',str(scene.render.fps),'-i',str(out/'frame-%04d.png'),'-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(out/'capture.mp4')]
  if subprocess.run(command,capture_output=True,timeout=120).returncode:raise ValueError('MP4 encoding failed')
 (out/'pose-evidence.json').write_text(json.dumps(pose_evidence,indent=2))
 (out/'worker.json').write_text(json.dumps({'status':'CAPTURED_VISUAL_REVIEW_PENDING','mode':spec['mode'],'engine':bpy.app.version_string,'cgroup_memory_max':int(limit),'cgroup_memory_peak':(group/'memory.peak').read_text().strip(),'seconds':time.time()-start,'images':images,'files':['inventory.json','prepared-inventory.json','pose-evidence.json']+images+(['capture.mp4'] if spec.get('output_format')=='mp4' else []),'source':str(source),'preview_budget':{'subdivision_max':1,'texture_limit':'1024','device':'CPU','threads':2,'samples':scene.cycles.samples,'resolution':resolution},'bounds':{'low':list(low),'high':list(high)}},indent=2))

if __name__=='__main__':main()
