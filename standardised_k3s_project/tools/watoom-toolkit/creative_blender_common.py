import bpy, bmesh, pathlib, json, struct, urllib.parse
from mathutils import Vector


def material(name, color):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value = (*color, 1)
    return m


def load(path):
    p = pathlib.Path(path)
    if p.suffix.lower() in (".glb", ".gltf"):
        if p.suffix.lower() == ".glb":
            with p.open("rb") as handle:
                head = handle.read(20)
                size, kind = struct.unpack_from("<II", head, 12)
                if kind != 0x4E4F534A or size > 16 * 1024**2:
                    raise ValueError("Invalid/bounded GLB metadata")
                document = json.loads(handle.read(size))
        else:
            document = json.loads(p.read_text())
        for item in document.get("buffers", []) + document.get("images", []):
            uri = item.get("uri", "")
            if not uri or uri.startswith("data:"):
                continue
            parsed = urllib.parse.urlsplit(uri)
            if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
                raise ValueError("External network dependency is not supported")
            dependency = (p.parent / urllib.parse.unquote(parsed.path)).resolve()
            if not dependency.is_relative_to(pathlib.Path("/assets")) or not dependency.is_file():
                raise ValueError("Missing or unapproved source dependency: " + uri)
    if p.suffix.lower() == ".blend":
        bpy.ops.wm.open_mainfile(filepath=str(p), load_ui=False, use_scripts=False)
    elif p.suffix.lower() in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(p))
    elif p.suffix.lower() == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(p), use_anim=True)
    elif p.suffix.lower() == ".obj":
        bpy.ops.wm.obj_import(filepath=str(p))
    else:
        raise ValueError("Unverified creative import format")
    for library in bpy.data.libraries:
        dependency = pathlib.Path(bpy.path.abspath(library.filepath)).resolve()
        if not dependency.is_relative_to(pathlib.Path("/assets")) or not dependency.is_file():
            raise ValueError("Missing or unapproved linked library")
    for image in bpy.data.images:
        if image.source != "FILE" or image.packed_file:
            continue
        dependency = pathlib.Path(bpy.path.abspath(image.filepath)).resolve()
        if not dependency.is_relative_to(pathlib.Path("/assets")) or not dependency.is_file():
            raise ValueError("Missing or unapproved texture dependency: " + image.name)
    return list(bpy.context.scene.objects)


def cube(name, location, scale, mat=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    if mat:
        o.data.materials.append(mat)
    return o


def fix(mesh):
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.00001)
    bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=0.000001)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()


def uv(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project()
    bpy.ops.object.mode_set(mode="OBJECT")
