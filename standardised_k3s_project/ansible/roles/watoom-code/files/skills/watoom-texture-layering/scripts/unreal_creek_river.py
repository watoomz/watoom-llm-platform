#!/usr/bin/env python3
"""watoom-texture-layering: rebuild a creek's water spline from the carved bed (host-side; numpy + pillow).

Terrain regenerates and creeks get carved after their water was placed, so an old spline ends up on the wrong path and at the wrong
heights (buried or floating). This finds the real bed and writes a new spline for a `WaterBodyRiver`:

  unreal_creek_river.py --heights heightmap16_live_full.png --polyline old_path.json --z0 3677.7 --raw-per-cm 4.4387 --size-m 4000 \
      --start-z 8608 --out creek_points.json --out-text creek_spline.txt [--points 46]

--polyline is a json list of [x, y, z] world points of the OLD creek in flow order (the old ribbon splines, a previous water spline,
or any rough path); it only has to stay within about 4 pixels of the real bed. The bed is the cheapest path between its first and last
point over the heights, where cells that sit lower than their neighbourhood cost less (the carved channel). It is smoothed and
resampled to --points points (default 46). Water Z at each point is the bed + --over-cm, capped at --start-z (the lake surface at the
head) and then raised where needed so it never sits below anything downstream, falling at least --fall-cm per point.

Outputs: --out the points as [[x, y, z], ...] (feed it to unreal_creek_profile.py --spline and ue_creek_foliage.py --spline) and --out-text
the complete `SplineCurves` value (Position, Rotation, Scale curves, open spline) for
`level.set_component_property {actorLabel, componentName:"WaterSpline", propertyName:"SplineCurves", value:<text>}` on a fresh WaterBodyRiver.
Use pass the heights from BEFORE the lakes were carved if a lake's dam rim stands between the head and the bed (the head is capped at --start-z anyway).
"""
import argparse
import heapq
import json
import math
import sys

import numpy as np
from PIL import Image
from os.path import abspath as _abspath, dirname as _dirname  # noqa: E402
sys.path.insert(0, _dirname(_abspath(__file__)))  # so `python3 -I script.py` finds ue_project
import ue_project  # noqa: E402


def ground(raw, z0, raw_per_cm):
    return raw.astype(float) / raw_per_cm + z0


def depression(z, r=3):
    """How far each cell stands above the lowest cell within r pixels (the carved channel is ~0)."""
    n, m = z.shape
    pad = np.pad(z, r, mode="edge")
    low = np.full(z.shape, np.inf)
    for dy in range(2 * r + 1):
        for dx in range(2 * r + 1):
            low = np.minimum(low, pad[dy:dy + n, dx:dx + m])
    return z - low


def corridor_mask(shape, polyline_px, radius=4):
    n, m = shape
    mask = np.zeros(shape, bool)
    for a, b in zip(polyline_px[:-1], polyline_px[1:]):
        k = max(2, int(math.hypot(b[0] - a[0], b[1] - a[1]) * 2))
        for f in np.linspace(0, 1, k):
            cx, cy = int(round(a[0] + (b[0] - a[0]) * f)), int(round(a[1] + (b[1] - a[1]) * f))
            mask[max(cy - radius, 0):cy + radius + 1, max(cx - radius, 0):cx + radius + 1] = True
    return mask


def bed_path(z, polyline_px, radius=4):
    """Cheapest 8-connected path (list of (row, col)) from the first to the last polyline point inside the corridor."""
    n, m = z.shape
    mask = corridor_mask(z.shape, polyline_px, radius)
    dep = depression(z)
    cost = 1.0 + (dep / 60.0) ** 2
    s = (int(round(polyline_px[0][1])), int(round(polyline_px[0][0])))
    e = (int(round(polyline_px[-1][1])), int(round(polyline_px[-1][0])))
    s = (min(max(s[0], 0), n - 1), min(max(s[1], 0), m - 1))
    e = (min(max(e[0], 0), n - 1), min(max(e[1], 0), m - 1))
    mask[s] = mask[e] = True
    dist, prev, pq = {s: 0.0}, {}, [(0.0, s)]
    while pq:
        d, u = heapq.heappop(pq)
        if u == e:
            break
        if d > dist[u]:
            continue
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == dx == 0:
                    continue
                v = (u[0] + dy, u[1] + dx)
                if not (0 <= v[0] < n and 0 <= v[1] < m) or not mask[v]:
                    continue
                nd = d + math.hypot(dy, dx) * cost[v] + max(0.0, z[v] - z[u]) * 0.02
                if nd < dist.get(v, 1e18):
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(pq, (nd, v))
    if e not in dist:
        raise ValueError("no path inside the corridor: the polyline is more than %d px from any connected ground" % radius)
    path = [e]
    while path[-1] != s:
        path.append(prev[path[-1]])
    return path[::-1]


def resample(path, px_cm, n_points, smooth=3):
    xy = np.array([(c[1] * px_cm, c[0] * px_cm) for c in path], float)
    for _ in range(smooth):
        if len(xy) > 2:
            xy[1:-1] = 0.25 * xy[:-2] + 0.5 * xy[1:-1] + 0.25 * xy[2:]
    seg = np.hypot(*np.diff(xy, axis=0).T)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    return np.array([(np.interp(cum[-1] * k / (n_points - 1), cum, xy[:, 0]), np.interp(cum[-1] * k / (n_points - 1), cum, xy[:, 1])) for k in range(n_points)])


def bilinear(z, x, y, px_cm):
    n, m = z.shape
    gx, gy = min(max(x / px_cm, 0), m - 1.001), min(max(y / px_cm, 0), n - 1.001)
    j, i = int(gx), int(gy)
    fx, fy = gx - j, gy - i
    return z[i, j] * (1 - fx) * (1 - fy) + z[i, j + 1] * fx * (1 - fy) + z[i + 1, j] * (1 - fx) * fy + z[i + 1, j + 1] * fx * fy


def water_heights(bed_z, over_cm=40.0, fall_cm=3.0, start_z=None):
    """Water level per point: bed + over_cm, never below anything downstream (falls at least fall_cm per point), then capped at start_z
    (the lake surface at the head; the first points may then be level) and kept non-increasing."""
    z = np.asarray(bed_z, float) + over_cm
    for i in range(len(z) - 2, -1, -1):
        z[i] = max(z[i], z[i + 1] + fall_cm)
    if start_z is not None:
        z = np.minimum(z, start_z)
        for i in range(1, len(z)):
            z[i] = min(z[i], z[i - 1])
    return z


def spline_text(points):
    """Complete SplineCurves text (open spline) for a WaterBodyRiver; tangents are Catmull-Rom (next - prev) / 2."""
    n = len(points)
    pos, rot, sc = [], [], []
    for i, (x, y, z) in enumerate(points):
        a, b = points[max(i - 1, 0)], points[min(i + 1, n - 1)]
        f = 0.5 if 0 < i < n - 1 else 1.0
        t = tuple((b[k] - a[k]) * f for k in range(3))
        inv = "" if i == 0 else "InVal=%d.000000," % i
        pos.append("(%sOutVal=(X=%.6f,Y=%.6f,Z=%.6f),ArriveTangent=(X=%.6f,Y=%.6f,Z=%.6f),LeaveTangent=(X=%.6f,Y=%.6f,Z=%.6f),InterpMode=CIM_CurveAuto)" % ((inv, x, y, z) + t + t))
        rot.append("(%sOutVal=(X=0.000000,Y=0.000000,Z=0.000000,W=1.000000),ArriveTangent=(X=0.000000,Y=0.000000,Z=0.000000,W=1.000000),LeaveTangent=(X=0.000000,Y=0.000000,Z=0.000000,W=1.000000),InterpMode=CIM_CurveAuto)" % inv)
        sc.append("(%sOutVal=(X=1.000000,Y=1.000000,Z=1.000000),ArriveTangent=(X=0.000000,Y=0.000000,Z=0.000000),LeaveTangent=(X=0.000000,Y=0.000000,Z=0.000000),InterpMode=CIM_CurveAuto)" % inv)
    return "(Position=(Points=(%s)),Rotation=(Points=(%s)),Scale=(Points=(%s)))" % (",".join(pos), ",".join(rot), ",".join(sc))


def build(raw, polyline, z0, raw_per_cm, px_cm, n_points=46, over_cm=40.0, fall_cm=3.0, start_z=None, radius=4):
    z = ground(raw, z0, raw_per_cm)
    poly_px = [(p[0] / px_cm, p[1] / px_cm) for p in polyline]
    path = bed_path(z, poly_px, radius)
    xy = resample(path, px_cm, n_points)
    bed = [bilinear(z, x, y, px_cm) for x, y in xy]
    wz = water_heights(bed, over_cm, fall_cm, start_z)
    return [[float(x), float(y), float(w)] for (x, y), w in zip(xy, wz)], bed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--heights", required=True)
    ap.add_argument("--polyline", required=True)
    ap.add_argument("--z0", type=float, required=True)
    ap.add_argument("--raw-per-cm", type=float, required=True)
    ap.add_argument("--size-m", type=float, required=True)
    ap.add_argument("--points", type=int, default=46)
    ap.add_argument("--over-cm", type=float, default=40.0)
    ap.add_argument("--fall-cm", type=float, default=3.0)
    ap.add_argument("--start-z", type=float, default=None, help="water Z at the head (the lake surface); the water never starts higher")
    ap.add_argument("--corridor-px", type=int, default=4)
    ap.add_argument("--out", required=True)
    ap.add_argument("--out-text", required=True)
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    raw = np.asarray(Image.open(a.heights))
    px_cm = a.size_m * 100.0 / (raw.shape[0] - 1)
    pts, bed = build(raw, json.load(open(a.polyline)), a.z0, a.raw_per_cm, px_cm, a.points, a.over_cm, a.fall_cm, a.start_z, a.corridor_px)
    json.dump(pts, open(a.out, "w"))
    open(a.out_text, "w").write(spline_text(pts))
    over = [p[2] - b for p, b in zip(pts, bed)]
    print("%d points, water Z %.0f -> %.0f, above the bed: mean %.0f max %.0f cm; wrote %s and %s" % (len(pts), pts[0][2], pts[-1][2], np.mean(over), max(over), a.out, a.out_text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
