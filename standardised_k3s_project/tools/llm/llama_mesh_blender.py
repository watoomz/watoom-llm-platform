"""Run only through llama_mesh.py prepare; CPU-only, no downloads or network."""
import json
import sys
from pathlib import Path
import bpy
import bmesh

args=sys.argv[sys.argv.index('--')+1:];folder=Path(args[0]);size=float(args[1]);geometry=json.loads((folder/'geometry.json').read_text())
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
mesh=bpy.data.meshes.new('GeneratedMesh');mesh.from_pydata(geometry['vertices'],[],geometry['faces']);mesh.update()
obj=bpy.data.objects.new('GeneratedMesh',mesh);bpy.context.collection.objects.link(obj);bpy.context.view_layer.objects.active=obj;obj.select_set(True)
bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1e-7);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bmesh.ops.triangulate(bm,faces=list(bm.faces));bm.to_mesh(mesh);bm.free();mesh.update()
# One Blender coordinate unit represents one centimetre. Largest dimension = size_cm.
minimum=[min(v.co[i] for v in mesh.vertices) for i in range(3)];maximum=[max(v.co[i] for v in mesh.vertices) for i in range(3)];extent=max(maximum[i]-minimum[i] for i in range(3));scale=size/extent
center=[(minimum[0]+maximum[0])/2,(minimum[1]+maximum[1])/2,minimum[2]]
for v in mesh.vertices:
    for i in range(3):v.co[i]=(v.co[i]-center[i])*scale
mesh.update();bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=0.01
bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.uv.smart_project(island_margin=0.02);bpy.ops.object.mode_set(mode='OBJECT')
material=bpy.data.materials.new('PrototypeNeutral');material.diffuse_color=(0.5,0.5,0.5,1.0);mesh.materials.append(material)
bpy.ops.wm.save_as_mainfile(filepath=str(folder/'preview.blend'))
bpy.ops.export_scene.fbx(filepath=str(folder/'unreal.fbx'),use_selection=True,object_types={'MESH'},apply_unit_scale=True,global_scale=1.0,axis_forward='-Y',axis_up='Z',use_mesh_modifiers=True,bake_anim=False,path_mode='AUTO')
(folder/'blender-report.json').write_text(json.dumps({'blender_version':bpy.app.version_string,'vertices':len(mesh.vertices),'triangles':len(mesh.polygons),'size_cm':size,'units':'centimetres','pivot':'XY center, bottom Z','uv_layers':len(mesh.uv_layers),'textures_generated':False,'rig_generated':False,'unreal_import_tested':False},indent=2)+'\n')
