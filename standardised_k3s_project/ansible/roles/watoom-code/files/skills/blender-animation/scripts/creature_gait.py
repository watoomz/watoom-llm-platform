"""Generate looping in-place clips (Idle, Walk, Run, Roar, Attack) for a tailed biped rigged by creature_rig.py, and
optionally export one engine FBX per clip (skinned mesh + that clip, the layout rig_import_fbx_character.py imports).

Why (T-0023, 2026-11-19): the owner's dinosaur packs are static statues with no clips. The clips are procedural, so any
creature rigged by blender-character-rigging/scripts/creature_rig.py (bones root, pelvis, spine_NN, neck_NN, head, tail_NN,
thigh/calf/foot/ball_l/r) gets the same set, scaled to its own leg length.
How: leg angles are set in the creature's side plane as WORLD targets (thigh swing, knee fold in the swing phase, foot
lift), each bone's local rotation is the target minus its rest angle minus what its parents already turned. A statue's
staggered rest pose therefore still walks symmetrically. Pelvis bob/yaw, spine counter-yaw, a travelling tail wave and a
steadied head ride on top. With --export-dir the file is converted to centimetres first (to_centimetres: an Unreal skeleton
must not carry a node scale, see its docstring), so the saved .blend is in cm units. Clips are in place (no root motion): the engine moves the creature (WatooMWanderComponent).
The walk cycle length follows --walk-speed: stride = 4 x hip height x sin(swing), frames = fps x stride / speed, so the
feet do not skate at that speed.
Usage:
  blender -b rig.blend -P creature_gait.py -- --armature TRex_Rig [--walk-speed 2.0] [--run-speed 5.0] [--fps 30]
      [--clips Idle Walk Run Roar Attack] [--export-dir DIR --mesh TRex_Body --prefix TRex] [--save out.blend]
  MCP: import creature_gait; print(creature_gait.run(armature="TRex_Rig", export_dir="/tmp/out", mesh="TRex_Body"))
"""
import math
import os
import re
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

LEFT, UP = Vector((1, 0, 0)), Vector((0, 0, 1))  # creature_rig faces -Y, so +X is its left
TAU = 2 * math.pi
CLIPS = ("Idle", "Walk", "Run", "Roar", "Attack")


def side_angle(d):
    """Angle of a bone direction in the side plane: 0 = straight down, + = pointing backward (+Y)."""
    return math.atan2(d.y, -d.z)


def chain(arm, prefix):
    return sorted((b.name for b in arm.data.bones if re.fullmatch(prefix + r"_\d+", b.name)), key=lambda n: int(n.rsplit("_", 1)[1]))


def smooth(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


class Rig:
    def __init__(self, arm):
        self.arm = arm
        self.bones = {b.name: b for b in arm.data.bones}
        self.rest = {n: side_angle((b.tail_local - b.head_local).normalized()) for n, b in self.bones.items()}
        self.spine, self.neck, self.tail = chain(arm, "spine"), chain(arm, "neck"), chain(arm, "tail")
        self.legs = [s for s in "lr" if all(n + "_" + s in self.bones for n in ("thigh", "calf", "foot"))]
        if not self.legs:
            raise ValueError("no thigh/calf/foot_l|r bones: rig the creature with creature_rig.py")
        self.hip_h = max(self.bones["thigh_" + s].head_local.z for s in self.legs)
        mean = lambda n: sum(self.rest[n + "_" + s] for s in self.legs) / len(self.legs)
        self.stance = {n: mean(n) for n in ("thigh", "calf", "foot", "ball") if all(n + "_" + s in self.bones for s in self.legs)}

    def local(self, name, axis, angle):
        m = self.bones[name].matrix_local.to_3x3().inverted()
        return Quaternion((m @ axis).normalized(), angle)

    def legs_pose(self, p, swing, knee, lift, crouch=0.0):
        """{bone: angle about LEFT}: the world side-plane targets turned into per-bone local angles."""
        out = {}
        for s, phase in zip(self.legs, (0.0, 0.5)):
            q = (p + phase) % 1.0
            sw = math.sin(math.pi * (q - 0.5) / 0.5) if q >= 0.5 else 0.0
            target = {"thigh": self.stance["thigh"] - swing * math.cos(TAU * q) - crouch,
                      "calf": self.stance["calf"] - 0.6 * swing * math.cos(TAU * q) + knee * sw + 1.6 * crouch,
                      "foot": self.stance["foot"] + lift * sw - 0.6 * crouch}
            if "ball" in self.stance:
                target["ball"] = self.stance["ball"] + 0.5 * lift * sw
            above = 0.0
            for n in ("thigh", "calf", "foot", "ball"):
                b = n + "_" + s
                if n in target and b in self.bones:
                    d = target[n] - self.rest[b] - above
                    out[b] = d
                    above += d
        return out


def key_pose(rig, frame, rots, pelvis_offset=None):
    """rots: {bone: [(world axis, angle), ...]}; every other deform bone is keyed at rest so each clip is complete."""
    for name, pb in rig.arm.pose.bones.items():
        pb.rotation_mode = "QUATERNION"
        q = Quaternion()
        for axis, ang in rots.get(name, ()):
            q = q @ rig.local(name, axis, ang)
        pb.rotation_quaternion = q
        pb.keyframe_insert("rotation_quaternion", frame=frame)
        if name == "pelvis":
            off = pelvis_offset or Vector()
            pb.location = rig.bones[name].matrix_local.to_3x3().inverted() @ off
            pb.keyframe_insert("location", frame=frame)


def body(rig, p, rots, sway=0.0, bob=0.0, tail_wave=0.0, head_steady=True, cycles=1):
    """Pelvis yaw, spine counter-yaw, travelling tail wave, steadied head. Adds to rots in place; returns the pelvis offset."""
    yaw = sway * math.sin(TAU * cycles * p)
    rots.setdefault("pelvis", []).append((UP, yaw))
    for n in rig.spine:
        rots.setdefault(n, []).append((UP, -yaw / max(1, len(rig.spine))))
    for i, n in enumerate(rig.tail):
        k = (i + 1) / len(rig.tail)
        rots.setdefault(n, []).append((UP, tail_wave * k * math.sin(TAU * cycles * p - 0.7 * (i + 1))))
    z = -bob * math.cos(2 * TAU * cycles * p)
    if head_steady and rig.neck:
        rots.setdefault(rig.neck[-1], []).append((LEFT, 0.5 * z / max(rig.hip_h, 1e-3)))
    return Vector((0, 0, z))


def make_clip(rig, name, frames, fps, pose):
    act = bpy.data.actions.get(name) or bpy.data.actions.new(name)
    act.use_fake_user = True
    rig.arm.animation_data_create()
    rig.arm.animation_data.action = act
    for f in range(frames + 1):  # last frame = first, so the loop closes
        p = (f % frames) / frames
        rots, off = pose(p)
        key_pose(rig, f + 1, rots, off)
    act.frame_range = (1, frames + 1)
    return act


def clips(rig, fps=30, walk_speed=2.0, run_speed=5.0, names=CLIPS):
    h = rig.hip_h
    deg = math.radians

    def cycle(swing, speed):
        return max(12, int(round(fps * 4 * h * math.sin(swing) / speed)))

    def legs_rots(p, *a, **k):
        return {b: [(LEFT, d)] for b, d in rig.legs_pose(p, *a, **k).items()}

    def idle(p):
        r = legs_rots(p, 0, 0, 0)
        breath = math.sin(TAU * p)
        for n in rig.spine[1:]:
            r.setdefault(n, []).append((LEFT, deg(1.2) * breath))
        if rig.neck:
            r.setdefault(rig.neck[0], []).append((LEFT, -deg(2) * breath))
        if "head" in rig.bones:
            r.setdefault("head", []).append((UP, deg(8) * math.sin(TAU * p)))
        off = body(rig, p, r, sway=0, bob=0.006 * h, tail_wave=deg(5), head_steady=False)
        return r, off

    def gait(swing, knee, lift, sway, bob, tail):
        def pose(p):
            r = legs_rots(p, swing, knee, lift)
            return r, body(rig, p, r, sway=sway, bob=bob, tail_wave=tail)
        return pose

    def roar(p):
        e = smooth(p / 0.25) * (1 - smooth((p - 0.7) / 0.3))
        r = legs_rots(p, 0, 0, 0, crouch=deg(6) * e)
        for n, a in zip(rig.neck, (-15, -10)):
            r.setdefault(n, []).append((LEFT, deg(a) * e))
        if "head" in rig.bones:
            r.setdefault("head", []).append((LEFT, -deg(12) * e))
            r["head"].append((UP, deg(5) * e * math.sin(TAU * 6 * p)))
        if rig.spine:
            r.setdefault(rig.spine[-1], []).append((LEFT, -deg(6) * e))
        for n in rig.tail:
            r.setdefault(n, []).append((LEFT, deg(4) * e))
        off = body(rig, p, r, bob=0, tail_wave=deg(3) * e, head_steady=False)
        return r, off + Vector((0, 0, -0.04 * h * e))

    def attack(p):
        wind = smooth(p / 0.3) * (1 - smooth((p - 0.3) / 0.15))
        strike = smooth((p - 0.3) / 0.15) * (1 - smooth((p - 0.6) / 0.4))
        r = legs_rots(p, 0, 0, 0, crouch=deg(8) * strike)
        for n in rig.spine:
            r.setdefault(n, []).append((LEFT, deg(5) * strike - deg(2) * wind))
        for n, a in zip(rig.neck, (12, 8)):
            r.setdefault(n, []).append((LEFT, deg(a) * strike - deg(10) * wind))
        if "head" in rig.bones:
            r.setdefault("head", []).append((LEFT, deg(6) * strike - deg(8) * wind))
        for n in rig.tail:
            r.setdefault(n, []).append((LEFT, deg(3) * strike))
        off = body(rig, p, r, bob=0, tail_wave=deg(3), head_steady=False)
        return r, off + Vector((0, -0.06 * h * strike, -0.03 * h * strike))

    spec = {
        "Idle": (int(3 * fps), idle),
        "Walk": (cycle(deg(18), walk_speed), gait(deg(18), deg(35), deg(15), deg(3), 0.025 * h, deg(7))),
        "Run": (cycle(deg(28), run_speed), gait(deg(28), deg(60), deg(25), deg(4), 0.05 * h, deg(10))),
        "Roar": (int(2.5 * fps), roar),
        "Attack": (int(1.5 * fps), attack),
    }
    out = {}
    for n in names:
        frames, pose = spec[n]
        make_clip(rig, n, frames, fps, pose)
        out[n] = {"frames": frames + 1, "seconds": round(frames / fps, 3)}
    return out


def to_centimetres(arm, meshes):
    """Unreal-ready units: scene unit scale 0.01 and rig + meshes scaled x100 and applied (pose-bone location keys x100 too).

    Why (2026-11-19, T-0023): exported in metres, the armature object becomes a top bone with scale 100 in the mesh while every
    clip plays it at scale 1, so in game the whole skeleton shrank 100x (pelvis at 3.6 cm, feet barely moving, the creature
    slid along unanimated). FBX_SCALE_ALL did not change it; a rig built in centimetres carries no node scale at all."""
    if abs(bpy.context.scene.unit_settings.scale_length - 0.01) < 1e-9:
        return False
    bpy.context.scene.unit_settings.scale_length = 0.01
    obs = [arm] + list(meshes)
    for o in obs:
        if o.parent is None:
            o.matrix_world = Matrix.Scale(100.0, 4) @ o.matrix_world
    bx.select_only(obs, active=arm)
    with bpy.context.temp_override(active_object=arm, selected_editable_objects=obs, object=arm):
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for act in bpy.data.actions:
        bags = [cb for layer in act.layers for strip in layer.strips for cb in strip.channelbags] if hasattr(act, "layers") else [act]
        for bag in bags:
            for fc in bag.fcurves:
                if fc.data_path.endswith(".location"):
                    for k in fc.keyframe_points:
                        k.co.y *= 100.0
                        k.handle_left.y *= 100.0
                        k.handle_right.y *= 100.0
    return True


def run(armature=None, fps=30, walk_speed=2.0, run_speed=5.0, clips_=None, export_dir=None, mesh=None, prefix=None, **kw):
    bx.object_mode()
    arm = bpy.data.objects[armature]
    bpy.context.scene.render.fps = fps
    rig = Rig(arm)
    made = clips(rig, fps, walk_speed, run_speed, clips_ or kw.get("clips") or CLIPS)
    res = {"ok": True, "armature": arm.name, "hip_height": round(rig.hip_h, 3), "legs": rig.legs,
           "tail_bones": len(rig.tail), "clips": made}
    if export_dir:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "blender-export-pipelines", "scripts"))
        import export_asset
        prefix = prefix or arm.name
        res["centimetres"] = to_centimetres(arm, [bpy.data.objects[mesh]] if mesh else [])
        files = {}
        for n in made:
            arm.animation_data.action = bpy.data.actions[n]
            bpy.context.scene.frame_start, bpy.context.scene.frame_end = 1, made[n]["frames"]
            r = export_asset.run(preset="unreal_skeletal", objects=[arm.name] + ([mesh] if mesh else []),
                                 out=os.path.join(export_dir, "%s_%s.fbx" % (prefix, n)),
                                 # textures inside the FBX: statue/scan packs keep them packed or beside a temp .fbm folder,
                                 # and the engine import (Interchange) reads embedded textures
                                 set=["path_mode=COPY", "embed_textures=true"])
            files[n] = r["files"][0]["file"] if r["ok"] else r
        arm.animation_data.action = bpy.data.actions["Idle"] if "Idle" in made else None
        res["fbx"] = files
    return res


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--armature", required=True)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--walk-speed", type=float, default=2.0, help="m/s the engine moves the creature while Walk plays")
    p.add_argument("--run-speed", type=float, default=5.0)
    p.add_argument("--clips", nargs="*", default=list(CLIPS), choices=list(CLIPS))
    p.add_argument("--export-dir", default=None, help="write <prefix>_<Clip>.fbx (unreal_skeletal preset) per clip")
    p.add_argument("--mesh", default=None, help="skinned mesh to include in each FBX")
    p.add_argument("--prefix", default=None)
    p.add_argument("--save", default=None)
    bx.cli(run, p)
