#!/usr/bin/env python3
"""watoom-texture-layering: carve a real cross-section along a creek spline: deep in the middle, shallower towards the banks (host-side; numpy + pillow).

A water body's own Depth value does not dig terrain, and one landscape pixel is ~8 m wide, so a creek with a deep centre and
shelving sides needs a channel several pixels wide. This carves the live heights along the creek's spline:

  unreal_creek_profile.py --heights heightmap16_live_full.png --spline creek1_points.json --z0 3677.7 --raw-per-cm 4.4387 \
      --size-m 4000 --half-width-m 20 --deep-cm 700 --berm-cm 40 --out creek_profile_calls.json --out-heights heightmap16_creek_deep.png

Lakes use the same maths with a single centre point: `--lake X,Y,Z,RADIUS_M,DEEP_CM` (repeatable; X,Y,Z = the lake disc's centre and water surface in world cm)
carves a round bowl, deepest in the middle, with a bank rim (--lake-berm-cm, fading over --lake-berm-px pixels) so the flat water cannot spill downhill.
Order: lakes (with rim), then every --spline creek in turn (its channel cuts through the lake rim as the outlet), then the lake interiors again without a rim (inside 85% of the radius), so a creek that starts inside its lake leaves no bank ring standing in the water. --spline is optional when --lake is given.

--heights are the heights IN THE EDITOR now (landscape.get_height_region merged, 127 px tiles pasted into one png). --spline is a
json list of [x, y, z] world points (the water level) read with level.get_spline_info. For every pixel within --half-width-m of the
creek line the bed is set to  water_z - deep * (1 - (s/half)^2)^power  (s = distance from the line): --deep-cm at the centre,
rounding off to the water level at the edge, so the middle is the deepest and the sides are shallow. Terrain is only lowered
there (never raised) except for a low rim (--berm-cm above the water, fading over --berm-px pixels outside the channel) that
stops the flat water level flooding low ground beside the creek. Output: a `heights` phase of landscape.set_height_region tiles
(changed tiles only) and the new heights png. The carve is returned as `profile_px` so the foliage fit can use the same maths.
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
from os.path import abspath as _abspath, dirname as _dirname  # noqa: E402
sys.path.insert(0, _dirname(_abspath(__file__)))  # so `python3 -I script.py` finds ue_project
import ue_project  # noqa: E402


def hermite(points, step_cm=120.0):
    """Dense samples (x, y, z) along a Catmull-Rom spline through the points (tangent = (next - prev) / 2, ends = difference)."""
    p = np.asarray(points, float)
    n = len(p)
    m = np.zeros_like(p)
    m[1:-1] = (p[2:] - p[:-2]) / 2.0
    m[0], m[-1] = p[1] - p[0], p[-1] - p[-2]
    out = []
    for i in range(n - 1):
        k = max(2, int(np.linalg.norm(p[i + 1, :2] - p[i, :2]) / step_cm))
        t = np.linspace(0.0, 1.0, k, endpoint=False)[:, None]
        h00, h10, h01, h11 = 2 * t**3 - 3 * t**2 + 1, t**3 - 2 * t**2 + t, -2 * t**3 + 3 * t**2, t**3 - t**2
        out.append(h00 * p[i] + h10 * m[i] + h01 * p[i + 1] + h11 * m[i + 1])
    out.append(p[-1][None, :])
    return np.vstack(out)


def profile(shape, px_cm, samples, half_cm, deep_cm, power=1.5, berm_cm=40.0, berm_px=2.0, berm_min_z=None):
    """Returns (target_bed_z, berm_z, s) arrays shaped `shape`; target_bed_z is NaN outside the channel, berm_z NaN outside the rim.
    Pixel (row y, col x) is at world (x * px_cm, y * px_cm)."""
    n, m = shape
    yy, xx = np.mgrid[0:n, 0:m]
    wx, wy = xx * px_cm, yy * px_cm
    reach = half_cm + berm_px * px_cm
    xmin, xmax = samples[:, 0].min() - reach, samples[:, 0].max() + reach
    ymin, ymax = samples[:, 1].min() - reach, samples[:, 1].max() + reach
    sel = (wx >= xmin) & (wx <= xmax) & (wy >= ymin) & (wy <= ymax)
    ys, xs = np.nonzero(sel)
    px, py = wx[ys, xs], wy[ys, xs]
    s = np.full(len(ys), np.inf)
    wz = np.zeros(len(ys))
    for a in range(0, len(ys), 2000):
        d = np.hypot(px[a:a + 2000, None] - samples[None, :, 0], py[a:a + 2000, None] - samples[None, :, 1])
        j = d.argmin(axis=1)
        s[a:a + 2000] = d[np.arange(len(j)), j]
        wz[a:a + 2000] = samples[j, 2]
    bed = np.full(shape, np.nan)
    berm = np.full(shape, np.nan)
    sg = np.full(shape, np.inf)
    sg[ys, xs] = s
    inch = s < half_cm
    r = np.clip(s / half_cm, 0.0, 1.0)
    depth = deep_cm * (1.0 - r**2) ** power
    bed[ys[inch], xs[inch]] = (wz - depth)[inch]
    out = (s >= half_cm * 0.85) & (s < reach)
    f = np.clip(1.0 - (s - half_cm) / (berm_px * px_cm), 0.0, 1.0)
    f = np.where(s < half_cm, 1.0, f)
    if berm_min_z is not None:
        out = out & (wz > berm_min_z)  # no bank rim where the water is at sea level (it would lift the sea floor above the sea)
    berm[ys[out], xs[out]] = (wz + berm_cm * f)[out]
    return bed, berm, sg


def carve(raw, samples, z0, raw_per_cm, px_cm, half_cm, deep_cm, power=1.5, berm_cm=40.0, berm_px=2.0, rim=True, berm_min_z=None):
    """Returns (new uint16 heights, s distance array in cm). rim=False carves the channel / bowl only (never raises anything)."""
    z = raw.astype(float) / raw_per_cm + z0
    bed, berm, s = profile(raw.shape, px_cm, samples, half_cm, deep_cm, power, berm_cm, berm_px, berm_min_z)
    new = np.where(np.isnan(bed), z, np.minimum(z, bed))  # channel: only ever lowered
    if rim:
        ring = ~np.isnan(berm) & (s >= half_cm * 0.85)
        new = np.where(ring, np.maximum(new, berm), new)  # rim: lifted just enough to keep the water in
    return np.clip(np.round((new - z0) * raw_per_cm), 0, 65535).astype(np.uint16), s


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
    ap.add_argument("--spline", action="append", default=[], help="json list of [x, y, z] world points (water level); repeatable, one per creek")
    ap.add_argument("--lake", action="append", default=[], metavar="X,Y,Z,RADIUS_M,DEEP_CM", help="a round lake bowl (repeatable)")
    ap.add_argument("--lake-power", type=float, default=1.2)
    ap.add_argument("--lake-berm-cm", type=float, default=60.0)
    ap.add_argument("--lake-berm-px", type=float, default=3.0)
    ap.add_argument("--z0", type=float, required=True)
    ap.add_argument("--raw-per-cm", type=float, required=True)
    ap.add_argument("--size-m", type=float, required=True)
    ap.add_argument("--half-width-m", type=float, default=20.0)
    ap.add_argument("--deep-cm", type=float, default=700.0)
    ap.add_argument("--power", type=float, default=1.5)
    ap.add_argument("--berm-cm", type=float, default=40.0)
    ap.add_argument("--berm-px", type=float, default=2.0)
    ap.add_argument("--sea-z", type=float, default=None, help="no creek bank rim where the water is within 5 cm of this level (the sea)")
    ap.add_argument("--landscape", required=True, help="landscape actor label (or set landscape in the --project profile)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--out-heights", required=True)
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    raw = np.asarray(Image.open(a.heights))
    px_cm = a.size_m * 100.0 / (raw.shape[0] - 1)
    new = raw
    for spec in a.lake:
        x, y, z, r_m, deep = [float(v) for v in spec.split(",")]
        new, _ = carve(new, np.array([[x, y, z]]), a.z0, a.raw_per_cm, px_cm, r_m * 100.0, deep, a.lake_power, a.lake_berm_cm, a.lake_berm_px)
    for sp in a.spline:
        new, s = carve(new, hermite(json.load(open(sp))), a.z0, a.raw_per_cm, px_cm, a.half_width_m * 100.0, a.deep_cm, a.power, a.berm_cm, a.berm_px, berm_min_z=None if a.sea_z is None else a.sea_z + 5.0)
    if a.spline:
        for sp in a.spline:  # every channel again, rim-free: a later creek's bank rim must not stand up inside an earlier creek's channel at a junction
            new, _ = carve(new, hermite(json.load(open(sp))), a.z0, a.raw_per_cm, px_cm, a.half_width_m * 100.0, a.deep_cm, a.power, rim=False)
        for spec in a.lake:  # lake interiors again, bowl only: cuts back any creek bank rim that stands up inside a lake (the creek starts in its lake)
            x, y, z, r_m, deep = [float(v) for v in spec.split(",")]
            new, _ = carve(new, np.array([[x, y, z]]), a.z0, a.raw_per_cm, px_cm, r_m * 85.0, deep, a.lake_power, rim=False)
    Image.fromarray(new).save(a.out_heights)
    phases = calls_for(raw, new, a.landscape)
    json.dump({"phases": phases}, open(a.out, "w"))
    print("%d lake(s)%s: lowered %d px, raised %d px, wrote %s: %d tile calls"
          % (len(a.lake), (", creek half-width %.0f m (%.1f px) deep %.0f cm" % (a.half_width_m, a.half_width_m * 100.0 / px_cm, a.deep_cm)) if a.spline else "", (new < raw).sum(), (new > raw).sum(), a.out, len(phases[0]["calls"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
