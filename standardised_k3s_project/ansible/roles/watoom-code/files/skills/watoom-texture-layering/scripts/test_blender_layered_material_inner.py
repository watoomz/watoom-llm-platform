"""Runs inside Blender: blender -b --factory-startup -P test_blender_layered_material_inner.py -- <workdir>. Prints @@RESULT@@{json}."""
import json
import math
import os
import sys

import bpy
import mathutils
from bpy_extras.object_utils import world_to_camera_view

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_layered_material as blm  # noqa: E402

work = sys.argv[sys.argv.index("--") + 1]
res = {}

# --- scene: sphere over a ground plane, sun from above-front, camera above-front
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(0, 0, 0), segments=48, ring_count=24)
sphere = bpy.context.object
sphere.name = "Ball"
bpy.ops.mesh.primitive_plane_add(size=12, location=(0, 0, -1.0))
plane = bpy.context.object
plane.name = "Ground"
bpy.ops.object.light_add(type="SUN", rotation=(math.radians(40), 0, math.radians(20)))
bpy.context.object.data.energy = 1.6
bpy.ops.object.camera_add(location=(0, -6.5, 3.5), rotation=(math.radians(62), 0, 0))
cam = bpy.context.object
bpy.context.scene.camera = cam
world = bpy.data.worlds.new("W")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.25
bpy.context.scene.world = world
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.samples = 24
sc.cycles.device = "CPU"
sc.render.resolution_x = sc.render.resolution_y = 160
sc.render.resolution_percentage = 100
sc.view_settings.view_transform = "Standard"

SPEC = {"name": "M_Test", "layers": [
    {"name": "grass", "color": [0.1, 0.5, 0.1], "roughness": 0.9},
    {"name": "rock", "color": [0.45, 0.45, 0.45], "roughness": 0.8, "mask": {"type": "slope", "from_deg": 30, "to_deg": 50}},
    {"name": "snow", "color": [0.95, 0.95, 1.0], "roughness": 0.5, "mask": {"type": "height", "from_m": 0.55, "to_m": 0.8}},
]}
res["build"] = blm.build(SPEC, ["Ball", "Ground"])
bpy.context.view_layer.update()


def pixel_for(world_point):
    uv = world_to_camera_view(sc, cam, mathutils.Vector(world_point))
    return int(uv.x * sc.render.resolution_x), int((1.0 - uv.y) * sc.render.resolution_y)


sc.render.filepath = os.path.join(work, "render.png")
bpy.ops.render.render(write_still=True)
img = bpy.data.images.load(sc.render.filepath)
W, H = img.size
px = list(img.pixels)


def rgb(world_point):
    x, y = pixel_for(world_point)
    i = ((H - 1 - y) * W + x) * 4  # pixels are bottom-up
    return px[i:i + 3]


res["ground"] = rgb((3.0, 0.0, -1.0))          # flat, low        -> grass
res["ball_front_mid"] = rgb((0.0, -0.98, 0.1))  # vertical-ish, low -> rock
res["ball_top"] = rgb((0.0, -0.35, 0.93))       # flat, high       -> snow

# --- every mask type builds and the graph links (no exception, an output reaches the BSDF)
kinds = [{"type": "uniform"}, {"type": "slope"}, {"type": "height", "from_m": 0, "to_m": 1, "noise": {"scale_m": 2, "amount": 0.3}},
         {"type": "noise", "scale_m": 2}, {"type": "ao"}, {"type": "edges", "radius": 0.02},
         {"type": "slope", "invert": True, "contrast": 2.0, "noise": {"scale_m": 1, "amount": 0.2}}]
built = []
for m in kinds:
    r = blm.build({"name": "M_Mask", "layers": [{"name": "a", "color": [0.2, 0.2, 0.2]}, {"name": "b", "color": [0.8, 0.8, 0.8], "mask": m}]})
    mat = bpy.data.materials["M_Mask"]
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    built.append(m["type"] + ":" + str(bsdf.inputs["Base Color"].is_linked))
res["masks"] = built
mv = blm.build({"name": "M_Vcol", "layers": [{"name": "a", "color": [0.2, 0.2, 0.2]}, {"name": "b", "color": [1, 1, 1], "mask": {"type": "vertex_color", "attribute": "Wear", "channel": "g"}}]})
res["vcol_ok"] = mv["ok"]
try:
    blm.build({"name": "M_Bad", "layers": [{"name": "a"}, {"name": "b", "mask": {"type": "bogus"}}]})
    res["bad_mask_rejected"] = False
except ValueError:
    res["bad_mask_rejected"] = True

# --- texture folder: colour spaces, normal chain, box-projection warning
tex = os.path.join(work, "rock")
os.makedirs(tex, exist_ok=True)
for suffix, col in (("basecolor", (0.4, 0.4, 0.4, 1)), ("normal", (0.5, 0.5, 1, 1)), ("roughness", (0.7, 0.7, 0.7, 1)), ("ao", (0.9, 0.9, 0.9, 1))):
    im = bpy.data.images.new("rock_" + suffix, 8, 8)
    im.pixels = list(col) * 64
    im.filepath_raw = os.path.join(tex, "rock_%s.png" % suffix)
    im.file_format = "PNG"
    im.save()
r = blm.build({"name": "M_Tex", "tiling": 3, "macro": {"scale_m": 8, "tint": [0.9, 0.9, 0.8]}, "layers": [{"name": "base", "color": [0.3, 0.3, 0.3]}, {"name": "rock", "textures": tex, "mask": {"type": "slope"}}]})
nodes = bpy.data.materials["M_Tex"].node_tree.nodes
spaces = {n.image.name.split(".")[0]: n.image.colorspace_settings.name for n in nodes if n.type == "TEX_IMAGE"}
res["tex_spaces"] = spaces
res["tex_normal_node"] = any(n.type == "NORMAL_MAP" for n in nodes)
res["tex_warnings"] = r["warnings"]
rb = blm.build({"name": "M_Box", "layers": [{"name": "base", "color": [0.3, 0.3, 0.3]}, {"name": "rock", "textures": tex, "projection": "box", "mask": {"type": "slope"}}]})
res["box_warnings"] = rb["warnings"]
try:
    blm.build({"name": "M_NoColor", "layers": [{"name": "a"}, {"name": "b", "textures": work}]})
    res["missing_basecolor_rejected"] = False
except ValueError:
    res["missing_basecolor_rejected"] = True
ex = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates", "material.example.json")))
res["example"] = blm.build(ex, ["Ball"])
print("@@RESULT@@" + json.dumps(res))
