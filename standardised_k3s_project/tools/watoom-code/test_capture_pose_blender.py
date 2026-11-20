"""Operator integration fixture. Run only inside an external4GiB Blender unit."""

import bpy, sys, pathlib, json
from mathutils import Vector

out = pathlib.Path(sys.argv[sys.argv.index("--") + 1])
assert out.is_dir()
line = next(x for x in pathlib.Path("/proc/self/cgroup").read_text().splitlines() if x.startswith("0::"))
group = pathlib.Path("/sys/fs/cgroup") / line[3:].lstrip("/")
assert (group / "memory.max").read_text().strip() == "4294967296"
bpy.ops.wm.read_factory_settings(use_empty=True)
arm = bpy.data.armatures.new("FixtureRig")
rig = bpy.data.objects.new("FixtureRig", arm)
bpy.context.scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
bone = arm.edit_bones.new("Arm")
bone.head = (0, 0, 0)
bone.tail = (0, 0, 2)
bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.mesh.primitive_cube_add(size=1, location=(0.3, 0, 1))
mesh = bpy.context.object
mesh.name = "FixtureMesh"
mesh.scale = (0.5, 0.5, 2)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
groupv = mesh.vertex_groups.new(name="Arm")
groupv.add(list(range(len(mesh.data.vertices))), 1, "REPLACE")
mod = mesh.modifiers.new("FixtureSkin", "ARMATURE")
mod.object = rig
mat = bpy.data.materials.new("FixtureBlue")
mat.use_nodes = True
mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.06, 0.22, 0.65, 1)
mesh.data.materials.append(mat)
bone = rig.pose.bones["Arm"]
bone.rotation_mode = "XYZ"
for frame, angle in [(1, 0.0), (4, 0.8)]:
    bone.rotation_euler = (0, 0, angle)
    bone.keyframe_insert("rotation_euler", frame=frame)
rig.animation_data.action.name = "FixtureMotion"
bpy.context.scene.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=str(out / "source.blend"))
print("FIXTURE_SAVED; actual4GiB; keyed deform bone and visible skinned mesh")
