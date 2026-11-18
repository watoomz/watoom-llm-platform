#!/usr/bin/env python3
"""Turn a round lake into a native `WaterBodyLake` (driver, not a skill script).

  ue_lake_as_waterbody.py --label ZAS_Lake_1 --center-x 177777.78 --center-y 167460.32 --water-z 8607.86 --radius-cm 12250 \
      --material /Game/ZAS/Water/MI_ZAS_River.MI_ZAS_River [--old-label Lake_1] [--delete-old]

Why WaterBodyLake, not WaterBodyRiver (see T-0049/T-0053/T-0056): ue_lake_as_river.py used a closed-loop WaterBodyRiver with
an inflated RiverWidth to try to fill the disc -- that floods the exterior by the same radius it fills the interior for any
single closed spline (no tuning fixes it; it broke live, owner caught it, reverted). A WaterBodyLake's closed spline loop IS
the fill: it has no width property at all (FixedWaterDepth is a single scalar, not a per-point curve), so there is no
equivalent flood-the-exterior failure mode.

THE FIX for "WaterBodyLake renders no water" (previously blamed on an unresolved engine bug, see ue_lake_as_river.py's old
docstring): a lake's rendered water height comes from the ACTOR'S OWN ROOT TRANSFORM Z, not the per-point spline Z -- writing
SplineCurves with points at the right world Z is not enough; nothing re-syncs it until the actor itself moves. Fix: after
writing the spline, move_actor the lake to {x:0, y:0, z:water_z}; that move triggers the construction script that actually
syncs the water height. Verified live on a disposable test lake (T-0049, 2026-11-18): without the move, no water rendered at
all; with it, a clean, solid, correctly bounded circular lake, no donut hole, no outward flood.

Landscape carve: bAffectsLandscape=true fires the Water plugin's OWN automatic landscape brush on rebuild_water_zone (confirmed
live, T-0049 2026-11-18, after the owner enabled the WaterAdvanced/WaterExtras plugins and restarted -- earlier the same evening,
before that restart, bAffectsLandscape did nothing headlessly here). That native carve runs independently of, and fights, this
script's own manual carve_lake_bank() -- it was the cause of a lake reading as flat sea level after two manual carve attempts,
and of a small residual drift versus the expected merged height even on an otherwise-correct carve. So bAffectsLandscape is set
FALSE here (same as ue_lake_as_river.py's WaterBodyRiver), and this script's own carve_lake_bank() (imported from there -- it is
landscape-only and does not care which WaterBody class owns the spline) is the only thing that touches the landscape.

Steps (each checked; stops at the first failure; safe to re-run, an existing actor with --label is reused):
  1. place (or reuse) a WaterBodyLake at the origin; write a --points-count point closed circle (center, radius, constant
     water-z) onto its WaterSpline's SplineCurves (circle_spline_text, imported from ue_lake_as_river.py).
  2. set WaterMaterial/WaterInfoMaterial/UnderwaterPostProcessMaterial/WaterHLODMaterial, bAffectsLandscape=False (see above),
     FixedWaterDepth.
  3. move_actor the lake to {0,0,water_z} -- THE fix above; skip this and the lake is invisible.
  4. carve_lake_bank(): same steepened-bank carve as ue_lake_as_river.py (steepen the real terrain right at the circle's
     edge so the water never shows grass/dirt through it and never leaves a dry gap).
  5. rebuild the WaterZone and save. --delete-old removes the old Lake_<n> StaticMeshActor cylinder (only once the new body
     is confirmed visually); without it the old actor is left in place so the caller can hide-and-compare first.

Re-running on an existing lake (T-0049, 2026-11-18) -- pick the narrowest mode that does the job:
  --carve-only         only the landscape: (optional clear) + carve + rebuild + save. The water body is not touched. Use this to fix a
                       bed under a lake that already renders correctly. Re-running the FULL steps (spline rewrite + move_actor) on an
                       existing, already-correct lake was followed live by that lake rendering as an unclipped square plane at the wrong
                       height (Lake_3, then Lake_4); root cause not confirmed, so do not rewrite a good lake's spline just to re-carve.
  --clear-water-first  write neutral (32768) to the whole carve rectangle's Water layer before carving. Needed whenever the bed may
                       hold stale offsets: the carve keeps any vertex already below its target, so carving over a corrupted bed
                       preserves the corruption and reports a misleading "0 of N changed".
  --materials-only     existing lake: set the water/info/underwater/HLOD materials, bAffectsLandscape and FixedWaterDepth only -- no
                       spline rewrite, no move_actor, no carve -- then the --old-label hide/delete, rebuild and save. Use it to switch a
                       lake to the creek's material (MI_ZAS_River; MI_ZAS_Lake renders flat and glassy) or to delete an old disc.
  --recreate           delete the existing water body and place a fresh one, then run every step. The fix that worked live when an
                       existing lake would not render clipped to its spline.
Afterwards run ue_lake_check.py on the lake (bed health), then capture it from several angles and distances
(ue_viewport_shot.py --around) -- a single camera angle hid a broken lake on T-0049. A level.load (e.g. opening an autosave and
coming back) can also reset editor-hidden actors, so re-run with --old-label (it re-hides) if the old cylinder shows again.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_route  # noqa: E402
from ue_lake_as_river import carve_lake_bank, circle_spline_text, clear_water_region, lake_region, write_water_revert, PX_CM_DEFAULT  # noqa: E402
HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "..", "..", "ansible", "roles", "watoom-code", "files", "skills", "watoom-texture-layering", "scripts")
sys.path.insert(0, SKILL)
import ue_project  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", required=True)
    ap.add_argument("--center-x", type=float, required=True)
    ap.add_argument("--center-y", type=float, required=True)
    ap.add_argument("--water-z", type=float, required=True)
    ap.add_argument("--radius-cm", type=float, required=True)
    ap.add_argument("--points", type=int, default=32)
    ap.add_argument("--material", required=True, help="water material to reuse (normally the creek's own instance)")
    ap.add_argument("--depth-cm", type=float, default=300.0, help="FixedWaterDepth -- a lake has one scalar depth, not a per-point curve")
    ap.add_argument("--landscape", default="ZAS_Landscape")
    ap.add_argument("--px-cm", type=float, default=PX_CM_DEFAULT)
    ap.add_argument("--bank-cm", type=float, default=350.0, help="width of the steep carved drop just outside the water's edge (widened to at least 2 landscape vertex spacings, see carve_lake_bank)")
    ap.add_argument("--submerge-cm", type=float, default=90.0, help="how far below water level the bed sits at/inside the edge")
    ap.add_argument("--no-carve", action="store_true", help="skip carve_lake_bank (spline/material/metadata only)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--carve-only", action="store_true", help="existing lake: landscape only, do not touch the water body (see above)")
    mode.add_argument("--materials-only", action="store_true", help="existing lake: materials/properties (+ --old-label) only, see above")
    mode.add_argument("--recreate", action="store_true", help="delete the existing water body first and place a fresh one")
    ap.add_argument("--out-revert", default=None, help="revert file written BEFORE any landscape write (default lake_revert_<label>.json)")
    ap.add_argument("--clear-water-first", action="store_true", help="neutral-clear the carve rectangle's Water layer before carving")
    ap.add_argument("--old-label", default=None, help="old Lake_<n> StaticMeshActor cylinder to hide (and optionally delete)")
    ap.add_argument("--delete-old", action="store_true")
    ap.add_argument("--host", default="10.99.1.44")
    ap.add_argument("--port", type=int, default=2224)
    ap.add_argument("--user", default="uemcp")
    ap.add_argument("--key-dir", default=ue_route.DEFAULT_KEY_DIR)
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    if a.carve_only and a.no_carve:
        ap.error("--carve-only with --no-carve would do nothing")

    t = ue_route.SshTransport(ue_route.ssh_command(a.host, a.port, a.user, a.key_dir))

    def call(cat, meth, args, what, timeout=180):
        r = t.call(cat, meth, args, timeout)
        if ue_route.reply_failed(r, getattr(t, "is_error", False)):
            raise SystemExit("FAILED %s: %s" % (what, r[:400]))
        return r

    try:
        have = t.call("level", "get_actor_details", {"actorLabel": a.label}, 60)
        exists = ue_route.reply_ok(have)
        if (a.carve_only or a.materials_only) and not exists:
            raise SystemExit("FAILED --%s: no actor labelled %s (place it first without that flag)"
                             % ("carve-only" if a.carve_only else "materials-only", a.label))
        if a.recreate and exists:
            call("level", "delete_actor", {"actorLabel": a.label}, "delete_actor (--recreate)")
            print("deleted existing", a.label, "(--recreate)")
            exists = False
        if not exists:
            call("level", "place_actor", {"actorClass": "WaterBodyLake", "label": a.label, "location": {"x": 0, "y": 0, "z": 0}, "onConflict": "fail"}, "place_actor")
            have = call("level", "get_actor_details", {"actorLabel": a.label}, "get_actor_details")
        path = re.search(r'"actorPath":\s*"([^"]+)"', have).group(1)
        print(a.label, path, "radius", a.radius_cm)

        if not a.carve_only:
            if not a.materials_only:
                text = circle_spline_text(a.center_x, a.center_y, a.water_z, a.radius_cm, a.points)
                call("level", "set_component_property", {"actorLabel": a.label, "componentName": "WaterSpline", "propertyName": "SplineCurves", "value": text}, "SplineCurves", 300)

            for prop, val in (("WaterMaterial", a.material), ("WaterInfoMaterial", "/Water/Materials/WaterInfo/DrawWaterInfo.DrawWaterInfo"),
                              ("UnderwaterPostProcessMaterial", "/Water/Materials/PostProcessing/M_UnderWater_PostProcess_Volume.M_UnderWater_PostProcess_Volume"),
                              ("WaterHLODMaterial", "/Water/Materials/HLOD/HLODWater.HLODWater"), ("bAffectsLandscape", False),
                              ("FixedWaterDepth", a.depth_cm)):
                call("level", "set_water_body_property", {"actorLabel": a.label, "propertyName": prop, "value": val}, prop)
            print("materials and metadata set")

            # THE fix: a lake's water height is driven by the actor's own root Z, not the spline point Z -- nothing re-syncs
            # it until the actor itself moves. Without this call the lake places and saves fine but renders no visible water.
            if not a.materials_only:
                call("level", "move_actor", {"actorLabel": a.label, "location": {"x": 0, "y": 0, "z": a.water_z}}, "move_actor (water-height sync)")
                print("moved to water-z", a.water_z, "-- water-height sync triggered")
        else:
            print("--carve-only: water body left untouched")

        if not a.no_carve and not a.materials_only:
            lh = call("level", "get_actor_details", {"actorLabel": a.landscape}, "get_actor_details landscape")
            lpath = re.search(r'"actorPath":\s*"([^"]+)"', lh).group(1)
            region, _ = lake_region(a.center_x, a.center_y, a.radius_cm, a.px_cm, a.bank_cm)
            rpath = a.out_revert or "lake_revert_%s.json" % a.label
            print("revert written:", rpath, write_water_revert(call, a.landscape, lpath, region, rpath), "Water vertices (ue_run_phases.py it to undo)")
            if a.clear_water_first:
                n = clear_water_region(call, a.landscape, lpath, region)
                print("Water layer cleared to neutral:", n, "vertices", region)
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
