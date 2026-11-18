"""Trusted Blender 5.2 exporter for the existing isolated inspection worker."""
import bpy,sys,pathlib,json,math
r=pathlib.Path(sys.argv[sys.argv.index('--')+1])
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH' and not o.get('watoom_editor_only',False)]
rigs=[o for o in bpy.context.scene.objects if o.type=='ARMATURE']
bones={};animations=[]
for rig in rigs:
 bones.update({b.name:(b.parent.name if b.parent else None) for b in rig.data.bones})
 if rig.animation_data:
  rig.animation_data.action=None
  for t in rig.animation_data.nla_tracks:t.mute=True
 for pb in rig.pose.bones:pb.rotation_euler=(0,0,0);pb.location=(0,0,0);pb.scale=(1,1,1)
bpy.context.scene.frame_set(1);bpy.context.view_layer.update()
points=[o.matrix_world@v.co for o in meshes for v in o.data.vertices]
bounds=[[min(v[i] for v in points),max(v[i] for v in points)] for i in range(3)]
for rig in rigs:
 for t in rig.animation_data.nla_tracks:t.mute=False
animations=[a.name for a in bpy.data.actions]
bpy.ops.object.select_all(action='DESELECT')
for o in meshes+rigs:o.select_set(True)
bpy.ops.export_scene.fbx(filepath=str(r/'asset.fbx'),use_selection=True,object_types={'MESH','ARMATURE'},add_leaf_bones=False,bake_anim=bool(rigs),bake_anim_use_all_actions=False,bake_anim_use_nla_strips=True,path_mode='COPY',embed_textures=True,mesh_smooth_type='FACE',axis_forward='-Z',axis_up='Y')
(r/'source.json').write_text(json.dumps({'bones':bones,'animations':animations,'skeletal':bool(rigs),'bounds_metres':bounds,'units':'metres','up':'Z','fbx_sha256':__import__('hashlib').sha256((r/'asset.fbx').read_bytes()).hexdigest()},indent=2))
