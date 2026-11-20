#!/usr/bin/env python3
"""Live check in PIE that the wandering creatures of a spec really roam and animate (unreal_combat.py calls file).

  ue_roam_check.py --from-calls creatures_calls.json [--labels ZAS_TRex_1 ...] [--samples 5] [--every 4] [--keep-pie]

Finds every placed character whose Blueprint has Wander.bEnabled true (or the given --labels), starts PIE on the open level,
and samples each one --samples times, --every seconds apart:
  moved     the root/pelvis bone in world space travelled more than 100 cm from the first sample (the wander moves it)
  --below Z the root stayed under Z (fish under the water surface); --root-bones/--limb-bones name other skeletons' bones
  animated  a foot bone in component space moved more than 3 cm between samples (a T-posed or frozen mesh slides
            with a still foot; a reference pose can look animated in a single capture, so this is the deciding number)
Fish (T-0020, 2026-11-19): BP_FishWander Arapaima, --root-bones root --limb-bones c_tail_02_x --below <water Z>. Use a body
bone: the tail tip c_tail_07_x read 0.0 cm on the fish of two lakes while c_tail_02_x swung 6-9 cm on every fish (moving the
PIE player next to them and AlwaysTickPose changed nothing).
PASS needs both. Bones are tried by common names (pelvis/Hips/root, foot_l/LeftFoot/...). Exit 1 on any FAIL.

Why (T-0023, 2026-11-19): the creature checks were done by hand (positions, anim_state, bone samples) every time a creature
was added; the dinosaurs rigged with creature_rig.py made it the fourth time. A wanderer pauses (WaitMin..WaitMax s), so
the samples span longer than one pause.
"""
import argparse
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_route  # noqa: E402
from ue_combat_check import Rig  # noqa: E402

ROOTS = ("pelvis", "Hips", "hips", "Pelvis", "root", "Root")
FEET = ("foot_l", "LeftFoot", "foot_L", "Foot_L", "l_foot", "foot_r", "RightFoot")


def wanderers(calls_file):
    """-> [label] of placed characters whose Blueprint sets Wander.bEnabled true (pure, tested)."""
    with open(calls_file) as f:
        phases = {p["name"]: p["calls"] for p in json.load(f)["phases"]}
    wander_bps = {a["assetPath"] for m, a in phases.get("characters", [])
                  if m == "blueprint.set_class_default" and a.get("propertyName") == "Wander.bEnabled" and a.get("value") is True}
    out = []
    for m, a in phases.get("place", []):
        if m == "level.place_actor" and a.get("actorClass", "").rsplit(".", 1)[0] in wander_bps:
            out.append(a["label"])
    return out


def judge(roots, feet, min_travel=100.0, min_swing=3.0):
    """roots/feet: lists of (x, y, z) samples -> (moved, animated, travel_cm, swing_cm)."""
    travel = max((math.dist(roots[0], r) for r in roots[1:]), default=0.0) if roots else 0.0
    swing = max((math.dist(a, b) for a, b in zip(feet, feet[1:])), default=0.0) if feet else 0.0
    return travel > min_travel, swing > min_swing, travel, swing


def bone(rig, label, names, space):
    for n in names:
        r = rig.call("animation.get_bone_transform", {"actorLabel": label, "boneName": n, "world": "pie", "space": space}, 60)
        loc = r.get("location") if r.get("success", True) else None
        if isinstance(loc, dict) and "x" in loc:
            return n, (loc["x"], loc["y"], loc["z"])
    return None, None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-calls", required=True)
    ap.add_argument("--labels", nargs="*", default=None)
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--every", type=float, default=4.0)
    ap.add_argument("--keep-pie", action="store_true")
    ap.add_argument("--root-bones", nargs="*", default=[], help="tried before the defaults (a fish: root)")
    ap.add_argument("--limb-bones", nargs="*", default=[], help="tried before the feet (Arapaima: c_tail_02_x, a body bone)")
    ap.add_argument("--below", type=float, default=None, help="FAIL when the root rises above this world Z (fish under a water surface)")
    ap.add_argument("--key-dir", default=ue_route.DEFAULT_KEY_DIR)
    a = ap.parse_args(argv)
    labels = a.labels or wanderers(a.from_calls)
    if not labels:
        raise SystemExit("no wandering characters in %s" % a.from_calls)
    rig = Rig(a.key_dir)
    fails = 0
    try:
        rig.call("editor.play_in_editor", {"pieAction": "stop"})
        rig.call("editor.play_in_editor", {"pieAction": "start"})
        time.sleep(8)
        roots = {l: [] for l in labels}
        feet = {l: [] for l in labels}
        names = {}
        for i in range(a.samples):
            for l in labels:
                rn, r = bone(rig, l, tuple(a.root_bones) + ROOTS, "world")
                fn, f = bone(rig, l, tuple(a.limb_bones) + FEET, "component")
                old = names.get(l, (None, None))
                names[l] = (rn or old[0], fn or old[1])
                if r:
                    roots[l].append(r)
                if f:
                    feet[l].append(f)
            if i < a.samples - 1:
                time.sleep(a.every)
        for l in labels:
            moved, animated, travel, swing = judge(roots[l], feet[l])
            top = max((r[2] for r in roots[l]), default=float("nan"))
            ok = moved and animated and (a.below is None or top < a.below)
            fails += not ok
            print("%s %-28s travel %.0f cm (%s), limb swing %.1f cm (%s), highest Z %.0f, %d samples" % (
                "PASS" if ok else "FAIL", l, travel, names[l][0], swing, names[l][1], top, len(roots[l])))
    finally:
        if not a.keep_pie:
            rig.call("editor.play_in_editor", {"pieAction": "stop"})
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
