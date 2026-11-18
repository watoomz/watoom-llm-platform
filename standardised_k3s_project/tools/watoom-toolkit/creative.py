"""Creative operations reuse Toolkit jobs, publication, CPU workers and native scoped dispatch."""
import json,math,pathlib,re,shutil,sys,os
import asset_catalog
import dungeon_pipeline
TASKS={'asset-index','asset-search','3d-creative'}
OPERATIONS={'inspect','optimize','world','character','material'}
BASE=['asset.blend','asset.glb','manifest.json','validation.json','front.png','back.png','left.png','right.png','top.png','perspective.png']
ENGINE=['creative.json','godot-validation.json','project.godot','scene.tscn','verify.gd']
MAPS=['albedo.png','normal.png','roughness.png','metallic.png','orm.png']
def validate(payload):
 task=payload.get('task')
 allowed={'task','timeout','operation_id'}
 allowed|= {'limit'} if task=='asset-index' else {'query','category','format','limit'} if task=='asset-search' else {'operation','asset_id','asset_ids','seed','parameters','dungeon'}
 if task not in TASKS or set(payload)-allowed:raise ValueError('Unsupported creative request field/task')
 if 'operation_id' in payload and not re.fullmatch('[a-f0-9]{64}',str(payload['operation_id'])):raise ValueError('Invalid native operation identity')
 if task=='asset-index':
  if type(payload.get('limit',256)) is not int or not 1<=payload.get('limit',256)<=1024:raise ValueError('Index batch outside bounds')
 elif task=='asset-search':
  if not isinstance(payload.get('query',''),str) or len(payload.get('query',''))>256 or type(payload.get('limit',16)) is not int or not 1<=payload.get('limit',16)<=16:raise ValueError('Invalid bounded search')
  if payload.get('category') and payload['category'] not in asset_catalog.CATEGORIES:raise ValueError('Unknown category')
  if payload.get('format') and '.'+payload['format'].lower().lstrip('.') not in asset_catalog.FORMATS:raise ValueError('Unknown format')
 else:
  if payload.get('operation') not in OPERATIONS:raise ValueError('Unsupported creative operation')
  ids=[payload.get('asset_id'),*payload.get('asset_ids',[])]
  if not 1<=len(ids)<=4 or any(not isinstance(x,str) or not re.fullmatch('ast_[a-f0-9]{24}',x) for x in ids):raise ValueError('Select indexed existing library assets first')
  if type(payload.get('seed',0)) is not int or not 0<=payload.get('seed',0)<=2147483647:raise ValueError('Invalid seed')
  if 'dungeon' in payload:
   if payload['operation']!='world' or ('parameters' in payload and (not isinstance(payload['parameters'],dict) or payload['parameters'])):raise ValueError('Dungeon options apply only to native world mode')
   dungeon_pipeline.validate(payload['dungeon'],payload.get('seed',0))
   if len(ids)!=(2 if payload['dungeon']['style']=='mixed' else 1) or len(set(ids))!=len(ids):raise ValueError('Select one pack anchor or two compatible mixed anchors')
   return
  params=payload.get('parameters',{})
  bounds={'size':(2,32),'resolution':(4,48),'height':(0,3),'instances':(1,64),'density':(0,1),'lod_ratio':(.1,1),'roughness':(0,1),'metallic':(0,1),'texture_resolution':(32,512)}
  if not isinstance(params,dict) or set(params)-set(bounds):raise ValueError('Unknown creative parameter')
  for name,value in params.items():
   if type(value) not in (int,float) or not math.isfinite(value) or not bounds[name][0]<=value<=bounds[name][1]:raise ValueError('Creative parameter outside bounds')
   if name in ('resolution','instances','texture_resolution') and type(value) is not int:raise ValueError('Integer parameter required')
def names(payload):
 if payload['task'].startswith('asset-'):return ['result.json','manifest.json']
 if 'dungeon' in payload:return dungeon_pipeline.OUTPUTS
 return BASE+ENGINE+(['world-layout.json'] if payload['operation']=='world' else MAPS if payload['operation']=='material' else [clip+'-'+frame+'.png' for clip in ['Idle','Walk','Run'] for frame in ['a','b']] if payload['operation']=='character' else [])
def required(payload,jobid):return ['jobs/'+jobid+'/worker/artifacts/'+n for n in names(payload)]
def native_engine_sha():
 expected=os.environ.get('WATOOM_UNREAL_EDITOR_SHA256','')
 if not re.fullmatch('[a-f0-9]{64}',expected):raise ValueError('Accepted Unreal editor checksum must be configured')
 if asset_catalog.checksum(pathlib.Path('/unreal-engine/Engine/Binaries/Linux/UnrealEditor'))!=expected:
  raise ValueError('Mounted Unreal editor does not match accepted checksum')
 return expected
def command(payload,jobdir,catalog):
 validate(payload)
 if 'dungeon' in payload:
  if os.environ.get('WATOOM_DUNGEON_ENABLED')!='1':raise ValueError('Native dungeon execution is not enabled until validated engine, pack adapters and worker integration pass')
  engine_sha=native_engine_sha()
  plan=dungeon_pipeline.prepare(payload,catalog)
  required={p['asset'] for p in plan['placements']}
  if required!={p['object_path'] for p in plan.get('portable_modules',[])}:raise ValueError('Every selected module requires a verified textured derivative')
  if plan['layout']['stairs'] and plan.get('vertical_contract')!='east-bay-v1':raise ValueError('Multi-level native traversal requires the verified vertical contract')
  request={**payload,'output':str(jobdir/'worker/artifacts'),'job_id':jobdir.name,'expected_plan_sha256':plan['plan_sha256'],'expected_engine_sha256':engine_sha}
  return ['python3','-B','/opt/watoom/dungeon_worker.py',json.dumps(request,separators=(',',':'))]
 output=jobdir/'worker/artifacts'
 if payload['task'].startswith('asset-'):
  request={**payload,'root':str(catalog.root),'catalog':str(catalog.state),'output':str(output),'job_id':jobdir.name}
  return ['python3','-B','/opt/watoom/creative.py',json.dumps(request,separators=(',',':'))]
 sources=[]
 for asset_id in [payload['asset_id'],*payload.get('asset_ids',[])]:
  cached=catalog.load()['records'].get(asset_id)
  if not cached or cached.get('bytes',0)>320*1024**2:raise ValueError('Selected asset exceeds bounded CPU import budget or is not indexed')
  suffix=pathlib.Path(cached['path']).suffix.lower()
  supported=('.png','.jpg','.jpeg','.tif','.tiff') if payload['operation']=='material' else ('.glb','.gltf','.blend','.fbx','.obj')
  if suffix not in supported:raise ValueError('Selected asset requires archive/editor staging rather than portable import')
  path,record=catalog.resolve(asset_id)
  sources.append({'path':str(path),'reference':record})
 if payload['operation']=='material':
  if pathlib.Path(sources[0]['path']).suffix.lower() not in ('.png','.jpg','.jpeg','.tif','.tiff'):raise ValueError('Material source must be an indexed image')
 elif any(pathlib.Path(x['path']).suffix.lower() not in ('.glb','.gltf','.blend','.fbx','.obj') for x in sources):raise ValueError('Selected format requires Unreal/editor or archive staging; not a portable Blender input')
 binary=shutil.which('blender')
 if not binary:raise ValueError('Existing Blender unavailable')
 request={**payload,'input':sources[0]['path'],'sources':sources,'output':str(output),'job_id':jobdir.name}
 return [binary,'--factory-startup','--disable-autoexec','--background','--threads','1','--python-exit-code','1','--python','/opt/watoom/creative_blender.py','--',json.dumps(request,separators=(',',':'))]
def validate_catalog_manifest(evidence,data):
 import hashlib
 manifest=json.loads(data)
 if manifest.get('schema')!=1 or manifest.get('status')!='PASS':raise ValueError('Catalog job manifest invalid')
 actual={pathlib.PurePosixPath(x['path']).name:x for x in evidence}
 for item in manifest['outputs']:
  old=actual.get(item['path'])
  if not old or old['sha256']!=item['sha256'] or old['bytes']!=item['bytes']:raise ValueError('Catalog artifact changed')
 if set(actual)!={'manifest.json','result.json'}:raise ValueError('Catalog artifact set mismatch')
def main(request):
 import hashlib
 catalog=asset_catalog.Catalog(request['root'],request['catalog'])
 result=catalog.index(limit=request.get('limit',256)) if request['task']=='asset-index' else {'results':catalog.search(request.get('query',''),request.get('category'),request.get('format'),request.get('limit',16))}
 if request['task']=='asset-search':
  selected=[];budget=24000
  for record in result['results']:
   encoded=json.dumps(record).encode()
   if len(encoded)>budget:
    result['truncated']=True;break
   selected.append(record);budget-=len(encoded)
  result['results']=selected
 output=pathlib.Path(request['output']);output.mkdir(parents=True,exist_ok=False)
 blob=json.dumps(result,sort_keys=True,indent=2).encode();(output/'result.json').write_bytes(blob)
 manifest={'schema':1,'status':'PASS','job_id':request['job_id'],'task':request['task'],'outputs':[{'path':'result.json','bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest()}]}
 (output/'manifest.json').write_text(json.dumps(manifest,indent=2))
 print(json.dumps(result)[:10000])
if __name__=='__main__':main(json.loads(sys.argv[1]))
