#!/usr/bin/env python3
"""watoom-texture-layering: make the ground lusher and muddy along creeks by moving landscape layer weight (host-side; numpy + pillow).

  unreal_ground_paint.py plan --weights live_weights.npz --heights heightmap16_live_full.png --creek c1_points.json [--creek ...] \
      --z0 3677.7 --raw-per-cm 4.4387 --size-m 4000 --sea-z 4849.26 --out ground_calls.json --out-weights new_weights.npz

live_weights.npz holds uint8 arrays (505 x 505) named grass, dry_grass, dirt, mud read with landscape.get_layer_weight_region in 127 px tiles
(the driver tools/rig-ue-mcp/ue_ground_fetch.py does that; it also reads rock). Weight is only ever moved between layers of the same pixel, so
every pixel's total stays what it was (weights keep summing to 255). The lush and swamp steps move weight among the four layers only; the slope
pass also WRITES rock (and dirt). Sand and stone are never read or written. The layer names are fixed here (LAYERS / ALL below) and in
ue_ground_fetch.py; they are not taken from the --project profile.
 * lush grass: where the ground is gentle (slope below --max-slope, fading to 0 by --max-slope + 0.2) and above sea level + --min-above-cm,
   --dry-to-grass (0.85) of the dry_grass weight and --dirt-to-grass (0.5) of the dirt weight become grass.
 * slope layers (a second pass, `slope_pass`; needs `rock` in the weights, off with --no-slope-layers): steep ground becomes dirt and then rock instead of
   stretched grass or mud (planar landscape UVs streak on steep banks, and real banks are bare). A noise field breaks the slope edge up so rock
   pokes through in patches instead of following a contour line (professional terrain-texturing practice: slope mask, smoothstep, noise breakup).
   Slopes are rise/run: dirt from --dirt-slope A,B (0.28,0.5), rock from --rock-slope A,B (0.5,0.85); --noise-amp (0.8) sets how much noise moves the edge.
   Sand and stone are never touched.
 * swamp: within --swamp-m metres (60) of a creek line, on gentle ground, up to --mud (0.75) of the pixel's four-layer weight becomes mud, strongest
   at the water's edge and fading out with distance; inside the channel itself (under the water) it is mud almost fully.
Output: a `paint` phase of landscape.set_layer_weight_region calls (changed tiles and layers only) for tools/rig-ue-mcp/ue_run_phases.py.
"""
import argparse
import base64
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unreal_coast import tiles  # noqa: E402
from unreal_creek_profile import hermite  # noqa: E402
from os.path import abspath as _abspath, dirname as _dirname  # noqa: E402
sys.path.insert(0, _dirname(_abspath(__file__)))  # so `python3 -I script.py` finds ue_project
import ue_project  # noqa: E402

LAYERS = ("grass", "dry_grass", "dirt", "mud")
ALL = LAYERS + ("rock",)  # the slope pass also moves weight into rock (rock is read and written when present)


def slope_of(z, px_cm):
    gy, gx = np.gradient(z)
    return np.hypot(gx, gy) / px_cm


def creek_distance(shape, px_cm, creeks):
    """Distance in cm from every pixel to the nearest creek sample (only within a window around each creek)."""
    n, m = shape
    yy, xx = np.mgrid[0:n, 0:m]
    wx, wy = xx * px_cm, yy * px_cm
    best = np.full(shape, np.inf)
    for pts in creeks:
        s = hermite(pts, 400.0)
        for a in range(0, len(s), 1):
            q = s[a]
            x0, x1 = int(max((q[0] - 9000) / px_cm, 0)), int(min((q[0] + 9000) / px_cm + 2, m))
            y0, y1 = int(max((q[1] - 9000) / px_cm, 0)), int(min((q[1] + 9000) / px_cm + 2, n))
            d = np.hypot(wx[y0:y1, x0:x1] - q[0], wy[y0:y1, x0:x1] - q[1])
            best[y0:y1, x0:x1] = np.minimum(best[y0:y1, x0:x1], d)
    return best


def plan(w, z, px_cm, dist, sea_z, max_slope=0.35, dry_to_grass=0.85, dirt_to_grass=0.5, min_above_cm=150.0, swamp_cm=6000.0, mud=0.75, half_cm=2400.0):
    """w: dict of uint8 arrays for LAYERS. Returns new dict (uint8) with the same four-layer total per pixel."""
    g, dry, dirt, mu = [w[k].astype(float) for k in LAYERS]
    total = g + dry + dirt + mu
    sl = slope_of(z, px_cm)
    gentle = np.clip((max_slope + 0.2 - sl) / 0.2, 0.0, 1.0)
    land = (z > sea_z + min_above_cm).astype(float)
    f = gentle * land
    g2 = g + f * (dry_to_grass * dry + dirt_to_grass * dirt)
    dry2 = dry * (1 - f * dry_to_grass)
    dirt2 = dirt * (1 - f * dirt_to_grass)
    mu2 = mu.copy()
    # swamp: mud target as a share of the four-layer total, strongest at the water's edge
    edge = np.clip(1.0 - (dist - half_cm) / max(swamp_cm - half_cm, 1.0), 0.0, 1.0)
    target = np.where(dist <= half_cm, 0.95, mud * edge) * np.clip((max_slope + 0.2 - sl) / 0.2, 0.0, 1.0)
    want = total * target
    take = np.maximum(want - mu2, 0.0)
    rest = g2 + dry2 + dirt2
    share = np.where(rest > 0, np.minimum(take, rest) / np.maximum(rest, 1e-9), 0.0)
    g2, dry2, dirt2 = g2 * (1 - share), dry2 * (1 - share), dirt2 * (1 - share)
    mu2 = mu2 + share * rest
    r = round_to_total(np.stack([g2, dry2, dirt2, mu2]), total)
    out = dict(w)  # layers outside LAYERS (rock) pass through unchanged
    out.update({k: r[i] for i, k in enumerate(LAYERS)})
    return out


def round_to_total(out, total):
    """Round a (layers, h, w) float stack to uint8 with largest-remainder so every pixel sums to exactly round(total)."""
    r = np.floor(out)
    need = (np.round(total) - r.sum(axis=0)).astype(int)
    order = np.argsort(-(out - r), axis=0)
    for k in range(out.shape[0]):
        add = need > k
        for L in range(out.shape[0]):
            r[L] += np.where(add & (order[k] == L), 1, 0)
    return np.clip(r, 0, 255).astype(np.uint8)


def fbm(shape, seed=1, cells=(48, 16, 5), gain=0.5):
    """Smooth multi-scale value noise in [0, 1] (numpy only): `cells` = grid cells across the map per octave, coarse to fine."""
    rnd = np.random.RandomState(seed)
    n, m = shape
    acc, amp, tot = np.zeros(shape), 1.0, 0.0
    ys, xs = np.linspace(0, 1, n), np.linspace(0, 1, m)
    for c in cells:
        g = rnd.rand(c + 2, c + 2)
        fy, fx = ys * c, xs * c
        y0, x0 = fy.astype(int), fx.astype(int)
        ty, tx = (fy - y0)[:, None], (fx - x0)[None, :]
        ty, tx = ty * ty * (3 - 2 * ty), tx * tx * (3 - 2 * tx)
        a, b = g[y0][:, x0], g[y0][:, x0 + 1]
        c2, d = g[y0 + 1][:, x0], g[y0 + 1][:, x0 + 1]
        acc += amp * ((a * (1 - tx) + b * tx) * (1 - ty) + (c2 * (1 - tx) + d * tx) * ty)
        tot += amp
        amp *= gain
    acc /= tot
    return (acc - acc.min()) / max(acc.max() - acc.min(), 1e-9)


def smooth(lo, hi, x):
    t = np.clip((x - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def slope_pass(w, z, px_cm, sea_z, dirt_slope=(0.28, 0.5), rock_slope=(0.5, 0.85), noise_amp=0.8, soft=0.25, seed=11, min_above_cm=0.0):
    """Steep land -> dirt then rock, with the slope edge broken up by noise. w holds LAYERS (+ rock). Total per pixel is preserved;
    sand/stone and anything else are untouched. Returns a new dict (rock added)."""
    names = [k for k in ALL if k in w]
    if "rock" not in names:
        raise ValueError("slope pass needs a rock layer in the weights (refetch with ue_ground_fetch.py)")
    a = {k: w[k].astype(float) for k in names}
    total = sum(a.values())
    sl = slope_of(z, px_cm)
    land = (z > sea_z + min_above_cm).astype(float)
    noise = fbm(z.shape, seed)

    def share(rng):
        steep = smooth(rng[0], rng[1], sl)
        m = np.clip((steep - 0.5 + (noise - 0.5) * noise_amp) / soft + 0.5, 0.0, 1.0)
        return m * smooth(0.0, 0.15, steep) * land

    mr = share(rock_slope)
    md = share(dirt_slope) * (1.0 - mr)
    gain_rock = sum(a[k] * mr for k in names if k != "rock")
    for k in names:
        if k != "rock":
            a[k] = a[k] * (1.0 - mr)
    a["rock"] = a["rock"] + gain_rock
    movers = [k for k in names if k not in ("rock", "dirt")]
    gain_dirt = sum(a[k] * md for k in movers)
    for k in movers:
        a[k] = a[k] * (1.0 - md)
    a["dirt"] = a["dirt"] + gain_dirt
    r = round_to_total(np.stack([a[k] for k in names]), total)
    out = dict(w)
    out.update({k: r[i] for i, k in enumerate(names)})
    return out


def calls_for(old, new, landscape="Landscape"):
    shape = old["grass"].shape
    out = []
    for y0, y1, x0, x1 in tiles(shape):
        for k in [k for k in ALL if k in new]:
            blk = new[k][y0:y1 + 1, x0:x1 + 1]
            if (blk != old[k][y0:y1 + 1, x0:x1 + 1]).any():
                out.append(["landscape.set_layer_weight_region", {"layerName": k, "actorLabel": landscape, "region": {"minX": x0, "minY": y0, "maxX": x1, "maxY": y1},
                                                                  "weightsBase64": base64.b64encode(blk.tobytes()).decode()}])
    return [{"name": "paint", "calls": out}]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--weights", required=True)
    p.add_argument("--heights", required=True)
    p.add_argument("--creek", action="append", default=[])
    p.add_argument("--z0", type=float, required=True)
    p.add_argument("--raw-per-cm", type=float, required=True)
    p.add_argument("--size-m", type=float, required=True)
    p.add_argument("--sea-z", type=float, required=True)
    p.add_argument("--landscape", required=True, help="landscape actor label (or set landscape in the --project profile)")
    p.add_argument("--max-slope", type=float, default=0.35)
    p.add_argument("--dry-to-grass", type=float, default=0.85)
    p.add_argument("--dirt-to-grass", type=float, default=0.5)
    p.add_argument("--min-above-cm", type=float, default=150.0)
    p.add_argument("--swamp-m", type=float, default=60.0)
    p.add_argument("--mud", type=float, default=0.75)
    p.add_argument("--half-width-m", type=float, default=24.0)
    p.add_argument("--no-slope-layers", action="store_true", help="skip the slope pass (dirt/rock on steep ground)")
    p.add_argument("--dirt-slope", default="0.28,0.5", help="rise/run where dirt starts and is complete")
    p.add_argument("--rock-slope", default="0.5,0.85", help="rise/run where rock starts and is complete")
    p.add_argument("--noise-amp", type=float, default=0.8)
    p.add_argument("--seed", type=int, default=11)
    p.add_argument("--out", required=True)
    p.add_argument("--out-weights", required=True)
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    d = np.load(a.weights)
    old = {k: d[k] for k in ALL if k in d.files}
    raw = np.asarray(Image.open(a.heights))
    z = raw.astype(float) / a.raw_per_cm + a.z0
    px_cm = a.size_m * 100.0 / (raw.shape[0] - 1)
    dist = creek_distance(raw.shape, px_cm, [json.load(open(c)) for c in a.creek]) if a.creek else np.full(raw.shape, np.inf)
    new = plan(old, z, px_cm, dist, a.sea_z, a.max_slope, a.dry_to_grass, a.dirt_to_grass, a.min_above_cm, a.swamp_m * 100.0, a.mud, a.half_width_m * 100.0)
    if not a.no_slope_layers:
        new = slope_pass(new, z, px_cm, a.sea_z, tuple(float(x) for x in a.dirt_slope.split(",")), tuple(float(x) for x in a.rock_slope.split(",")), a.noise_amp, seed=a.seed)
    np.savez_compressed(a.out_weights, **new)
    ph = calls_for(old, new, a.landscape)
    json.dump({"phases": ph}, open(a.out, "w"))
    tot_old = sum(old[k].astype(int) for k in old); tot_new = sum(new[k].astype(int) for k in new)
    print("grass mean %.0f -> %.0f, dry_grass %.0f -> %.0f, dirt %.0f -> %.0f, mud %.0f -> %.0f, rock %.0f -> %.0f; totals changed at %d px; %d calls"
          % (old["grass"].mean(), new["grass"].mean(), old["dry_grass"].mean(), new["dry_grass"].mean(), old["dirt"].mean(), new["dirt"].mean(), old["mud"].mean(), new["mud"].mean(), old.get("rock", np.zeros(1)).mean(), new.get("rock", np.zeros(1)).mean(),
             int((tot_old != tot_new).sum()), len(ph[0]["calls"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
