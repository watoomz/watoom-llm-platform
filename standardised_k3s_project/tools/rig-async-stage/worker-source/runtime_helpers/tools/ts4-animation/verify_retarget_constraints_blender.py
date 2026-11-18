"""Run in a bounded operator Blender unit; no source assets are loaded."""
import bpy,sys,json,tempfile
from pathlib import Path
from mathutils import Quaternion,Matrix,Euler,Vector
sys.path.insert(0,str(Path(__file__).parent))
import retarget_blender as r
line=next(x for x in Path('/proc/self/cgroup').read_text().splitlines() if x.startswith('0::'))
assert (Path('/sys/fs/cgroup')/line[3:].lstrip('/')/'memory.max').read_text().strip()=='4294967296'
bpy.ops.wm.read_factory_settings(use_empty=True)
data=bpy.data.armatures.new('Fixture');rig=bpy.data.objects.new('Fixture',data);bpy.context.scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active=rig;rig.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
bone=data.edit_bones.new('control');bone.head=(0,0,0);bone.tail=(0,1,0)
bpy.ops.object.mode_set(mode='OBJECT');rig.animation_data_create()
bone=rig.pose.bones['control'];bone.rotation_mode='XYZ'
c=bone.constraints.new('LIMIT_ROTATION');c.owner_space='LOCAL';c.use_limit_x=True;c.min_x=-.2;c.max_x=.2
bone.rotation_euler=(.8,0,0);bpy.context.view_layer.update()
before=(c.min_x,c.max_x,c.mute,c.influence)
events=r.clamp_authored_limits(rig,bone)
assert events and abs(bone.rotation_euler.x-.2)<1e-5
assert r.angle_error(bone.matrix.to_quaternion(),r.unconstrained_pose_rotation(bone))<.001
assert before==(c.min_x,c.max_x,c.mute,c.influence)
# A legal pose is unchanged.
bone.rotation_euler=(.1,0,0);bpy.context.view_layer.update()
assert not r.clamp_authored_limits(rig,bone)
# Unsupported constraint spaces and partial influence are never projected.
c.owner_space='WORLD';bone.rotation_euler=(.8,0,0);bpy.context.view_layer.update()
assert not r.clamp_authored_limits(rig,bone)
c.owner_space='LOCAL';c.influence=.5
assert not r.clamp_authored_limits(rig,bone)
assert r.angle_error(Quaternion((1,0,0,0)),Quaternion((-1,0,0,0)))==0
# Errors still fail, but leave a persistent machine-readable diagnostic.
original=r._prepare
def fail(*args):raise ValueError('fixture unresolved control')
r._prepare=fail
with tempfile.TemporaryDirectory() as directory:
 try:r.prepare({'profile':'fixture'},directory)
 except ValueError:pass
 else:raise AssertionError('Error swallowed')
 evidence=json.loads((Path(directory)/'retarget-diagnostics.json').read_text())
 assert evidence['status']=='FAIL' and evidence['error']=='fixture unresolved control'
r._prepare=original
print('PASS: clamp, in-range, unchanged limits, unsupported space/influence, quaternion signs, persistent failures')
