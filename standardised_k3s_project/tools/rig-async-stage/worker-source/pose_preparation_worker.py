"""Fixed installed pose helper adapter; called only inside the capture cgroup."""
import pathlib,json,sys,time,hashlib,importlib.util
import bpy
from windows_job import current_limit

def prepare(out,spec,group,limit,start):
 current_limit()
 scripts=(pathlib.Path(__file__).resolve().parent/'runtime_helpers')/'ansible/roles/watoom-code/files/skills/human-pose-agent/scripts'
 # Save a working copy while Blender rebases relative dependencies from the source.
 bpy.ops.wm.save_as_mainfile(filepath=str(out/'working-source.blend'),check_existing=True)
 method=spec.get('preparation',{}).get('method','inspect')
 if method!='inspect':(out/'pose-plan.json').write_text(json.dumps(spec['preparation']['plan'],indent=2))
 helper=scripts/'prepare_pose.py'
 module_spec=importlib.util.spec_from_file_location('watoom_fixed_prepare_pose',helper)
 module=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(module)
 if method=='ts4-retarget':
  sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'runtime_helpers/tools/ts4-animation'))
  from retarget_blender import prepare as retarget
  retarget(spec['preparation']['plan'],out)
 elif method=='rig-adapter':
  adapter_spec=importlib.util.spec_from_file_location('watoom_fixed_rig_adapter',scripts/'rig_adapter.py');adapter=importlib.util.module_from_spec(adapter_spec);adapter_spec.loader.exec_module(adapter);adapter.apply(spec['preparation']['plan'],out)
 else:
  args=['prepare_pose.py','--','--revision',str(out),'--mode',method,'--report','inspection.json']
  if method!='inspect':args+=['--plan','pose-plan.json','--output','posed.blend','--validation','pose-validation.json']
  previous=sys.argv
  try:
   sys.argv=args;code=module.main()
  finally:sys.argv=previous
  if code:raise ValueError('Pose helper failed; preserve diagnostic reports')
 adapter_spec=importlib.util.spec_from_file_location('watoom_fixed_rig_inventory',scripts/'rig_adapter.py');adapter_inventory=importlib.util.module_from_spec(adapter_spec);adapter_spec.loader.exec_module(adapter_inventory)
 supported=adapter_inventory.inventory();(out/'adapter-inventory.json').write_text(json.dumps(supported,indent=2))
 files=['working-source.blend','adapter-inventory.json']+(['inspection.json'] if (out/'inspection.json').is_file() else [])
 result={'status':'PASS' if method=='inspect' else 'PREPARED_REVIEW_PENDING','mode':spec['mode'],'engine':bpy.app.version_string,'seconds':time.time()-start,'adapter_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'requires_visual_review':method!='inspect','images':[],'rig_adapter':supported,'rig_adapter_id':supported['adapter'] if supported.get('compatible') else None,'rig_adapter_compatible':supported.get('compatible',False),'rig_fingerprint':supported.get('rig_fingerprint'),'helper_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [helper,scripts/'human_pose_agent.py',scripts/'auto_ik_validation.py',scripts/'rig_adapter.py']}}
 if method=='ts4-retarget':
  evidence=json.loads((out/'retarget-evidence.json').read_text())
  result['constraint_limited']=evidence.get('constraint_limited',False)
  result['constraint_warning']='Authored joint limits changed requested motion; review actual output' if result['constraint_limited'] else None
  result['retarget_diagnostics']=str(out/'retarget-diagnostics.json')
  files+=['retarget-evidence.json','retarget-diagnostics.json']
 if method!='inspect':
  validation=json.loads((out/'pose-validation.json').read_text());result['pose_status']=validation['status'];result['prepared_source']=str(out/'posed.blend');files+=['pose-plan.json','pose-validation.json','posed.blend']
  if validation['status'] in ('FAIL','BLOCKED') or not (out/'posed.blend').is_file():raise ValueError('No accepted preparation candidate')
 result.update(current_limit());result['files']=files;(out/'worker.json').write_text(json.dumps(result,indent=2))
