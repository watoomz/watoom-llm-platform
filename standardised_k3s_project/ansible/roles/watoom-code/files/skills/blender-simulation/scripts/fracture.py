"""Pre-fracture one mesh into Voronoi pieces for a game engine (no Cell Fracture add-on needed).

  blender -b -P fracture.py -- --source wall.fbx --pieces 24 --out wall_fractured.glb [--seed 1] [--object NAME]
  blender -b -P fracture.py -- --box 4 0.4 3 --pieces 24 --out box_wall.glb          (a test wall, no source file)
  MCP: import fracture; print(fracture.run(object="Wall", pieces=24, out="//wall_fractured.glb"))

Each piece is the source mesh cut by the bisecting planes between its Voronoi seed and every other seed (bmesh
bisect_plane, keep the seed's side), the cut closed with holes_fill and given the material "Inner" (add your own
texture to it in the engine). Seeds are spread over the mesh's bounding box, a little denser near --focus (a hit
point in object space) when given. The .glb holds "Intact" (the source, unchanged) and "Piece_000".. with each
piece's origin at its own centre, positioned where it sits in the intact mesh, so swapping Intact for the pieces
at runtime shows no jump. Godot: watoom-godot-game gg_destruction.py + addons/gg/game/destructible.gd.

--basecolor IMG [--normal IMG] [--uv-scale 2]: for sources whose engine material is triplanar (no usable UVs, e.g.
the modular-castle walls) every face, cut faces included, gets a box-projected UV (the axis its normal points along,
--uv-scale metres per tile, in the INTACT object's space so the pattern is continuous across pieces and stays on each
piece as it falls) and the materials get the image (Outer as is, Inner 0.6 darker); the glb embeds it. --tint R G B
multiplies it: the castle Stone_basecolor.tga is a near-white greyscale map that its Unreal material tints.

Checks in the JSON line: pieces, volume of the intact mesh and the sum of the pieces (a closed source keeps the
sum within a few %; `volume_ratio` far from 1 means the source is not closed and the cuts could not be capped).
Why (T-0066, 2026-11-19): Godot 4 has no Chaos-style runtime fracture; the pieces are made offline. Blender 5.2's
Cell Fracture is an extension that may be missing on a headless host, so this uses plain bmesh.
"""
import os
import random
import sys

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _bpyx as bx  # noqa: E402

MIN_PIECE_VOLUME = 1e-6


def _import(path):
    before = set(bpy.data.objects)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    else:
        raise ValueError("source %s: use .fbx, .glb/.gltf or .obj" % path)
    meshes = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    if not meshes:
        raise ValueError("source %s has no mesh" % path)
    return meshes


def _join(meshes):
    """One mesh object with transforms applied (several imported parts become one solid)."""
    bx.object_mode()
    bx.select_only(meshes, meshes[0])
    if len(meshes) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    for o in list(bpy.data.objects):
        if o.type == "EMPTY" and not o.children:
            bpy.data.objects.remove(o)
    ob.parent = None
    bx.select_only([ob], ob)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return ob


def _box(size):
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    ob = bpy.context.active_object
    ob.scale = Vector(size)
    bpy.ops.object.transform_apply(scale=True)
    ob.location = (0, 0, size[2] / 2)   # standing on the ground
    bpy.ops.object.transform_apply(location=True)
    mat = bpy.data.materials.new("Outer")
    ob.data.materials.append(mat)
    return ob


def seeds(lo, hi, n, rng, focus=None, focus_share=0.5):
    """n points in the box lo..hi; with focus, focus_share of them within a quarter of the box around it."""
    pts = []
    size = hi - lo
    for i in range(n):
        if focus is not None and i < int(n * focus_share):
            p = Vector(focus) + Vector([rng.uniform(-0.25, 0.25) * s for s in size])
            p = Vector([min(max(p[k], lo[k]), hi[k]) for k in range(3)])
        else:
            p = Vector([rng.uniform(lo[k], hi[k]) for k in range(3)])
        pts.append(p)
    return pts


def cell(src_mesh, i, pts, inner_index):
    """bmesh of src cut to Voronoi cell i, cuts capped and set to the inner material."""
    bm = bmesh.new()
    bm.from_mesh(src_mesh)
    me = pts[i]
    for j, other in enumerate(pts):
        if j == i or not bm.verts:
            continue
        n = (other - me).normalized()   # the plane's normal points AWAY from this seed: clear that side
        mid = (me + other) / 2
        res = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=mid, plane_no=n,
                                     clear_outer=True)
        cut = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
        if cut:
            made = bmesh.ops.holes_fill(bm, edges=cut, sides=0)
            for f in made["faces"]:
                f.material_index = inner_index
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm


def box_uv(bm, scale, offset=Vector()):
    """Box-projected UV for every face: the two axes across its dominant normal, in metres / scale (offset = where
    this bmesh's origin sits in the intact object, so a piece keeps the intact pattern)."""
    uv = bm.loops.layers.uv.verify()
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda k: abs(n[k]))
        u, v = [(1, 2), (0, 2), (0, 1)][ax]
        for loop in f.loops:
            p = loop.vert.co + offset
            loop[uv].uv = (p[u] / scale, p[v] / scale)


def _image_material(mat, path, tint=1.0, normal=None, colour=(1.0, 1.0, 1.0)):
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(os.path.abspath(path), check_existing=True)
    c = [k * tint for k in colour]
    if c != [1.0, 1.0, 1.0]:
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 1.0
        mix.inputs[7].default_value = (c[0], c[1], c[2], 1.0)
        nt.links.new(tex.outputs["Color"], mix.inputs[6])
        nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
    else:
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    if normal:
        nt_tex = nt.nodes.new("ShaderNodeTexImage")
        nt_tex.image = bpy.data.images.load(os.path.abspath(normal), check_existing=True)
        nt_tex.image.colorspace_settings.name = "Non-Color"
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(nt_tex.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])


def run(source=None, object=None, box=None, pieces=24, seed=1, focus=None, out=None, basecolor=None, normal=None, uv_scale=2.0, tint=None, **_):
    if pieces < 2:
        raise ValueError("--pieces must be at least 2")
    if source:
        src = _join(_import(os.path.abspath(source)))
    elif object:
        src = _join([bpy.data.objects[object]])
    elif box:
        src = _box(box)
    else:
        raise ValueError("give --source FILE, --object NAME or --box X Y Z")
    src.name = "Intact"
    mesh = src.data
    if not mesh.materials:
        mesh.materials.append(bpy.data.materials.new("Outer"))
    inner = bpy.data.materials.get("Inner") or bpy.data.materials.new("Inner")
    inner.diffuse_color = (0.55, 0.5, 0.45, 1.0)
    mesh.materials.append(inner)
    inner_index = len(mesh.materials) - 1
    if basecolor:
        if not os.path.isfile(basecolor):
            raise ValueError("--basecolor %s does not exist" % basecolor)
        col = tuple(tint) if tint else (1.0, 1.0, 1.0)
        for m in mesh.materials[:inner_index]:
            _image_material(m, basecolor, 1.0, normal, col)
        _image_material(inner, basecolor, 0.6, normal, col)
        bm = bmesh.new()
        bm.from_mesh(mesh)
        box_uv(bm, uv_scale)
        bm.to_mesh(mesh)
        bm.free()

    bm0 = bmesh.new()
    bm0.from_mesh(mesh)
    vol0 = abs(bm0.calc_volume(signed=True))
    lo = Vector([min(v.co[k] for v in bm0.verts) for k in range(3)])
    hi = Vector([max(v.co[k] for v in bm0.verts) for k in range(3)])
    bm0.free()
    eps = (hi - lo) * 0.02
    rng = random.Random(seed)
    pts = seeds(lo + eps, hi - eps, pieces, rng, focus)

    made, vols = [], []
    for i in range(len(pts)):
        bm = cell(mesh, i, pts, inner_index)
        v = abs(bm.calc_volume(signed=True)) if bm.faces else 0.0
        if v < MIN_PIECE_VOLUME:
            bm.free()
            continue
        centre = sum((x.co for x in bm.verts), Vector()) / len(bm.verts)
        if basecolor:
            box_uv(bm, uv_scale)   # still in intact space here: cut faces get the same continuous pattern
        bmesh.ops.translate(bm, verts=bm.verts[:], vec=-centre)
        me = bpy.data.meshes.new("Piece_%03d" % len(made))
        bm.to_mesh(me)
        bm.free()
        for m in mesh.materials:
            me.materials.append(m)
        ob = bpy.data.objects.new(me.name, me)
        ob.location = centre
        bpy.context.scene.collection.objects.link(ob)
        made.append(ob)
        vols.append(v)

    total = sum(vols)
    res = {"ok": len(made) >= 2, "source": source or object or "box", "pieces": len(made), "seeds": len(pts),
           "intact_volume": bx.r(vol0, 5), "pieces_volume": bx.r(total, 5),
           "volume_ratio": bx.r(total / vol0, 4) if vol0 else None,
           "bounds": [bx.r(x, 3) for x in list(lo) + list(hi)],
           "smallest_piece": bx.r(min(vols), 6) if vols else None, "largest_piece": bx.r(max(vols), 5) if vols else None}
    if vol0 and abs(total / vol0 - 1) > 0.05:
        res["warning"] = "pieces volume differs from the intact mesh by more than 5%: the source is probably not closed"
    if out:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender-export-pipelines", "scripts"))
        import export_asset
        r = export_asset.run(preset="godot", objects=[src.name] + [o.name for o in made], out=os.path.abspath(out))
        res["export"] = r if not r.get("ok") else {"ok": True, "file": r["files"][0]["file"], "summary": r["files"][0].get("summary")}
        res["ok"] = res["ok"] and r.get("ok", False)
    return res


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--source", default=None, help=".fbx/.glb/.gltf/.obj to fracture (all its meshes joined into one)")
    p.add_argument("--object", default=None, help="an object already in the open .blend")
    p.add_argument("--box", nargs=3, type=float, default=None, metavar=("X", "Y", "Z"), help="a test box of this size (m)")
    p.add_argument("--pieces", type=int, default=24)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--focus", nargs=3, type=float, default=None, metavar=("X", "Y", "Z"),
                   help="half the seeds near this object-space point (smaller pieces around a planned hit)")
    p.add_argument("--out", default=None, help=".glb with Intact + Piece_NNN (export_asset preset godot)")
    p.add_argument("--basecolor", default=None, help="image for a triplanar-material source: box-projected UVs + this texture")
    p.add_argument("--normal", default=None, help="normal map image to go with --basecolor")
    p.add_argument("--uv-scale", type=float, default=2.0, help="metres per texture tile for --basecolor")
    p.add_argument("--tint", nargs=3, type=float, default=None, metavar=("R", "G", "B"),
                   help="multiply --basecolor (0..1): greyscale masks made for a tinted engine material (the castle stone)")
    p.add_argument("--save", default=None)
    bx.cli(run, p)
