#!/usr/bin/env python3
"""Shared lake library: the landscape carve and spline helpers that ue_lake_as_waterbody.py and ue_lake_check.py import.

  lake_region()        the vertex rectangle a lake carve writes (one definition for the carve, the neutral clear and the check)
  read_layers()        base Layer + Water layer reads, merged computed from them (the plain merged reply can be stale)
  write_water_revert() save the region's Water values as a ue_run_phases.py undo file BEFORE any write (T-0056)
  clear_water_region() write the neutral 32768 over a rectangle's Water layer (recovery before re-carving)
  carve_lake_bank()    steepened submerged bank carve through the additive Water layer
  circle_spline_text() a uniform closed circle for a water body spline

DO NOT use this script's own main() for lakes. It makes a closed-loop WaterBodyRiver with an inflated RiverWidth, and for a single
closed spline filling the middle by width floods the outside by the same distance: live it put the forest under water (T-0027,
reverted). Its old reason -- "WaterBodyLake has an unresolved WaterZone-registration bug" -- was wrong: the lake only needed a
move_actor after the spline write (see ue_lake_as_waterbody.py). main() therefore refuses unless --i-know-this-floods is given; it is
kept only so the history of the approach stays reproducible. Use:

  ue_lake_as_waterbody.py --label ZAS_LakeBody_1 --center-x X --center-y Y --water-z Z --radius-cm R --material M --old-label Lake_1

The old river recipe's steps (each checked; stops at the first failure; an existing actor with --label is reused):
  1. place (or reuse) a WaterBodyRiver at the origin; write a --points-count point closed circle (center, radius, constant water-z) onto its
     WaterSpline's SplineCurves. A perfectly uniform circle is used on purpose: this component's `closedLoop` property cannot be set true through
     any property path tried so far (bClosedLoop writes report success but get_spline_info still reads closedLoop:false), so the loop is only
     visually seamless when every point is equidistant from the centre. A NON-uniform radius (e.g. a per-point fit to the original organic bank)
     showed a visible crease/self-intersection at the point-0/point-(n-1) wrap on this build -- do not do that; fit the shape with carve_lake_bank
     below instead, which touches the landscape, not the spline.
  2. set WaterMaterial (--material, normally the creek's own instance -- reusing it is what makes the two match and avoids a new asset),
     WaterInfoMaterial, UnderwaterPostProcessMaterial, WaterHLODMaterial, bAffectsLandscape false.
  3. set RiverWidth/Depth curves (uniform across all points): width defaults to a value that, combined with a closed loop, fills the whole disc
     rather than leaving a ring (see carve_lake_bank's docstring for why the exact fill math does not matter here).
  4. carve_lake_bank(): steepen the real bank right at the circle's edge so the water never shows grass/dirt through it and never leaves a dry gap,
     regardless of how well the circle matches the original hand-carved bowl. This is the fix for "lake looks right overall but a couple of spots
     spill onto land or leave a strip of dry bed" -- done on the landscape, which stays correct and matches "real creek" banks, rather than by
     chasing the water shape (the W=0, FollowingAnything-matches-exactly approach was tried and reverted; see T-0027 notes / unreal-scene.md).
  5. rebuild the WaterZone and save. --delete-old removes the old Lake_<n> StaticMeshActor cylinder (only once the new body is confirmed visually);
     without it the old actor is left in place so the caller can hide-and-compare first (level.set_editor_visibility).
"""
import argparse
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_route  # noqa: E402
HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "..", "..", "ansible", "roles", "watoom-code", "files", "skills", "watoom-texture-layering", "scripts")
sys.path.insert(0, SKILL)
import ue_project  # noqa: E402

PX_CM_DEFAULT = 793.6507936507936  # this map: 505 verts, 4000m/504 gaps (ue_heights_fetch.py); override with --px-cm for a different map


def curve(v, n):
    return "(Points=(" + ",".join(("(OutVal=%.1f,InterpMode=CIM_Linear)" % v if i == 0 else "(InVal=%d.000000,OutVal=%.1f,InterpMode=CIM_Linear)" % (i, v)) for i in range(n)) + "))"


def circle_spline_text(cx, cy, z, r, n):
    pts = [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n), z) for i in range(n)]
    pos = []
    for i in range(n):
        x, y, zz = pts[i]
        px, py, _ = pts[(i - 1) % n]
        nx, ny, _ = pts[(i + 1) % n]
        tx, ty = (nx - px) * 0.5, (ny - py) * 0.5
        inv = "" if i == 0 else "InVal=%d.000000," % i
        pos.append("(%sOutVal=(X=%.6f,Y=%.6f,Z=%.6f),ArriveTangent=(X=%.6f,Y=%.6f,Z=0.000000),LeaveTangent=(X=%.6f,Y=%.6f,Z=0.000000),InterpMode=CIM_CurveAuto)" % (inv, x, y, zz, tx, ty, tx, ty))
    rot = ["(%sOutVal=(X=0.000000,Y=0.000000,Z=0.000000,W=1.000000),ArriveTangent=(X=0.000000,Y=0.000000,Z=0.000000,W=0.000000),LeaveTangent=(X=0.000000,Y=0.000000,Z=0.000000,W=0.000000),InterpMode=CIM_CurveAuto)" % ("" if i == 0 else "InVal=%d.000000," % i) for i in range(n)]
    sc = ["(%sOutVal=(X=1.000000,Y=1.000000,Z=1.000000),ArriveTangent=(X=0.000000,Y=0.000000,Z=0.000000),LeaveTangent=(X=0.000000,Y=0.000000,Z=0.000000),InterpMode=CIM_CurveAuto)" % ("" if i == 0 else "InVal=%d.000000," % i) for i in range(n)]
    return "(Position=(Points=(%s)),Rotation=(Points=(%s)),Scale=(Points=(%s)))" % (",".join(pos), ",".join(rot), ",".join(sc))


WATER_LAYER_MID = 32768  # LandscapeDataAccess::MidValue: the Water edit layer's raw zero-delta point (confirmed empirically, T-0049 2026-11-18,
# by writing known raw values to an isolated test vertex and reading merged back): merged_raw = clamp(base_raw + (water_raw - MID), 0, 65535).
# The `Water` edit layer composites ADDITIVELY onto the base `Layer`, not as an absolute override -- writing an absolute-looking target
# height straight into it (the old bug) silently corrupts every vertex it touches, because merged = base + (written - MID) double-counts
# base almost everywhere. To make the merged result equal a desired absolute target_z, write the CHANGE on top of the current Water
# value: water_raw + (target_raw - merged_raw) (equal to MID + target_raw - base_raw when the reads agree). Built from the merged and
# Water reads only, because the base `Layer` read is wrong on whole lines of this map (see read_layers).
MAX_VERTEX = 504  # this map's last vertex index per side (505 verts); a region is clamped to [0, MAX_VERTEX]


def lake_region(cx, cy, r, px_cm, bank_cm, max_vertex=MAX_VERTEX):
    """The vertex rectangle carve_lake_bank writes for a lake, and the bank width it really uses (floored to 2 vertex spacings,
    see carve_lake_bank). Shared by the carve, the neutral clear and ue_lake_check.py so all three agree on the same rectangle --
    a clear or check over a different rectangle than the carve wrote leaves (or misses) a seam at the edge."""
    bank_cm = max(bank_cm, px_cm * 2.0)
    margin = r * 0.25 + bank_cm + 200.0
    region = {"minX": max(int((cx - r - margin) / px_cm) - 1, 0), "maxX": min(int((cx + r + margin) / px_cm) + 1, max_vertex),
              "minY": max(int((cy - r - margin) / px_cm) - 1, 0), "maxY": min(int((cy + r + margin) / px_cm) + 1, max_vertex)}
    return region, bank_cm


def _region_reply(call, landscape_label, region, edit_layer, what):
    args = {"actorLabel": landscape_label, "region": region}
    if edit_layer:
        args["editLayer"] = edit_layer
    resp = call("landscape", "get_height_region", args, what)
    return json.loads(resp[resp.index("{"):])


def read_layers(call, landscape_label, region):
    """Read a rectangle three ways: the plain merged reply (the visible height -- trust this one), the base `Layer` and the `Water`
    layer. Returns {w, h, rpc, z0, merged, water, base, computed}; `computed` is base + Water, kept only to compare.

    Do NOT build heights from the base read: on this map it returns garbage along whole vertex lines while the merged read and the
    rendered terrain are correct -- confirmed T-0049 2026-11-18 on flat untouched ground with a neutral Water layer: merged 318 at
    x=126,y=40 and x=60,y=126, but editLayer:"Layer" read 32549 and 53850 there (x/y = 127, 252, 378 agreed). An earlier note blamed
    the merged read for being "stale inside a water body"; every scan behind that ran along y=126, so it was this base-read fault."""
    d = _region_reply(call, landscape_label, region, None, "get_height_region (merged)")
    rpc = d["rawUnitsPerWorldCm"]
    base = _region_reply(call, landscape_label, region, "Layer", "get_height_region (base)")["heights"]
    water = _region_reply(call, landscape_label, region, "Water", "get_height_region (water)")["heights"]
    computed = [max(0, min(65535, b + (wr - WATER_LAYER_MID))) for b, wr in zip(base, water)]
    return {"w": d["region"]["width"], "h": d["region"]["height"], "rpc": rpc,
            "z0": d["height"]["meanZ"] - d["height"]["meanRaw"] / rpc,
            "merged": d["heights"], "water": water, "base": base, "computed": computed}


def write_water_revert(call, landscape_label, landscape_path, region, path):
    """BEFORE any Water-layer write: save the region's current Water-layer values as a ue_run_phases.py file that puts them back
    (set_height_region on the Water layer + merge). The carve and the neutral clear have no undo in the engine; this file is it.
    Why (T-0056, 2026-11-19): carve_lake_bank wrote the landscape with no revert, unlike unreal_lake_smooth.py --out-revert;
    only ad-hoc heightmap backups covered the real lakes. Returns the number of vertices saved."""
    water = _region_reply(call, landscape_label, region, "Water", "get_height_region (water, for the revert)")["heights"]
    phases = {"phases": [{"name": "revert Water layer %s" % json.dumps(region, sort_keys=True), "calls": [
        ["landscape.set_height_region", {"actorPath": landscape_path, "region": region, "space": "quad", "heights": water,
                                         "editLayer": "Water", "heightSpace": "raw"}],
        ["landscape.merge_edit_layers", {"actorLabel": landscape_label, "updateNow": True}]]}]}
    with open(path, "w") as f:
        json.dump(phases, f)
    return len(water)


def clear_water_region(call, landscape_label, landscape_path, region):
    """Write the neutral value (32768) to every Water-layer vertex in `region`, then merge. The recovery step before re-carving a
    region whose Water layer may hold stale offsets: carve_lake_bank keeps any vertex already below its target, so carving over
    a corrupted bed preserves the corruption as 'already deep enough' (T-0049, 2026-11-18). Does not save."""
    n = (region["maxX"] - region["minX"] + 1) * (region["maxY"] - region["minY"] + 1)
    call("landscape", "set_height_region", {"actorPath": landscape_path, "region": region, "space": "quad",
                                             "heights": [WATER_LAYER_MID] * n, "editLayer": "Water", "heightSpace": "raw"},
         "set_height_region (clear Water to neutral)")
    call("landscape", "merge_edit_layers", {"actorLabel": landscape_label, "updateNow": True}, "merge_edit_layers (after clear)")
    return n


def carve_lake_bank(t, call, landscape_label, landscape_path, cx, cy, water_z, r, px_cm, bank_cm, submerge_cm):
    """Steepen the real terrain bank right at the water's edge so the circle never spills onto land or leaves a dry ring, whatever the
    original hand-carved bowl's exact shape was. Inside the circle: clamp height to at most water_z - submerge_cm (never above water).
    In a bank_cm-wide ring just outside the circle: ramp from that submerged level back up to the EXISTING terrain, i.e. a short, steep
    drop -- "steeper banks like a real creek" -- instead of the lake's original (often gentle) shoreline slope. Beyond that ring: untouched.
    Writes to the landscape's `Water` edit layer (the one already used for carved creek/lake beds), merges layers and returns vertex counts;
    does not save -- call level.save afterwards.

    bank_cm is widened to at least 2 landscape vertex spacings (2*px_cm) when the caller's value is narrower than that: a ring
    thinner than about one vertex step has no vertex actually positioned inside it for most radii (this map's vertices are
    ~793.65cm apart, well over the old flat 350cm default), so the ramp collapses into a single-vertex cliff between
    "fully submerged" and "untouched" instead of a gradient. That is invisible on gentle terrain (both ends are close together
    anyway) but carves a dramatic, visible pit wall on sloped terrain -- found testing a WaterBodyLake off to the side near the
    coast (T-0049, 2026-11-18): the default 350cm bank on this map's coarse grid cut a near-vertical trench, not a smooth bank.

    orig_z ("the terrain as currently visible") is the plain merged read, and the value written to the `Water` layer is the change
    on top of the current Water value: water_raw + (target_raw - merged_raw), so a vertex meant to stay put is rewritten unchanged.
    Neither uses the base `Layer` read, which is wrong along whole vertex lines of this map (see read_layers). Writing the target
    height itself into the additive Water layer was the original bug: it dragged the whole written rectangle toward raw 0 (a lake
    bed at sea level and a square pit at the rectangle's edge on the real Lake_1, T-0049 2026-11-18)."""
    region, bank_cm = lake_region(cx, cy, r, px_cm, bank_cm)
    vx0, vy0 = region["minX"], region["minY"]
    lay = read_layers(call, landscape_label, region)
    w, h, rpc, z0 = lay["w"], lay["h"], lay["rpc"], lay["z0"]
    water_raw = lay["water"]

    target_submerged = water_z - submerge_cm
    out = []
    changed = 0
    for i in range(h):
        for j in range(w):
            k = i * w + j
            x, y = (vx0 + j) * px_cm, (vy0 + i) * px_cm
            dist = math.hypot(x - cx, y - cy)
            orig_raw = lay["merged"][k]
            orig_z = orig_raw / rpc + z0
            if dist <= r:
                target_z = min(orig_z, target_submerged)
            elif dist <= r + bank_cm:
                frac = (dist - r) / bank_cm
                ramp = target_submerged + (orig_z - target_submerged) * frac
                target_z = min(orig_z, ramp) if orig_z < target_submerged else ramp
            else:
                target_z = orig_z
            target_raw = int(round((target_z - z0) * rpc))
            new_water_raw = max(0, min(65535, water_raw[k] + (target_raw - orig_raw)))
            out.append(new_water_raw)
            if target_raw != orig_raw:
                changed += 1
    call("landscape", "set_height_region", {"actorPath": landscape_path, "region": region,
                                             "space": "quad", "heights": out, "editLayer": "Water", "heightSpace": "raw"}, "set_height_region")
    call("landscape", "merge_edit_layers", {"actorLabel": landscape_label, "updateNow": True}, "merge_edit_layers")
    return w * h, changed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", required=True)
    ap.add_argument("--center-x", type=float, required=True)
    ap.add_argument("--center-y", type=float, required=True)
    ap.add_argument("--water-z", type=float, required=True)
    ap.add_argument("--radius-cm", type=float, required=True)
    ap.add_argument("--points", type=int, default=32)
    ap.add_argument("--material", required=True, help="water material to reuse (normally the creek's own instance)")
    ap.add_argument("--width-cm", type=float, default=None, help="default: min(2*radius+1500, 2.2*radius)")
    ap.add_argument("--depth-cm", type=float, default=300.0)
    ap.add_argument("--landscape", default="ZAS_Landscape")
    ap.add_argument("--px-cm", type=float, default=PX_CM_DEFAULT)
    ap.add_argument("--bank-cm", type=float, default=350.0, help="width of the steep carved drop just outside the water's edge (widened to at least 2 landscape vertex spacings, see carve_lake_bank)")
    ap.add_argument("--submerge-cm", type=float, default=90.0, help="how far below water level the bed sits at/inside the edge")
    ap.add_argument("--out-revert", default=None, help="revert file written BEFORE the carve (default lake_revert_<label>.json)")
    ap.add_argument("--no-carve", action="store_true", help="skip carve_lake_bank (spline/material/metadata only)")
    ap.add_argument("--old-label", default=None, help="old Lake_<n> StaticMeshActor cylinder to hide (and optionally delete)")
    ap.add_argument("--delete-old", action="store_true")
    ap.add_argument("--host", default="10.99.1.44")
    ap.add_argument("--port", type=int, default=2224)
    ap.add_argument("--user", default="uemcp")
    ap.add_argument("--key-dir", default=ue_route.DEFAULT_KEY_DIR)
    ap.add_argument("--i-know-this-floods", action="store_true", help="run the old closed-loop WaterBodyRiver recipe anyway (see above)")
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    if not a.i_know_this_floods:
        print("REFUSED: a closed-loop WaterBodyRiver lake floods the land around it by its own radius (T-0027). "
              "Use ue_lake_as_waterbody.py instead; pass --i-know-this-floods only to reproduce the old recipe.")
        return 2
    width = a.width_cm if a.width_cm is not None else min(a.radius_cm * 2.0 + 1500.0, a.radius_cm * 2.2)

    t = ue_route.SshTransport(ue_route.ssh_command(a.host, a.port, a.user, a.key_dir))

    def call(cat, meth, args, what, timeout=180):
        r = t.call(cat, meth, args, timeout)
        if ue_route.reply_failed(r, getattr(t, "is_error", False)):
            raise SystemExit("FAILED %s: %s" % (what, r[:400]))
        return r

    try:
        have = t.call("level", "get_actor_details", {"actorLabel": a.label}, 60)
        if not ue_route.reply_ok(have):
            call("level", "place_actor", {"actorClass": "WaterBodyRiver", "label": a.label, "location": {"x": 0, "y": 0, "z": 0}, "onConflict": "fail"}, "place_actor")
            have = call("level", "get_actor_details", {"actorLabel": a.label}, "get_actor_details")
        path = re.search(r'"actorPath":\s*"([^"]+)"', have).group(1)
        print(a.label, path, "radius", a.radius_cm, "width", width)

        text = circle_spline_text(a.center_x, a.center_y, a.water_z, a.radius_cm, a.points)
        call("level", "set_component_property", {"actorLabel": a.label, "componentName": "WaterSpline", "propertyName": "SplineCurves", "value": text}, "SplineCurves", 300)

        for prop, val in (("WaterMaterial", a.material), ("WaterInfoMaterial", "/Water/Materials/WaterInfo/DrawWaterInfo.DrawWaterInfo"),
                          ("UnderwaterPostProcessMaterial", "/Water/Materials/PostProcessing/M_UnderWater_PostProcess_Volume.M_UnderWater_PostProcess_Volume"),
                          ("WaterHLODMaterial", "/Water/Materials/HLOD/HLODWater.HLODWater"), ("bAffectsLandscape", False)):
            call("level", "set_water_body_property", {"actorLabel": a.label, "propertyName": prop, "value": val}, prop)
        for prop, v in (("RiverWidth", width), ("Depth", a.depth_cm)):
            call("editor", "set_property", {"objectPath": path + ".WaterSplineMetadata", "propertyName": prop, "value": curve(v, a.points)}, prop, 120)
        print("materials, landscape flag and metadata set")

        if not a.no_carve:
            lh = call("level", "get_actor_details", {"actorLabel": a.landscape}, "get_actor_details landscape")
            lpath = re.search(r'"actorPath":\s*"([^"]+)"', lh).group(1)
            region, _ = lake_region(a.center_x, a.center_y, a.radius_cm, a.px_cm, a.bank_cm)
            n = write_water_revert(call, a.landscape, lpath, region, a.out_revert or "lake_revert_%s.json" % a.label)
            print("revert written:", a.out_revert or "lake_revert_%s.json" % a.label, n, "Water vertices (ue_run_phases.py it to undo)")
            total, changed = carve_lake_bank(t, call, a.landscape, lpath, a.center_x, a.center_y, a.water_z, a.radius_cm, a.px_cm, a.bank_cm, a.submerge_cm)
            print("bank carved:", changed, "of", total, "vertices in region changed")

        call("level", "rebuild_water_zone", {"actorLabel": "WaterZone"}, "rebuild_water_zone")

        if a.old_label:
            have_old = t.call("level", "get_actor_details", {"actorLabel": a.old_label}, 60)
            if ue_route.reply_ok(have_old):
                call("level", "set_editor_visibility", {"hidden": True, "actorLabels": [a.old_label]}, "hide old")
                print("hidden old actor", a.old_label)
                if a.delete_old:
                    call("level", "delete_actor", {"actorLabel": a.old_label}, "delete old")
                    print("deleted old actor", a.old_label)

        call("level", "save", {"force": True}, "save")
        print("saved")
    finally:
        t.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
