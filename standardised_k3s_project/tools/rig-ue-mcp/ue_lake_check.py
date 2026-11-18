#!/usr/bin/env python3
"""Read-only health check of a carved lake's landscape bed (driver, stdlib only). Run it after every lake carve, clear or recovery.

  ue_lake_check.py --lake ZAS_LakeBody_3,133922.2,100764.6,8860,4043 [--lake ...] [--lakes lakes.json] [--json]

A lake is LABEL,X,Y,WATER_Z,RADIUS_CM (world cm, the same numbers ue_lake_as_waterbody.py takes), or --lakes FILE with a json list of
{"label", "x", "y", "water_z", "radius_cm"}. It reads the carve rectangle (the exact one carve_lake_bank writes, via lake_region) plus
--pad vertices around it (merged = the visible height, plus the Water and base layers), and reports the failure signatures found live on T-0049:

  FINDINGS (exit 1):
  sea_clamp           vertices whose merged height is raw 0, the absolute floor -- the additive-layer corruption pulls a bed there
  water_outside_ring  Water-layer values that are not neutral (32768) beyond radius + bank, where a carve never writes anything but
                      neutral -- leftover offsets from an older or buggy write
  seam                a height step across the carve rectangle's border much larger than the steps just outside it -- the visible
                      "square depression/dugout" where corrupted written vertices meet untouched ones
  dry_inside          ground above the water level inside the circle -- grass or dirt showing through the water
  missing_actor       the water body label is not in the level (or not a WaterBodyLake)
  WARNINGS (exit 0):
  layer_read_mismatch base + Water disagrees with the merged read. The merged read is the visible height and is what every check
                      uses; on this map the editLayer:"Layer" read is wrong along whole vertex lines (x=126 and y=126), so a
                      mismatch there is the read fault, not a terrain problem -- never build heights from the base read
  deep_inside         bed more than --max-depth-cm below the water inside the circle

A carve reporting "0 of N vertices changed" is NOT proof of a clean bed: it also happens when the bed is already (wrongly) below the
target. Use this check instead. It does not judge the water surface itself (clipping, height vs. the creek) -- that needs captures from
several angles and distances (ue_viewport_shot.py --around).
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_route  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "ansible", "roles", "watoom-code",
                                "files", "skills", "watoom-texture-layering", "scripts"))
import ue_project  # noqa: E402
from ue_lake_as_river import PX_CM_DEFAULT, WATER_LAYER_MID, lake_region, read_layers  # noqa: E402

FINDINGS = ("sea_clamp", "water_outside_ring", "seam", "dry_inside", "missing_actor")


def parse_lake(spec):
    parts = spec.split(",")
    if len(parts) != 5:
        raise ValueError("--lake wants LABEL,X,Y,WATER_Z,RADIUS_CM: %r" % spec)
    return {"label": parts[0], "x": float(parts[1]), "y": float(parts[2]), "water_z": float(parts[3]), "radius_cm": float(parts[4])}


def padded(region, pad, max_vertex=504):
    return {"minX": max(region["minX"] - pad, 0), "minY": max(region["minY"] - pad, 0),
            "maxX": min(region["maxX"] + pad, max_vertex), "maxY": min(region["maxY"] + pad, max_vertex)}


def analyse(lake, carve, read, lay, px_cm, bank_cm, seam_cm=400.0, seam_ratio=2.5, max_depth_cm=2500.0):
    """Pure check of one lake. carve = the rectangle carve_lake_bank writes; read = the (padded) rectangle `lay` covers.
    Returns {"findings": {name: detail}, "warnings": {name: detail}, "stats": {...}}."""
    w, h, rpc, z0 = lay["w"], lay["h"], lay["rpc"], lay["z0"]
    cx, cy, wz, r = lake["x"], lake["y"], lake["water_z"], lake["radius_cm"]
    z = [m / rpc + z0 for m in lay["merged"]]

    def at(vx, vy):
        return (vy - read["minY"]) * w + (vx - read["minX"])

    def inside_carve(vx, vy):
        return carve["minX"] <= vx <= carve["maxX"] and carve["minY"] <= vy <= carve["maxY"]

    clamp, outside_water, dry, stale, deepest = [], [], [], 0, None
    for i in range(h):
        for j in range(w):
            k = i * w + j
            vx, vy = read["minX"] + j, read["minY"] + i
            dist = math.hypot(vx * px_cm - cx, vy * px_cm - cy)
            if lay["merged"][k] == 0:
                clamp.append((vx, vy))
            if dist > r + bank_cm and lay["water"][k] != WATER_LAYER_MID:
                outside_water.append((vx, vy, lay["water"][k]))
            if dist <= r:
                if z[k] > wz:
                    dry.append((vx, vy, round(z[k] - wz, 1)))
                depth = wz - z[k]
                deepest = depth if deepest is None else max(deepest, depth)
            if abs(lay["computed"][k] - lay["merged"][k]) > 1:
                stale += 1

    # step across the carve rectangle's border vs. steps between neighbouring vertices just outside it
    border, outside = [], []
    for i in range(h):
        for j in range(w):
            vx, vy = read["minX"] + j, read["minY"] + i
            for dx, dy in ((1, 0), (0, 1)):
                nx, ny = vx + dx, vy + dy
                if nx > read["maxX"] or ny > read["maxY"]:
                    continue
                step = abs(z[at(vx, vy)] - z[at(nx, ny)])
                a, b = inside_carve(vx, vy), inside_carve(nx, ny)
                if a != b:
                    border.append((step, (vx, vy), (nx, ny)))
                elif not a and not b:
                    outside.append(step)
    border_max = max(border) if border else (0.0, None, None)
    outside_max = max(outside) if outside else 0.0
    seam = border_max[0] > max(seam_cm, seam_ratio * outside_max)

    findings, warnings = {}, {}
    if clamp:
        findings["sea_clamp"] = {"count": len(clamp), "sample": clamp[:5]}
    if outside_water:
        findings["water_outside_ring"] = {"count": len(outside_water), "sample": outside_water[:5]}
    if seam:
        findings["seam"] = {"border_step_cm": round(border_max[0], 1), "at": [border_max[1], border_max[2]],
                            "largest_step_outside_cm": round(outside_max, 1)}
    if dry:
        findings["dry_inside"] = {"count": len(dry), "sample": dry[:5]}
    if stale:
        warnings["layer_read_mismatch"] = {"count": stale}
    if deepest is not None and deepest > max_depth_cm:
        warnings["deep_inside"] = {"deepest_cm": round(deepest, 1)}
    return {"findings": findings, "warnings": warnings,
            "stats": {"vertices": w * h, "deepest_cm": None if deepest is None else round(deepest, 1),
                      "border_step_cm": round(border_max[0], 1), "largest_step_outside_cm": round(outside_max, 1)}}


def check_lake(call, landscape, lake, px_cm, bank_cm, pad, **kw):
    have = call("level", "get_actor_details", {"actorLabel": lake["label"]}, "get_actor_details", fail_ok=True)
    carve, used_bank = lake_region(lake["x"], lake["y"], lake["radius_cm"], px_cm, bank_cm)
    read = padded(carve, pad)
    res = analyse(lake, carve, read, read_layers(call, landscape, read), px_cm, used_bank, **kw)
    if not ue_route.reply_ok(have) or '"WaterBodyLake"' not in have:
        res["findings"]["missing_actor"] = {"label": lake["label"]}
    res["carve_region"] = carve
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lake", action="append", default=[], metavar="LABEL,X,Y,WATER_Z,RADIUS_CM")
    ap.add_argument("--lakes", default=None, metavar="FILE")
    ap.add_argument("--landscape", default="ZAS_Landscape", help="landscape actor label (or landscape in the --project profile)")
    ap.add_argument("--px-cm", type=float, default=PX_CM_DEFAULT)
    ap.add_argument("--bank-cm", type=float, default=350.0, help="the --bank-cm the lake was carved with (floored to 2 vertex spacings)")
    ap.add_argument("--pad", type=int, default=2, help="vertices read around the carve rectangle, for the seam check")
    ap.add_argument("--seam-cm", type=float, default=400.0)
    ap.add_argument("--max-depth-cm", type=float, default=2500.0)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--host", default="10.99.1.44")
    ap.add_argument("--port", type=int, default=2224)
    ap.add_argument("--user", default="uemcp")
    ap.add_argument("--key-dir", default=ue_route.DEFAULT_KEY_DIR)
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    lakes = [parse_lake(s) for s in a.lake]
    if a.lakes:
        lakes += [{"label": k["label"], "x": float(k["x"]), "y": float(k["y"]), "water_z": float(k["water_z"]),
                   "radius_cm": float(k["radius_cm"])} for k in json.load(open(a.lakes))]
    if not lakes:
        ap.error("give at least one --lake or a --lakes file")

    t = ue_route.SshTransport(ue_route.ssh_command(a.host, a.port, a.user, a.key_dir))

    def call(cat, meth, args, what, timeout=180, fail_ok=False):
        r = t.call(cat, meth, args, timeout)
        if not fail_ok and ue_route.reply_failed(r, getattr(t, "is_error", False)):
            raise SystemExit("FAILED %s: %s" % (what, r[:400]))
        return r

    out, bad = {}, 0
    try:
        for lake in lakes:
            res = check_lake(call, a.landscape, lake, a.px_cm, a.bank_cm, a.pad, seam_cm=a.seam_cm, max_depth_cm=a.max_depth_cm)
            out[lake["label"]] = res
            bad += bool(res["findings"])
    finally:
        t.close()
    if a.json:
        print(json.dumps(out, indent=1))
    else:
        for label, res in out.items():
            state = "BAD" if res["findings"] else "ok"
            print("%-16s %s  deepest %s cm, border step %s cm (largest outside %s cm)" % (
                label, state, res["stats"]["deepest_cm"], res["stats"]["border_step_cm"], res["stats"]["largest_step_outside_cm"]))
            for name, detail in res["findings"].items():
                print("  FINDING %s: %s" % (name, json.dumps(detail)))
            for name, detail in res["warnings"].items():
                print("  warning %s: %s" % (name, json.dumps(detail)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
