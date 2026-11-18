#!/usr/bin/env python3
"""Refit foliage to a carved creek through the ue-mcp route (driver for scripts/unreal_creek_foliage_fit.py in the watoom-texture-layering skill).

  ue_creek_foliage.py --spline creek1_points.json --new-heights heightmap16_creek_deep.png --z0 3677.7 --raw-per-cm 4.4387 --size-m 4000 [--apply]
  ue_creek_foliage.py --lake X,Y,Z,RADIUS_M [--lake ...] [--spline ...] --new-heights ... (a lake = its disc centre and water surface in world cm; --spline is optional)

Creeks and lakes in one run are planned together over the union of instances, so a tree touched by both is handled once (instance indices shift after a removal).

Reads every foliage instance in circles along the creek (foliage.get_instances), plans remove / refit / keep, prints the counts, and with --apply removes
the instances (one foliage.remove_instances per type) and adds the refitted ones back at the new ground height (foliage.add_instances). Without --apply
nothing is changed. If a removal fails it STOPS (nothing is re-added on top of instances that are still there, no further type is touched) and exits 1;
a failed re-add also exits 1. --apply first writes a removed-instances receipt (--out-removed, default creek_foliage_removed.json: type path,
index, location/rotation/scale of every instance it is about to remove, refitted or not), so a bad run can be put back with
foliage.add_instances from that file -- the engine has no undo for a removal. Re-adds go in batches of --add-batch (default 200).
RIG FAULT, FIXED (T-0061, 2026-11-19): every foliage add crashed the editor while the experimental MeshPartitionWater plugin was
enabled; it is disabled through tools/rig-ue-mcp/project_plugins.json (rig_project_plugins.py --apply). Before an --apply, a dry run of
rig_project_plugins.py must report that the rig matches; a crash still loses the unsaved removal (the saved level stays unchanged). After a stop, read the instances again (rerun the dry run) before applying: the indices have shifted. Run it AFTER the landscape carve was applied and BEFORE anything else edits the foliage (instance indices are only stable until then).
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "..", "..", "ansible", "roles", "watoom-code", "files", "skills", "watoom-texture-layering", "scripts")
sys.path.insert(0, HERE)
sys.path.insert(0, SKILL)
import ue_project  # noqa: E402
import ue_route  # noqa: E402
import unreal_creek_profile as cp  # noqa: E402
import unreal_creek_foliage_fit as ff  # noqa: E402


def j(text):
    return json.loads(text[text.index("{"):])


def batches(items, n):
    """Split a list into chunks of at most n (n < 1 means one chunk)."""
    n = n if n and n > 0 else max(len(items), 1)
    return [items[i:i + n] for i in range(0, len(items), n)]


def write_receipt(path, insts, remove):
    """Write every instance about to be removed (type, index, location, rotation, scale) before any removal call."""
    want = {(r["type"], r["index"]) for r in remove}
    rows = [{"type": i["type"], "index": i["index"], "location": {"x": i["x"], "y": i["y"], "z": i["z"]},
             "rotation": i["rotation"], "scale": i["scale"]} for i in insts if (i["type"], i["index"]) in want]
    with open(path, "w") as f:
        json.dump({"removed": rows}, f)
    return len(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spline", action="append", default=[], help="creek points json (repeatable)")
    ap.add_argument("--lake", action="append", default=[], metavar="X,Y,Z,RADIUS_M")
    ap.add_argument("--new-heights", required=True)
    ap.add_argument("--z0", type=float, required=True)
    ap.add_argument("--raw-per-cm", type=float, required=True)
    ap.add_argument("--size-m", type=float, required=True)
    ap.add_argument("--reach-m", type=float, default=42.0, help="distance from the creek line that the carve and rim can change")
    ap.add_argument("--lake-rim-m", type=float, default=30.0, help="how far past a lake's radius the rim can change the ground")
    ap.add_argument("--keep-depth-cm", type=float, default=150.0)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--add-batch", type=int, default=200, help="transforms per foliage.add_instances call (a 2031-instance call crashed the editor)")
    ap.add_argument("--out-removed", default="creek_foliage_removed.json", help="--apply: removed-instances receipt, written before any removal")
    ap.add_argument("--host", default="10.99.1.44")
    ap.add_argument("--port", type=int, default=2224)
    ap.add_argument("--user", default="uemcp")
    ap.add_argument("--key-dir", default=ue_route.DEFAULT_KEY_DIR)
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    raw = np.asarray(Image.open(a.new_heights))
    px_cm = a.size_m * 100.0 / (raw.shape[0] - 1)
    reach = a.reach_m * 100.0
    features = []  # (samples, reach_cm)
    centers = []
    for sp in a.spline:
        samples = cp.hermite(json.load(open(sp)), 120.0)
        features.append((samples, reach))
        last = None
        for c in samples[::40]:
            if last is None or np.hypot(c[0] - last[0], c[1] - last[1]) >= 5000:
                centers.append(c)
                last = c
    for spec in a.lake:
        x, y, z, r_m = [float(v) for v in spec.split(",")]
        rr = (r_m + a.lake_rim_m) * 100.0
        features.append((np.array([[x, y, z]]), rr))
        for gx in np.arange(x - rr, x + rr + 1, 5000.0):
            for gy in np.arange(y - rr, y + rr + 1, 5000.0):
                if np.hypot(gx - x, gy - y) <= rr + 2500:
                    centers.append(np.array([gx, gy, z]))
    t = ue_route.SshTransport(ue_route.ssh_command(a.host, a.port, a.user, a.key_dir))
    seen, insts = set(), []
    try:
        for c in centers:
            start = 0
            while True:
                d = j(t.call("foliage", "get_instances", {"center": {"x": float(c[0]), "y": float(c[1]), "z": float(c[2])}, "radius": 5600, "limit": 3000, "startIndex": start, "includeTransforms": True}, 240))
                for ty in d.get("types", []):
                    for it in ty.get("instances", []):
                        key = (ty["foliageTypePath"], it["index"])
                        if key in seen:
                            continue
                        seen.add(key)
                        insts.append({"type": ty["foliageTypePath"], "index": it["index"], "x": it["location"]["x"], "y": it["location"]["y"], "z": it["location"]["z"],
                                      "rotation": it["rotation"], "scale": it["scale"]})
                if not d.get("hasMore"):
                    break
                start += d.get("returned", 3000)
        pos = {(i["type"], i["index"]): (round(i["x"], 1), round(i["y"], 1)) for i in insts}
        rm, deep, refit = set(), set(), {}
        for smp, rch in features:
            p = ff.plan(insts, raw, a.z0, a.raw_per_cm, px_cm, smp, rch, a.keep_depth_cm)
            refit_pos = {(r["type"], round(r["location"]["x"], 1), round(r["location"]["y"], 1)) for r in p["add"]}
            for r in p["remove"]:
                key = (r["type"], r["index"])
                rm.add(key)
                if (key[0],) + pos[key] not in refit_pos:
                    deep.add(key)  # removed with no re-add: deep water, this feature wants it gone
            for r in p["add"]:
                refit[(r["type"], round(r["location"]["x"], 1), round(r["location"]["y"], 1))] = r
        deep_pos = {(k[0],) + pos[k] for k in deep}
        plan = {"remove": [{"type": t_, "index": i_} for t_, i_ in sorted(rm)],
                "add": [v for k, v in refit.items() if k not in deep_pos], "kept": len(insts) - len(rm)}
        by = {}
        for r in plan["remove"]:
            by.setdefault(r["type"], {"rm": [], "add": []})["rm"].append(r["index"])
        for r in plan["add"]:
            by.setdefault(r["type"], {"rm": [], "add": []})["add"].append({"location": r["location"], "rotation": r["rotation"], "scale": r["scale"]})
        print("instances read %d: remove %d (of which re-added %d), kept %d, types touched %d" % (len(insts), len(plan["remove"]), len(plan["add"]), plan["kept"], len(by)))
        for ty, v in sorted(by.items()):
            print("  %-60s remove %4d  re-add %4d" % (ty.split("/")[-1][:60], len(v["rm"]), len(v["add"])))
        if not a.apply:
            return 0
        write_receipt(a.out_removed, insts, plan["remove"])
        print("removed-instances receipt:", a.out_removed, flush=True)
        failures = 0
        for ty, v in by.items():
            if v["rm"]:
                r = t.call("foliage", "remove_instances", {"foliageTypePath": ty, "instanceIndices": sorted(v["rm"])}, 300)
                good = ue_route.reply_ok(r, getattr(t, "is_error", False))
                print("removed", ty.split("/")[-1], "ok" if good else "FAILED " + r[:200], flush=True)
                if not good:
                    failures += 1
                    print("stopped: nothing re-added for this type and later types left untouched; rerun the dry run before applying again", flush=True)
                    break   # never re-add on top of instances that were not removed: that would duplicate them
            for b in batches(v["add"], a.add_batch):
                r = t.call("foliage", "add_instances", {"foliageTypePath": ty, "transforms": b, "projectToGround": False, "applyTypeRules": False, "skipCollision": True}, 300)
                good = ue_route.reply_ok(r, getattr(t, "is_error", False))
                print("added  ", ty.split("/")[-1], len(b), "ok" if good else "FAILED " + r[:200], flush=True)
                if not good:
                    failures += 1
                    break
    finally:
        t.close()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
