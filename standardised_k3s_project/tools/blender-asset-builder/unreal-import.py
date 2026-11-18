"""Run with the discovered UE PythonScript commandlet, in an isolated project."""
import unreal, pathlib, json, traceback
ROOT=pathlib.Path(__file__).resolve().parent
report={'engine':unreal.SystemLibrary.get_engine_version(),'fixtures':{},'status':'FAIL'}
out=ROOT/'reports/unreal-import.json'
try:
 tools=unreal.AssetToolsHelpers.get_asset_tools()
 for kind in ['prop','environment','magpie']:
  sk=kind=='magpie';dest='/Game/BuilderValidationV7/'+kind
  options=unreal.FbxImportUI()
  for key,val in {'automated_import_should_detect_type':False,'import_as_skeletal':sk,'import_mesh':True,'import_animations':sk,'import_materials':True,'import_textures':True,'create_physics_asset':False,'mesh_type_to_import':unreal.FBXImportType.FBXIT_SKELETAL_MESH if sk else unreal.FBXImportType.FBXIT_STATIC_MESH}.items():options.set_editor_property(key,val)
  if not sk:
   options.static_mesh_import_data.set_editor_property('combine_meshes',True)
   options.static_mesh_import_data.set_editor_property('auto_generate_collision',True)
  task=unreal.AssetImportTask()
  for key,val in {'filename':str(ROOT/('magpie-v7' if sk else kind)/'game-ready/asset.fbx'),'destination_path':dest,'destination_name':'asset','automated':True,'replace_existing':True,'save':True,'options':options}.items():task.set_editor_property(key,val)
  tools.import_asset_tasks([task])
  paths=list(task.get_editor_property('imported_object_paths'))

  types=(unreal.AnimSequence,unreal.Skeleton,unreal.SkeletalMesh,unreal.StaticMesh,unreal.Material,unreal.Texture)
  assets=[x for x in unreal.ObjectIterator() if isinstance(x,types) and x.get_path_name().startswith(dest+'/')]
  for x in assets:unreal.EditorAssetLibrary.save_loaded_asset(x,only_if_is_dirty=False)
  paths=[x.get_path_name() for x in assets]

  row={'paths':paths,'classes':{x.get_path_name():x.get_class().get_name() for x in assets if x},'status':'FAIL'}
  meshes=[x for x in assets if isinstance(x,unreal.SkeletalMesh if sk else unreal.StaticMesh)]
  row['mesh_count']=len(meshes)
  if sk:
   animations=[x for x in assets if isinstance(x,unreal.AnimSequence)]
   row['skeleton']=meshes[0].get_editor_property('skeleton').get_path_name() if meshes else None
   row['animations']=[]
   for x in animations:
    name=x.get_name()
    bone='head' if 'Idle' in name else ('thigh_L' if 'Walk' in name else 'wing_L')
    a=unreal.AnimationLibrary.get_bone_pose_for_time(x,bone,0.,False)
    b=unreal.AnimationLibrary.get_bone_pose_for_time(x,bone,.25,False)
    row['animations'].append({'name':name,'duration':x.get_play_length(),'motion':str(a)!=str(b),'pose0':str(a),'pose1':str(b)})
   sub=unreal.SkeletalMeshEditorSubsystem
   row['hierarchy']={n:str(sub.get_bone_parent(meshes[0],n)) for n in ['pelvis','spine','neck','head','wing_L','wing_R','thigh_L','shin_L','foot_L']}
   row['status']='PASS' if meshes and row['skeleton'] and len(animations)>=3 and all(x['duration']>0 and x['motion'] for x in row['animations']) else 'FAIL'
  else:
   row['bounds']=[str(x.get_bounds()) for x in meshes]
   row['status']='PASS' if meshes else 'FAIL'
  report['fixtures'][kind]=row;out.write_text(json.dumps(report,indent=2))
 report['status']='PASS' if all(x['status']=='PASS' for x in report['fixtures'].values()) else 'FAIL'
except Exception:
 report['exception']=traceback.format_exc()
finally:out.write_text(json.dumps(report,indent=2))
if report['status']!='PASS':raise RuntimeError('See '+str(out))
