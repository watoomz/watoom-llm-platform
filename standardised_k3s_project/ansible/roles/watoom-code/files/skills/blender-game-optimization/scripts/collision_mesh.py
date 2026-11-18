"""Generate convex collision proxies (hull or per-island compound) for real-time engines.

mode=hull: one convex hull enclosing the whole object - cheap, best for already-convex-ish props.
mode=compound: split into connected mesh islands first (Separate by Loose Parts), convex-hull each
island separately - a standard "compound collider" approximation for concave/multi-part meshes,
with no external library (no V-HACD) required.

Generated proxies are named/tagged so each engine's own import-time convention picks them up
automatically:
  --convention unreal (default): UCX_<base> (single) or UCX_<base>_00, UCX_<base>_01, ... (compound).
    Unreal's FBX importer auto-detects UCX_-prefixed siblings of a static mesh as its collision.
  --convention godot: <base>-convcolonly (single) or <base>_00-convcolonly, ... (compound). Godot's
    scene importer auto-detects the -convcolonly/-colonly suffix and generates a convex/trimesh
    StaticBody for that node, without rendering it.
  --convention both: generates one proxy set per convention (doubles proxy object count).
Proxies get hide_render=True (never rendered) and a custom property ob["watoom_collision"] on the
generated object recording the mode and (for compound) piece index.
Usage:
  blender -b f.blend -P collision_mesh.py -- --objects SM_Rock [--mode compound] [--convention unreal]
      [--max-pieces 24] [--parent] [--save out.blend]
  MCP: import collision_mesh; print(collision_mesh.run(objects=["SM_Rock"], mode="compound"))
"""
import os
import sys

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402


def _convex_hull_mesh(me_src, name):
    """New mesh data: the convex hull of me_src's vertices."""
    bm = bmesh.new()
    bm.from_mesh(me_src)
    ret = bmesh.ops.convex_hull(bm, input=bm.verts[:], use_existing_faces=False)
    interior = [g for g in ret["geom_interior"] if isinstance(g, bmesh.types.BMVert)]
    if interior:
        bmesh.ops.delete(bm, geom=interior, context="VERTS")
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


def _separate_islands(ob):
    """Split a (temporary, already-duplicated) object by loose parts. Returns the resulting objects
    (ob itself, renamed, plus any new siblings), restoring selection/mode afterward."""
    bx.select_only([ob])
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.separate(type="LOOSE")
    bpy.ops.object.mode_set(mode="OBJECT")
    return list(bpy.context.selected_objects)


def _name_for(base, convention, index=None, total=1):
    names = []
    if convention in ("unreal", "both"):
        names.append(f"UCX_{base}" if total == 1 else f"UCX_{base}_{index:02d}")
    if convention in ("godot", "both"):
        names.append(f"{base}-convcolonly" if total == 1 else f"{base}_{index:02d}-convcolonly")
    return names


def run(objects=None, mode="hull", convention="unreal", max_pieces=24, parent=False, **_):
    bx.object_mode()
    out = {}
    warnings = []
    col = bpy.context.scene.collection
    for src in bx.objects(objects):
        base = src.name
        pieces_src = [src]
        if mode == "compound":
            tmp = src.copy()
            tmp.data = src.data.copy()
            tmp.name = f"{base}__collision_tmp"
            for c in src.users_collection or [col]:
                c.objects.link(tmp)
            pieces_src = _separate_islands(tmp)
            if len(pieces_src) > max_pieces:
                warnings.append(f"{base}: {len(pieces_src)} islands > max_pieces={max_pieces}; "
                                 f"using the {max_pieces} largest by vertex count")
                pieces_src.sort(key=lambda o: len(o.data.vertices), reverse=True)
                for extra in pieces_src[max_pieces:]:
                    bpy.data.meshes.remove(extra.data)
                    bpy.data.objects.remove(extra)
                pieces_src = pieces_src[:max_pieces]
        total = len(pieces_src)
        produced = []
        for i, piece in enumerate(pieces_src):
            hull_me = _convex_hull_mesh(piece.data, f"{base}_hull{i:02d}")
            for name in _name_for(base, convention, i, total):
                ob = bpy.data.objects.new(name, hull_me if not produced else hull_me.copy())
                ob.matrix_world = piece.matrix_world
                ob.hide_render = True
                ob.display_type = "WIRE"
                ob["watoom_collision"] = mode
                if total > 1:
                    ob["watoom_collision_piece"] = i
                for c in src.users_collection or [col]:
                    c.objects.link(ob)
                if parent:
                    ob.parent = src
                    ob.matrix_parent_inverse = src.matrix_world.inverted()
                produced.append(ob)
        if mode == "compound":
            for piece in pieces_src:
                me = piece.data
                bpy.data.objects.remove(piece)
                bpy.data.meshes.remove(me)
        out[base] = {"mode": mode, "pieces": total,
                     "proxies": [o.name for o in produced],
                     "hull_tris": [bx.mesh_tris(o, evaluated=False) for o in produced[:total]]}
    return {"ok": True, "convention": convention, "objects": out, "warnings": warnings,
            "note": "proxies are hide_render + WIRE display; verify in-engine collision after export "
                    "(Unreal: UCX_ siblings in the same FBX; Godot: -convcolonly/-colonly node suffix)"}


if __name__ == "__main__":
    p = bx.add_common(bx.parser(__doc__))
    p.add_argument("--mode", choices=["hull", "compound"], default="hull")
    p.add_argument("--convention", choices=["unreal", "godot", "both"], default="unreal")
    p.add_argument("--max-pieces", dest="max_pieces", type=int, default=24)
    p.add_argument("--parent", action="store_true")
    bx.cli(run, p)
