"""Typed fixed 3D Toolkit operations. No downloaded scripts or model runtimes are executed."""
import json, math, pathlib, shutil

REVISION = '76780c798562ef63786bc75debe3ec084d1025f2'
VIEWS = ('front','back','left','right','top','perspective')
FIELDS = {
 'asset-assistant.avian': {'body_length_cm':(42,12,140),'body_width_cm':(16,5,60),'body_height_cm':(20,6,70),'wingspan_cm':(90,20,320),'tail_length_cm':(22,4,100)},
 'asset-assistant.quadruped': {'body_length_cm':(70,25,140),'shoulder_height_cm':(55,15,100),'body_width_cm':(24,8,55),'head_length_cm':(24,8,45),'tail_length_cm':(35,5,80)},
 'asset-assistant.human': {'height_cm':(180,120,240),'weight_kg':(95,30,300)},
 'watoom.tree': {'height':(3,0.5,10),'branches':(8,3,24)},
 'watoom.terrain': {'size':(6,1,20),'resolution':(24,4,64),'height':(0.5,0,3)},
 'watoom.building': {'width':(3,1,10),'depth':(4,1,10),'height':(3,1,10)},
 'watoom.rock': {'radius':(0.5,0.1,3),'subdivisions':(2,1,3)},
}
CAPABILITIES = {
 'avian':['procedural-3d','bird-generation','rigging','animation','asset-export'],
 'quadruped':['procedural-3d','animal-generation','rigging','animation','asset-export'],
 'human':['procedural-3d','human-generation','rigging','animation','asset-export'],
 'tree':['procedural-3d','vegetation-generation','asset-export'],
 'terrain':['procedural-3d','terrain-generation','asset-export'],
 'building':['procedural-3d','architecture-generation','asset-export'],
 'rock':['procedural-3d','prop-generation','asset-export'],
}
def registry():
    return [{'id':key,'name':key,'capabilities':CAPABILITIES[key.split('.')[-1]],'backend':'blender-cpu',
      'source_revision':REVISION if key.startswith('asset-assistant.') else 'watoom-procedural/1.0.0',
      'license':'GPL-3.0-or-later' if key.startswith('asset-assistant.') else 'MIT',
      'state':'READY' if shutil.which('blender') else 'UNAVAILABLE',
      'dependencies':['Blender 5.2.3 verified native API subset'],'cpu':1,'gpu':0,'timeout':180,
      'parameters':{name:{'default':value[0],'minimum':value[1],'maximum':value[2],'type':'integer' if name in ('branches','resolution','subdivisions') else 'number'} for name,value in fields.items()},
      'output_contract':'watoom-3d/v1','formats':['blend','glb'],'permission':'watoom_toolkit_generate3d',
      'cancellation':'bounded-process-group','recovery':'persisted-receipt-no-blind-replay'} for key,fields in FIELDS.items()] + [
      {'id':'llama-mesh','state':'EXPERIMENTAL','capabilities':['text-to-3d'],'backend':'generic-specialist','reason':'Live GPU fencing and handover not authorized'},
      *[{'id':key,'state':'UNAVAILABLE','capabilities':['image-to-3d'],'backend':'generic-specialist','reason':'Optional runtime/weights not installed or validated'} for key in ('spar3d','sf3d','hunyuan3d')]]

def validate(payload):
    task=payload.get('task')
    allowed={'task','timeout','generator','parameters','seed','style'} if task=='3d-generate' else {'task','timeout','path','parameters'}
    if set(payload)-allowed: raise ValueError('unknown 3D request field')
    if task=='3d-generate':
        generator=payload.get('generator')
        if generator not in FIELDS: raise ValueError('generator unavailable or not approved')
        fields=FIELDS[generator]
        params=payload.get('parameters',{})
        if not isinstance(params,dict) or set(params)-set(fields): raise ValueError('unknown generator parameter')
        for name,value in params.items():
            if type(value) not in (int,float) or not math.isfinite(value) or not fields[name][1]<=value<=fields[name][2]: raise ValueError('generator parameter outside range')
            if name in ('resolution','branches','subdivisions') and type(value) is not int: raise ValueError('integer generator parameter required')
        seed=payload.get('seed',0)
        if type(seed) is not int or not 0<=seed<=2147483647: raise ValueError('invalid generator seed')
        if payload.get('style','default') not in ('default','magpie','wombat'): raise ValueError('unsupported style')
        if payload.get('style')=='magpie' and generator!='asset-assistant.avian': raise ValueError('magpie style requires Avian')
        if payload.get('style')=='wombat' and generator!='asset-assistant.quadruped': raise ValueError('wombat style requires Quadruped')
    elif task not in ('3d-inspect','3d-repair'): raise ValueError('unknown 3D operation')
    if 'parameters' in payload and task!='3d-generate':
        params=payload['parameters']
        if task!='3d-inspect' or not isinstance(params,dict) or set(params)!={'engine_validation'} or type(params['engine_validation']) is not int or params['engine_validation']!=1:raise ValueError('Only explicit real engine validation is supported for inspection')

# Engine-content asset registry cache for the pinned editor, generated once from an empty EngineValidation
# project. A warm cache halves the playback editor's startup; any mismatch only means a cold (slower) start.
UNREAL_REGISTRY_SEED = {
 'engine_sha256': '74dc43e1a653fe3a46f68a1b3db6c3500d04d0f68a8878c9aa1b76b36a08fad3',
 'root': '/data/ai/toolchains/unreal/5.8.3/asset-registry-seed-74dc43e1a653',
 'files': {'CachedAssetRegistry_0.ref': 'b701096754eb8e196f1e7220aa6382cad125cc917d82bd3d686c1619c0d9dec9',
           'CachedAssetRegistry_0_01A18A13A9DB7C249553DED8F64C8C79.bin': 'c2128f620b9ad4271e86f6ffacc4640f86a09bf2ca15aae402955ff8a797ee5d'}}

def seed_files_valid(folder, engine_sha256):
    """Return {name: bytes} when every pinned seed file is present and matches, else None."""
    import hashlib
    if engine_sha256 != UNREAL_REGISTRY_SEED['engine_sha256']: return None
    files = {}
    for name, digest in UNREAL_REGISTRY_SEED['files'].items():
        path = pathlib.Path(folder) / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024 * 1024: return None
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest: return None
        files[name] = data
    return files

def stage_registry_seed(worker_dir, engine_sha256):
    """Controller side: copy the verified seed into the worker's job directory."""
    files = seed_files_valid(UNREAL_REGISTRY_SEED['root'], engine_sha256)
    if files is None: return 'UNAVAILABLE'
    target = pathlib.Path(worker_dir) / 'asset-registry-seed'; target.mkdir(mode=0o770)
    for name, data in files.items(): (target / name).write_bytes(data)
    return 'STAGED'

def engine_validation(payload):
    return payload.get('task')=='3d-inspect' and payload.get('parameters')=={'engine_validation':1}

def command(payload,jobdir,input_path=None):
    validate(payload)
    request={**payload,'output':str(jobdir/'artifacts'),'job_id':jobdir.name}
    if input_path is not None: request['input']=str(input_path)
    if engine_validation(payload):
        import creative
        request['expected_engine_sha256']=creative.native_engine_sha()
        return ['python3','-B','/opt/watoom/engine_validate_worker.py',json.dumps(request,separators=(',',':'))]
    binary=shutil.which('blender')
    if not binary: raise ValueError('Blender unavailable')
    return [binary,'--factory-startup','--disable-autoexec','--background','--threads','1','--python-exit-code','1','--python','/opt/watoom/blender_3d.py','--',json.dumps(request,separators=(',',':'))]

def required(payload,jobid):
    if payload["task"]=="3d-creative":
        import creative
        return creative.required(payload,jobid)
    files=['manifest.json','validation.json','asset.blend','asset.glb',*[view+'.png' for view in VIEWS]]
    if payload['task']=='3d-repair': files.append('before-validation.json')
    return ['jobs/'+jobid+'/worker/artifacts/'+name for name in files]

def validate_artifact(data,relative):
    if relative.endswith('.blend') and not data.startswith(b'BLENDER'):
        raise ValueError('invalid editable Blender artifact')
    if relative.endswith('.glb'):
        import struct
        if len(data)<20 or struct.unpack_from('<4sII',data)!=(b'glTF',2,len(data)): raise ValueError('invalid GLB envelope')
        size,kind=struct.unpack_from('<II',data,12)
        if kind!=0x4E4F534A or size>len(data)-20: raise ValueError('invalid GLB JSON chunk')
        document=json.loads(data[20:20+size])
        if not document.get('meshes') or not document.get('buffers') or not document.get('accessors'): raise ValueError('GLB missing geometry')
    if pathlib.PurePosixPath(relative).name == 'validation.json':
        validation=json.loads(data)
        if not validation.get('meshes') or validation.get('finite') is not True or validation.get('degenerate_faces',1)!=0 or validation.get('duplicate_faces',1)!=0: raise ValueError('invalid generated geometry')
    if relative.endswith('manifest.json'):
        manifest=json.loads(data)
        if manifest.get('schema')!=1 or manifest.get('status')!='PASS' or manifest.get('export_reimport') is not True or not manifest.get('outputs'): raise ValueError('unverified 3D artifact manifest')

def validate_manifest(evidence,data):
    import hashlib
    manifest=json.loads(data)
    recorded={pathlib.PurePosixPath(item['path']).name:item for item in evidence}
    declared={item['path']:item for item in manifest['outputs']}
    if len(declared)!=len(manifest['outputs']) or set(declared)!=set(recorded)-{'manifest.json'}:raise ValueError('3D manifest output set mismatch')
    if recorded['manifest.json']['sha256']!=hashlib.sha256(data).hexdigest():raise ValueError('3D manifest changed during validation')
    for name,item in declared.items():
        if item.get('sha256')!=recorded[name]['sha256'] or item.get('bytes')!=recorded[name]['bytes']:raise ValueError('3D manifest output hash mismatch')
