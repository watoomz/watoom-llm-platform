"""Real installed UE import/reimport validator; isolated content only."""
import unreal,pathlib,json,traceback,math
r=pathlib.Path(__file__).resolve().parent;source=json.loads((r/'source.json').read_text())
report={'status':'FAIL','engine':unreal.SystemLibrary.get_engine_version(),'scope':'real FBX import, saved dependencies, hierarchy and animation pose evaluation','gpu':'NullRHI'}
try:
 assert report['engine'].startswith('5.8.3-')
 dest='/Game/WatoomBuilderValidation'
 tools=unreal.AssetToolsHelpers.get_asset_tools();sk=source['skeletal']
 def imported():
  types=(unreal.AnimSequence,unreal.Skeleton,unreal.SkeletalMesh,unreal.StaticMesh,unreal.Material,unreal.Texture)
  return [x for x in unreal.ObjectIterator() if isinstance(x,types) and x.get_path_name().startswith(dest+'/')]
 def mesh_task():
  ui=unreal.FbxImportUI()
  for k,v in {'automated_import_should_detect_type':False,'import_as_skeletal':sk,'import_mesh':True,'import_animations':sk,'import_materials':True,'import_textures':True,'create_physics_asset':False,'mesh_type_to_import':unreal.FBXImportType.FBXIT_SKELETAL_MESH if sk else unreal.FBXImportType.FBXIT_STATIC_MESH}.items():ui.set_editor_property(k,v)
  if not sk:
   ui.static_mesh_import_data.set_editor_property('combine_meshes',True)
   ui.static_mesh_import_data.set_editor_property('auto_generate_collision',True)
  task=unreal.AssetImportTask()
  for k,v in {'filename':str(r/'asset.fbx'),'destination_path':dest,'destination_name':'asset','automated':True,'replace_existing':True,'save':True,'options':ui}.items():task.set_editor_property(k,v)
  tools.import_asset_tasks([task])
  assets=imported()
  for a in assets:unreal.EditorAssetLibrary.save_loaded_asset(a,only_if_is_dirty=False)
  return assets
 assets=mesh_task();meshes=[x for x in assets if isinstance(x,unreal.SkeletalMesh if sk else unreal.StaticMesh)]
 assert len(meshes)==1,'Expected one imported combined mesh'
 mesh=meshes[0];report['mesh']=mesh.get_path_name()
 report['classes']={x.get_path_name():x.get_class().get_name() for x in assets}
 if sk:
  report['skeleton']=mesh.get_editor_property('skeleton').get_path_name()
  report['hierarchy']={n:str(unreal.SkeletalMeshEditorSubsystem.get_bone_parent(mesh,n)) for n in source['bones']}
  for n,parent in source['bones'].items():
   if parent is not None:assert report['hierarchy'][n]==parent,'Bone hierarchy mismatch: '+n
  animations=[x for x in assets if isinstance(x,unreal.AnimSequence)]
  report['animations']=[]
  for a in animations:
   duration=a.get_play_length();assert math.isfinite(duration) and duration>0
   changes=[]
   for bone in source['bones']:
    pa=unreal.AnimationLibrary.get_bone_pose_for_time(a,bone,0.,False)
    pb=unreal.AnimationLibrary.get_bone_pose_for_time(a,bone,duration*.25,False)
    if str(pa)!=str(pb):changes.append(bone)
   assert changes,'Imported clip is stationary: '+a.get_name()
   report['animations'].append({'name':a.get_name(),'seconds':duration,'moving_bones':changes})
  assert len(animations)>=len(source['animations']),'Missing source clips'
 else:
  bounds=mesh.get_bounds()
  ext=[bounds.box_extent.x,bounds.box_extent.y,bounds.box_extent.z]
  assert all(math.isfinite(x) and x>0 for x in ext)
  expected=sorted((hi-lo)*50 for lo,hi in source['bounds_metres'])
  assert all(abs(a-b)<=max(.1,b*.025) for a,b in zip(sorted(ext),expected)),'Scale mismatch'
  report['bounds_cm']=ext;report['lod_count']=mesh.get_num_lods()
  body=mesh.get_editor_property('body_setup');geom=body.get_editor_property('agg_geom')
  report['collision_primitives']=sum(len(geom.get_editor_property(k)) for k in ['box_elems','sphere_elems','sphyl_elems','convex_elems'])
  assert report['collision_primitives']>0,'No collision geometry'
 # Reimport into the same isolated namespace and validate asset identity/dependency retention.
 before={x.get_path_name():x.get_class().get_name() for x in assets}
 after={x.get_path_name():x.get_class().get_name() for x in mesh_task()}
 assert before==after,'Repeat import changed the asset set'
 report['reimport']='PASS';report['status']='PASS'
except Exception:report['exception']=traceback.format_exc()
finally:(r/'unreal-result.json').write_text(json.dumps(report,indent=2))
if report['status']!='PASS':raise RuntimeError('Real Unreal engine validation failed')
