"""Unreal-side portable export of a mounted Fab pack (runs under UnrealEditor-Cmd -run=PythonScript).

Reads /job/request.json: {"root": "/Game/<Folder>", "classes": ["SkeletalMesh","AnimSequence","StaticMesh","Texture2D"],
"include": ["substring", ...] (optional), "exclude": ["/Demo/", ...] (optional), "max_assets": 400}.
Writes GLB for skeletal meshes and animations (glTF Exporter: the FBX skeletal exporter needs a render
mesh object, which -NullRHI lacks), FBX for static meshes and TGA for textures,
request.json may set "anim_format": "fbx" to write animation sequences as FBX (tested headless); default is GLB.
under /job/exported/<relative asset path>, and /job/native-result.json with hashes. Source is read-only.
"""
import unreal,json,pathlib,traceback,hashlib,gc
JOB=pathlib.Path('/job');OUT=JOB/'exported'
r={'status':'FAIL','scope':'Portable FBX/TGA export of purchased Unreal source; source content is mounted read-only.'}
SUFFIX={'SkeletalMesh':'.glb','AnimSequence':'.glb','StaticMesh':'.fbx','Texture2D':'.tga'}
GLTF={'SkeletalMesh','AnimSequence'}
def fbx_options(kind):
 o=unreal.FbxExportOption()
 for key,value in [('fbx_export_compatibility',unreal.FbxExportCompatibility.FBX_2020),('ascii',False),('force_front_x_axis',False),
                   ('vertex_color',True),('level_of_detail',False),('collision',False),('export_morph_targets',True),
                   ('export_preview_mesh',False),('map_skeletal_motion_to_root',False),('export_local_time',True)]:
  try:o.set_editor_property(key,value)
  except Exception:pass  # property absent in this engine version: keep its default
 return o
def gltf_options():
 o=unreal.GLTFExportOptions()
 for key,value in [('bake_material_inputs',getattr(unreal.GLTFMaterialBakeMode,'DISABLED',None)),('export_vertex_skin_weights',True),('export_animation_sequences',True),
                   ('export_mesh_quantization',False),('export_level_sequences',False),('texture_image_format',getattr(unreal.GLTFTextureImageFormat,'NONE',None))]:
  if value is None:continue
  try:o.set_editor_property(key,value)
  except Exception:pass  # property absent in this engine version: keep its default
 return o
try:
 req=json.loads((JOB/'request.json').read_text());root=req['root'].rstrip('/')
 if req.get('anim_format')=='fbx':  # animation sequences as FBX (skeleton + animation, no preview mesh) instead of GLB; default stays GLB
  SUFFIX['AnimSequence']='.fbx';GLTF.discard('AnimSequence')
 classes=set(req.get('classes') or SUFFIX);bad=classes-set(SUFFIX)
 if bad:raise ValueError('Unsupported export classes: '+', '.join(sorted(bad)))
 include=req.get('include') or [];exclude=req.get('exclude') or ['/Demo/','/Maps/','/Levels/']
 registry=unreal.AssetRegistryHelpers.get_asset_registry();registry.scan_paths_synchronous([root],True)
 rows=[{'path':str(x.package_name),'class':str(x.asset_class_path.asset_name)} for x in registry.get_assets_by_path(root,True)]
 rows=[x for x in rows if x['class'] in classes and not any(e in x['path'] for e in exclude) and (not include or any(i.lower() in x['path'].lower() for i in include))]
 if not rows:raise ValueError('No matching assets under '+root)
 if len(rows)>int(req.get('max_assets',400)):raise ValueError('%d assets exceed max_assets; narrow include/classes'%len(rows))
 exported=[];failed=[]
 for row in sorted(rows,key=lambda x:(x['class']!='SkeletalMesh',x['path'])):
  try:
   asset=unreal.load_asset(row['path'])
   if asset is None:raise ValueError('load failed')
   target=(OUT/str(pathlib.PurePosixPath(row['path']).relative_to(root))).with_suffix(SUFFIX[row['class']]);target.parent.mkdir(parents=True,exist_ok=True)
   task=None
   if row['class'] in GLTF:
    ok=unreal.GLTFExporter.export_to_gltf(asset,str(target),gltf_options(),set())
    ok=ok[0] if isinstance(ok,tuple) else ok
   else:
    task=unreal.AssetExportTask()
    for key,value in {'object':asset,'filename':str(target),'automated':True,'prompt':False,'replace_identical':True}.items():task.set_editor_property(key,value)
    if row['class']!='Texture2D':task.set_editor_property('options',fbx_options(row['class']))
    ok=unreal.Exporter.run_asset_export_task(task)
   if not ok or not target.is_file() or target.stat().st_size==0:raise ValueError('exporter wrote nothing')
   info={**row,'file':str(target.relative_to(JOB)),'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
   if row['class']=='AnimSequence':
    skel=asset.get_editor_property('skeleton');info.update(skeleton=skel.get_path_name() if skel else None,seconds=round(asset.get_editor_property('sequence_length') if hasattr(asset,'sequence_length') else unreal.AnimationLibrary.get_sequence_length(asset),4))
   if row['class']=='SkeletalMesh':
    skel=asset.get_editor_property('skeleton');info['skeleton']=skel.get_path_name() if skel else None
   exported.append(info)
  except Exception as exc:failed.append({**row,'error':str(exc)[:300]})
  task=None;asset=None;gc.collect()
 if sum(x['bytes'] for x in exported)>4*1024**3:raise ValueError('Export exceeds the 4GiB output budget')
 r.update(status='PORTABLE_EXPORT_PASS' if exported and not failed else 'PARTIAL_EXPORT' if exported else 'FAIL',engine=unreal.SystemLibrary.get_engine_version(),
          root=root,exported=exported,failed=failed,counts={c:sum(1 for x in exported if x['class']==c) for c in sorted(classes)})
except Exception:r['error']=traceback.format_exc()
(JOB/'native-result.json').write_text(json.dumps(r,indent=2))
if r['status']=='FAIL':raise RuntimeError(r.get('error','export failed'))
