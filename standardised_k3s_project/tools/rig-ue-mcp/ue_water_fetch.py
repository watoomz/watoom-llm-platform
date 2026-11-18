#!/usr/bin/env python3
"""Read every water body in the open level into one json (read-only; the `--water` input of unreal_water_berms.py).

  ue_water_fetch.py --out water.json [--project FILE]

Writes {"sea_z": Z, "creeks": [{"label", "points": [[x, y, z], ...], "widths_cm": [...]}],
        "lakes": [{"label", "x", "y", "water_z", "radius_cm"}]}
- creeks: every WaterBodyRiver -- its WaterSpline world points (z = the water level) and its RiverWidth curve (full width, one value
  per spline point, read from the body's WaterSplineMetadata with editor.get_property; a missing point repeats the last value).
- lakes: every WaterBodyLake -- centre and radius from its circle spline (ue_lake_as_waterbody.py writes a uniform circle), water level
  from its points' z. The `lakes` list is also a valid ue_lake_check.py --lakes file.
- sea_z: the WaterBodyOcean actor's Z (the sea surface).
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_route  # noqa: E402
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "ansible", "roles", "watoom-code", "files", "skills", "watoom-texture-layering", "scripts"))
import ue_project  # noqa: E402


def as_json(reply):
    return json.loads(reply[reply.index("{"):])


def widths(curve, n):
    """RiverWidth FInterpCurveFloat -> one width per spline point (InVal = point index)."""
    pts = sorted(curve.get("Points", []), key=lambda p: p.get("InVal", 0))
    if not pts:
        return None
    out, k = [], 0
    for i in range(n):
        while k + 1 < len(pts) and pts[k + 1].get("InVal", 0) <= i:
            k += 1
        out.append(float(pts[k]["OutVal"]))
    return out


def fetch(call):
    state = as_json(call("level", "get_water_state", {}, "get_water_state"))
    out = {"sea_z": None, "creeks": [], "lakes": []}
    for b in state.get("bodies", []):
        label, cls, path = b["actorLabel"], b.get("componentClass", ""), b["actorPath"]
        if "Ocean" in cls:
            out["sea_z"] = as_json(call("level", "get_actor_details", {"actorLabel": label}, "ocean details"))["location"]["z"]
            continue
        if "River" not in cls and "Lake" not in cls:
            continue
        info = as_json(call("level", "get_spline_info", {"actorLabel": label, "componentName": "WaterSpline"}, "spline " + label))
        pts = [[p["worldLocation"]["x"], p["worldLocation"]["y"], p["worldLocation"]["z"]] for p in info["points"]]
        if "River" in cls:
            w = as_json(call("editor", "get_property", {"objectPath": path + ".WaterSplineMetadata", "propertyName": "RiverWidth"},
                             "RiverWidth " + label))
            out["creeks"].append({"label": label, "points": pts, "widths_cm": widths(w.get("value", {}), len(pts))})
        else:
            cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
            out["lakes"].append({"label": label, "x": round(cx, 2), "y": round(cy, 2), "water_z": pts[0][2],
                                 "radius_cm": round(sum(math.hypot(p[0] - cx, p[1] - cy) for p in pts) / len(pts), 1)})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--host", default="10.99.1.44")
    ap.add_argument("--port", type=int, default=2224)
    ap.add_argument("--user", default="uemcp")
    ap.add_argument("--key-dir", default=ue_route.DEFAULT_KEY_DIR)
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    t = ue_route.SshTransport(ue_route.ssh_command(a.host, a.port, a.user, a.key_dir))

    def call(cat, meth, args, what, timeout=120):
        r = t.call(cat, meth, args, timeout)
        if ue_route.reply_failed(r, getattr(t, "is_error", False)):
            raise SystemExit("FAILED %s: %s" % (what, r[:400]))
        return r
    try:
        water = fetch(call)
    finally:
        t.close()
    json.dump(water, open(a.out, "w"), indent=1)
    print("wrote %s: %d creek(s), %d lake(s), sea_z %s" % (a.out, len(water["creeks"]), len(water["lakes"]), water["sea_z"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
