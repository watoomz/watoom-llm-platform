"""Compose verified Vulkan-baked source modules using the native assembly transforms.
This fixed CPU stage never evaluates downloaded Python or modifies source modules.
"""

import pathlib, json, sys, hashlib, math, struct
import bpy
from mathutils import Vector, Matrix, Euler

request = json.loads(sys.argv[sys.argv.index("--") + 1])
plan = json.loads(pathlib.Path(request["plan"]).read_text())
bakes = json.loads(pathlib.Path(request["bakes"]).read_text())
if bakes.get("status") != "PASS":
    raise ValueError("Actual material-bake receipt required")
output = pathlib.Path(request["output"])
output.mkdir(parents=True, exist_ok=False)
bpy.ops.wm.read_factory_settings(use_empty=True)
templates = {}
materials = []
for module in bakes["modules"]:
    path = pathlib.Path(module["file"])
    blob = path.read_bytes()
    if hashlib.sha256(blob).hexdigest() != module["sha256"]:
        raise ValueError("Verified portable source changed")
    if len(blob) > 32 * 1024**2:
        raise ValueError("Portable module exceeds32MiB budget")
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    objects = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    if not objects or not all(o.data.uv_layers and len(o.material_slots) for o in objects):
        raise ValueError("Portable module lost UV/materials")
    for obj in objects:
        obj.data.use_fake_user = True
    templates[module["object_path"]] = [(o.data, o.matrix_world.copy()) for o in objects]
    materials += [{"source": module["object_path"], "sha256": module["sha256"], "images": module["images"]}]
    for obj in list(bpy.data.objects):
        if obj not in before:
            bpy.data.objects.remove(obj, do_unlink=True)
meshes = []
for index, item in enumerate(plan["placements"]):
    if item["asset"] not in templates:
        raise ValueError("Module has no verified textured derivative")
    pitch, yaw, roll = [math.radians(x) for x in item.get("rotation", [0, item["yaw"], 0])]
    # Unreal exporter uses (X,Z,Y) in glTF; Blender import adds Y-up to Z-up.
    # Net position is (X,-Y,Z), and rotation is Z(-yaw)*Y(-pitch)*X(roll).
    transform = (
        Matrix.Translation(Vector((item["position"][0] / 100, -item["position"][1] / 100, item["position"][2] / 100)))
        @ Euler((roll, -pitch, -yaw), "XYZ").to_matrix().to_4x4()
        @ Matrix.Diagonal((*item["scale"], 1))
    )
    for part, (mesh, matrix) in enumerate(templates[item["asset"]]):
        obj = bpy.data.objects.new("Dungeon_%04d_%s_%d-col" % (index, item["role"], part), mesh)
        bpy.context.collection.objects.link(obj)
        obj.matrix_world = transform @ matrix
        meshes.append(obj)
if not meshes or len(meshes) > 4096:
    raise ValueError("Bounded scene geometry required")
report = {
    "meshes": len(meshes),
    "vertices": 0,
    "faces": 0,
    "finite": True,
    "degenerate_faces": 0,
    "duplicate_faces": 0,
    "materials": "PROCEDURAL_TEST_TEXTURES" if bakes.get("fixture_only") else "VULKAN_BAKED_TEXTURES",
    "source_material_parity": "Selected static material inputs baked at256px; world-space effects frozen per module; dynamic/animated shader behavior excluded",
}
for obj in meshes:
    report["vertices"] += len(obj.data.vertices)
    report["faces"] += len(obj.data.polygons)
    report["finite"] &= all(math.isfinite(v) for row in obj.matrix_world for v in row) and all(
        math.isfinite(v) for vertex in obj.data.vertices for v in vertex.co
    )
    seen = set()
    for face in obj.data.polygons:
        key = tuple(sorted(face.vertices))
        report["duplicate_faces"] += int(key in seen)
        seen.add(key)
        report["degenerate_faces"] += int(face.area < 1e-12)
    if not obj.data.uv_layers or any(s.material is None for s in obj.material_slots):
        raise ValueError("Scene has unresolved UV/materials")
if not report["finite"] or report["degenerate_faces"] or report["duplicate_faces"]:
    raise ValueError("Geometry QA failed: " + json.dumps(report))
bpy.ops.object.select_all(action="DESELECT")
for obj in meshes:
    obj.select_set(True)
bpy.ops.export_scene.gltf(
    filepath=str(output / "asset.glb"), export_format="GLB", use_selection=True, export_animations=False
)
blob = (output / "asset.glb").read_bytes()
size = struct.unpack_from("<I", blob, 12)[0]
doc = json.loads(blob[20 : 20 + size])
if not doc.get("images") or not doc.get("textures"):
    raise ValueError("Final scene lost baked textures")
points = [obj.matrix_world @ Vector(c) for obj in meshes for c in obj.bound_box]
low = Vector(tuple(min(v[i] for v in points) for i in range(3)))
high = Vector(tuple(max(v[i] for v in points) for i in range(3)))
center = (low + high) / 2
radius = max((high - low).length, 0.1)
report["bounds_m"] = {"min": list(low), "max": list(high)}
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 8
scene.render.resolution_x = 512
scene.render.resolution_y = 512
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.world = bpy.data.worlds.new("DungeonPreviewWorld")
scene.world.color = (0.18, 0.18, 0.18)
for n, direction in enumerate(((1, -1, 2), (-1, 1, 2))):
    light = bpy.data.lights.new("PreviewLight" + str(n), "AREA")
    light.energy = 35 * radius * radius
    light.size = radius
    obj = bpy.data.objects.new(light.name, light)
    scene.collection.objects.link(obj)
    obj.location = center + Vector(direction) * radius
    obj.rotation_euler = (center - obj.location).to_track_quat("-Z", "Y").to_euler()
camera_data = bpy.data.cameras.new("PreviewCamera")
camera = bpy.data.objects.new(camera_data.name, camera_data)
scene.collection.objects.link(camera)
scene.camera = camera
camera_data.type = "ORTHO"
camera_data.ortho_scale = radius
camera.location = center + Vector((1, -1, 1.6)).normalized() * radius * 2
camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
scene.render.filepath = str(output / "perspective.png")
bpy.ops.render.render(write_still=True)
if plan["layout"].get("mode") == "fixed-grid":
    camera.location = center + Vector((0, 0, radius * 2))
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.ortho_scale = max(high.x - low.x, high.y - low.y) * 1.1
    scene.render.filepath = str(output / "overhead.png")
    bpy.ops.render.render(write_still=True)
# Reimport the actual final portable artifact, not an in-memory mesh assertion.
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(output / "asset.glb"))
loaded = [o for o in bpy.data.objects if o.type == "MESH"]
if len(loaded) != len(meshes) or not sum(len(o.data.polygons) for o in loaded):
    raise ValueError("Final GLB reimport failed")
report["export_reimport"] = True
(output / "validation.json").write_text(json.dumps(report, indent=2))
(output / "portable-materials.json").write_text(
    json.dumps({"status": "PASS", "modules": materials, "limitations": report["source_material_parity"]}, indent=2)
)
print("DUNGEON_PORTABLE_PASS=" + json.dumps(report))
