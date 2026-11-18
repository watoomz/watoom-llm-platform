"""Blender 4.2 request adapter. Writes only a fresh version directory."""
import bpy, bmesh, sys, json, pathlib, math, hashlib
from mathutils import Vector, Matrix
args=sys.argv[sys.argv.index('--')+1:]
root=pathlib.Path(args[0]); req=json.loads(pathlib.Path(args[1]).read_text())
assert req['kind'] in ['magpie','prop','environment']
for d in ['source','game-ready','reports','renders']: (root/d).mkdir(parents=True,exist_ok=True)
assert not (root/'source/runtime.blend').exists(), 'use a fresh version'
kind=req['kind']
pilot=next(p for p in [pathlib.Path('/data/ai/assets/generated/blender-asset-builder/20261020T072530Z-budget'),pathlib.Path('/workspace/blender-asset-builder/20261020T072530Z-budget')] if (p/'source/WP4_validated.blend').is_file())
sys.path.insert(0,str(pilot/'upstream/EL4CTEO/skills/blender-asset-qa/scripts'))
import qa_check
if kind=='magpie':
 bpy.ops.wm.open_mainfile(filepath=str(pilot/'source/WP4_validated.blend'))
 for o in list(bpy.data.objects):
  if o.type!='MESH' or any(c.name=='90_Studio' for c in o.users_collection): bpy.data.objects.remove(o,do_unlink=True)
 # Replace the folded-only pilot wings with articulated flight surfaces.
 black=next(m for m in bpy.data.materials if 'charcoal satin' in m.name)
 white=next(m for m in bpy.data.materials if 'ivory' in m.name)
 def blade(name,start,end,width,mat,coll,bone):
  start=Vector(start);end=Vector(end);axis=(end-start).normalized()
  across=Vector((-axis.y,axis.x,0)).normalized();verts=[];faces=[];rings=8;sides=6
  for i in range(rings+1):
   t=i/rings;ctr=start.lerp(end,t)
   profile=.025+math.sin(math.pi*t)**.7*(1.0-.2*t)
   for j in range(sides):
    angle=j/sides*math.tau
    verts.append(ctr+across*math.cos(angle)*width*profile+Vector((0,0,math.sin(angle)*.0012*profile)))
  for i in range(rings):
   for j in range(sides):
    a=i*sides+j;c=i*sides+(j+1)%sides;faces.append((a,c,c+sides,a+sides))
  faces.extend([tuple(range(sides-1,-1,-1)),tuple(rings*sides+j for j in range(sides))])
  me=bpy.data.meshes.new(name);me.from_pydata(verts,[],faces);me.update()
  ob=bpy.data.objects.new(name,me);coll.objects.link(ob);me.materials.append(mat);ob['wing_bone']=bone
  bm=bmesh.new();bm.from_mesh(me);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(me);bm.free()
  for f in me.polygons:f.use_smooth=True
 for side,sign in [('L',-1),('R',1)]:
  coll=bpy.data.collections['03_Wing_L' if side=='L' else '04_Wing_R']
  folded=bpy.data.collections.new('FoldedWing_'+side);bpy.context.scene.collection.children.link(folded)
  for ob in list(coll.objects):
   ob['folded_wing']=side;coll.objects.unlink(ob);folded.objects.link(ob)
  bpy.ops.mesh.primitive_uv_sphere_add(segments=20,ring_count=12,location=(sign*.16,.035,.24))
  ob=bpy.context.object;ob.name='WingWeb_'+side;ob.scale=(.125,.036,.010)
  bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
  ob.data.materials.append(black)
  for c in list(ob.users_collection):c.objects.unlink(ob)
  coll.objects.link(ob)

  for i in range(10):
   # Fan from wrist to the fingered outer primary tips.
   blade('Primary_'+side+'_'+str(i),(sign*(.20+i*.003),-.005+i*.004,.24),
    (sign*(.27+.009*i),.17-.013*i,.238+.035*math.sin(math.pi*(i+1)/12)),.013,black,coll,'wing_hand_'+side)
  for i in range(9):
   x=.075+i*.017
   blade('Secondary_'+side+'_'+str(i),(sign*x,.018,.241),
    (sign*(x+.012),.145-.10*(x-.075),.237+.018*math.sin(math.pi*(x-.05)/.3)),.015,black,coll,'wing_'+side if x<.13 else 'wing_forearm_'+side)
  for i in range(9):
   x=.05+i*.020
   blade('Covert_'+side+'_'+str(i),(sign*x,-.008,.246),
    (sign*(x+.01),.065,.247),.016,white if i<6 else black,coll,'wing_'+side if x<.13 else 'wing_forearm_'+side)
 # Enlarge the expressive head gently while preserving the neck transition and face alignment.
 pivot=Vector((0,-.065,.295))
 for ob in list(bpy.context.scene.objects):
  if ob.type!='MESH':continue
  if any(c.name=='02_Face' for c in ob.users_collection):
   inv=ob.matrix_world.inverted()
   for v in ob.data.vertices:
    co=ob.matrix_world@v.co;v.co=inv@(pivot+(co-pivot)*1.16)
  elif 'Torso_Neck_Head' in ob.name:
   inv=ob.matrix_world.inverted()
   for v in ob.data.vertices:
    co=ob.matrix_world@v.co;weight=max(0,min(1,(co.z-.258)/.035))
    v.co=inv@(co+(co-pivot)*.16*weight)
 # Union overlapping feather shells; retain the nearest authored plumage material.
 from mathutils.kdtree import KDTree
 for side in ['L','R']:
  coll=bpy.data.collections['03_Wing_L' if side=='L' else '04_Wing_R']
  group=list(coll.objects);points=[]
  for ob in group:
   for face in ob.data.polygons:points.append((ob.matrix_world@face.center,ob.data.materials[face.material_index]))
  kd=KDTree(len(points))
  for i,(co,mat) in enumerate(points):kd.insert(co,i)
  kd.balance()
  bpy.ops.object.select_all(action='DESELECT')
  for ob in group:ob.select_set(True)
  bpy.context.view_layer.objects.active=group[0];bpy.ops.object.join();ob=group[0]
  ob.name='ArticulatedWing_'+side;ob['articulated_wing']=side
  if 'wing_bone' in ob:del ob['wing_bone']
  mod=ob.modifiers.new('Closed flight feather union','REMESH');mod.mode='VOXEL';mod.voxel_size=.00065
  bpy.ops.object.modifier_apply(modifier=mod.name)
  mod=ob.modifiers.new('Feather edge smoothing','SMOOTH');mod.factor=.65;mod.iterations=4
  bpy.ops.object.modifier_apply(modifier=mod.name)
  ob.data.materials.clear();ob.data.materials.append(black);ob.data.materials.append(white)
  for face in ob.data.polygons:
   co=ob.matrix_world@face.center;face.material_index=int(abs(co.x)<.20 and co.y<.09 and co.z>.242)
else:
 bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
 def cube(name,loc,scale):
  bpy.ops.mesh.primitive_cube_add(size=1,location=loc)
  o=bpy.context.object;o.name=name;o.scale=scale;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
  bevel=o.modifiers.new('Manufactured edges','BEVEL');bevel.width=.025;bevel.segments=2;bpy.ops.object.modifier_apply(modifier=bevel.name)
  return o
 if kind=='prop':
  cube('Crate', (0,0,.4),(.8,.6,.8))
  for x in [-.38,.38]: cube('ReinforcingRail',(x,0,.4),(.06,.65,.86))
 else:
  cube('Floor',(0,0,-.1),(4,4,.2))
  for x in [-1.8,1.8]:
   for y in [-1.8,1.8]:cube('Pillar',(x,y,1.25),(.25,.25,2.5))
  cube('Roof',(0,0,2.6),(4.2,4.2,.2))
 mat=bpy.data.materials.new('PBR_Surface');mat.use_nodes=True
 bs=mat.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=tuple(req.get('color',[.19,.24,.28]))+(1,);bs.inputs['Roughness'].default_value=.65
 for o in bpy.context.scene.objects:
  if o.type=='MESH':
   o.data.materials.append(mat);bpy.context.view_layer.objects.active=o
   bpy.ops.object.select_all(action='DESELECT');o.select_set(True)
   bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.uv.smart_project();bpy.ops.object.mode_set(mode='OBJECT')
if kind=='magpie':
 for side,sign in [('L',-1),('R',1)]:
  bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=10,location=(sign*.038,.032,.246))
  o=bpy.context.object;o.name='Shoulder_'+side;o.scale=(.018,.025,.018)
  bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
  o.data.materials.append(next(m for m in bpy.data.materials if 'charcoal satin' in m.name))
  for c in list(o.users_collection):c.objects.unlink(o)
  bpy.data.collections['03_Wing_L' if side=='L' else '04_Wing_R'].objects.link(o)
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
if kind=='magpie':
 # Separate tail feather islands in depth by 0.2 mm; preserve closed geometry and UVs.
 for o in meshes:
  if not any('05_Tail'==c.name for c in o.users_collection):continue
  bm=bmesh.new();bm.from_mesh(o.data);seen=set();islands=[]
  for v in bm.verts:
   if v in seen:continue
   todo=[v];seen.add(v);part=[]
   while todo:
    a=todo.pop();part.append(a)
    for e in a.link_edges:
     w=e.other_vert(a)
     if w not in seen:seen.add(w);todo.append(w)
   islands.append(part)
  islands.sort(key=lambda vs:sum(v.co.x for v in vs)/len(vs))
  for i,part in enumerate(islands):
   for v in part:v.co.z+=i*.0002
  bm.to_mesh(o.data);bm.free()
  bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
  mod=o.modifiers.new('Tail feather surface union','REMESH');mod.mode='VOXEL';mod.voxel_size=.0005
  bpy.ops.object.modifier_apply(modifier=mod.name)

original=sum(len(o.data.polygons) for o in meshes)
for o in meshes:
 bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
 o.data.calc_loop_triangles()
 count=len(o.data.loop_triangles)
 if kind=='magpie' and count>500:
  m=o.modifiers.new('Runtime reduction','DECIMATE');m.ratio=min(.14,4000/count) if any(c.name=='05_Tail' for c in o.users_collection) else (min(.14,7500/count) if o.get('articulated_wing') else (.14 if count>5000 else .35))
  bpy.ops.object.modifier_apply(modifier=m.name)
 for mod in list(o.modifiers):
  if mod.type not in ['ARMATURE']:bpy.ops.object.modifier_apply(modifier=mod.name)
rig=None
if kind=='magpie':
 bpy.ops.object.select_all(action='DESELECT')
 arm=bpy.data.armatures.new('MagpieSkeleton');rig=bpy.data.objects.new('MagpieRig',arm);bpy.context.collection.objects.link(rig)
 rig.select_set(True);bpy.context.view_layer.objects.active=rig;bpy.ops.object.mode_set(mode='EDIT')
 defs=[
 ('root',(0,0,0),(0,0,.08),None),
 ('pelvis',(0,.03,.12),(0,.02,.19),'root'),
 ('spine',(0,.02,.19),(0,-.025,.25),'pelvis'),
 ('neck',(0,-.025,.25),(0,-.05,.285),'spine'),
 ('head',(0,-.05,.285),(0,-.10,.31),'neck'),
 ('tail',(0,.07,.19),(0,.23,.11),'pelvis')]
 for side,sign in [('L',-1),('R',1)]:
  defs += [('wing_'+side,(sign*.035,0,.24),(sign*.13,.02,.24),'spine'),
           ('wing_forearm_'+side,(sign*.13,.02,.24),(sign*.22,-.015,.24),'wing_'+side),
           ('wing_hand_'+side,(sign*.22,-.015,.24),(sign*.34,.04,.24),'wing_forearm_'+side),
           ('folded_wing_'+side,(sign*.035,0,.24),(sign*.035,.10,.22),'spine'),
           ('thigh_'+side,(sign*.023,.03,.14),(sign*.024,.034,.099),'pelvis'),
           ('shin_'+side,(sign*.024,.034,.099),(sign*.024,.01,.031),'thigh_'+side),
           ('foot_'+side,(sign*.024,.01,.031),(sign*.024,-.04,.008),'shin_'+side)]
 for n,h,t,parent in defs:
  b=arm.edit_bones.new(n);b.head=h;b.tail=t
  if parent:b.parent=arm.edit_bones[parent]
 bpy.ops.object.mode_set(mode='OBJECT')
 for o in meshes:
  coll=' '.join(c.name for c in o.users_collection)
  side='L' if '_L' in o.name or o.name.startswith('L_') else 'R'
  bone='spine'
  if 'Wing_L' in coll:bone='wing_L'
  elif 'Wing_R' in coll:bone='wing_R'
  elif 'Tail' in coll:bone='tail'
  elif '02_Face' in coll:bone='head'
  elif o.name.startswith('Thigh'):bone='thigh_'+side
  elif o.name.startswith('Leg'):bone='shin_'+side
  elif '06_Legs' in coll:bone='foot_'+side
  elif 'Torso_Neck_Head' in o.name:
   groups={n:o.vertex_groups.new(name=n) for n in ['spine','neck','head']}
   for v in o.data.vertices:
    z=(o.matrix_world@v.co).z
    h=max(0,min(1,(z-.27)/.025));n=max(0,min(1,(z-.235)/.035))*(1-h)
    for name,w in [('spine',1-h-n),('neck',n),('head',h)]:
     if w>0:groups[name].add([v.index],w,'REPLACE')
   bone=None
  if o.get('articulated_wing'):
   side=o['articulated_wing']
   gs={n:o.vertex_groups.new(name=n+'_'+side) for n in ['wing','wing_forearm','wing_hand']}
   for v in o.data.vertices:
    x=abs((o.matrix_world@v.co).x)
    h=max(0,min(1,(x-.20)/.04));f=max(0,min(1,(x-.11)/.04))*(1-h)
    for n,w in [('wing',1-h-f),('wing_forearm',f),('wing_hand',h)]:
     if w>0:gs[n].add([v.index],w,'REPLACE')
   bone=None
  elif o.get('wing_bone'):bone=o['wing_bone']
  if o.get('folded_wing'):bone='folded_wing_'+o['folded_wing']
  if bone:o.vertex_groups.new(name=bone).add(list(range(len(o.data.vertices))),1,'REPLACE')
  mod=o.modifiers.new('Runtime skin','ARMATURE');mod.object=rig
  o.parent=rig
 scene=bpy.context.scene;scene.render.fps=24;scene.frame_start=1;scene.frame_end=25
 rig.animation_data_create()
 motion={}
 for name in ['Idle','Walk','Flight']:
  action=bpy.data.actions.new(name);rig.animation_data.action=action
  for pb in rig.pose.bones:pb.rotation_mode='XYZ'
  for frame in [1,7,13,19,25]:
   scene.frame_set(frame)
   phase=(frame-1)/24*math.tau
   for pb in rig.pose.bones:
    pb.rotation_euler=(0,0,0);pb.location=(0,0,0);pb.scale=(1,1,1)
   rig.pose.bones['head'].rotation_euler.x=.10*math.sin(phase)
   if name=='Idle':rig.pose.bones['head'].rotation_euler.y=.18*math.sin(phase)

   if name=='Walk':
    for side,sign in [('L',1),('R',-1)]:
     rig.pose.bones['thigh_'+side].rotation_euler.x=.35*math.sin(phase)*sign
     rig.pose.bones['shin_'+side].rotation_euler.x=.18*math.sin(phase+.7)*sign
   if name=='Flight':
    for side,sign in [('L',1),('R',-1)]:
     rig.pose.bones['wing_'+side].rotation_euler.z=0
     rig.pose.bones['wing_'+side].rotation_euler.x=.45*math.sin(phase)
     rig.pose.bones['thigh_'+side].rotation_euler.x=1.1
     rig.pose.bones['shin_'+side].rotation_euler.x=-.9
     rig.pose.bones['foot_'+side].rotation_euler.x=.5
    rig.pose.bones['root'].location.y=.25
    rig.pose.bones['root'].rotation_euler.x=math.radians(65)
    rig.pose.bones['head'].rotation_euler.x=-math.radians(65)+.06*math.sin(phase)
   for side in ['L','R']:
    rig.pose.bones['folded_wing_'+side].scale=(.001,.001,.001) if name=='Flight' else (1,1,1)
    if name in ['Idle','Walk']:rig.pose.bones['wing_'+side].scale=(.001,.001,.001)
   if name=='Flight':rig.pose.bones['tail'].rotation_euler.x=-math.radians(40)
   for pb in rig.pose.bones:
    pb.keyframe_insert('rotation_euler',frame=frame,group=pb.name);pb.keyframe_insert('location',frame=frame,group=pb.name);pb.keyframe_insert('scale',frame=frame,group=pb.name)
  samples=[]
  for f in [1,7]:
   scene.frame_set(f);bpy.context.view_layer.update()
   samples.append([list((rig.matrix_world@pb.matrix).translation)+list(pb.matrix.to_quaternion()) for pb in rig.pose.bones])
  motion[name]={'changed':samples[0]!=samples[1],'frames':[1,7],'samples':samples}
  track=rig.animation_data.nla_tracks.new();track.name=name;track.strips.new(name,1,action)
 rig.animation_data.action=None
 for t in rig.animation_data.nla_tracks:t.mute=True
 bpy.context.scene.frame_set(1)
 for pb in rig.pose.bones:pb.rotation_euler=(0,0,0);pb.location=(0,0,0);pb.scale=(1,1,1)
 bpy.context.view_layer.update()
 bpy.ops.object.select_all(action='DESELECT')
 for o in meshes:o.select_set(True)
 bpy.context.view_layer.objects.active=meshes[0];bpy.ops.object.join()
 meshes=[bpy.context.object];meshes[0].name='Magpie_GameMesh'
 o=meshes[0]
 o.data.calc_loop_triangles()
 budget=req.get('max_triangles',45000)
 if len(o.data.loop_triangles)>budget:
  reduction=o.modifiers.new('Whole character triangle budget','DECIMATE');reduction.ratio=budget*.98/len(o.data.loop_triangles)
  bpy.ops.object.modifier_apply(modifier=reduction.name)
 bm=bmesh.new();bm.from_mesh(o.data)
 bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.000001)
 bmesh.ops.triangulate(bm,faces=list(bm.faces))
 # Remove only tiny detached remeshing debris, never anatomical mesh islands.
 seen=set();debris=[]
 for v in bm.verts:
  if v in seen:continue
  todo=[v];seen.add(v);part=[]
  while todo:
   w=todo.pop();part.append(w)
   for e in w.link_edges:
    other=e.other_vert(w)
    if other not in seen:seen.add(other);todo.append(other)
  faces={f for w in part for f in w.link_faces}
  if len(part)<=8 and all(abs((o.matrix_world@w.co).x)>.10 and (o.matrix_world@w.co).z>.225 for w in part):debris.extend(part)
 removed=len(debris)
 bmesh.ops.delete(bm,geom=debris,context='VERTS')
 (root/'reports/remesh-cleanup.json').write_text(json.dumps({'removed_vertices':removed,'criterion':'disconnected islands <=8 vertices, confined to outer flight feather region; anatomical islands excluded','original_revision_preserved':'magpie-v20-20261020'}))
 bm.to_mesh(o.data);bm.free()
 # One packed UV map for the joined runtime mesh, rather than mismatched source layers.
 while o.data.uv_layers: o.data.uv_layers.remove(o.data.uv_layers[0])
 bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT')
 bpy.ops.uv.smart_project(angle_limit=1.15,island_margin=.003)
 bpy.ops.object.mode_set(mode='OBJECT')

 (root/'reports/animation.json').write_text(json.dumps({'status':'PASS' if all(v['changed'] for v in motion.values()) else 'FAIL','actions':motion,'visual_deformation':'PENDING'},indent=2))
for o in meshes:
 for face in o.data.polygons:face.use_smooth=True
 o.data.validate(verbose=True,clean_customdata=True);o.data.update()
q=qa_check.run(objects=[o.name for o in meshes],profile='game',eps=.00001,tol=.002,max_tris=req.get('max_triangles',45000))
triangles=0;unweighted=0
for o in meshes:
 o.data.calc_loop_triangles();triangles+=len(o.data.loop_triangles)
 if rig:unweighted+=sum(not v.groups or abs(sum(g.weight for g in v.groups)-1)>1e-4 for v in o.data.vertices)
metrics={'triangles':triangles,'original_polygons':original,'unweighted_vertices':unweighted,'upstream':q,'visual':'PENDING','reference_match':'PENDING'}
(root/'reports/quality.json').write_text(json.dumps(metrics,indent=2))
bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=1
bpy.ops.wm.save_as_mainfile(filepath=str(root/'source/runtime.blend'))
bpy.ops.object.select_all(action='DESELECT')
for o in meshes:o.select_set(True)
if rig:
 rig.select_set(True);bpy.context.view_layer.objects.active=rig
 for t in rig.animation_data.nla_tracks:t.mute=False
params={'filepath':str(root/'game-ready/asset.glb'),'use_selection':True,'export_animations':bool(rig)}
bpy.ops.export_scene.gltf(**params)
bpy.ops.export_scene.fbx(filepath=str(root/'game-ready/asset.fbx'),use_selection=True,object_types={'MESH','ARMATURE'},add_leaf_bones=False,bake_anim=bool(rig),bake_anim_use_all_actions=True,axis_forward='-Z',axis_up='Y',path_mode='COPY',embed_textures=True,mesh_smooth_type='FACE')
(root/'reports/build.json').write_text(json.dumps({'status':'BUILT','kind':kind,'blender':bpy.app.version_string,'triangles':triangles,'technical_pass':q['pass'] and triangles<=req.get('max_triangles',45000) and unweighted==0,'complete':False,'remaining':['visual review','reference comparison','Godot playback','Unreal import/playback']}))
print(json.dumps({'kind':kind,'triangles':triangles,'qa':q['pass'],'unweighted':unweighted}))
if not (q['pass'] and triangles<=req.get('max_triangles',45000) and unweighted==0):raise RuntimeError('Technical acceptance failed; outputs retained for diagnosis')
