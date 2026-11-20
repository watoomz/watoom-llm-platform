"""Trusted CPU Blender generator/inspection/export entry point. Artist source is preserved."""

import hashlib, json, math, random, struct, sys
from pathlib import Path

sys.path.insert(0, "/opt/watoom")
sys.path.insert(0, "/opt/asset-assistant")
import bpy, bmesh
from mathutils import Vector
from three_d import FIELDS, REVISION, VIEWS, validate

request = json.loads(sys.argv[sys.argv.index("--") + 1])
validate({k: v for k, v in request.items() if k not in ("output", "job_id", "input", "creative_operation")})
output = Path(request["output"])
output.mkdir(parents=True, exist_ok=False)
rng = random.Random(request.get("seed", 0))


def material(name, color):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    mat.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value = (*color, 1)
    mat.node_tree.nodes.get("Principled BSDF").inputs["Roughness"].default_value = 0.72
    return mat


def use_action(rig, action):
    # Blender 4.4+ layered actions animate only through an assigned slot; 4.2 has no slots.
    rig.animation_data.action = action
    if getattr(rig.animation_data, "action_slot", 1) is None and rig.animation_data.action_suitable_slots:
        rig.animation_data.action_slot = rig.animation_data.action_suitable_slots[0]


def inspection(objects):
    meshes = [o for o in objects if o.type == "MESH"]
    report = {
        "meshes": len(meshes),
        "vertices": 0,
        "faces": 0,
        "finite": True,
        "degenerate_faces": 0,
        "duplicate_faces": 0,
        "non_manifold_edges": 0,
        "inconsistent_normals": 0,
        "disconnected_components": 0,
        "missing_materials": 0,
        "missing_uv_meshes": 0,
        "uv_nonfinite": 0,
        "unweighted_vertices": 0,
        "bones": 0,
        "bone_hierarchy_valid": True,
        "animation_clips": [],
        "warnings": [],
    }
    for obj in meshes:
        mesh = obj.data
        report["vertices"] += len(mesh.vertices)
        report["faces"] += len(mesh.polygons)
        report["finite"] &= all(math.isfinite(x) for v in mesh.vertices for x in v.co)
        report["finite"] &= all(math.isfinite(x) for row in obj.matrix_world for x in row)
        seen = set()
        for face in mesh.polygons:
            key = tuple(sorted(face.vertices))
            report["degenerate_faces"] += int(face.area < 1e-12 or len(set(face.vertices)) < 3)
            report["duplicate_faces"] += int(key in seen)
            seen.add(key)
            report["missing_materials"] += int(
                face.material_index >= len(mesh.materials) or mesh.materials[face.material_index] is None
            )
        report["missing_uv_meshes"] += int(not mesh.uv_layers)
        report["uv_nonfinite"] += sum(
            not all(math.isfinite(x) for x in uv.uv) for layer in mesh.uv_layers for uv in layer.data
        )
        bm = bmesh.new()
        bm.from_mesh(mesh)
        report["non_manifold_edges"] += sum(not e.is_manifold for e in bm.edges)
        report["inconsistent_normals"] += sum(e.is_manifold and not e.is_contiguous for e in bm.edges)
        remaining = set(bm.verts)
        while remaining:
            report["disconnected_components"] += 1
            stack = [remaining.pop()]
            while stack:
                for edge in stack.pop().link_edges:
                    for vertex in edge.verts:
                        if vertex in remaining:
                            remaining.remove(vertex)
                            stack.append(vertex)
        bm.free()
        if any(m.type == "ARMATURE" for m in obj.modifiers):
            report["unweighted_vertices"] += sum(sum(g.weight for g in v.groups) < 0.99 for v in mesh.vertices)
    for obj in objects:
        if obj.type == "ARMATURE":
            report["bones"] += len(obj.data.bones)
            for bone in obj.data.bones:
                parents = set()
                current = bone
                while current.parent:
                    if current.name in parents:
                        report["bone_hierarchy_valid"] = False
                        break
                    parents.add(current.name)
                    current = current.parent
                report["finite"] &= all(math.isfinite(x) for v in (bone.head_local, bone.tail_local) for x in v)
    report["animation_clips"] = [a.name for a in bpy.data.actions]
    for key in (
        "non_manifold_edges",
        "inconsistent_normals",
        "disconnected_components",
        "missing_materials",
        "missing_uv_meshes",
        "unweighted_vertices",
    ):
        if report[key]:
            report["warnings"].append(key + ": " + str(report[key]))
    return report


def primitives(generator, params):
    created = []

    def keep(color):
        obj = bpy.context.object
        obj.data.materials.append(color)
        created.append(obj)
        return obj

    if generator == "watoom.tree":
        height = params["height"]
        wood = material("Bark", (0.18, 0.08, 0.03))
        leaf = material("Leaves", (0.06, 0.28, 0.05))
        bpy.ops.mesh.primitive_cone_add(
            vertices=12, radius1=height * 0.06, radius2=height * 0.02, depth=height, location=(0, 0, height / 2)
        )
        keep(wood)
        for i in range(int(params["branches"])):
            angle = i * 2.4
            z = height * (0.4 + 0.55 * i / params["branches"])
            length = height * (0.22 - 0.08 * i / params["branches"])
            end = Vector((math.cos(angle) * length, math.sin(angle) * length, z + height * 0.12))
            start = Vector((0, 0, z))
            bpy.ops.mesh.primitive_cone_add(
                vertices=8,
                radius1=height * 0.015,
                radius2=height * 0.003,
                depth=(end - start).length,
                location=(start + end) / 2,
            )
            branch = keep(wood)
            branch.rotation_euler = (end - start).to_track_quat("Z", "Y").to_euler()
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=height * 0.20, location=end)
            crown = keep(leaf)
            crown.scale.z = 0.7
    elif generator == "watoom.terrain":
        size = params["size"]
        n = int(params["resolution"])
        height = params["height"]
        phase = rng.random() * math.pi * 2
        vertices = [
            (
                (x / n - 0.5) * size,
                (y / n - 0.5) * size,
                height * (0.45 * math.sin(x / n * 8 + phase) * math.cos(y / n * 7) + 0.2 * math.sin((x + y) / n * 11)),
            )
            for y in range(n + 1)
            for x in range(n + 1)
        ]
        faces = [
            (y * (n + 1) + x, y * (n + 1) + x + 1, (y + 1) * (n + 1) + x + 1, (y + 1) * (n + 1) + x)
            for y in range(n)
            for x in range(n)
        ]
        mesh = bpy.data.meshes.new("Terrain")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        obj = bpy.data.objects.new("Terrain", mesh)
        bpy.context.collection.objects.link(obj)
        obj.data.materials.append(material("Earth", (0.20, 0.25, 0.10)))
        created.append(obj)
    elif generator == "watoom.building":
        wall = material("Masonry", (0.56, 0.47, 0.32))
        roof = material("Roof", (0.18, 0.22, 0.28))
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, params["height"] / 2))
        house = keep(wall)
        house.scale = (params["width"], params["depth"], params["height"])
        bpy.ops.mesh.primitive_cone_add(
            vertices=4,
            radius1=1,
            depth=params["height"] * 0.4,
            location=(0, 0, params["height"] * 1.2),
            rotation=(0, 0, math.pi / 4),
        )
        cap = keep(roof)
        cap.scale = (params["width"] / 1.3, params["depth"] / 1.3, 1)
    elif generator == "watoom.rock":
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=int(params["subdivisions"]), radius=params["radius"])
        rock = keep(material("Stone", (0.27, 0.28, 0.30)))
        for vertex in rock.data.vertices:
            vertex.co *= rng.uniform(0.8, 1.2)
        rock.data.update()
    for obj in created:
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project()
        bpy.ops.object.mode_set(mode="OBJECT")
    return created


bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
generator = request.get("generator", "asset-inspection")
params = {name: values[0] for name, values in FIELDS.get(generator, {}).items()}
params.update(request.get("parameters", {}))
root = None
if request["task"] == "3d-generate" and generator.startswith("asset-assistant."):
    from object_core.objects import get_provider
    from blender_adapter.adapter import create_character
    from blender_adapter.workflow import add_basic_rig
    from blender_adapter.animation import add_idle, add_flight, add_locomotion
    from blender_adapter.materials import prepare_materials

    provider = get_provider(generator.split(".")[-1])
    values = {field.key: field.default for field in provider.parameters}
    values.update(params)
    params = values
    root = create_character(provider.mesh(values), name="WatooM-" + request.get("style", provider.key))
    root["object_type"] = provider.key
    for key, value in values.items():
        root[key] = value
    rig = add_basic_rig(root, bpy.context)
    prepare_materials(root)
    add_idle(root, bpy.context.scene)
    if getattr(provider, "supports_flight", False):
        add_flight(root, bpy.context.scene)
    else:
        add_locomotion(root, bpy.context.scene)
    objects = [root, *root.children_recursive]
    style = request.get("style", "default")
    if style == "magpie":
        # Shape the provider's narrow wing blockout into a readable flight silhouette.
        # Keep vertex indices and skin weights, so the recovered provider rig remains authoritative.
        scale = root["coordinate_scale"]
        length = values["body_length_cm"] * scale
        width = values["body_width_cm"] * scale
        span = values["wingspan_cm"] * scale
        for obj in objects:
            if obj.type != "MESH":
                continue
            for vertex in obj.data.vertices:
                if abs(vertex.co.x) > width * 0.55:
                    progress = (abs(vertex.co.x) - width * 0.36) / (span * 0.5 - width * 0.36)
                    axis = length * (0.08 - 0.16 * progress)
                    vertex.co.y = axis + (vertex.co.y - axis) * 3.2
            obj.data.update()
            smooth = obj.modifiers.new("Magpie rounded silhouette", "SUBSURF")
            smooth.levels = 1
            smooth.render_levels = 1
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.modifier_apply(modifier=smooth.name)
            for face in obj.data.polygons:
                face.use_smooth = True
    if style in ("magpie", "wombat"):
        base = material(
            "Magpie Black" if style == "magpie" else "Wombat Fur",
            (0.015, 0.018, 0.02) if style == "magpie" else (0.24, 0.16, 0.09),
        )
        patch = material("Magpie White", (0.82, 0.85, 0.88)) if style == "magpie" else None
        for obj in objects:
            if obj.type != "MESH":
                continue
            obj.data.materials.clear()
            obj.data.materials.append(base)
            if patch:
                obj.data.materials.append(patch)
                for face in obj.data.polygons:
                    white = 0
                    for index in face.vertices:
                        white += int(
                            any(
                                (
                                    "wing.upper" in obj.vertex_groups[g.group].name
                                    or obj.vertex_groups[g.group].name == "neck"
                                )
                                and g.weight > 0.65
                                for g in obj.data.vertices[index].groups
                            )
                        )
                    face.material_index = int(white >= len(face.vertices) / 2)
        if style == "magpie":
            # Explicit facial landmarks distinguish the bird from an unreviewed blockout.
            scale = root["coordinate_scale"]
            length = values["body_length_cm"] * scale
            width = values["body_width_cm"] * scale
            height = values["body_height_cm"] * scale
            eye_mat = material("Magpie Eye", (0.012, 0.008, 0.006))
            beak_mat = material("Magpie Beak", (0.30, 0.34, 0.36))
            features = []
            for sign in (-1, 1):
                bpy.ops.mesh.primitive_uv_sphere_add(
                    segments=12,
                    ring_count=8,
                    radius=width * 0.045,
                    location=(sign * width * 0.255, length * 0.63, height * 0.89),
                )
                eye = bpy.context.object
                eye.name = "Magpie Eye " + str(sign)
                eye.data.materials.append(eye_mat)
                features.append(eye)
            bpy.ops.mesh.primitive_cone_add(
                vertices=12,
                radius1=width * 0.095,
                radius2=width * 0.012,
                depth=length * 0.23,
                location=(0, length * 0.845, height * 0.78),
                rotation=(-math.pi / 2, 0, 0),
            )
            beak = bpy.context.object
            beak.name = "Magpie Beak"
            beak.data.materials.append(beak_mat)
            features.append(beak)
            for obj in features:
                bpy.context.view_layer.objects.active = obj
                bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
                obj.parent = root
                group = obj.vertex_groups.new(name="head")
                group.add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")
                mod = obj.modifiers.new("Head articulation", "ARMATURE")
                mod.object = rig
                bpy.ops.object.mode_set(mode="EDIT")
                bpy.ops.mesh.select_all(action="SELECT")
                bpy.ops.uv.smart_project()
                bpy.ops.object.mode_set(mode="OBJECT")
                for face in obj.data.polygons:
                    face.use_smooth = True
            objects = [root, *root.children_recursive]
elif request["task"] == "3d-generate":
    objects = primitives(generator, params)
else:
    input_path = Path(request["input"])
    if input_path.suffix.lower() == ".blend":
        bpy.ops.wm.open_mainfile(filepath=str(input_path), load_ui=False, use_scripts=False)
    elif input_path.suffix.lower() in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(input_path))
    else:
        raise ValueError("only trusted blend and glb/gltf inspection formats are supported")
    objects = [obj for obj in bpy.context.scene.objects if not obj.get("watoom_editor_only", False)]
    if request["task"] == "3d-repair":
        (output / "before-validation.json").write_text(json.dumps(inspection(objects), indent=2))
        for obj in objects:
            if obj.type != "MESH":
                continue
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.00001)
            bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=0.000001)
            bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
            bm.to_mesh(obj.data)
            bm.free()
            obj.data.update()

report = inspection(objects)
if (
    not report["meshes"]
    or not report["finite"]
    or report["degenerate_faces"]
    or report["duplicate_faces"]
    or report["uv_nonfinite"]
    or not report["bone_hierarchy_valid"]
):
    raise ValueError("geometry validation failed: " + json.dumps(report))
(output / "validation.json").write_text(json.dumps(report, indent=2))
# Prove evaluated vertex motion through the actual Blender rig, rather than clip names alone.
deformation = {}
for rig in [obj for obj in objects if obj.type == "ARMATURE"]:
    mesh = next(
        (
            obj
            for obj in objects
            if obj.type == "MESH" and any(mod.type == "ARMATURE" and mod.object == rig for mod in obj.modifiers)
        ),
        None,
    )
    if not mesh:
        continue
    for action in bpy.data.actions:
        use_action(rig, action)
        samples = []
        for frame in (1, 12):
            bpy.context.scene.frame_set(frame)
            evaluated = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
            data = evaluated.to_mesh()
            samples.append([v.co.copy() for v in data.vertices])
            evaluated.to_mesh_clear()
        deformation[action.name] = max((a - b).length for a, b in zip(*samples))

bpy.ops.object.select_all(action="DESELECT")
for obj in objects:
    obj.select_set(True)
if root:
    from blender_adapter.targets import get_adapter

    result = get_adapter("GODOT", asset_use="ANIMATED").export(root, bpy.context, output / "asset.glb")
    if not result.success:
        raise ValueError("native Asset Assistant export failed: " + str(result.issues))
else:
    bpy.ops.export_scene.gltf(
        filepath=str(output / "asset.glb"), export_format="GLB", use_selection=True, export_animations=True
    )
blob = (output / "asset.glb").read_bytes()
size, kind = struct.unpack_from("<II", blob, 12)
document = json.loads(blob[20 : 20 + size])
if not document.get("meshes"):
    raise ValueError("GLB mesh missing")
clips = [a.get("name") for a in document.get("animations", [])]
if generator == "asset-assistant.avian" and (not {"Idle", "Flight"}.issubset(clips) or not document.get("skins")):
    raise ValueError("Avian export lost skin or clips")

scene = bpy.context.scene
scene.frame_set(1)
points = [obj.matrix_world @ Vector(corner) for obj in objects if obj.type == "MESH" for corner in obj.bound_box]
low = Vector(tuple(min(p[i] for p in points) for i in range(3)))
high = Vector(tuple(max(p[i] for p in points) for i in range(3)))
center = (low + high) / 2
radius = max((high - low).length, 0.1)
report["bounds"] = {"min": list(low), "max": list(high), "dimensions": list(high - low)}
report["material_count"] = len(
    {slot.material.name for obj in objects if obj.type == "MESH" for slot in obj.material_slots if slot.material}
)
report["input_sha256"] = (
    hashlib.sha256(Path(request["input"]).read_bytes()).hexdigest() if request.get("input") else None
)
(output / "validation.json").write_text(json.dumps(report, indent=2))
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 8
scene.render.resolution_x = 256
scene.render.resolution_y = 256
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False
if scene.world is None:
    scene.world = bpy.data.worlds.new("WatooM Preview World")
scene.world.color = (0.18, 0.18, 0.18)
for index, offset in enumerate(((1, -1, 2), (-1, 1, 1))):
    data = bpy.data.lights.new("WatooM Light " + str(index), "AREA")
    data.energy = 35 * radius * radius
    data.shape = "DISK"
    data.size = radius
    obj = bpy.data.objects.new(data.name, data)
    scene.collection.objects.link(obj)
    obj.location = center + Vector(offset) * radius
    obj.rotation_euler = (center - obj.location).to_track_quat("-Z", "Y").to_euler()
camera_data = bpy.data.cameras.new("WatooM Camera")
camera = bpy.data.objects.new("WatooM Camera", camera_data)
scene.collection.objects.link(camera)
scene.camera = camera
camera_data.type = "ORTHO"
camera_data.ortho_scale = radius * 1.1
directions = ((0, -1, 0.1), (0, 1, 0.1), (-1, 0, 0.1), (1, 0, 0.1), (0, 0, 1), (1, -1, 0.7))
for view, direction in zip(VIEWS, directions):
    camera.location = center + Vector(direction).normalized() * radius * 2
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = str(output / (view + ".png"))
    bpy.ops.render.render(write_still=True)
if request.get("creative_operation") == "character":
    rig = next(obj for obj in objects if obj.type == "ARMATURE")
    for track in rig.animation_data.nla_tracks:
        track.mute = True
    for clip in ["Idle", "Walk", "Run"]:
        action = bpy.data.actions.get(clip)
        if action is None:
            raise ValueError("Required rendered clip missing")
        use_action(rig, action)
        for label, fraction in [("a", 0.1), ("b", 0.37)]:
            start, end = action.frame_range
            scene.frame_set(int(start + (end - start) * fraction))
            deps = bpy.context.evaluated_depsgraph_get()
            points = []
            for obj in objects:
                if obj.type != "MESH":
                    continue
                evaluated = obj.evaluated_get(deps)
                mesh = evaluated.to_mesh()
                points.extend(evaluated.matrix_world @ v.co for v in mesh.vertices)
                evaluated.to_mesh_clear()
            low = Vector(tuple(min(p[i] for p in points) for i in range(3)))
            high = Vector(tuple(max(p[i] for p in points) for i in range(3)))
            pivot = (low + high) / 2
            distance = max((high - low).length, 0.1)
            camera.location = pivot + Vector((1, -1, 0.7)).normalized() * distance * 2
            camera.rotation_euler = (pivot - camera.location).to_track_quat("-Z", "Y").to_euler()
            camera_data.ortho_scale = distance * 0.55
            scene.render.filepath = str(output / (clip + "-" + label + ".png"))
            bpy.ops.render.render(write_still=True)
    for track in rig.animation_data.nla_tracks:
        track.mute = False
# Uncompressed: inputs saved with compression would otherwise carry it into the published artifact.
bpy.ops.wm.save_as_mainfile(filepath=str(output / "asset.blend"), check_existing=False, compress=False)
# Reimport the real exported file in a fresh scene; retain the editable source .blend above.
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.gltf(filepath=str(output / "asset.glb"))
imported = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
if not imported or not sum(len(o.data.polygons) for o in imported):
    raise ValueError("GLB reimport failed")
files = sorted(p for p in output.iterdir() if p.is_file())
manifest = {
    "schema": 1,
    "status": "PASS",
    "job_id": request["job_id"],
    "generator_id": generator,
    "generator_version": "0.9.0" if generator.startswith("asset-assistant.") else "1.0.0",
    "source_revision": REVISION if generator.startswith("asset-assistant.") else "watoom-procedural/1.0.0",
    "blender": bpy.app.version_string,
    "parameters": params,
    "seed": request.get("seed", 0),
    "input_manifest": {k: v for k, v in request.items() if k not in ("output", "input")},
    "export_format": "glb",
    "export_reimport": True,
    "geometry_validation": report,
    "materials": [mat.name for mat in bpy.data.materials],
    "animations": clips,
    "deformation": deformation,
    "skin_count": len(document.get("skins", [])),
    "views": {
        "names": VIEWS,
        "resolution": [256, 256],
        "engine": "CYCLES",
        "device": "CPU",
        "samples": 8,
        "camera_type": "ORTHO",
        "center": list(center),
        "radius": radius,
    },
    "warnings": report["warnings"]
    + (
        ["Native quadruped is a canine-derived stylized wombat approximation; no wombat anatomy certification."]
        if request.get("style") == "wombat"
        else []
    ),
    "outputs": [
        {"path": p.name, "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in files
    ],
}
(output / "manifest.json").write_text(json.dumps(manifest, indent=2))
print(
    "WATOOM_3D_RESULT="
    + json.dumps(
        {
            "status": "PASS",
            "generator": generator,
            "files": len(files),
            "vertices": report["vertices"],
            "animations": clips,
            "export_reimport": True,
        }
    )
)
