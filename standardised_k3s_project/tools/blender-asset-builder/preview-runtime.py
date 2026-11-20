import bpy, sys, pathlib, math
from mathutils import Vector

r = pathlib.Path(sys.argv[sys.argv.index("--") + 1])
(r / "renders").mkdir(exist_ok=True)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 8
scene.render.threads_mode = "FIXED"
scene.render.threads = 2
scene.render.resolution_x = 384
scene.render.resolution_y = 384
scene.render.resolution_percentage = 100
scene.world.use_nodes = True
scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.18, 0.20, 0.24, 1)
scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
meshes = [o for o in scene.objects if o.type == "MESH"]
coords = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
lo = Vector(tuple(min(p[i] for p in coords) for i in range(3)))
hi = Vector(tuple(max(p[i] for p in coords) for i in range(3)))
target = (lo + hi) / 2
size = max(hi - lo) * 1.5


def aim(o):
    o.rotation_euler = (target - o.location).to_track_quat("-Z", "Y").to_euler()


for name, v, power in [("Key", (1, -1, 2), 90), ("Fill", (-1, -0.3, 1), 50), ("Rim", (0, 1, 2), 80)]:
    d = bpy.data.lights.new(name, "AREA")
    d.energy = power * size * size
    d.shape = "DISK"
    d.size = size
    o = bpy.data.objects.new(name, d)
    scene.collection.objects.link(o)
    o.location = target + Vector(v) * size
    aim(o)
d = bpy.data.cameras.new("ReviewCamera")
cam = bpy.data.objects.new("ReviewCamera", d)
scene.collection.objects.link(cam)
scene.camera = cam
d.type = "ORTHO"
d.ortho_scale = size
rig = next((o for o in scene.objects if o.type == "ARMATURE"), None)
actions = ["Idle", "Walk", "Flight"] if rig else ["Static"]
for act in actions:
    if rig:
        for t in rig.animation_data.nla_tracks:
            t.mute = True
        rig.animation_data.action = bpy.data.actions.get(act)
        scene.frame_set(7)
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        pts = [o.evaluated_get(dg).matrix_world @ Vector(c) for o in meshes for c in o.evaluated_get(dg).bound_box]
        lo = Vector(tuple(min(v[i] for v in pts) for i in range(3)))
        hi = Vector(tuple(max(v[i] for v in pts) for i in range(3)))
        target = (lo + hi) / 2
        size = max(hi - lo) * 1.5
        d.ortho_scale = size
    for name, view in [("side", (1, 0.1, 0.3)), ("front", (0.2, -1, 0.3))]:
        cam.location = target + Vector(view) * size * 2
        aim(cam)
        scene.render.filepath = str(r / "renders" / (act + "-" + name + ".png"))
        bpy.ops.render.render(write_still=True)
