#!/usr/bin/env python3
"""Create a `WaterBodyRiver` from a spline through the ue-mcp route (driver for scripts/unreal_creek_river.py in the watoom-texture-layering skill).

  ue_place_river.py --label ZAS_Creek_2 --spline-text creek_spline.txt --points 46 [--depth-cm 700] [--width-cm 4800] [--hide-prefix CreekRibbon_2_]

Steps (each checked; stops at the first failure; safe to re-run, an existing actor with the label is reused): level.place_actor WaterBodyRiver at the origin; write `SplineCurves` on its WaterSpline from the text file
(unreal_creek_river.py --out-text); set WaterMaterial (--material), WaterInfoMaterial, UnderwaterPostProcessMaterial and WaterHLODMaterial; set
bAffectsLandscape false (the terrain was carved with unreal_creek_profile.py; the water brush would fight it); set the `Depth` and `RiverWidth` curves on the
body's WaterSplineMetadata (one point per spline point, so --points must equal the spline's point count); optionally hide the old ribbon actors whose label
starts with --hide-prefix (editor visibility only, reversible). Run level.rebuild_water_zone (WaterZone actor) and level.save afterwards.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_route  # noqa: E402
HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "..", "..", "ansible", "roles", "watoom-code", "files", "skills", "watoom-texture-layering", "scripts")
sys.path.insert(0, SKILL)
import ue_project  # noqa: E402


def curve(v, n):
    return "(Points=(" + ",".join(("(OutVal=%.1f,InterpMode=CIM_Linear)" % v if i == 0 else "(InVal=%d.000000,OutVal=%.1f,InterpMode=CIM_Linear)" % (i, v)) for i in range(n)) + "))"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", required=True)
    ap.add_argument("--spline-text", required=True)
    ap.add_argument("--points", type=int, required=True)
    ap.add_argument("--depth-cm", type=float, default=700.0)
    ap.add_argument("--width-cm", type=float, default=4800.0)
    ap.add_argument("--material", required=True, help="river water material (or water_material in the --project profile)")
    ap.add_argument("--hide-prefix", default=None)
    ap.add_argument("--host", default="10.99.1.44")
    ap.add_argument("--port", type=int, default=2224)
    ap.add_argument("--user", default="uemcp")
    ap.add_argument("--key-dir", default=ue_route.DEFAULT_KEY_DIR)
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    text = open(a.spline_text).read().strip()
    t = ue_route.SshTransport(ue_route.ssh_command(a.host, a.port, a.user, a.key_dir))

    def call(cat, meth, args, what):
        r = t.call(cat, meth, args, 300)
        if ue_route.reply_failed(r, getattr(t, "is_error", False)):
            raise SystemExit("FAILED %s: %s" % (what, r[:400]))
        return r

    try:
        have = t.call("level", "get_actor_details", {"actorLabel": a.label}, 60)
        if not ue_route.reply_ok(have):
            call("level", "place_actor", {"actorClass": "WaterBodyRiver", "label": a.label, "location": {"x": 0, "y": 0, "z": 0}, "onConflict": "fail"}, "place_actor")
            have = call("level", "get_actor_details", {"actorLabel": a.label}, "get_actor_details")
        path = re.search(r'"actorPath":\s*"([^"]+)"', have).group(1)
        print("river body", a.label, path)
        call("level", "set_component_property", {"actorLabel": a.label, "componentName": "WaterSpline", "propertyName": "SplineCurves", "value": text}, "SplineCurves")
        info = call("level", "get_spline_info", {"actorLabel": a.label, "componentName": "WaterSpline"}, "get_spline_info")
        n = int(re.search(r'"splinePointCount":\s*(\d+)', info).group(1))
        print("spline points", n)
        if n != a.points:
            raise SystemExit("spline has %d points, expected --points %d" % (n, a.points))
        for prop, val in (("WaterMaterial", a.material), ("WaterInfoMaterial", "/Water/Materials/WaterInfo/DrawWaterInfo.DrawWaterInfo"),
                          ("UnderwaterPostProcessMaterial", "/Water/Materials/PostProcessing/M_UnderWater_PostProcess_Volume.M_UnderWater_PostProcess_Volume"),
                          ("WaterHLODMaterial", "/Water/Materials/HLOD/HLODWater.HLODWater"), ("bAffectsLandscape", False)):
            call("level", "set_water_body_property", {"actorLabel": a.label, "propertyName": prop, "value": val}, prop)
        for prop, v in (("Depth", a.depth_cm), ("RiverWidth", a.width_cm)):
            call("editor", "set_property", {"objectPath": path + ".WaterSplineMetadata", "propertyName": prop, "value": curve(v, n)}, prop)
        print("materials, landscape flag and metadata set")
        if a.hide_prefix:
            out = t.call("level", "get_outliner", {"nameFilter": a.hide_prefix, "limit": 400}, 120)
            labels = sorted(set(re.findall(r'"(?:actorLabel|label)":\s*"(%s[^"]*)"' % re.escape(a.hide_prefix), out)))
            if labels:
                call("level", "set_editor_visibility", {"hidden": True, "actorLabels": labels}, "hide")
            print("hidden", len(labels), "old ribbon actors")
    finally:
        t.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
