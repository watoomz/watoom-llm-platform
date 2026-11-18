#!/usr/bin/env python3
"""watoom-texture-layering: keep the sea out of the land and ring the island with a sand beach (host-side; numpy + pillow).

Two faults show up after an island is carved and creeks are cut:
  1. the flat sea plane appears inland wherever the land was left below the sea level (bays, lakes, flat coastal plain);
  2. the shore is the same colour as the rest of the land, so there is no beach.

  unreal_coast.py --heights heightmap16_live_full.png --under island_under.u8 --cliff island_cliff.u8 --layers-dir with_creeks \
      --sea-cm 4849.26 --z0 3677.7 --raw-per-cm 4.4387 --out coast_calls.json --out-layers coast_layers

--heights must be the heights that are IN THE EDITOR now (read them with landscape.get_height_region in 127-pixel tiles; village
pads and creek carves are only there), --under is the island's sea mask (255 = sea), --cliff the cliff mask. Phases written:
`heights` (landscape.set_height_region tiles, changed ones only) and `paint` (landscape.set_layer_weight_region for all layers in
every tile the beach touches; every pixel's weights still sum to 255). Land below sea + --min-above-cm is raised to that level and
smoothed; sand weight ramps from 1 at the water line to 0 --beach-px pixels inland, but not on cliffs.
"""
import argparse
import base64
import json
import os
import sys

import numpy as np
from PIL import Image
from os.path import abspath as _abspath, dirname as _dirname  # noqa: E402
sys.path.insert(0, _dirname(_abspath(__file__)))  # so `python3 -I script.py` finds ue_project
import ue_project  # noqa: E402

LAYERS = ("sand", "grass", "dirt", "rock", "stone", "mud", "dry_grass")


def dist_to(mask, iters=None):
    """Chamfer (3-4) distance in pixels from every pixel to the nearest True pixel of mask."""
    n, m = mask.shape
    big = 1e9
    d = np.where(mask, 0.0, big)
    for _ in range(2):
        for y in range(n):
            if y:
                d[y] = np.minimum(d[y], d[y - 1] + 1)
                d[y, 1:] = np.minimum(d[y, 1:], d[y - 1, :-1] + 1.4142)
                d[y, :-1] = np.minimum(d[y, :-1], d[y - 1, 1:] + 1.4142)
            for x in range(1, m):
                d[y, x] = min(d[y, x], d[y, x - 1] + 1)
        for y in range(n - 1, -1, -1):
            if y < n - 1:
                d[y] = np.minimum(d[y], d[y + 1] + 1)
                d[y, 1:] = np.minimum(d[y, 1:], d[y + 1, :-1] + 1.4142)
                d[y, :-1] = np.minimum(d[y, :-1], d[y + 1, 1:] + 1.4142)
            for x in range(m - 2, -1, -1):
                d[y, x] = min(d[y, x], d[y, x + 1] + 1)
    return d


def box3(a):
    p = np.pad(a, 1, mode="edge")
    return sum(p[i:i + a.shape[0], j:j + a.shape[1]] for i in range(3) for j in range(3)) / 9.0


def raise_land(raw, sea_mask, sea_cm, z0, raw_per_cm, min_above_cm=150.0):
    """Land (not sea_mask) below sea + min_above_cm is raised to it, then blended with a 3x3 mean. Returns uint16 array."""
    z = raw.astype(float) / raw_per_cm + z0
    land = ~sea_mask
    floor = sea_cm + min_above_cm
    low = land & (z < floor)
    base = np.where(low, floor, z)  # land is never lowered and never left under the floor
    near = land & (box3(low.astype(float)) > 0)
    new = np.where(near, np.maximum(box3(box3(base)), base), base)
    new = np.where(land, new, z)
    return np.clip(np.round((new - z0) * raw_per_cm), 0, 65535).astype(np.uint16)


def beach_weight(sea_mask, cliff, beach_px=10.0):
    d = dist_to(sea_mask)
    w = np.clip(1.0 - (d - 1.0) / beach_px, 0.0, 1.0) ** 0.8
    w = np.where(sea_mask, 0.0, w)
    return w * (1.0 - np.asarray(cliff, float) / 255.0)


def repaint(layers, w):
    """layers: {name: float 0..1 (sum 1)}. Sand becomes max(sand, w); the other layers shrink to keep the sum 1. Returns uint8 arrays summing to 255."""
    sand = layers["sand"]
    new_sand = np.maximum(sand, w)
    rest = sum(v for k, v in layers.items() if k != "sand")
    scale = np.where(rest > 1e-6, (1.0 - new_sand) / np.maximum(rest, 1e-6), 0.0)
    out = {"sand": new_sand}
    for k, v in layers.items():
        if k != "sand":
            out[k] = v * scale
    names = list(out)
    q = {k: np.round(out[k] * 255).astype(int) for k in names}
    tot = sum(q.values())
    big = np.argmax(np.stack([q[k] for k in names]), axis=0)
    for i, k in enumerate(names):
        q[k] = q[k] + np.where(big == i, 255 - tot, 0)
    return {k: np.clip(q[k], 0, 255).astype(np.uint8) for k in names}


def tiles(shape, tile=127):
    n, m = shape
    for y0 in range(0, n, tile):
        for x0 in range(0, m, tile):
            yield y0, min(n - 1, y0 + tile - 1), x0, min(m - 1, x0 + tile - 1)


def calls_for(old_raw, new_raw, old_layers, new_layers, landscape="Landscape"):
    hc, pc = [], []
    for y0, y1, x0, x1 in tiles(old_raw.shape):
        blk = new_raw[y0:y1 + 1, x0:x1 + 1]
        if (blk != old_raw[y0:y1 + 1, x0:x1 + 1]).any():
            hc.append(["landscape.set_height_region", {"actorLabel": landscape, "region": {"minX": x0, "minY": y0, "maxX": x1, "maxY": y1},
                                                       "heightsBase64": base64.b64encode(blk.astype("<u2").tobytes()).decode()}])
        if any((new_layers[k][y0:y1 + 1, x0:x1 + 1] != old_layers[k][y0:y1 + 1, x0:x1 + 1]).any() for k in new_layers):
            for k in new_layers:
                pc.append(["landscape.set_layer_weight_region", {"layerName": k, "actorLabel": landscape, "region": {"minX": x0, "minY": y0, "maxX": x1, "maxY": y1},
                                                                 "weightsBase64": base64.b64encode(new_layers[k][y0:y1 + 1, x0:x1 + 1].tobytes()).decode()}])
    return [{"name": "heights", "calls": hc}, {"name": "paint", "calls": pc}]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--heights", required=True)
    ap.add_argument("--under", required=True)
    ap.add_argument("--cliff", required=True)
    ap.add_argument("--layers-dir", required=True)
    ap.add_argument("--sea-cm", type=float, required=True)
    ap.add_argument("--z0", type=float, required=True)
    ap.add_argument("--raw-per-cm", type=float, required=True)
    ap.add_argument("--min-above-cm", type=float, default=150.0)
    ap.add_argument("--beach-px", type=float, default=10.0)
    ap.add_argument("--landscape", required=True, help="landscape actor label (or set landscape in the --project profile)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--out-layers", required=True)
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    raw = np.asarray(Image.open(a.heights))
    n = raw.shape[0]
    sea = np.fromfile(a.under, np.uint8).reshape(n, n) > 127
    cliff = np.fromfile(a.cliff, np.uint8).reshape(n, n)
    old = {k: np.fromfile(os.path.join(a.layers_dir, k + ".u8"), np.uint8).reshape(n, n) for k in LAYERS}
    new_raw = raise_land(raw, sea, a.sea_cm, a.z0, a.raw_per_cm, a.min_above_cm)
    w = beach_weight(sea, cliff, a.beach_px)
    new = repaint({k: v / 255.0 for k, v in old.items()}, w)
    os.makedirs(a.out_layers, exist_ok=True)
    for k, v in new.items():
        v.tofile(os.path.join(a.out_layers, k + ".u8"))
    Image.fromarray(new_raw).save(os.path.join(a.out_layers, "heightmap16_coast.png"))
    phases = calls_for(raw, new_raw, old, new, a.landscape)
    json.dump({"phases": phases}, open(a.out, "w"))
    print("raised %d land px, beach px %d, wrote %s: %s" % ((new_raw != raw).sum(), (w > 0.05).sum(), a.out, ", ".join("%s=%d" % (p["name"], len(p["calls"])) for p in phases)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
