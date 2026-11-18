"""Operator test inside pinned external Blender; never an app-shell command."""
import sys,pathlib,json,importlib.util
import bpy
args=sys.argv[sys.argv.index('--')+1:];source=pathlib.Path(args[0]);output=pathlib.Path(args[1])
cg=next(x[3:] for x in pathlib.Path('/proc/self/cgroup').read_text().splitlines() if x.startswith('0::'));limit=(pathlib.Path('/sys/fs/cgroup')/cg.lstrip('/')/'memory.max').read_text().strip();assert limit=='4294967296'
assert bpy.app.version[:3]==(5,2,1)
bpy.ops.wm.open_mainfile(filepath=str(source),load_ui=False,use_scripts=False)
helper=pathlib.Path(__file__).resolve().parents[2]/'ansible/roles/watoom-code/files/skills/human-pose-agent/scripts/rig_adapter.py';spec=importlib.util.spec_from_file_location('reviewed_adapter',helper);adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
assert adapter.inventory()['compatible'];rig=bpy.data.objects['Shadowheart'];bone=rig.pose.bones['hip'];locks=tuple(bone.lock_location);bone.lock_location=(True,False,False);assert not adapter.inventory()['compatible'];bone.lock_location=locks
profile=json.loads(adapter.PROFILE.read_text());record=profile['drivers'][0];driver=next(d for d in rig.animation_data.drivers if d.data_path==record['path'] and d.array_index==record['index']);old=driver.driver.expression;driver.driver.expression='1-x' if old!='1-x' else 'x';assert not adapter.inventory()['compatible'];driver.driver.expression=old;assert adapter.inventory()['compatible']
output.write_text(json.dumps({'status':'PASS','cases':['baseline match','changed control lock rejected','changed driver expression rejected','restored rig matches'],'cgroup_memory_max':int(limit),'assets_saved':False},indent=2))
