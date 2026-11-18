#!/usr/bin/env python3
"""watoom-texture-layering: put buildings and props on the ground (host-side; numpy + pillow).

A placed building floats or sinks when its height is set from one point, because the ground under a footprint is not flat and
because actor-level bounds include lights, smoke and other parts that are not the building. This script works from the real
mesh bounds instead:

  1. the base of a building is its body / base / foundation meshes (the lowest of those, not the lowest part such as a barrel on a porch),
  2. the footprint is the union of those meshes' x/y bounds,
  3. the ground level is the mean landscape height under the footprint (from the heightmap currently in the editor),
  4. the terrain under the footprint is flattened to that level with a smooth falloff (landscape.set_height_region tiles),
  5. the building is moved vertically (level.batch_translate) so its base sits 2 cm into the pad.

  unreal_ground_fit.py --components building_components.json --ue-dir ue --heights heightmap16_creeks.png \
      --size-m 4000 --z0 3677.7 --raw-per-cm 4.4387 --out ground_fit.json

building_components.json: {"<actor label>": [{"name": "SM_BLD_body_v02_01", "o": {x,y,z}, "e": {x,y,z}}, ...]} where o / e are
boundsOrigin / boundsBoxExtent of the StaticMeshComponents from level.get_component_tree (read it with a large output limit:
a house tree is tens of kB). Run the phases in order: `pad` (save the level after), then `move`. The new heights are written
to heightmap16_pads.png: use it as the baseline of the next terrain edit.
"""
import argparse
import base64
import json
import math
import os
import sys

import numpy as np
from PIL import Image
from os.path import abspath as _abspath, dirname as _dirname  # noqa: E402
sys.path.insert(0, _dirname(_abspath(__file__)))  # so `python3 -I script.py` finds ue_project
import ue_project  # noqa: E402

BASE_KEYS = ("body", "base", "found")


def base_parts(comps, keys=BASE_KEYS):
    parts = [c for c in comps if any(k in c["name"].lower() for k in keys)]
    return parts or list(comps)


def fit(components, heights, size_m, z0, raw_per_cm, keys=BASE_KEYS, margin_px=1.0, falloff_px=3.0, sink_cm=2.0, min_range_cm=15.0, tile=127):
    """heights: N x N uint16 array (the heightmap now in the editor). Returns {moves, pad, report, heights}."""
    img = np.asarray(heights).astype(float)
    n = img.shape[0]
    cm = size_m * 100.0 / (n - 1)
    zcm = img / raw_per_cm + z0
    new = img.copy()
    yy, xx = np.mgrid[0:n, 0:n]
    moves, report = [], []
    for label, comps in components.items():
        if not comps:
            report.append({"label": label, "skipped": "no mesh components"})
            continue
        parts = base_parts(comps, keys)
        bottom = min(c["o"]["z"] - c["e"]["z"] for c in parts)
        x0 = min(c["o"]["x"] - c["e"]["x"] for c in parts) / cm
        x1 = max(c["o"]["x"] + c["e"]["x"] for c in parts) / cm
        y0 = min(c["o"]["y"] - c["e"]["y"] for c in parts) / cm
        y1 = max(c["o"]["y"] + c["e"]["y"] for c in parts) / cm
        iy0, iy1 = max(0, int(math.floor(y0 - margin_px))), min(n - 1, int(math.ceil(y1 + margin_px)))
        ix0, ix1 = max(0, int(math.floor(x0 - margin_px))), min(n - 1, int(math.ceil(x1 + margin_px)))
        ground = zcm[iy0:iy1 + 1, ix0:ix1 + 1]
        rng = float(ground.max() - ground.min())
        target = float(ground.mean())
        entry = {"label": label, "bottom_cm": bottom, "ground_min_cm": float(ground.min()), "ground_mean_cm": target,
                 "ground_max_cm": float(ground.max()), "range_cm": rng, "padded": False}
        if rng >= min_range_cm:
            ry0, ry1, rx0, rx1 = int(max(0, iy0 - falloff_px - 1)), int(min(n, iy1 + falloff_px + 2)), int(max(0, ix0 - falloff_px - 1)), int(min(n, ix1 + falloff_px + 2))
            dy = np.maximum(np.maximum(iy0 - yy[ry0:ry1, rx0:rx1], yy[ry0:ry1, rx0:rx1] - iy1), 0)
            dx = np.maximum(np.maximum(ix0 - xx[ry0:ry1, rx0:rx1], xx[ry0:ry1, rx0:rx1] - ix1), 0)
            d = np.hypot(dy, dx)
            w = np.where(d <= 0, 1.0, np.clip(1.0 - d / falloff_px, 0, 1))
            w = 0.5 - 0.5 * np.cos(np.pi * w)
            tgt_raw = (target - z0) * raw_per_cm
            new[ry0:ry1, rx0:rx1] = new[ry0:ry1, rx0:rx1] * (1 - w) + tgt_raw * w
            entry["padded"] = True
        dz = target - sink_cm - bottom
        entry["move_dz_cm"] = dz
        report.append(entry)
        if abs(dz) > 0.5:
            moves.append(["level.batch_translate", {"actorLabels": [label], "offset": {"x": 0, "y": 0, "z": float(dz)}}])
    new16 = np.clip(np.round(new), 0, 65535).astype(np.uint16)
    old16 = np.clip(np.round(img), 0, 65535).astype(np.uint16)
    pad = []
    for y0 in range(0, n, tile):
        for x0 in range(0, n, tile):
            y1, x1 = min(n - 1, y0 + tile - 1), min(n - 1, x0 + tile - 1)
            blk = new16[y0:y1 + 1, x0:x1 + 1]
            if (blk != old16[y0:y1 + 1, x0:x1 + 1]).any():
                pad.append(["landscape.set_height_region", {"region": {"minX": x0, "minY": y0, "maxX": x1, "maxY": y1},
                                                             "heightsBase64": base64.b64encode(blk.astype("<u2").tobytes()).decode()}])
    return {"report": report, "phases": [{"name": "pad", "calls": pad}, {"name": "move", "calls": moves}], "heights": new16}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--components", required=True)
    ap.add_argument("--ue-dir", required=True)
    ap.add_argument("--heights", default="heightmap16_creeks.png", help="heightmap png currently in the editor (inside --ue-dir)")
    ap.add_argument("--size-m", type=float, required=True)
    ap.add_argument("--z0", type=float, required=True)
    ap.add_argument("--raw-per-cm", type=float, required=True)
    ap.add_argument("--falloff-px", type=float, default=3.0)
    ap.add_argument("--out", required=True)
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    comps = json.load(open(a.components))
    img = np.asarray(Image.open(os.path.join(a.ue_dir, a.heights)))
    out = fit(comps, img, a.size_m, a.z0, a.raw_per_cm, falloff_px=a.falloff_px)
    Image.fromarray(out.pop("heights")).save(os.path.join(a.ue_dir, "heightmap16_pads.png"))
    json.dump(out, open(a.out, "w"))
    for r in out["report"]:
        print("%-14s base %7.0f ground %7.0f..%7.0f mean %7.0f  move %+7.1f cm%s" % (r["label"], r.get("bottom_cm", 0), r.get("ground_min_cm", 0), r.get("ground_max_cm", 0),
              r.get("ground_mean_cm", 0), r.get("move_dz_cm", 0), "  (pad)" if r.get("padded") else ""))
    print("wrote %s: %s" % (a.out, ", ".join("%s=%d" % (p["name"], len(p["calls"])) for p in out["phases"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
