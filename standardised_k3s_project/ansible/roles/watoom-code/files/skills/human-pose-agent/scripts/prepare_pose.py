"""WatooM builder-stage entry; run inside the pinned Blender, never as a shell command."""
import argparse,json,hashlib,sys,math
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
import human_pose_agent as agent
from auto_ik_validation import apply_auto_plan
ROOT=Path('/data/ai/projects/llm/pipelines/blender-asset-builder')
def digest(p):
 with p.open('rb') as stream:
  h=hashlib.sha256()
  for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def path(root,value,new=False):
 p=root/value
 if Path(value).is_absolute() or '..' in Path(value).parts or p.resolve()!=p or not p.is_relative_to(root):raise ValueError('Use direct task-relative paths')
 if new and p.exists():raise ValueError('Refusing existing output: '+str(p))
 if not p.parent.is_dir():raise ValueError('Output parent must already exist')
 return p
def main():
 args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
 p=argparse.ArgumentParser();p.add_argument('--revision',required=True);p.add_argument('--mode',choices=['inspect','auto','recipe'],default='inspect');p.add_argument('--report',required=True);p.add_argument('--plan');p.add_argument('--output');p.add_argument('--validation');a=p.parse_args(args)
 root=Path(a.revision)
 capture_root=Path('/data/ai/projects/images/.opencode/captures')
 in_worker=root.parent==capture_root and Path('/sys/fs/cgroup').is_dir()
 if in_worker:
  cg=next(x[3:] for x in Path('/proc/self/cgroup').read_text().splitlines() if x.startswith('0::'));limit=(Path('/sys/fs/cgroup')/cg.lstrip('/')/'memory.max').read_text().strip();in_worker=limit=='4294967296'
 if root.resolve()!=root or not root.is_dir() or not (root!=ROOT and root.is_relative_to(ROOT) or in_worker):raise ValueError('Task-local revision or verified capture-worker output required')
 if bpy.app.version[:3]!=(5,2,1):raise ValueError('Pinned Blender 5.2.1 required')
 source=Path(bpy.data.filepath)
 if not source.is_file():raise ValueError('Load a task-local working blend through the builder stage')
 if source.resolve()!=source or not source.is_relative_to(root):raise ValueError('Work only on a task-local asset copy')
 source_sha=digest(source);report=path(root,a.report,new=True);validation=None
 if a.mode!='inspect':
  if not a.plan or not a.output or not a.validation:raise ValueError('Pose preparation needs plan, new output and validation report')
  plan=path(root,a.plan);output=path(root,a.output,new=True);validation=path(root,a.validation,new=True)
  if output.suffix!='.blend':raise ValueError('Output must be a new .blend')
  if len({source,report,validation,output,plan})!=5:raise ValueError('Inputs and outputs must be distinct')
  data=json.loads(plan.read_text());arm=bpy.data.objects.get(data.get('armature',''))
  if arm is None or arm.type!='ARMATURE':raise ValueError('Select an exact inspected armature')
  if a.mode=='auto' and 'pelvis_world_position' in data:raise ValueError('Pelvis translation requires separate keyed-animation qualification')
  if a.mode=='recipe':
   for name,channels in data.get('poses',{}).items():
    bone=arm.pose.bones.get(name)
    if bone is None or bone.constraints or any(bone.lock_rotation) or any(bone.lock_location):raise ValueError('Unqualified constrained/locked recipe bone: '+name)
 try:
  inspection=agent.inspect();inspection['environment']={'blender':bpy.app.version_string,'source':str(source),'source_sha256':source_sha,'capture_route':'asset-image-clip-capture; native watoom_asset_capture'};agent.atomic_json(report,inspection)
  if a.mode=='auto':result=apply_auto_plan(inspection,plan,output,validation)
  elif a.mode=='recipe':result=agent.apply_recipe(inspection,plan,output);agent.atomic_json(validation,result)
  else:result={'status':'INSPECTED','armatures':len(inspection['armatures'])}
  unchanged=digest(source)==source_sha
  ok=unchanged and result.get('status') not in ('FAIL','BLOCKED')
  print('@@JSON@@'+json.dumps({'ok':ok,'status':result['status'],'source_unchanged':unchanged,'report':str(report),'validation':str(validation) if validation else None,'requires_visual_review':a.mode!='inspect'}),flush=True)
  return 0 if ok else 3
 except Exception as error:
  if validation is not None and not validation.exists():agent.atomic_json(validation,{'status':'BLOCKED','error':str(error),'saved':False})
  raise
if __name__=='__main__':
 try:raise SystemExit(main())
 except Exception as error:print('@@JSON@@'+json.dumps({'ok':False,'status':'BLOCKED','error':str(error)}),flush=True);raise SystemExit(2)
