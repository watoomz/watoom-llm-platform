"""Build a pinned Windows adapter from the exact maintained server implementation."""
import argparse, hashlib, json, pathlib, shutil

def build(root, output):
    output=pathlib.Path(output);root=pathlib.Path(root);capsule=output/'runtime_helpers'
    inputs={}
    locations=['tools/ts4-animation','ansible/roles/watoom-code/files/skills/human-pose-agent']
    for relative in locations:
        for source in (root/relative).rglob('*'):
            if source.is_file() and source.suffix in ('.py','.json') and '__pycache__' not in source.parts:
                target=capsule/source.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
                inputs[str(source.relative_to(root))]=hashlib.sha256(source.read_bytes()).hexdigest()
    helper=capsule/'ansible/roles/watoom-code/files/skills/human-pose-agent/scripts/prepare_pose.py'
    code=helper.read_text()
    needle=" if root.resolve()!=root or not root.is_dir()"
    position=code.index(needle)
    code=code[:position]+" if sys.platform=='win32':\n  import re\n  from windows_job import current_limit\n  current_limit();in_worker=bool(re.fullmatch('[a-f0-9]{64}',root.name)) and root.parent.name=='jobs' and (root.parent.parent/'worker.lock').is_file()\n"+code[position:]
    helper.write_text(code)
    contract=capsule/'tools/ts4-animation/retarget_contract.py'
    contract.write_text(contract.read_text().replace("not plan['clip'].startswith('/')", "not Path(plan['clip']).is_absolute()"))
    for name in ['asset_capture_contract.py','pose_preparation_contract.py','animation_sampling.py','rig_pose_contract.py']:
        source=root/'tools/watoom-code'/name;shutil.copy2(source,output/name)
        inputs['tools/watoom-code/'+name]=hashlib.sha256(source.read_bytes()).hexdigest()
    p=output/'pose_preparation_contract.py'
    p.write_text(p.read_text().replace("pathlib.Path(__file__).resolve().parents[1]/'ts4-animation'","pathlib.Path(__file__).resolve().parent/'runtime_helpers/tools/ts4-animation'"))
    source=root/'tools/watoom-code/asset_capture_blender.py';text=source.read_text()
    inputs['tools/watoom-code/asset_capture_blender.py']=hashlib.sha256(source.read_bytes()).hexdigest()
    a=text.index('def cgroup():');b=text.index('def bounds(',a);text=text[:a]+text[b:]
    text=text.replace('from mathutils import Vector','from mathutils import Vector\nfrom windows_job import current_limit\nfrom portable_inputs import open_source')
    a=text.index(' group,limit=cgroup()');b=text.index(' if bpy.app.version',a)
    text=text[:a]+" limits=current_limit();group=None;limit=str(limits['memory_limit_bytes'])\n"+text[b:]
    a=text.index(" if source.suffix.lower()=='.blend':");b=text.index(" if spec['mode'] in ('pose-inspect'",a)
    text=text[:a]+" open_source(request)\n"+text[b:]
    text=text.replace("'cgroup_memory_max':int(limit),",'')
    text=text.replace("'cgroup_memory_peak':(group/'memory.peak').read_text().strip(),",'')
    text=text.replace("scene.render.threads=2;","scene.render.threads=4;").replace("'threads':2,","'threads':4,")
    text=text.replace(" scene.render.threads_mode='FIXED';", """ device=request.get('device','CPU')
 if device not in ('CPU','OPTIX'):raise ValueError('Unqualified worker device')
 if device=='OPTIX':
  preferences=bpy.context.preferences.addons['cycles'].preferences
  preferences.compute_device_type='OPTIX';preferences.refresh_devices()
  if not any(d.type=='OPTIX' for d in preferences.devices):raise ValueError('OptiX unavailable')
  for d in preferences.devices:d.use=d.type=='OPTIX'
  scene.cycles.device='GPU';scene.cycles.denoiser='OPTIX';scene.cycles.denoising_use_gpu=True
 else:
  scene.cycles.denoiser='OPENIMAGEDENOISE';scene.cycles.denoising_use_gpu=False
 scene.render.use_persistent_data=device=='OPTIX' and spec['mode'] in ('animation','turntable')
 scene.render.threads_mode='FIXED';""")
    text=text.replace('bpy.ops.render.render(write_still=True)','timed_render(scene,out)')
    timing_helper="FRAME_TIMINGS=[]\ndef timed_render(scene,out):\n start=time.perf_counter();bpy.ops.render.render(write_still=True)\n FRAME_TIMINGS.append({'frame':scene.frame_current,'seconds':time.perf_counter()-start,'memory_peak_bytes':current_limit()['memory_peak_bytes']})\n (out/'render-timings.json').write_text(json.dumps({'frames':FRAME_TIMINGS,'persistent_data':scene.render.use_persistent_data,'denoiser':scene.cycles.denoiser,'denoising_use_gpu':scene.cycles.denoising_use_gpu},indent=2))\n\n"
    text=text.replace('def main():',timing_helper+'def main():')
    text=text.replace("if __name__=='__main__':main()", """if __name__=='__main__':
 output=pathlib.Path(sys.argv[sys.argv.index('--')+1]).parent
 sys.stdout=(output/'blender.log').open('a',buffering=1);sys.stderr=sys.stdout
 main()
 plan=output/'plan.json';request=json.loads(plan.read_text());receipt=output/'worker.json';value=json.loads(receipt.read_text())
 if value.get('prepared_source'):
  bpy.ops.file.pack_all()
  bpy.ops.wm.save_as_mainfile(filepath=str(output/'posed.blend'),check_existing=True)
 value.update(current_limit());value['renderer_sha256']=__import__('hashlib').sha256(pathlib.Path(__file__).read_bytes()).hexdigest();value['runtime_manifest_sha256']=__import__('hashlib').sha256(pathlib.Path(__file__).with_name('renderer-provenance.json').read_bytes()).hexdigest();value.update(platform='Windows',stage=True,source_sha256=request.get('original_source_sha256',request['manifest']['source_sha256']),device=request.get('device','CPU'),render_device=bpy.context.scene.cycles.device)
 if 'preview_budget' in value:
  value['preview_budget']['device']=value['device']
  value['render_settings']={'persistent_data':bpy.context.scene.render.use_persistent_data,'denoiser':bpy.context.scene.cycles.denoiser,'denoising_use_gpu':bpy.context.scene.cycles.denoising_use_gpu}
  if (output/'render-timings.json').is_file():value['files'].append('render-timings.json')
 receipt.write_text(json.dumps(value,indent=2))
""")
    (output/'stage_renderer.py').write_text(text)
    source=root/'tools/watoom-code/pose_preparation_worker.py';text=source.read_text()
    inputs['tools/watoom-code/pose_preparation_worker.py']=hashlib.sha256(source.read_bytes()).hexdigest()
    text=text.replace('import bpy','import bpy\nfrom windows_job import current_limit')
    text=text.replace(" if limit!='4294967296':raise ValueError('External 4GiB worker required')",' current_limit()')
    text=text.replace("pathlib.Path(__file__).resolve().parents[2]", "(pathlib.Path(__file__).resolve().parent/'runtime_helpers')")
    text=text.replace("pathlib.Path(__file__).resolve().parents[1]/'ts4-animation'", "pathlib.Path(__file__).resolve().parent/'runtime_helpers/tools/ts4-animation'")
    text=text.replace("'cgroup_memory_max':int(limit),",'').replace("'cgroup_memory_peak':(group/'memory.peak').read_text().strip(),",'')
    text=text.replace(" result['files']=files;", " result.update(current_limit());result['files']=files;")
    (output/'pose_preparation_worker.py').write_text(text)
    (output/'renderer-provenance.json').write_text(json.dumps({'outputs':{str(f.relative_to(output)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [output/'stage_renderer.py',output/'pose_preparation_worker.py',*[output/n for n in ['asset_capture_contract.py','pose_preparation_contract.py','animation_sampling.py','rig_pose_contract.py']],*[f for f in capsule.rglob('*') if f.is_file() and f.suffix in ('.py','.json')]]},'inputs':inputs,'adapter_sha256':hashlib.sha256((output/'stage_renderer.py').read_bytes()).hexdigest(),'blender_version':'5.2.1','boundary':'Windows Job Object, 8GiB; Linux evidence fields are never asserted'},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--iac-root',required=True);parser.add_argument('--output',required=True);args=parser.parse_args();build(args.iac_root,args.output)
