#!/usr/bin/env python3
"""watoom-texture-layering: make the sea floor drop away from the shore so the water gets deep and dark (host-side; numpy + pillow).

An island heightmap usually leaves the whole sea as one flat plateau a few cm above the sea level, so the water is zero deep
everywhere and the Water plugin's depth-based colour never darkens. This lowers the sea floor in a smooth ramp from the
waterline out to --ramp-m metres, then holds --deep-cm below sea level.

  unreal_ocean_depth.py --heights heightmap16_live_full.png --sea-cm 4849.26 --z0 3677.7 --raw-per-cm 4.4387 \
      --size-m 4000 --ramp-m 100 --deep-cm 1100 --out ocean_depth_calls.json --out-heights heightmap16_ocean_deep.png

--heights must be the heights that are IN THE EDITOR now (16 landscape.get_height_region tiles of 127 px pasted into one png).
Only sea is touched: pixels at or just above the sea level that are connected to the map edge. Land, beaches, inland lakes and
creek beds are never changed, and nothing is ever raised. The deepest possible floor is raw height 0 (z0), so --deep-cm is
capped at sea - z0 - --floor-margin-cm. Output: a `heights` phase of landscape.set_height_region tiles (changed tiles only).
"""
import argparse
import base64
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unreal_coast import dist_to, tiles  # noqa: E402
from os.path import abspath as _abspath, dirname as _dirname  # noqa: E402
sys.path.insert(0, _dirname(_abspath(__file__)))  # so `python3 -I script.py` finds ue_project
import ue_project  # noqa: E402


def edge_connected(low):
    """Pixels of `low` that are connected (4-neighbour) to the map edge through `low`."""
    seen = np.zeros_like(low)
    seen[0, :] = low[0, :]
    seen[-1, :] |= low[-1, :]
    seen[:, 0] |= low[:, 0]
    seen[:, -1] |= low[:, -1]
    while True:
        g = seen.copy()
        g[1:, :] |= seen[:-1, :]
        g[:-1, :] |= seen[1:, :]
        g[:, 1:] |= seen[:, :-1]
        g[:, :-1] |= seen[:, 1:]
        g &= low
        if (g == seen).all():
            return seen
        seen = g


def deepen(raw, sea_cm, z0, raw_per_cm, ramp_px, deep_cm=1100.0, floor_margin_cm=60.0, flat_tol_cm=40.0):
    """Returns (new uint16 heights, sea mask, achieved deep_cm)."""
    z = raw.astype(float) / raw_per_cm + z0
    sea = edge_connected(z < sea_cm + flat_tol_cm)
    deep = max(0.0, min(deep_cm, sea_cm - z0 - floor_margin_cm))
    d = dist_to(~sea)  # pixels from the nearest land pixel
    t = np.clip((d - 0.5) / max(ramp_px, 1e-6), 0.0, 1.0)
    depth = deep * t * t * (3.0 - 2.0 * t)
    new_z = np.where(sea, np.minimum(z, sea_cm - depth), z)
    new = np.clip(np.round((new_z - z0) * raw_per_cm), 0, 65535).astype(np.uint16)
    new = np.where(sea, np.minimum(new, raw), raw).astype(np.uint16)  # never raise
    return new, sea, deep


def calls_for(old_raw, new_raw, landscape="Landscape"):
    out = []
    for y0, y1, x0, x1 in tiles(old_raw.shape):
        blk = new_raw[y0:y1 + 1, x0:x1 + 1]
        if (blk != old_raw[y0:y1 + 1, x0:x1 + 1]).any():
            out.append(["landscape.set_height_region", {"actorLabel": landscape, "region": {"minX": x0, "minY": y0, "maxX": x1, "maxY": y1},
                                                        "heightsBase64": base64.b64encode(blk.astype("<u2").tobytes()).decode()}])
    return [{"name": "heights", "calls": out}]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--heights", required=True)
    ap.add_argument("--sea-cm", type=float, required=True)
    ap.add_argument("--z0", type=float, required=True)
    ap.add_argument("--raw-per-cm", type=float, required=True)
    ap.add_argument("--size-m", type=float, required=True, help="landscape width in metres (sets the pixel size)")
    ap.add_argument("--ramp-m", type=float, default=100.0, help="distance from the waterline to full depth")
    ap.add_argument("--deep-cm", type=float, default=1100.0)
    ap.add_argument("--floor-margin-cm", type=float, default=60.0)
    ap.add_argument("--landscape", required=True, help="landscape actor label (or set landscape in the --project profile)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--out-heights", required=True)
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    raw = np.asarray(Image.open(a.heights))
    px_m = a.size_m / (raw.shape[0] - 1)
    new, sea, deep = deepen(raw, a.sea_cm, a.z0, a.raw_per_cm, a.ramp_m / px_m, a.deep_cm, a.floor_margin_cm)
    Image.fromarray(new).save(a.out_heights)
    phases = calls_for(raw, new, a.landscape)
    json.dump({"phases": phases}, open(a.out, "w"))
    print("sea px %d, lowered %d px, ramp %.1f px (%.0f m), deepest %.0f cm below sea, wrote %s: %d tile calls"
          % (sea.sum(), (new != raw).sum(), a.ramp_m / px_m, a.ramp_m, deep, a.out, len(phases[0]["calls"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
