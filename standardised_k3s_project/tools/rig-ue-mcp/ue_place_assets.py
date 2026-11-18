#!/usr/bin/env python3
"""Place imported meshes in the level from a manifest, sit them on the ground, clear trees under them, save (ue-mcp route; stdlib + numpy + pillow).

  ue_place_assets.py manifest.json --heights heightmap16_live_full.png --z0 3677.7 --raw-per-cm 4.4387 --size-m 4000 [--dry-run]

manifest.json is a list of items:
  {"label": "ZAS_Lighthouse", "kind": "static" | "skeletal", "asset": "/Game/ZAS/Landmarks/SM_Lighthouse.SM_Lighthouse",
   "x": 138095, "y": 74603, "scale": 60, "rotation": {"pitch": 0, "yaw": 0, "roll": 90},   (rotation optional, default 0)
   "sink_cm": 30,                    (how far the lowest point goes below the ground; default 20)
   "clear_foliage_cm": 1800}         (optional: remove foliage instances within this radius of x,y)
Steps per item (re-runnable: an existing actor with the label is reused and moved): ground Z = bilinear sample of the heights png (world x/y cm,
pixel = x / (size_m*100/(rows-1))); place_actor StaticMeshActor (staticMesh) or SkeletalMeshActor (then set_component_property
SkeletalMeshComponent0.SkeletalMeshAsset); level.get_actor_bounds; move the actor up/down so the lowest point of the bounds sits `sink_cm` below the ground.
Lessons: GLB (Interchange) imports land in subfolders (/Game/.../model/StaticMeshes/NAME): list the folder with asset.list and use the real path or the actor
gets an empty mesh (bounds extent 0). OBJ files are Y-up: roll 90 stands them up. Skeletal FBX with millions of triangles needs LODs
(asset.generate_skeletal_mesh_lods). Import with asset.import_static_mesh / import_skeletal_mesh from the rig path (the Epic vault is C:\\ProgramData\\Epic\\EpicGamesLauncher\\VaultCache\\FabLibrary\\<name>-<id8>), one call per
file (a skeletal import can exceed the 30 s bridge timeout: the asset is usually still created, check asset.list).
Finish with level.save and asset.save_all_dirty (done here unless --no-save). If any step failed (place, mesh assignment, move, empty
bounds, foliage removal) it does NOT save and exits 1, so a half-placed level is never written; --force-save saves anyway. A failed save exits 1.
The manifest and the heights png go through ue_asset_check.py first (dry run included): a missing field, a duplicate label, a zero or NaN scale,
a malformed asset path or a heights file that is not a 16-bit PNG exits 1 before anything is sent to the editor.
"""
import argparse
import json
import os
import re
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_route  # noqa: E402
import ue_asset_check  # noqa: E402
HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "..", "..", "ansible", "roles", "watoom-code", "files", "skills", "watoom-texture-layering", "scripts")
sys.path.insert(0, SKILL)
import ue_project  # noqa: E402


def ground_z(raw, x, y, z0, raw_per_cm, px_cm):
    n, m = raw.shape
    gx, gy = min(max(x / px_cm, 0), m - 1.001), min(max(y / px_cm, 0), n - 1.001)
    j, i = int(gx), int(gy)
    fx, fy = gx - j, gy - i
    v = raw[i, j] * (1 - fx) * (1 - fy) + raw[i, j + 1] * fx * (1 - fy) + raw[i + 1, j] * (1 - fx) * fy + raw[i + 1, j + 1] * fx * fy
    return float(v) / raw_per_cm + z0


def actor_z_for_bottom(actor_z, bounds_origin_z, bounds_extent_z, ground, sink_cm):
    """New actor Z so that the lowest point of the bounds (origin - extent) is sink_cm below the ground."""
    bottom = bounds_origin_z - bounds_extent_z
    return actor_z + (ground - sink_cm - bottom)


def j(text):
    m = re.search(r"\{", text)
    return json.loads(text[m.start():]) if m else {}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifest")
    ap.add_argument("--heights", required=True)
    ap.add_argument("--z0", type=float, required=True)
    ap.add_argument("--raw-per-cm", type=float, required=True)
    ap.add_argument("--size-m", type=float, required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--force-save", action="store_true", help="save the level even when a step failed (default: stop before saving and exit 1)")
    ap.add_argument("--host", default="10.99.1.44")
    ap.add_argument("--port", type=int, default=2224)
    ap.add_argument("--user", default="uemcp")
    ap.add_argument("--key-dir", default=ue_route.DEFAULT_KEY_DIR)
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    if ue_asset_check.gate(ue_asset_check.check_manifest(a.manifest, size_m=a.size_m) + ue_asset_check.check_heights(a.heights), a.manifest):
        return 1
    items = json.load(open(a.manifest))
    raw = np.asarray(Image.open(a.heights)).astype(float)
    px_cm = a.size_m * 100.0 / (raw.shape[0] - 1)
    plan = []
    for it in items:
        g = ground_z(raw, it["x"], it["y"], a.z0, a.raw_per_cm, px_cm)
        plan.append((it, g))
        print("%-24s %-8s x=%.0f y=%.0f ground=%.0f scale=%s" % (it["label"], it.get("kind", "static"), it["x"], it["y"], g, it.get("scale", 1)))
    if a.dry_run:
        return 0
    t = ue_route.SshTransport(ue_route.ssh_command(a.host, a.port, a.user, a.key_dir))
    failed = []

    def bad(r):
        return ue_route.reply_failed(r, getattr(t, "is_error", False))
    try:
        for it, g in plan:
            lab, kind = it["label"], it.get("kind", "static")
            s = it.get("scale", 1)
            sc = s if isinstance(s, dict) else {"x": s, "y": s, "z": s}
            rot = it.get("rotation", {"pitch": 0, "yaw": 0, "roll": 0})
            have = t.call("level", "get_actor_details", {"actorLabel": lab}, 60)
            args = {"actorClass": "SkeletalMeshActor" if kind == "skeletal" else "StaticMeshActor", "label": lab, "location": {"x": it["x"], "y": it["y"], "z": g + 100},
                    "rotation": rot, "scale": sc, "onConflict": "fail"}
            if kind != "skeletal":
                args["staticMesh"] = it["asset"]
            if not ue_route.reply_ok(have):
                r = t.call("level", "place_actor", args, 120)
                if not ue_route.reply_ok(r, getattr(t, "is_error", False)):
                    print("  FAILED place:", r[:200])
                    failed.append(lab)
                    continue
                if kind == "skeletal":
                    r = t.call("level", "set_component_property", {"actorLabel": lab, "componentName": "SkeletalMeshComponent0", "propertyName": "SkeletalMeshAsset", "value": it["asset"]}, 120)
                    if bad(r):
                        print("  FAILED set skeletal mesh:", r[:200])
                        failed.append(lab)
                        continue
            else:
                r = t.call("level", "move_actor", {"actorLabel": lab, "location": args["location"], "rotation": rot, "scale": sc}, 60)
                if bad(r):
                    print("  FAILED move:", r[:200])
                    failed.append(lab)
                    continue
            b = j(t.call("level", "get_actor_bounds", {"actorLabel": lab}, 60))
            if not b.get("success") or b["extent"]["z"] == 0:
                print("  %s: bounds are empty: the mesh path is probably wrong (%s)" % (lab, it["asset"]))
                failed.append(lab)
                continue
            nz = actor_z_for_bottom(g + 100, b["origin"]["z"], b["extent"]["z"], g, it.get("sink_cm", 20))
            r = t.call("level", "move_actor", {"actorLabel": lab, "location": {"x": it["x"], "y": it["y"], "z": nz}}, 60)
            if bad(r):
                print("  FAILED final move:", r[:200])
                failed.append(lab)
                continue
            print("  %s placed: ground %.0f, actor z %.0f, extent %s" % (lab, g, nz, {k: round(v) for k, v in b["extent"].items()}))
            rad = it.get("clear_foliage_cm")
            if rad:
                d = j(t.call("foliage", "get_instances", {"center": {"x": it["x"], "y": it["y"], "z": g}, "radius": rad, "limit": 3000, "includeTransforms": False}, 300))
                removed = 0
                for ty in d.get("types", []):
                    idx = sorted(i["index"] for i in ty.get("instances", []))
                    if idx:
                        r = t.call("foliage", "remove_instances", {"foliageTypePath": ty["foliageTypePath"], "instanceIndices": idx}, 300)
                        if bad(r):
                            print("  FAILED foliage removal:", r[:200])
                            failed.append(lab)
                            continue
                        removed += len(idx)
                print("  removed %d foliage instances within %.0f cm" % (removed, rad))
        if failed and not a.force_save:
            print("NOT saving: %d step(s) failed (%s). Fix them and rerun, or pass --force-save." % (len(failed), ", ".join(sorted(set(failed)))))
            return 1
        if not a.no_save:
            for cat, meth, args in (("level", "save", {}), ("asset", "save_all_dirty", {"saveMapPackages": False, "saveContentPackages": True})):
                r = t.call(cat, meth, args, 300)
                if bad(r):
                    print("FAILED %s.%s: %s" % (cat, meth, r[:200]))
                    return 1
            print("saved")
        if failed:
            return 1   # saved on request (--force-save) but steps failed
    finally:
        t.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
