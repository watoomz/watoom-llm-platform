import bpy, bmesh, math, json, sys, random, shutil
from pathlib import Path
from mathutils import Vector
import numpy as np

ROOT = Path(sys.argv[sys.argv.index("--") + 1])
ROOT.mkdir(parents=True, exist_ok=True)
for folder in ["source", "textures", "renders", "game-ready", "reports"]:
    (ROOT / folder).mkdir(exist_ok=True)
shutil.copyfile(__file__, ROOT / "source" / "build_script.py")
STATE = ROOT / "reports"
STATE.mkdir(exist_ok=True)
random.seed(71)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 8
scene.cycles.use_denoising = True
scene.render.threads_mode = "FIXED"
scene.render.threads = 4
scene.render.resolution_x = 384
scene.render.resolution_y = 384
scene.render.resolution_percentage = 100
scene.world.color = (0.16, 0.16, 0.16)
scene.view_settings.view_transform = "AgX"
collections = {}
for name in [
    "01_Anatomy",
    "02_Face",
    "03_Wing_L",
    "04_Wing_R",
    "05_Tail",
    "06_Legs_Feet",
    "07_Contour_Plumage",
    "90_Studio",
]:
    c = bpy.data.collections.new(name)
    scene.collection.children.link(c)
    collections[name] = c


def move(o, c):
    for old in list(o.users_collection):
        old.objects.unlink(o)
    collections[c].objects.link(o)


def material(name, color, rough=0.5, metal=0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes.get("Principled BSDF")
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    return m


black = material("Plumage | charcoal satin", (0.018, 0.024, 0.03), 0.48)
white = material("Plumage | ivory", (0.78, 0.79, 0.75), 0.62)
silver = material("Bill | cool bone-grey", (0.41, 0.49, 0.53), 0.36)
tip = material("Bill tip | charcoal", (0.025, 0.029, 0.032), 0.38)
skin = material("Tarsus | graphite scales", (0.012, 0.016, 0.017), 0.68)
claw = material("Claws | horn", (0.019, 0.022, 0.024), 0.42)
iris = material("Iris | deep chestnut", (0.13, 0.037, 0.012), 0.27)
pupil = material("Pupil | obsidian", (0.002, 0.003, 0.004), 0.12)


def finish(o, name, mat, c):
    o.name = name
    move(o, c)
    o.data.materials.append(mat)
    if o.type == "MESH":
        for p in o.data.polygons:
            p.use_smooth = True
    return o


def ellipsoid(name, loc, scale, mat, c="01_Anatomy", segments=24, rings=16):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=loc)
    o = bpy.context.object
    o.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish(o, name, mat, c)


def mesh(name, verts, faces, mat, c, uv=None):
    d = bpy.data.meshes.new(name)
    d.from_pydata(verts, [], faces)
    d.update()
    o = bpy.data.objects.new(name, d)
    collections[c].objects.link(o)
    d.materials.append(mat)
    for p in d.polygons:
        p.use_smooth = True
    bm = bmesh.new()
    bm.from_mesh(d)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(d)
    bm.free()
    if uv:
        layer = d.uv_layers.new(name="FeatherUV")
        for p in d.polygons:
            for li in p.loop_indices:
                layer.data[li].uv = uv[d.loops[li].vertex_index]
    return o


def tube(name, points, radii, mat, c="06_Legs_Feet", sides=10):
    ps = [Vector(p) for p in points]
    v = []
    f = []
    for i, p in enumerate(ps):
        tangent = (ps[min(i + 1, len(ps) - 1)] - ps[max(0, i - 1)]).normalized()
        u = tangent.cross(Vector((1, 0, 0)))
        if u.length < 0.1:
            u = tangent.cross(Vector((0, 1, 0)))
        u.normalize()
        w = tangent.cross(u).normalized()
        for j in range(sides):
            v.append(p + radii[i] * (math.cos(j * 2 * math.pi / sides) * u + math.sin(j * 2 * math.pi / sides) * w))
    for i in range(len(ps) - 1):
        for j in range(sides):
            a = i * sides + j
            b = i * sides + (j + 1) % sides
            f.append((a, b, b + sides, a + sides))
    f.append(tuple(range(sides - 1, -1, -1)))
    f.append(tuple((len(ps) - 1) * sides + j for j in range(sides)))
    return mesh(name, v, f, mat, c)


def aim(o, at):
    o.rotation_euler = (Vector(at) - o.location).to_track_quat("-Z", "Y").to_euler()


def checkpoint(wp):
    p = ROOT / "source" / f"{wp}.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(p))
    with (STATE / "progress.md").open("a") as out:
        out.write(f"\n{wp} saved: {p}\n")
    (STATE / "handoff.md").write_text(
        f"# Handoff\nLast saved {wp}: {p}\nBuild script /data/ai/helper-scripts/build_magpie_character.py. Check live task process and reports before resuming. CPU only. Game and inference unchanged.\n"
    )
    return p


# Continuous torso and neck with a unioned head. Z up, forward -Y, real metres.
body = ellipsoid("Torso", (0, 0.015, 0.191), (0.047, 0.085, 0.072), black)
body.rotation_euler.x = math.radians(-24)
neck = ellipsoid("Neck", (0, -0.035, 0.260), (0.034, 0.041, 0.046), black)
head = ellipsoid("Head", (0, -0.073, 0.305), (0.032, 0.042, 0.029), black)
chest = ellipsoid("Chest transition", (0, -0.029, 0.232), (0.040, 0.052, 0.056), black)
bpy.ops.object.select_all(action="DESELECT")
for o in [body, neck, head, chest]:
    o.select_set(True)
bpy.context.view_layer.objects.active = body
bpy.ops.object.join()
body.name = "Torso_Neck_Head | continuous skin"
mod = body.modifiers.new("Anatomical union", "REMESH")
mod.mode = "VOXEL"
mod.voxel_size = 0.002
bpy.ops.object.modifier_apply(modifier=mod.name)
mod = body.modifiers.new("Smooth anatomical transitions", "SMOOTH")
mod.factor = 0.8
mod.iterations = 16
bpy.ops.object.modifier_apply(modifier=mod.name)
mod = body.modifiers.new("Final surface", "SUBSURF")
mod.levels = 1
bpy.ops.object.modifier_apply(modifier=mod.name)
body.data.materials.clear()
body.data.materials.append(black)
body.data.materials.append(white)
for p in body.data.polygons:
    co = body.matrix_world @ p.center
    # White nape behind crown, and white rump, retaining the black saddle.
    if (co.z > 0.263 and co.y > -0.044 + max(0, co.z - 0.302) * 0.9) or (co.y > 0.068 and 0.178 < co.z < 0.237):
        p.material_index = 1
    p.use_smooth = True
bpy.context.view_layer.objects.active = body
body.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.sphere_project()
bpy.ops.object.mode_set(mode="OBJECT")


def bill(name, upper):
    v = []
    f = []
    uv = []
    N = 20
    S = 16
    for i in range(N + 1):
        t = i / N
        y = -0.104 - 0.065 * t
        width = 0.013 * (1 - t) ** 0.75 + 0.00015
        height = (0.016 if upper else 0.006) * (1 - t) ** 0.8 + 0.00015
        z = 0.300 - 0.009 * t + 0.002 * math.sin(t * math.pi)
        if not upper:
            z -= 0.001
        for j in range(S):
            a = j / S * 2 * math.pi
            sn = math.sin(a)
            dz = (max(sn, 0) * height + min(sn, 0) * 0.0004) if upper else (min(sn, 0) * height + max(sn, 0) * 0.0003)
            v.append((width * math.cos(a), y, z + dz))
            uv.append((j / S, t))
    for i in range(N):
        for j in range(S):
            a = i * S + j
            b = i * S + (j + 1) % S
            f.append((a, b, b + S, a + S))
    f.extend([tuple(range(S - 1, -1, -1)), tuple(N * S + j for j in range(S))])
    o = mesh(name, v, f, silver, "02_Face", uv)
    o.data.materials.append(tip)
    for p in o.data.polygons:
        if p.center.y < -0.151:
            p.material_index = 1
    return o


bill("Beak_Upper", True)
bill("Beak_Lower", False)
for s, side in [(-1, "L"), (1, "R")]:
    tube(
        "Leg_" + side,
        [(s * 0.023, 0.031, 0.145), (s * 0.024, 0.034, 0.099), (s * 0.024, 0.010, 0.031), (s * 0.024, 0.007, 0.019)],
        [0.005, 0.0042, 0.0033, 0.0041],
        skin,
    )
    for k, spread in enumerate([-0.018, 0, 0.018]):
        x = s * 0.024
        end = (x + spread, -0.040 - (0.009 if k == 1 else 0), 0.007)
        tube(
            f"Toe_{side}_{k+1}",
            [(x, 0.007, 0.018), (x + spread * 0.48, -0.016, 0.010), end],
            [0.0032, 0.0026, 0.0015],
            skin,
        )
    tube(
        "Hallux_" + side,
        [(s * 0.024, 0.011, 0.018), (s * 0.024 - s * 0.008, 0.038, 0.010), (s * 0.024 - s * 0.012, 0.049, 0.007)],
        [0.0026, 0.002, 0.0014],
        skin,
    )

floor = material("Studio | warm slate", (0.095, 0.12, 0.13), 0.83)
bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, 0))
finish(bpy.context.object, "Ground", floor, "90_Studio")
world = scene.world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.16, 0.19, 0.23, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.5
for name, loc, power, size, color in [
    ("Key", (0.35, -0.4, 0.7), 35, 0.4, (1, 0.89, 0.76)),
    ("Fill", (-0.4, -0.2, 0.4), 18, 0.4, (0.72, 0.84, 1)),
    ("Rim", (0.15, 0.4, 0.55), 45, 0.3, (0.87, 0.94, 1)),
]:
    d = bpy.data.lights.new(name, "AREA")
    d.energy = power
    d.shape = "DISK"
    d.size = size
    d.color = color
    o = bpy.data.objects.new(name, d)
    collections["90_Studio"].objects.link(o)
    o.location = loc
    aim(o, (0, 0, 0.19))
d = bpy.data.cameras.new("AssetCamera")
camera = bpy.data.objects.new("AssetCamera", d)
collections["90_Studio"].objects.link(camera)
scene.camera = camera
camera.location = (0.6, -0.8, 0.43)
aim(camera, (0, 0.045, 0.185))
d.type = "ORTHO"
d.ortho_scale = 0.49
checkpoint("WP1_base_anatomy")
scene.render.resolution_x = 512
scene.render.resolution_y = 512
scene.cycles.samples = 16
scene.render.filepath = str(ROOT / "renders" / "WP1_silhouette.png")
bpy.ops.render.render(write_still=True)


# Closed feather blades. Their UVs encode vane direction; thin lens cross-section.
def feather(name, start, end, width, mat, c, normal=(1, 0, 0), white_base=False):
    start = Vector(start)
    end = Vector(end)
    axis = (end - start).normalized()
    norm = Vector(normal).normalized()
    across = axis.cross(norm).normalized()
    norm = across.cross(axis).normalized()
    small = (end - start).length < 0.024
    verts = []
    faces = []
    uv = []
    N = 12 if small else 22
    S = 8 if small else 12
    for i in range(N + 1):
        t = i / N
        ctr = start.lerp(end, t) + norm * ((0.00045 if small else 0.0025) * math.sin(math.pi * t))
        profile = (math.sin(math.pi * (0.045 + 0.935 * t)) ** 0.65) * (0.85 + 0.15 * t)
        if i in [0, N]:
            profile = 0.045
        for j in range(S):
            a = j / S * math.tau
            u = math.cos(a)
            w = width * profile * (0.86 if u < 0 else 1)
            verts.append(
                ctr
                + across * u * w
                + norm * math.sin(a) * ((0.00010 + 0.0001 * profile) if small else (0.00042 + 0.0006 * profile))
            )
            uv.append(((u + 1) / 2, t))
    for i in range(N):
        for j in range(S):
            a = i * S + j
            b = i * S + (j + 1) % S
            faces.append((a, b, b + S, a + S))
    faces += [tuple(range(S - 1, -1, -1)), tuple(N * S + j for j in range(S))]
    o = mesh(name, verts, faces, mat, c, uv)
    if white_base:
        o.data.materials.append(white)
        for p in o.data.polygons:
            if sum(uv[k][1] for k in p.vertices) / len(p.vertices) < 0.72:
                p.material_index = 1
    return o


for s, side in [(-1, "L"), (1, "R")]:
    c = "03_Wing_L" if s == -1 else "04_Wing_R"
    o = ellipsoid("Wing_" + side + " | folded foundation", (s * 0.039, 0.033, 0.216), (0.008, 0.058, 0.045), black, c)
    o.rotation_euler.x = math.radians(-28)
    for i in range(9):
        feather(
            f"{side}_Primary_{i+1:02}",
            (s * (0.042 + 0.0005 * i), -0.002 + i * 0.005, 0.226 - i * 0.004),
            (s * (0.055 + 0.0003 * i), 0.130 + i * 0.0015, 0.132 + i * 0.004),
            0.007,
            black,
            c,
            (s, 0, 0),
        )
    for i in range(8):
        feather(
            f"{side}_Secondary_{i+1:02}",
            (s * 0.035, -0.005 + i * 0.008, 0.249 - i * 0.003),
            (s * 0.057, 0.063 + i * 0.007, 0.179 + i * 0.001),
            0.008,
            black,
            c,
            (s, 0, 0),
        )
    for i in range(8):
        feather(
            f"{side}_Median_{i+1:02}",
            (s * 0.042, -0.022 + i * 0.006, 0.222 - i * 0.002),
            (s * 0.060, 0.025 + i * 0.006, 0.173 + i * 0.001),
            0.006,
            black,
            c,
            (s, 0, 0),
        )
    for row in range(3):
        for i in range(9 - row):
            start = (s * (0.028 + row * 0.004), -0.018 + i * 0.009, 0.266 - row * 0.014 - i * 0.002)
            end = (s * (0.050 + row * 0.002), start[1] + 0.035, start[2] - 0.025)
            feather(f"{side}_Covert_{row}_{i:02}", start, end, 0.0055, white if row < 2 else black, c, (s, 0, 0))
    for i in range(5):
        feather(
            f"{side}_Scapular_{i:02}",
            (s * (0.022 + i * 0.005), 0.006, 0.275),
            (s * (0.033 + i * 0.005), 0.061, 0.244 - i * 0.002),
            0.005,
            black,
            c,
            (s, 0, 0.8),
        )
    for o in collections[c].objects:
        o.location.z -= 0.009
for i in range(12):
    x = (i - 5.5) * 0.0042
    feather(
        f"Tail_Rectrix_{i+1:02}",
        (x * 0.62, 0.076, 0.191),
        (x * 1.2, 0.246 - 0.017 * abs(i - 5.5) / 5.5, 0.105),
        0.0057,
        black,
        "05_Tail",
        (0, 0, 1),
        False,
    )
for s, side in [(-1, "L"), (1, "R")]:
    ellipsoid("Thigh_" + side, (s * 0.023, 0.026, 0.132), (0.014, 0.021, 0.023), black)
    # Iris sits in a small dark orbital rim, natural size rather than cartoon eyes.
    ellipsoid("Orbital_rim_" + side, (s * 0.0283, -0.080, 0.312), (0.0048, 0.0058, 0.0056), black, "02_Face")
    ellipsoid("Eye_" + side, (s * 0.0314, -0.081, 0.312), (0.0025, 0.0041, 0.0041), iris, "02_Face")
    ellipsoid("Pupil_" + side, (s * 0.0334, -0.0818, 0.312), (0.0009, 0.0023, 0.0025), pupil, "02_Face")
    ellipsoid("Nostril_" + side, (s * 0.0095, -0.117, 0.306), (0.0008, 0.0022, 0.001), tip, "02_Face", 24, 12)
    for k, spread in enumerate([-0.018, 0, 0.018]):
        end = Vector((s * 0.024 + spread, -0.040 - (0.009 if k == 1 else 0), 0.007))
        tube(
            f"Claw_{side}_{k+1}",
            [end, end + Vector((0, -0.004, 0.002)), end + Vector((0, -0.010, -0.003))],
            [0.0017, 0.0013, 0.00015],
            claw,
        )
    end = Vector((s * 0.024 - s * 0.012, 0.049, 0.007))
    tube(
        "Hallux_claw_" + side,
        [end, end + Vector((-s * 0.002, 0.005, 0.001)), end + Vector((-s * 0.003, 0.010, -0.003))],
        [0.0014, 0.001, 0.00015],
        claw,
    )
    # Overlapping tarsal plates retain silhouette and catch soft light.
    for i in range(11):
        t = i / 11
        z = 0.037 + t * 0.057
        y = 0.010 + t * 0.022
        ellipsoid(
            f"Scale_{side}_{i:02}", (s * 0.024, y - 0.0032, z), (0.0035, 0.001, 0.0019), skin, "06_Legs_Feet", 16, 8
        )
# Small overlapping contour feather tips break the smooth toy-like breast and nape.
polys = list(body.data.polygons)
centers = np.array([tuple(body.matrix_world @ p.center) for p in polys], dtype=np.float32)
normals = np.array([tuple((body.matrix_world.to_3x3() @ p.normal).normalized()) for p in polys], dtype=np.float32)
seen = set()
candidates = []
for i, (co, n) in enumerate(zip(centers, normals)):
    exposed = (
        (n[1] < -0.4 and 0.145 < co[2] < 0.272)
        or (co[1] > -0.035 and co[2] > 0.266)
        or (co[1] > 0.068 and co[2] > 0.178)
    )
    if not exposed:
        continue
    key = tuple(np.floor(co / 0.008).astype(int))
    if key in seen:
        continue
    seen.add(key)
    candidates.append(i)
candidates = []  # Surface-tip experiment rejected in run 05; keep the continuous contour texture.
for count, i in enumerate(candidates):
    co = Vector(centers[i])
    n = Vector(normals[i])
    direction = Vector((0, 0.004, -0.012))
    direction -= n * direction.dot(n)
    if direction.length < 0.004:
        continue
    direction.normalize()
    target = co + direction * 0.012
    j = int(np.argmin(np.sum((centers - np.array(target)) ** 2, axis=1)))
    end = Vector(centers[j]) + Vector(normals[j]) * 0.0005
    start = co + n * 0.0005
    if (end - start).length < 0.006:
        continue
    mat = white if polys[i].material_index == 1 else black
    feather("Contour_" + str(count), start, end, 0.0034, mat, "07_Contour_Plumage", n)
checkpoint("WP2_geometry_detail")

# Portable image-backed PBR maps, created from scratch. No procedural-only GLB shaders.
N = 256
u, v = np.meshgrid(np.linspace(0, 1, N, dtype=np.float32), np.linspace(0, 1, N, dtype=np.float32))
rng = np.random.default_rng(71)
phase = (v * 160 + np.abs(u - 0.5) * 80) * math.tau
barbs = np.sin(phase) * 0.5 + 0.5
shaft = np.exp(-(((u - 0.5) / 0.018) ** 2))
noise = rng.random((N, N), dtype=np.float32)
variation = 0.78 + 0.12 * barbs + 0.10 * noise + 0.09 * shaft


def image_file(name, rgb, noncolor=False):
    im = bpy.data.images.new(name, width=N, height=N, alpha=True)
    if noncolor:
        im.colorspace_settings.name = "Non-Color"
    rgba = np.ones((N, N, 4), dtype=np.float32)
    rgba[:, :, :3] = rgb
    im.pixels.foreach_set(rgba.ravel())
    im.filepath_raw = str(ROOT / "textures" / (name + ".png"))
    im.file_format = "PNG"
    im.save()
    im.pack()
    return im


dark_img = image_file(
    "feather_charcoal_basecolor",
    variation[:, :, None] * np.array([0.065, 0.080, 0.095], dtype=np.float32)[None, None, :],
)
white_img = image_file(
    "feather_ivory_basecolor", variation[:, :, None] * np.array([0.88, 0.87, 0.82], dtype=np.float32)[None, None, :]
)
h = 0.018 * np.sin(phase) + 0.02 * shaft
dy, dx = np.gradient(h)
norm = np.stack([-dx * 28, -dy * 28, np.ones_like(h)], axis=-1)
norm /= np.linalg.norm(norm, axis=-1, keepdims=True)
normal_img = image_file("feather_vane_normal", norm * 0.5 + 0.5, True)
rough_img = image_file("feather_roughness", np.repeat((0.5 + 0.12 * noise + 0.06 * barbs)[:, :, None], 3, axis=2), True)
for mat, im in [(black, dark_img), (white, white_img)]:
    nt = mat.node_tree
    p = nt.nodes.get("Principled BSDF")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = im
    nt.links.new(tex.outputs["Color"], p.inputs["Base Color"])
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = rough_img
    nt.links.new(tex.outputs["Color"], p.inputs["Roughness"])
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = normal_img
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = 0.12
    nt.links.new(tex.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], p.inputs["Normal"])
    p.inputs["Specular IOR Level"].default_value = 0.22
# Body contour plumage has many small feather tips, distinct from long flight-feather vanes.
row = np.floor(v * 32)
col = u * 22 + ((row % 2) * 0.5)
fx = col % 1 - 0.5
fy = (v * 32) % 1
curve = 0.63 - 0.50 * (np.abs(fx) * 2) ** 1.7
edge = np.exp(-(((fy - curve) / 0.028) ** 2))
body_var = 0.85 + 0.035 * noise - 0.065 * edge
body_img = image_file(
    "body_charcoal_basecolor", body_var[:, :, None] * np.array([0.047, 0.057, 0.067], dtype=np.float32)[None, None, :]
)
body_h = 0.004 * edge
dy, dx = np.gradient(body_h)
bn = np.stack([-dx * 10, -dy * 10, np.ones_like(body_h)], axis=-1)
bn /= np.linalg.norm(bn, axis=-1, keepdims=True)
body_normal = image_file("body_contour_normal", bn * 0.5 + 0.5, True)
bodymat = black.copy()
bodymat.name = "Body | soft contour plumage"
for node in bodymat.node_tree.nodes:
    if node.type == "TEX_IMAGE" and node.image == dark_img:
        node.image = body_img
    elif node.type == "TEX_IMAGE" and node.image == normal_img:
        node.image = body_normal
    elif node.type == "NORMAL_MAP":
        node.inputs["Strength"].default_value = 0.3
body.data.materials[0] = bodymat
napemat = white.copy()
napemat.name = "Nape | soft ivory contour"
for node in napemat.node_tree.nodes:
    if node.type == "TEX_IMAGE" and node.image == normal_img:
        node.image = body_normal
body.data.materials[1] = napemat
# Join by functional feather group for browser draw-call efficiency; individual blades remain disconnected editable islands.
for c in ["03_Wing_L", "04_Wing_R", "05_Tail", "06_Legs_Feet", "07_Contour_Plumage"]:
    keys = (
        ["Primary", "Secondary", "Median", "Covert", "Scapular"]
        if "Wing" in c
        else (["Rectrix"] if "Tail" in c else (["Contour"] if "Contour" in c else ["Scale"]))
    )
    for key in keys:
        group = [o for o in list(collections[c].objects) if key in o.name and o.type == "MESH"]
        if len(group) > 1:
            bpy.ops.object.select_all(action="DESELECT")
            for o in group:
                o.select_set(True)
            bpy.context.view_layer.objects.active = group[0]
            bpy.ops.object.join()
            group[0].name = c + "_" + key + "_group"
checkpoint("WP3_materials")

asset = [o for o in scene.objects if o.type == "MESH" and collections["90_Studio"] not in o.users_collection]
# Put origin of every runtime component on the ground-centred character origin and apply transforms.
bpy.ops.object.select_all(action="DESELECT")
for o in asset:
    o.select_set(True)
bpy.context.view_layer.objects.active = body
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
scene.cursor.location = (0, 0, 0)
bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
for o in asset:
    o["rigging_note"] = (
        "Neutral folded pose; unrigged. Bind continuous skin and feather groups separately; split islands for feather controls if needed."
    )


def stats(objs):
    r = {
        "objects": len(objs),
        "vertices": 0,
        "triangles": 0,
        "nonmanifold_edges": 0,
        "zero_area_faces": 0,
        "nonfinite_coordinates": 0,
        "missing_uv_objects": [],
        "negative_volume_objects": [],
    }
    for o in objs:
        d = o.data
        d.calc_loop_triangles()
        r["vertices"] += len(d.vertices)
        r["triangles"] += len(d.loop_triangles)
        r["nonfinite_coordinates"] += sum(not all(math.isfinite(x) for x in v.co) for v in d.vertices)
        bm = bmesh.new()
        bm.from_mesh(d)
        r["nonmanifold_edges"] += sum(not e.is_manifold for e in bm.edges)
        r["zero_area_faces"] += sum(f.calc_area() < 1e-12 for f in bm.faces)
        if bm.calc_volume(signed=True) < 0:
            r["negative_volume_objects"].append(o.name)
        bm.free()
        if not d.uv_layers:
            r["missing_uv_objects"].append(o.name)
    coords = [o.matrix_world @ v.co for o in objs for v in o.data.vertices]
    r["bounds"] = [[min(p[i] for p in coords), max(p[i] for p in coords)] for i in range(3)]
    return r


# All remaining meshes get UVs for future painting; constant materials don't need textures.
for o in asset:
    if not o.data.uv_layers:
        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project()
        bpy.ops.object.mode_set(mode="OBJECT")
# WatooM repair: reduce body mesh budget and give closed end-caps real UV area.
bpy.ops.object.select_all(action="DESELECT")
bpy.context.view_layer.objects.active = body
body.select_set(True)
mod = body.modifiers.new("Runtime budget", "DECIMATE")
mod.ratio = 0.55
bpy.ops.object.modifier_apply(modifier=mod.name)
for ob in asset:
    me = ob.data
    uv = me.uv_layers.active
    if uv is None:
        continue
    for poly in me.polygons:
        loops = list(poly.loop_indices)
        points = [uv.data[i].uv for i in loops]
        area = abs(
            sum(
                points[i].x * points[(i + 1) % len(points)].y - points[(i + 1) % len(points)].x * points[i].y
                for i in range(len(points))
            )
        )
        if area < 1e-12:
            axis = max(range(3), key=lambda i: abs(poly.normal[i]))
            axes = [i for i in range(3) if i != axis]
            for li in loops:
                co = me.vertices[me.loops[li].vertex_index].co
                uv.data[li].uv = (0.5 + co[axes[0]], 0.5 + co[axes[1]])

# WatooM final repair: union intersecting wing layers; transfer plumage materials.
from mathutils.kdtree import KDTree

for coll in ["03_Wing_L", "04_Wing_R"]:
    group = [o for o in collections[coll].objects if o.type == "MESH"]
    points = []
    mats = []
    for ob in group:
        for poly in ob.data.polygons:
            points.append((ob.matrix_world @ poly.center, ob.data.materials[poly.material_index]))
    kd = KDTree(len(points))
    for i, (co, ma) in enumerate(points):
        kd.insert(co, i)
    kd.balance()
    bpy.ops.object.select_all(action="DESELECT")
    for ob in group:
        ob.select_set(True)
    ob = group[0]
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.join()
    ob.name = coll + "_unified_feathers"
    mod = ob.modifiers.new("Feather layer union", "REMESH")
    mod.mode = "VOXEL"
    mod.voxel_size = 0.00055
    bpy.ops.object.modifier_apply(modifier=mod.name)
    mod = ob.modifiers.new("Wing budget", "DECIMATE")
    mod.ratio = 0.12
    bpy.ops.object.modifier_apply(modifier=mod.name)
    ob.data.materials.clear()
    for ma in [black, white]:
        ob.data.materials.append(ma)
    for poly in ob.data.polygons:
        _, i, _ = kd.find(ob.matrix_world @ poly.center)
        poly.material_index = 1 if points[i][1] == white else 0
        poly.use_smooth = True
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project()
    bpy.ops.object.mode_set(mode="OBJECT")
asset = [o for o in scene.objects if o.type == "MESH" and collections["90_Studio"] not in o.users_collection]
bpy.ops.object.select_all(action="DESELECT")
for ob in asset:
    ob.select_set(True)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
source_stats = stats(asset)
bpy.ops.object.select_all(action="DESELECT")
for o in asset:
    o.select_set(True)
glb = ROOT / "game-ready" / "australian_magpie.glb"
bpy.ops.export_scene.gltf(
    filepath=str(glb), export_format="GLB", use_selection=True, export_yup=True, export_apply=True
)
final = checkpoint("WP4_export")
(ROOT / "reports" / "source-stats.json").write_text(json.dumps(source_stats, indent=2))
# Reimport in a distinct scene; do not replace the authoring scene.
original_scene = scene
bpy.ops.scene.new(type="NEW")
test_scene = bpy.context.scene
bpy.ops.import_scene.gltf(filepath=str(glb))
imported = [o for o in test_scene.objects if o.type == "MESH"]
reimport_stats = stats(imported)
report = {
    "source": source_stats,
    "reimport": reimport_stats,
    "glb_bytes": glb.stat().st_size,
    "blender": bpy.app.version_string,
    "glb_reimport": "PASS" if imported and not reimport_stats["nonfinite_coordinates"] else "FAIL",
    "rigged": False,
    "animated": False,
    "orientation": "Source Z up, forward -Y; glTF Y up, forward +Z",
    "texture_files": [p.name for p in (ROOT / "textures").glob("*.png")],
    "missing_image_files": [
        im.filepath
        for im in bpy.data.images
        if im.source == "FILE" and not im.packed_file and not Path(bpy.path.abspath(im.filepath)).exists()
    ],
}
(ROOT / "reports" / "validation.json").write_text(json.dumps(report, indent=2))
bpy.context.window.scene = original_scene
bpy.data.scenes.remove(test_scene)
bpy.ops.outliner.orphans_purge(do_recursive=True)
scene = original_scene
checkpoint("WP4_validated")
scene.render.resolution_x = 384
scene.render.resolution_y = 384
scene.cycles.samples = 8
views = {
    "front": (0, -1, 0.21),
    "side": (1, 0.045, 0.21),
    "rear": (0, 1, 0.21),
    "top": (0, 0.045, 1),
    "three_quarter": (0.7, -1, 0.46),
}
for name, loc in views.items():
    camera.location = loc
    aim(camera, (0, 0.045, 0.18))
    camera.data.ortho_scale = 0.48
    scene.render.filepath = str(ROOT / "renders" / (name + ".png"))
    bpy.ops.render.render(write_still=True)
camera.location = (0.65, -1, 0.46)
aim(camera, (0, 0.045, 0.185))
camera.data.ortho_scale = 0.46
scene.render.resolution_x = 512
scene.render.resolution_y = 512
scene.cycles.samples = 16
scene.render.filepath = str(ROOT / "renders" / "beauty.png")
bpy.ops.render.render(write_still=True)
checkpoint("WP5_rendered")
(ROOT / "reports" / "COMPLETE").write_text("Rendering complete; visual acceptance pending human/model image review.\n")
print("ASSET_BUILD_COMPLETE", ROOT, flush=True)
