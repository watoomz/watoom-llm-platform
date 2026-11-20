"""Rig an unrigged tailed biped (theropod dinosaur, raptor, ground bird) with a plain engine skeleton, then skin it.

Uses creature_fit.py (landmarks from the mesh surface, any facing/scale) and bind_mesh.py (heat weights, proxy fallback).
The mesh is first turned to face -Y (Blender's character convention), its feet put on Z=0 under the hips at the origin,
and optionally scaled so its body length is --length metres (statue packs come at arbitrary scale).
Every bone's local X is the creature's lateral axis, so a pitch is a rotation about X on every bone (legs, spine, tail)
and a yaw of the spine/tail is about Z: creature_gait.py relies on that.
Usage:
  blender -b -P creature_rig.py -- --source trex.fbx [--length 12] [--name TRex] [--tail-bones 6] [--method auto|proxy]
      --save trex_rigged.blend
  blender -b f.blend -P creature_rig.py -- --meshes Body [--length 12] --save out.blend
  MCP: import creature_rig; print(creature_rig.run(meshes=["Body"], length=12))
Report: creature_fit's landmarks (height, hip height, step, knee_forward per leg: a theropod knee sits forward of the hip,
negative values mean the leg fit should be looked at) and bind_mesh's per-mesh weighting result.
"""
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402
import bind_mesh  # noqa: E402
import creature_fit  # noqa: E402


def _import(path):
    before = set(bpy.data.objects)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    else:
        raise ValueError("unsupported source " + path)
    return [o for o in bpy.data.objects if o not in before and o.type == "MESH"]


def _join(obs, name):
    bx.object_mode()
    for o in obs:  # bake parents (glTF/FBX empties with scale) into the meshes
        mw = o.matrix_world.copy()
        o.parent = None
        o.matrix_world = mw
    bx.select_only(obs, active=obs[0])
    with bpy.context.temp_override(active_object=obs[0], selected_editable_objects=obs, object=obs[0]):
        if len(obs) > 1:
            bpy.ops.object.join()
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob = obs[0]
    ob.name = name
    for o in [o for o in bpy.data.objects if o.type == "EMPTY" and not o.children]:
        bpy.data.objects.remove(o)
    return ob


def sample(ob, n=40000, seed=1):
    """Area-weighted surface samples (dense faces do not bias the fit)."""
    me = ob.data
    me.calc_loop_triangles()
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    tri = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("vertices", tri)
    tri = tri.reshape(-1, 3)
    a, b, c = co[tri[:, 0]], co[tri[:, 1]], co[tri[:, 2]]
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    rng = np.random.default_rng(seed)
    pick = rng.choice(len(tri), size=n, p=area / area.sum())
    r1, r2 = np.sqrt(rng.random(n)), rng.random(n)
    pts = (1 - r1)[:, None] * a[pick] + (r1 * (1 - r2))[:, None] * b[pick] + (r1 * r2)[:, None] * c[pick]
    return np.vstack([pts, co])  # vertices too, so thin extremities (claws, tail tip) are present


def normalise(ob, length=None):
    """Face -Y, feet on Z=0, hips over the origin, optional body length in metres. Returns the scale applied."""
    f = creature_fit.fit(sample(ob, 20000))
    fwd = Vector(f["frame"]["forward"])
    yaw = math.atan2(fwd.x, -fwd.y)  # rotate fwd onto -Y
    ob.matrix_world = Matrix.Rotation(-yaw, 4, "Z") @ ob.matrix_world
    s = 1.0
    if length:
        s = length / f["report"]["length"]
        ob.matrix_world = Matrix.Scale(s, 4) @ ob.matrix_world
    bx.select_only([ob], active=ob)
    with bpy.context.temp_override(active_object=ob, selected_editable_objects=[ob], object=ob):
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    f = creature_fit.fit(sample(ob, 20000))
    root = Vector(f["joints"]["root"][0])
    ob.data.transform(Matrix.Translation(-root))
    ob.data.update()
    return s


def build_armature(fit, name):
    arm_data = bpy.data.armatures.new(name)
    arm = bpy.data.objects.new(name, arm_data)
    bpy.context.scene.collection.objects.link(arm)
    arm.show_in_front = True
    bx.select_only([arm], active=arm)
    bpy.ops.object.mode_set(mode="EDIT")
    left = Vector(fit["frame"]["left"])
    eb = arm_data.edit_bones
    for bname, (h, t) in fit["joints"].items():
        b = eb.new(bname)
        b.head, b.tail = Vector(h), Vector(t)
        if (b.tail - b.head).length < 1e-4:
            b.tail = b.head + Vector((0, 0, 0.01))
        d = (b.tail - b.head).normalized()
        z = left.cross(d)
        if z.length < 1e-3:
            z = Vector((0, 0, 1)).cross(d)
        b.align_roll(z.normalized())  # local X = lateral on every bone
    for bname, par in fit["parents"].items():
        if par:
            eb[bname].parent = eb[par]
            eb[bname].use_connect = False
    eb["root"].use_deform = False
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm


def run(source=None, meshes=None, name="Creature", length=None, tail_bones=6, method="auto", **_):
    if source:
        bpy.ops.wm.read_factory_settings(use_empty=True)  # no default cube/camera/light in the rig file
    bx.object_mode()
    obs = _import(source) if source else bx.objects(meshes)
    if not obs:
        raise ValueError("no meshes (give --source or --meshes)")
    body = _join(obs, name + "_Body")
    scale = normalise(body, length)
    f = creature_fit.fit(sample(body), tail_bones=tail_bones)
    arm = build_armature(f, name + "_Rig")
    bound = bind_mesh.run(armature=arm.name, meshes=[body.name], method=method)
    return {"ok": bound["ok"], "armature": arm.name, "mesh": body.name, "scale": round(scale, 4),
            "bones": len(arm.data.bones), "fit": f["report"], "bind": bound["meshes"]}


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--source", default=None, help="FBX / glTF / OBJ to import (else --meshes in the open file)")
    p.add_argument("--meshes", nargs="*", default=None)
    p.add_argument("--name", default="Creature")
    p.add_argument("--length", type=float, default=None, help="body length in metres after rigging (nose to tail tip)")
    p.add_argument("--tail-bones", type=int, default=6)
    p.add_argument("--method", default="auto", choices=["auto", "proxy", "envelope"])
    p.add_argument("--save", default=None)
    bx.cli(run, p)
