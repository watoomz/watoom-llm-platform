import bpy,bmesh,json,sys,math,struct
from pathlib import Path
root=Path(sys.argv[sys.argv.index('--')+1]);sys.path.insert(0,str(root/'upstream/EL4CTEO/skills/blender-asset-qa/scripts'))
import qa_check
objs=[o for o in bpy.context.scene.objects if o.type=='MESH' and not any(c.name=='90_Studio' for c in o.users_collection)]
q=qa_check.run(objects=[o.name for o in objs],profile='game',eps=.00001,tol=.002,max_tris=300000)
metrics={'triangles':0,'nonfinite':0,'degenerate':0,'missing_materials':[],'missing_uv':[],'duplicate_faces':0,'nonmanifold':0,'invalid_material_indices':0}
for o in objs:
 m=o.data;m.calc_loop_triangles();metrics['triangles']+=len(m.loop_triangles);metrics['nonfinite']+=sum(not all(math.isfinite(x) for x in v.co) for v in m.vertices)
 metrics['degenerate']+=sum(p.area<1e-12 for p in m.polygons)
 if not m.materials:metrics['missing_materials'].append(o.name)
 if not m.uv_layers:metrics['missing_uv'].append(o.name)
 metrics['invalid_material_indices']+=sum(p.material_index>=len(m.materials) for p in m.polygons)
 keys=[tuple(sorted(p.vertices)) for p in m.polygons];metrics['duplicate_faces']+=len(keys)-len(set(keys))
 bm=bmesh.new();bm.from_mesh(m);metrics['nonmanifold']+=sum(not e.is_manifold for e in bm.edges);bm.free()
bpy.ops.object.select_all(action='DESELECT')
for o in objs:o.select_set(True)
bpy.ops.export_scene.fbx(filepath=str(root/'game-ready/australian_magpie.fbx'),use_selection=True,object_types={'MESH'},add_leaf_bones=False,bake_anim=False,axis_forward='-Z',axis_up='Y')
data=(root/'game-ready/australian_magpie.glb').read_bytes();magic,version,size=struct.unpack_from('<4sII',data)
header=magic==b'glTF' and version==2 and size==len(data)
technical=bool(q['pass'] and header and metrics['triangles']<=300000 and not any(metrics[k] for k in ['nonfinite','degenerate','missing_materials','missing_uv','duplicate_faces','invalid_material_indices']))
(root/'reports/quality.json').write_text(json.dumps({'technical_pass':technical,'metrics':metrics,'upstream':q,'glb_structure':header,'visual':'NOT TESTED','anatomical_ratios':'NOT TESTED','deformation':'NOT TESTED','unreal_import':'NOT TESTED'},indent=2))
# True negative test against the unmodified upstream checker.
bpy.ops.object.select_all(action='DESELECT');m=bpy.data.meshes.new('malformed');m.from_pydata([(0,0,0),(1,0,0),(2,0,0)],[],[(0,1,2)]);o=bpy.data.objects.new('malformed',m);bpy.context.collection.objects.link(o)
bad=qa_check.run(objects=[o.name],profile='game');(root/'reports/negative-test.json').write_text(json.dumps({'status':'PASS' if not bad['pass'] else 'FAIL','upstream':bad},indent=2));assert not bad['pass']
print(json.dumps({'technical_pass':technical,'negative_test':'PASS'}))
