#!/usr/bin/env python3
"""watoom-texture-layering: make a creek reach the sea or merge into another creek (host-side; numpy + pillow).

A creek whose last point sits in a closed pit, on land, or beside another creek looks like it "stops". This extends its points:

  unreal_creek_extend.py --heights heightmap16_lakes_only.png --creek c2_points.json --sea --trim-below 4900 \
      --z0 3677.7 --raw-per-cm 4.4387 --size-m 4000 --sea-z 4849.3 --out c2_points_ext.json
  unreal_creek_extend.py --heights ... --creek c3_points.json --join c4_points.json --z0 ... --out c3_points_ext.json

--sea   routes from the creek's end to the nearest edge-connected sea (ground below --sea-z that touches the map border) by the
        cheapest path (climbing costs, descending is free), water falling to --sea-z + 10 at the coast.
--join  routes from the end to the nearest point of another creek's points json and ends exactly on its centre line, never higher
        than the creek's own last water level (so the end tucks under the bigger creek's surface and no gap shows).
--approach-m M  with --join: cut the creek where it first comes within M metres of the target and join straight from there (use when it runs
        alongside the target and the confluence would otherwise be a kink at the very end).
--into-sea-m M  with --sea: continue M metres past the coast (straight on, water at sea level) so the carve cuts the channel through the shallow beach ramp into the sea.
--trim-below Z  first drops trailing points whose water is lower than Z (a creek that dived below sea level into a pit).
Use the heights from BEFORE the creeks were carved (lakes-only terrain) so the route follows natural ground, then re-run
unreal_creek_profile.py with every extended creek, re-place the rivers (ue_place_river.py --points N) and re-fit foliage.
"""
import argparse
import heapq
import json
import math
import sys
from collections import deque

import numpy as np
from PIL import Image
from os.path import abspath as _abspath, dirname as _dirname  # noqa: E402
sys.path.insert(0, _dirname(_abspath(__file__)))  # so `python3 -I script.py` finds ue_project
import ue_project  # noqa: E402


def sea_mask(z, sea_z):
    """Cells below sea_z connected (8-neighbour) to the map border."""
    n, m = z.shape
    low = z < sea_z
    sea = np.zeros(z.shape, bool)
    q = deque()
    for i in range(n):
        for a, b in ((i, 0), (i, m - 1)):
            if low[a, b] and not sea[a, b]:
                sea[a, b] = True
                q.append((a, b))
    for j in range(m):
        for a, b in ((0, j), (n - 1, j)):
            if low[a, b] and not sea[a, b]:
                sea[a, b] = True
                q.append((a, b))
    while q:
        a, b = q.popleft()
        for da in (-1, 0, 1):
            for db in (-1, 0, 1):
                u, v = a + da, b + db
                if 0 <= u < n and 0 <= v < m and low[u, v] and not sea[u, v]:
                    sea[u, v] = True
                    q.append((u, v))
    return sea


def route(z, start_rc, goal_mask, climb_cost=0.05):
    """Cheapest 8-connected path (list of (row, col)) from start to any True cell of goal_mask; climbing costs, descending is free."""
    n, m = z.shape
    dist, prev, pq = {start_rc: 0.0}, {}, [(0.0, start_rc)]
    end = None
    while pq:
        d, u = heapq.heappop(pq)
        if goal_mask[u]:
            end = u
            break
        if d > dist[u]:
            continue
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == dx == 0:
                    continue
                v = (u[0] + dy, u[1] + dx)
                if not (0 <= v[0] < n and 0 <= v[1] < m):
                    continue
                nd = d + math.hypot(dy, dx) + max(0.0, z[v] - z[u]) * climb_cost
                if nd < dist.get(v, 1e18):
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(pq, (nd, v))
    if end is None:
        raise ValueError("no route from the creek end to the goal")
    path = [end]
    while path[-1] != start_rc:
        path.append(prev[path[-1]])
    return path[::-1]


def trim_below(points, level):
    p = [list(q) for q in points]
    while len(p) > 2 and p[-1][2] < level:
        p.pop()
    return p


def _resample_xy(path, px_cm, spacing_cm, smooth=2):
    xy = np.array([(c[1] * px_cm, c[0] * px_cm) for c in path], float)
    for _ in range(smooth):
        if len(xy) > 2:
            xy[1:-1] = 0.25 * xy[:-2] + 0.5 * xy[1:-1] + 0.25 * xy[2:]
    seg = np.hypot(*np.diff(xy, axis=0).T)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    k = max(2, int(round(cum[-1] / spacing_cm)) + 1)
    s = np.linspace(0, cum[-1], k)
    return np.stack([np.interp(s, cum, xy[:, 0]), np.interp(s, cum, xy[:, 1])], axis=1)


def extend(points, z, px_cm, sea_z=None, join=None, trim=None, fall_cm=3.0, approach_cm=None, into_sea_cm=0.0):
    """Returns the creek's points (list of [x, y, z]) extended to the sea (sea_z given) or onto the creek `join` (its points)."""
    p = trim_below(points, trim) if trim is not None else [list(q) for q in points]
    if join is not None and approach_cm:
        # a creek that runs alongside its target would only meet it in a kink at the end: cut it where it first comes within approach_cm
        from unreal_creek_profile import hermite
        dense0 = hermite(join, 120.0)
        for i in range(1, len(p)):
            if np.hypot(dense0[:, 0] - p[i][0], dense0[:, 1] - p[i][1]).min() <= approach_cm:
                p = p[:i + 1]
                break
    spacing = float(np.median(np.hypot(*np.diff(np.array(p)[:, :2], axis=0).T)))
    n, m = z.shape
    last = p[-1]
    start = (min(max(int(round(last[1] / px_cm)), 0), n - 1), min(max(int(round(last[0] / px_cm)), 0), m - 1))
    if join is not None:
        from unreal_creek_profile import hermite
        dense = hermite(join, 120.0)
        goal = np.zeros(z.shape, bool)
        d = np.hypot(dense[:, 0] - last[0], dense[:, 1] - last[1])
        t = dense[int(d.argmin())]
        gi, gj = min(max(int(round(t[1] / px_cm)), 0), n - 1), min(max(int(round(t[0] / px_cm)), 0), m - 1)
        goal[max(gi - 1, 0):gi + 2, max(gj - 1, 0):gj + 2] = True
        z_end = min(last[2], float(t[2]))
        end_xy = (float(t[0]), float(t[1]))
    else:
        goal = sea_mask(z, sea_z)
        z_end = sea_z + 10.0
        end_xy = None
    path = route(z, start, goal)
    xy = _resample_xy(path, px_cm, spacing)
    xy[0] = (last[0], last[1])
    if end_xy:
        xy[-1] = end_xy
    seg = np.hypot(*np.diff(xy, axis=0).T)
    frac = np.concatenate([[0.0], np.cumsum(seg)]) / max(seg.sum(), 1e-9)
    zz = last[2] + (min(z_end, last[2] - fall_cm * (len(xy) - 1)) - last[2]) * frac if join is None else last[2] + (z_end - last[2]) * frac
    if join is None:
        zz = np.maximum(zz, z_end)  # never below the sea at the coast; monotone because it is linear down
    out = p[:-1] + [[float(a), float(b), float(c)] for (a, b), c in zip(xy, zz)]
    if join is None and into_sea_cm > 0 and len(out) >= 2:
        # carry the channel on through the beach ramp into the sea (level with it), so the creek water meets the ocean instead of stopping at the shore
        a0, b0 = np.array(out[-2][:2]), np.array(out[-1][:2])
        d = (b0 - a0) / max(np.hypot(*(b0 - a0)), 1e-9)
        k = max(1, int(round(into_sea_cm / spacing)))
        for i in range(1, k + 1):
            q = b0 + d * spacing * i
            out.append([float(q[0]), float(q[1]), float(sea_z + 0.5)])
        out[-(k + 1)][2] = float(sea_z + 0.5) if k else out[-(k + 1)][2]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--heights", required=True)
    ap.add_argument("--creek", required=True)
    ap.add_argument("--sea", action="store_true")
    ap.add_argument("--join", default=None)
    ap.add_argument("--approach-m", type=float, default=None, help="with --join: cut the creek where it first comes within this many metres of the target, then join straight (stops a parallel run ending in a kink)")
    ap.add_argument("--into-sea-m", type=float, default=0.0, help="with --sea: carry the creek this many metres on into the sea, level with it (stops the mouth ending at a shallow beach)")
    ap.add_argument("--trim-below", type=float, default=None)
    ap.add_argument("--sea-z", type=float, default=None, help="sea level in cm (required with --sea; or sea_cm in the --project profile)")
    ap.add_argument("--z0", type=float, required=True)
    ap.add_argument("--raw-per-cm", type=float, required=True)
    ap.add_argument("--size-m", type=float, required=True)
    ap.add_argument("--out", required=True)
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    if bool(a.sea) == bool(a.join):
        ap.error("give exactly one of --sea or --join")
    raw = np.asarray(Image.open(a.heights))
    z = raw.astype(float) / a.raw_per_cm + a.z0
    px_cm = a.size_m * 100.0 / (raw.shape[0] - 1)
    pts = extend(json.load(open(a.creek)), z, px_cm, sea_z=a.sea_z if a.sea else None, join=json.load(open(a.join)) if a.join else None, trim=a.trim_below,
                 approach_cm=a.approach_m * 100.0 if a.approach_m else None, into_sea_cm=a.into_sea_m * 100.0)
    json.dump(pts, open(a.out, "w"))
    print("%d points, now ends at (%.0f, %.0f) water Z %.0f; wrote %s" % (len(pts), pts[-1][0], pts[-1][1], pts[-1][2], a.out))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
    sys.exit(main())
