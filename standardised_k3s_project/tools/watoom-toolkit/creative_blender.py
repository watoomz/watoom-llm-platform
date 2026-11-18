"""Library-derived preparation reusing the existing Blender QA, six renders and export validator."""
import sys,pathlib,json,runpy,shutil,subprocess,os
sys.path.insert(0,'/opt/watoom')
import bpy
from mathutils import Vector
import asset_catalog
from creative_blender_common import load,fix,uv,cube
request=json.loads(sys.argv[sys.argv.index('--')+1]);operation=request['operation'];params=request.get('parameters',{})
output=pathlib.Path(request['output']);work=output.parent/'creative-work';work.mkdir(parents=True,exist_ok=False)
sources=request['sources'];before={x['path']:asset_catalog.checksum(pathlib.Path(x['path'])) for x in sources}
assert all(before[x['path']]==x['reference']['sha256'] for x in sources),'Source changed before execution'
bpy.ops.wm.read_factory_settings(use_empty=True)
details={'operation':operation,'seed':request.get('seed',0),'parameters':params,'source_references':[x['reference'] for x in sources],'license_review_required':True,'unreal_acceptance':'BLOCKED until compatible editor is verified'}
if operation in ('inspect','optimize'):
 objects=load(sources[0]['path']);meshes=[o for o in objects if o.type=='MESH'];assert meshes,'Source has no geometry'
 if operation=='optimize':
  for obj in meshes:
   fix(obj.data)
   if not obj.data.uv_layers:uv(obj)
   if not any(m.type=='ARMATURE' for m in obj.modifiers):
    lod=obj.copy();lod.data=obj.data.copy();lod.name=obj.name+'_LOD1';bpy.context.collection.objects.link(lod)
    modifier=lod.modifiers.new('Bounded LOD','DECIMATE');modifier.ratio=params.get('lod_ratio',.5)
    bpy.context.view_layer.objects.active=lod;lod.select_set(True);bpy.ops.object.modifier_apply(modifier=modifier.name)
    lod.hide_render=True;lod['watoom_lod_level']=1;lod['watoom_editor_only']=True
  low=Vector(tuple(min((o.matrix_world@Vector(c))[i] for o in meshes for c in o.bound_box) for i in range(3)))
  high=Vector(tuple(max((o.matrix_world@Vector(c))[i] for o in meshes for c in o.bound_box) for i in range(3)))
  collision=cube('LibraryCollision-colonly',(low+high)/2,tuple(max(v,.01) for v in high-low));collision.hide_render=True
  details['optimization']={'normal_repair':True,'uv_creation_where_missing':True,'lod_ratio':params.get('lod_ratio',.5),'lod_runtime_policy':'Editable LOD retained in Blender; excluded from primary GLB to avoid overlapping runtime meshes; automatic engine LOD switching is NOT CONFIGURED','collision':'bounded box; Godot colonly import','nanite':'NOT MODIFIED'}
else:
 module=__import__('creative_'+operation)
 details.update(module.prepare(request,work))
prepared=work/'prepared.blend';bpy.ops.wm.save_as_mainfile(filepath=str(prepared),check_existing=False)
# Reuse the maintained generator's inspection, rendering, GLB validation and reimport.
sys.argv=['blender','--',json.dumps({'task':'3d-inspect','input':str(prepared),'output':str(output),'job_id':request['job_id'],'creative_operation':operation})]
runpy.run_path('/opt/watoom/blender_3d.py',run_name='__main__')
for filename in details.pop('_files',[]):shutil.copyfile(work/filename,output/filename)
for source in sources:assert asset_catalog.checksum(pathlib.Path(source['path']))==before[source['path']],'Source was modified'
details['source_hashes_unchanged']=True
(output/'creative.json').write_text(json.dumps(details,indent=2))
engine=output.parent/'godot-project';engine.mkdir();shutil.copyfile(output/'asset.glb',engine/'asset.glb')
project='config_version=5\n[application]\nconfig/name="WatooM Creative Acceptance"\nrun/main_scene="res://scene.tscn"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n'
scene='[gd_scene load_steps=2 format=3]\n[ext_resource type="PackedScene" path="res://asset.glb" id="1"]\n[node name="CreativeAcceptance" type="Node3D"]\n[node name="LibraryDerivative" parent="." instance=ExtResource("1")]\n'
verify=pathlib.Path('/opt/watoom/creative_verify.gd').read_text()
for name,value in [('project.godot',project),('scene.tscn',scene),('verify.gd',verify)]:
 (engine/name).write_text(value);(output/name).write_text(value)
binary=shutil.which('godot') or shutil.which('godot4')
if not binary:raise ValueError('Existing Godot unavailable')
environment={**os.environ,'WATOOM_CHARACTER':'1' if operation=='character' else '0','WATOOM_MATERIAL':'1' if operation=='material' else '0','WATOOM_COLLISION':'1' if operation=='optimize' else '0'}
for args in [[binary,'--headless','--path',str(engine),'--editor','--quit'],[binary,'--headless','--path',str(engine),'--script','res://verify.gd']]:
 result=subprocess.run(args,capture_output=True,text=True,timeout=45,env=environment)
 with (work/'godot.log').open('a') as log:log.write(result.stdout+result.stderr)
 if result.returncode:raise ValueError('Godot acceptance failed: '+(result.stdout+result.stderr)[-1600:])
acceptance=json.loads((engine/'acceptance.json').read_text());assert acceptance['status']=='PASS'
(output/'godot-validation.json').write_text(json.dumps(acceptance,indent=2))
manifest=json.loads((output/'manifest.json').read_text());manifest['creative']=details;manifest['godot_acceptance']=acceptance
files=[p for p in output.iterdir() if p.is_file() and p.name!='manifest.json']
manifest['outputs']=[{'path':p.name,'bytes':p.stat().st_size,'sha256':asset_catalog.checksum(p)} for p in sorted(files)]
(output/'manifest.json').write_text(json.dumps(manifest,indent=2))
print('WATOOM_CREATIVE_RESULT='+json.dumps({'status':'PASS','operation':operation,'source_integrity':'PASS','godot':'PASS'}))
