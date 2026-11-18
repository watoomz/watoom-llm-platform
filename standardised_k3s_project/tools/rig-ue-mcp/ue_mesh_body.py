#!/usr/bin/env python3
"""Measure how any skeletal mesh must sit in a Character: facing, capsule size and mesh offset (biped, quadruped, dragon, ...).

  ue_mesh_body.py --out bodies.json /Game/Path/SK_Mesh [/Game/Path/SK_Other ...] [--radius-margin 1.25]

Reads asset.get_mesh_bounds and asset.list_skeleton_bones (rest pose, component space) and writes
{"<mesh path>": {"facing": "+Y", "yaw": -90, "CapsuleHalfHeight": .., "CapsuleRadius": .., "Mesh.RelativeLocation": "(X=..)",
 "Mesh.RelativeRotation": "(Pitch=0,Yaw=-90,Roll=0)", "evidence": {...}}}
which unreal_combat.py takes as a character's "body" (spec key "bodies_file" or a "body" object), so the mesh stands upright,
feet on the capsule bottom, facing the capsule's +X (where the character moves, aims and swings).

Why (T-0063, 2026-11-18): the first combat character copied a humanoid's -90 cm / -90 deg offset by hand; without it the mesh
stood sideways and the sword sweep missed. That offset is a humanoid import convention, wrong for a dragon or a wolf. Measured:
 - facing: the larger of two horizontal pointers, toes ahead of the ankles (feet) and head ahead of the pelvis/root (body),
   snapped to the nearest axis. Wizard: toes +Y; dragon: head 800 cm +Y of the root. Bone names are matched loosely
   (head, neck, pelvis, hips, root, foot, ankle, toe, ball, ...) so any rig works; "evidence" says which pointer won.
 - capsule radius: the SIDEWAYS reach of the leg bones (named thigh/calf/knee/leg/foot/ankle/toe/paw/hoof..., else the bones
   below the pelvis, else the lower 40% of the mesh) from their centre, times --radius-margin, at least 0.18 x the height.
   Sideways (perpendicular to the facing) so a quadruped's length does not count; arms, robes, wings and tails are not legs.
   Never above the half height.
 - capsule half height: half the mesh's bounds height (at least the radius).
 - offset: the feet (bounds min z) go to the capsule bottom; the legs' centre goes onto the capsule axis after the rotation.
A Character capsule is always vertical: a long quadruped's body sticks out front and back, which is normal (movement uses the
capsule, hits use the mesh's physics asset). Check "evidence" for a mesh whose skeleton has no feet and no head (the facing is then
the Unreal default +Y and marked "guessed").
"""
import argparse
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_route  # noqa: E402

HEAD = re.compile(r"head|skull", re.I)
BODY = re.compile(r"^(pelvis|hips?|root|spine_?0?1|spine)$", re.I)
ANKLE = re.compile(r"foot|ankle|heel", re.I)
TOE = re.compile(r"toe|ball", re.I)
LEG = re.compile(r"thigh|calf|shin|knee|leg|foot|ankle|heel|toe|ball|paw|hoof", re.I)
MIN_RADIUS_OF_HEIGHT = 0.18  # a humanoid capsule is ~35 cm wide for ~195 cm tall; also the floor for thin-legged creatures
YAW = {"+X": 0.0, "+Y": -90.0, "-X": 180.0, "-Y": 90.0}


def _horiz(points):
    return [(p["x"], p["y"]) for p in points]


def _mean(pts):
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)) if pts else None


def snap(vx, vy):
    """Horizontal vector -> nearest axis name."""
    if abs(vx) >= abs(vy):
        return "+X" if vx >= 0 else "-X"
    return "+Y" if vy >= 0 else "-Y"


def facing(bones):
    """bones: {name: {x,y,z}} -> (axis, evidence). The longer horizontal pointer wins (feet or head-vs-body)."""
    cands = []
    toes = [v for n, v in bones.items() if TOE.search(n)]
    ankles = [v for n, v in bones.items() if ANKLE.search(n) and not TOE.search(n)]
    if toes and ankles:
        t, a = _mean(_horiz(toes)), _mean(_horiz(ankles))
        cands.append(("feet", t[0] - a[0], t[1] - a[1]))
    heads = [v for n, v in bones.items() if HEAD.search(n)]
    body = [v for n, v in bones.items() if BODY.match(n)]
    if heads and body:
        h, b = _mean(_horiz(heads)), _mean(_horiz(body))
        cands.append(("head", h[0] - b[0], h[1] - b[1]))
    cands = [c for c in cands if math.hypot(c[1], c[2]) > 1.0]
    if not cands:
        return "+Y", {"method": "guessed", "why": "no toe/ankle or head/pelvis bones with a horizontal offset; Unreal default +Y"}
    name, vx, vy = max(cands, key=lambda c: math.hypot(c[1], c[2]))
    return snap(vx, vy), {"method": name, "vector": [round(vx, 1), round(vy, 1)],
                          "others": [[c[0], round(c[1], 1), round(c[2], 1)] for c in cands if c[0] != name]}


def rotate(x, y, yaw_deg):
    r = math.radians(yaw_deg)
    return x * math.cos(r) - y * math.sin(r), x * math.sin(r) + y * math.cos(r)


def body(bounds, bones, radius_margin=1.25):
    """bounds {"min": {x,y,z}, "max": {..}}, bones {name: {x,y,z}} (component space) -> body dict."""
    lo, hi = bounds["min"], bounds["max"]
    height = hi["z"] - lo["z"]
    axis, evidence = facing(bones)
    yaw = YAW[axis]
    legs, source = [v for n, v in bones.items() if LEG.search(n)], "named leg bones"
    if len(legs) < 2:
        hips = [v["z"] for n, v in bones.items() if re.match(r"^(pelvis|hips?)$", n, re.I)]
        cut = min(hips) if hips else lo["z"] + 0.4 * height
        legs, source = [v for v in bones.values() if v["z"] < cut], "bones below the pelvis"
    if len(legs) < 2:
        legs, source = [v for v in bones.values() if v["z"] < lo["z"] + 0.4 * height] or list(bones.values()), "lower 40% of the mesh"
    c = _mean(_horiz(legs))
    side = (0.0, 1.0) if axis in ("+X", "-X") else (1.0, 0.0)  # unit vector perpendicular to the facing
    reach = max(abs((p[0] - c[0]) * side[0] + (p[1] - c[1]) * side[1]) for p in _horiz(legs)) if legs else 0.0
    half = max(height / 2.0, 1.0)
    radius = min(max(reach * radius_margin, MIN_RADIUS_OF_HEIGHT * height), half)
    half = max(half, radius)
    ox, oy = rotate(c[0], c[1], yaw)
    loc = (-ox, -oy, -half - lo["z"])
    return {"facing": axis, "yaw": yaw, "CapsuleHalfHeight": round(half, 2), "CapsuleRadius": round(radius, 2),
            "Mesh.RelativeLocation": "(X=%.6f,Y=%.6f,Z=%.6f)" % loc,
            "Mesh.RelativeRotation": "(Pitch=0.000000,Yaw=%.6f,Roll=0.000000)" % yaw,
            "evidence": dict(evidence, legs=len(legs), leg_source=source, leg_side_reach_cm=round(reach, 1), height_cm=round(height, 1))}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("meshes", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--radius-margin", type=float, default=1.25)
    ap.add_argument("--host", default="10.99.1.44")
    ap.add_argument("--port", type=int, default=2224)
    ap.add_argument("--user", default="uemcp")
    ap.add_argument("--key-dir", default=ue_route.DEFAULT_KEY_DIR)
    a = ap.parse_args(argv)
    t = ue_route.SshTransport(ue_route.ssh_command(a.host, a.port, a.user, a.key_dir))

    def call(cat, meth, args):
        r = t.call(cat, meth, args, 300)
        if ue_route.reply_failed(r, getattr(t, "is_error", False)):
            raise SystemExit("FAILED %s.%s: %s" % (cat, meth, r[:300]))
        return json.loads(r[r.index("{"):])
    out = {}
    try:
        for m in a.meshes:
            b = call("asset", "get_mesh_bounds", {"assetPath": m})
            k = call("asset", "list_skeleton_bones", {"assetPath": m, "includeTransforms": True, "limit": 2000})
            bones = {x["name"]: x["componentSpaceLocation"] for x in k.get("bones", []) if x.get("componentSpaceLocation")}
            out[m] = body(b, bones, a.radius_margin)
            e = out[m]
            print("%s: facing %s (%s), capsule r %.0f hh %.0f, mesh %s %s" % (m, e["facing"], e["evidence"]["method"], e["CapsuleRadius"],
                                                                          e["CapsuleHalfHeight"], e["Mesh.RelativeLocation"], e["Mesh.RelativeRotation"]))
    finally:
        t.close()
    write_bodies(a.out, out)
    return 0


def write_bodies(path, new):
    """Merge into an existing bodies file (measured meshes are replaced, the others kept). It used to overwrite: measuring
    two new meshes into bodies.zas.json dropped the Manny and wizard bodies the spec still used (2026-11-19)."""
    have = {}
    if os.path.exists(path):
        with open(path) as f:
            have = json.load(f)
    have.update(new)
    with open(path, "w") as f:
        json.dump(have, f, indent=1)
    return have


if __name__ == "__main__":
    sys.exit(main())
