#!/usr/bin/env python3
"""Water: sea, coast, creeks, and a distance-to-water map for planting. 3D only.

  gg_water.py creek   --project P (--auto | --waypoints "x,z x,z ...") [--width-m 4] [--depth-m 1.5] [--dry-run]
                       carves a channel into heights (bed never rises downstream), so layers and the terrain build must be re-run
  gg_water.py analyse --project P [--dry-run]       water mask, distance-to-water (m), coast stats -> gg_data/world/ (no engine)
  gg_water.py build   --project P [--dry-run] [--no-check-view]   water.tscn (sea plane + creek ribbons) and a top-view check

Order: gg_terrain.py heights -> gg_water.py creek (optional) -> gg_terrain.py layers -> gg_terrain.py build -> gg_water.py build.
Water is at world.sea_level_m. A cell is water when its terrain is below the sea level or it lies in a creek channel below the creek surface.
Exit codes: 0 pass | 1 check failed | 2 refused | 3 engine log fatal | 4 no verdict | 5 runner failure.
"""
import argparse
import heapq
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
import gg_godot  # noqa: E402
import gg_project  # noqa: E402
import gg_style  # noqa: E402
import gg_terrain  # noqa: E402
import gg_verify  # noqa: E402

BANK_SLOPE = 0.6  # metres of rise per metre away from the channel edge (about 31 degrees)


# ---------------------------------------------------------------- data
def load_heights(project):
    wd = gg_terrain.load_world(project)
    nx, nz = wd["size_px"]
    h = np.fromfile(os.path.join(gg_terrain.world_dir(project), "heights.f32"), "<f4").astype(np.float64)
    if h.size != nx * nz:
        raise gg_godot.Refused("heights.f32 has %d values but world.json says %dx%d" % (h.size, nx, nz))
    if gg_terrain.sha_file(os.path.join(gg_terrain.world_dir(project), "heights.f32")) != wd.get("heights_sha"):
        raise gg_godot.Refused("heights.f32 changed behind world.json's back: run gg_terrain.py heights again")
    return h.reshape(nz, nx), wd


def edt(mask, cell):
    """Exact euclidean distance (metres) from every cell to the nearest True cell (Felzenszwalb-Huttenlocher). All-False -> inf."""
    inf = 1e20
    f = np.where(mask, 0.0, inf)

    def pass1d(col):
        n = len(col)
        v = np.zeros(n, int)
        z = np.zeros(n + 1)
        k = 0
        z[0], z[1] = -inf, inf
        for q in range(1, n):
            while True:
                s = ((col[q] + q * q) - (col[v[k]] + v[k] ** 2)) / (2.0 * q - 2.0 * v[k])
                if s <= z[k] and k > 0:
                    k -= 1
                else:
                    break
            if s <= z[k] and k == 0:
                v[0] = q
                z[0], z[1] = -inf, inf
                continue
            k += 1
            v[k] = q
            z[k], z[k + 1] = s, inf
        out = np.zeros(n)
        k = 0
        for q in range(n):
            while z[k + 1] < q:
                k += 1
            out[q] = (q - v[k]) ** 2 + col[v[k]]
        return out
    g = np.apply_along_axis(pass1d, 0, f)
    g = np.apply_along_axis(pass1d, 1, g)
    d = np.sqrt(np.minimum(g, inf)) * cell
    return np.where(mask.any(), d, np.inf)


def sample(h, x, z, cell):
    """Bilinear height at world (x, z)."""
    nz, nx = h.shape
    fx = np.clip(x / cell, 0, nx - 1.000001)
    fz = np.clip(z / cell, 0, nz - 1.000001)
    i, j = int(fx), int(fz)
    tx, tz = fx - i, fz - j
    return (h[j, i] * (1 - tx) * (1 - tz) + h[j, i + 1] * tx * (1 - tz) + h[j + 1, i] * (1 - tx) * tz + h[j + 1, i + 1] * tx * tz)


def resample(poly, step):
    pts = [np.array(p, float) for p in poly]
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        n = max(1, int(np.ceil(np.linalg.norm(b - a) / step)))
        for k in range(1, n + 1):
            out.append(a + (b - a) * k / n)
    return np.array(out)


def auto_path(h, wd, sea):
    """Highest land cell far from the sea -> Dijkstra downhill (uphill steps cost extra) to the nearest sea cell. Returns [(x, z)] in metres."""
    cell = wd["cell_m"]
    nz, nx = h.shape
    land = h > sea
    if not land.any() or land.all():
        raise gg_godot.Refused("--auto needs both land and sea in the heights (land fraction %.2f)" % land.mean())
    dist_sea = edt(~land, cell)
    far = dist_sea >= 0.15 * max(nx, nz) * cell
    cand = np.where(far, h, -np.inf)
    if not np.isfinite(cand).any():
        cand = np.where(land, h, -np.inf)
    sj, si = np.unravel_index(np.argmax(cand), h.shape)
    best = {(sj, si): 0.0}
    prev = {}
    pq = [(0.0, sj, si)]
    goal = None
    while pq:
        c, j, i = heapq.heappop(pq)
        if c > best.get((j, i), 1e30):
            continue
        if h[j, i] <= sea:
            goal = (j, i)
            break
        for dj in (-1, 0, 1):
            for di in (-1, 0, 1):
                if (dj or di) and 0 <= j + dj < nz and 0 <= i + di < nx:
                    step = cell * (1.4142 if dj and di else 1.0)
                    dh = h[j + dj, i + di] - h[j, i]
                    nc = c + step * (1.0 + 12.0 * max(0.0, dh) / step)
                    if nc < best.get((j + dj, i + di), 1e30):
                        best[(j + dj, i + di)] = nc
                        prev[(j + dj, i + di)] = (j, i)
                        heapq.heappush(pq, (nc, j + dj, i + di))
    if goal is None:
        raise gg_godot.Refused("no downhill route from the highest inland point to the sea")
    path = [goal]
    while path[-1] in prev:
        path.append(prev[path[-1]])
    path = path[::-1]
    xz = np.array([(i * cell, j * cell) for j, i in path], float)
    k = 2  # moving average so the creek does not zig-zag along grid cells; end points stay put
    sm = xz.copy()
    for n in range(1, len(xz) - 1):
        a, b = max(0, n - k), min(len(xz), n + k + 1)
        sm[n] = xz[a:b].mean(axis=0)
    return sm


def carve(h, wd, poly, width, depth, sea):
    """Return (new_h, creek dict). The bed is the running minimum of the terrain along the path minus depth, so it never rises downstream."""
    cell = wd["cell_m"]
    nz, nx = h.shape
    pts = resample(poly, cell)
    ground = np.array([sample(h, x, z, cell) for x, z in pts])
    bed = np.minimum.accumulate(ground - depth)
    level = bed + min(depth * 0.5, 0.6)
    new = h.copy()
    R = min(width / 2.0 + (np.max(ground) - np.min(bed)) / BANK_SLOPE, width * 6)
    w = int(np.ceil(R / cell)) + 1
    # nearest path point and distance for every cell near the path; the channel floor of a cell is the bed of ITS nearest point
    dmin = np.full((nz, nx), np.inf)
    imin = np.zeros((nz, nx), int)
    for n, (x, z) in enumerate(pts):
        i0, j0 = int(round(x / cell)), int(round(z / cell))
        for j in range(max(0, j0 - w), min(nz, j0 + w + 1)):
            for i in range(max(0, i0 - w), min(nx, i0 + w + 1)):
                d = np.hypot(i * cell - x, j * cell - z)
                if d < dmin[j, i]:
                    dmin[j, i], imin[j, i] = d, n
    floor = bed[imin] + np.maximum(0.0, dmin - width / 2.0) * BANK_SLOPE
    new = np.where(dmin <= R, np.minimum(new, floor), new)
    # berm: land right beside the channel is never lower than the water surface (cross-slopes would spill it): cells farther than half a width
    # from every path point, raised to the level of the nearest point
    ring = (dmin > width / 2.0) & (dmin <= width / 2.0 + 1.5 * cell) & (new > sea) & (level[imin] > sea + 0.3)
    new = np.where(ring & (new < level[imin] + 0.25), level[imin] + 0.25, new)
    creek = {"points": [[float(x), float(lv), float(z)] for (x, z), lv in zip(pts, level)], "bed": [float(b) for b in bed], "width_m": width, "depth_m": depth}
    return new, creek


def bank_clearance(h, wd, creek):
    """Fraction of land cells in the ring right beside the channel (farther than width/2 from every path point, within 1.5 cells of it) that are at or
    above the water surface of the nearest point (1.0 = the water cannot spill sideways). Cells below sea level (the creek mouth) are skipped."""
    cell = wd["cell_m"]
    nz, nx = h.shape
    wdt = creek["width_m"]
    pts = np.array(creek["points"])
    w = int(np.ceil((wdt / 2.0 + 1.5 * cell) / cell)) + 1
    dmin = np.full((nz, nx), np.inf)
    imin = np.zeros((nz, nx), int)
    for n, (x, lv, z) in enumerate(pts):
        i0, j0 = int(round(x / cell)), int(round(z / cell))
        for j in range(max(0, j0 - w), min(nz, j0 + w + 1)):
            for i in range(max(0, i0 - w), min(nx, i0 + w + 1)):
                d = np.hypot(i * cell - x, j * cell - z)
                if d < dmin[j, i]:
                    dmin[j, i], imin[j, i] = d, n
    lv = pts[:, 1][imin]
    ring = (dmin > wdt / 2.0) & (dmin <= wdt / 2.0 + 1.5 * cell) & (h > wd["sea_level_m"]) & (lv > wd["sea_level_m"] + 0.3)
    return float(np.mean(h[ring] >= lv[ring] - 1e-6)) if ring.any() else 1.0


def creek_registration(h, wd, creeks):
    """How well each creek lies in the channel that was carved for it: min(bank clearance of the ring beside the channel, fraction of points whose
    terrain is not above the water surface + 1 m). A mirrored, shifted or edited creek sits on ordinary ground and fails. Independent of the
    mask and the mesh, which both come from creeks.json. The first 3 points (the source on a summit) are skipped for the centre test."""
    scores = []
    for c in creeks:
        pts = [p for p in c["points"][3:] if p[1] > wd["sea_level_m"] + 0.3]
        centre = float(np.mean([sample(h, x, z, wd["cell_m"]) <= lv + 1.0 for x, lv, z in pts])) if pts else 1.0
        scores.append(min(bank_clearance(h, wd, c), centre))
    return float(min(scores)) if scores else 1.0


def water_mask(h, wd, creeks):
    cell = wd["cell_m"]
    sea = wd["sea_level_m"]
    mask = h < sea
    nz, nx = h.shape
    jj, ii = np.mgrid[0:nz, 0:nx]
    for c in creeks:
        pts = np.array(c["points"])
        for (x, lv, z) in pts:
            near = np.hypot(ii * cell - x, jj * cell - z) <= c["width_m"] / 2.0 + 1e-9
            mask |= near & (h <= lv + 0.05)
    return mask


def load_creeks(project, wd):
    p = os.path.join(gg_terrain.world_dir(project), "creeks.json")
    if not os.path.isfile(p):
        return []
    c = json.load(open(p))
    if c.get("heights_sha") != wd.get("heights_sha"):
        raise gg_godot.Refused("creeks.json belongs to older heights: run gg_water.py creek again (or delete %s)" % p)
    return c["creeks"]


# ---------------------------------------------------------------- commands
def creek(project, auto=False, waypoints=None, width=4.0, depth=1.5, dry_run=False):
    prof = gg_project.load_profile(project)
    gg_style.check_applied(project, prof)
    h, wd = load_heights(project)
    sea = wd["sea_level_m"]
    cell = wd["cell_m"]
    if os.path.isfile(os.path.join(gg_terrain.world_dir(project), "creeks.json")):
        raise gg_godot.Refused("a creek was already carved; run gg_terrain.py heights again to start over (one creek per level for now)")
    if not 1.0 <= width <= 40 or not 0.3 <= depth <= 10:
        raise gg_godot.Refused("width_m must be 1..40 and depth_m 0.3..10 (got %s, %s)" % (width, depth))
    if width < 2 * cell:
        raise gg_godot.Refused("width_m %s is under two cells (%s m): the channel would not resolve on this grid" % (width, 2 * cell))
    if auto == bool(waypoints):
        raise gg_godot.Refused("give exactly one of --auto or --waypoints")
    if auto:
        poly = auto_path(h, wd, sea)
    else:
        try:
            poly = [[float(v) for v in w.split(",")] for w in waypoints.split()]
        except ValueError:
            raise gg_godot.Refused("--waypoints must look like \"20,30 60,80 120,200\" (x,z in metres)")
        sx, sz = wd["size_m"]
        for x, z in poly:
            if not (0 <= x <= sx and 0 <= z <= sz):
                raise gg_godot.Refused("waypoint %s,%s is outside the world (0..%s, 0..%s)" % (x, z, sx, sz))
        if len(poly) < 2:
            raise gg_godot.Refused("need at least two waypoints")
        if sample(h, poly[0][0], poly[0][1], cell) <= sea:
            raise gg_godot.Refused("the first waypoint is below sea level: start the creek on land")
        if sample(h, poly[-1][0], poly[-1][1], cell) > sea:
            raise gg_godot.Refused("the last waypoint (%s,%s) is on land (height %.1f m, sea %.1f m): end the creek in the sea" % (poly[-1][0], poly[-1][1], sample(h, poly[-1][0], poly[-1][1], cell), sea))
    new, cr = carve(h, wd, poly, width, depth, sea)
    lo, hi = wd["height_range_m"]
    if new.min() < lo:
        raise gg_godot.Refused("the channel would go below height_range_m (%.1f < %.1f): lower --depth-m or widen the range" % (new.min(), lo))
    clear = bank_clearance(new, wd, cr)
    depth_at = [lv - sample(new, x, z, cell) for x, lv, z in cr["points"] if lv > sea + 0.3]
    max_depth = float(max(depth_at)) if depth_at else 0.0
    info = {"points": len(cr["points"]), "length_m": float(np.sum(np.hypot(*np.diff(np.array(cr["points"])[:, [0, 2]], axis=0).T))), "source_height_m": float(cr["bed"][0] + depth),
            "bank_clearance": round(clear, 3), "max_water_depth_m": round(max_depth, 2), "cells_changed": int(np.sum(new < h - 1e-6))}
    warns = []
    if clear < 0.9:
        warns.append("only %.0f%% of the creek has banks above the water surface (terrain beside it is lower than the water): the creek would flood sideways; pick another route or a smaller --depth-m" % (clear * 100))
    if max_depth > max(2.0 * depth, 2.0):
        warns.append("the water surface is up to %.1f m above the channel floor (limit %.1f m): it would float above a trench; use a wider channel or fewer steep drops" % (max_depth, max(2.0 * depth, 2.0)))
    if dry_run:
        print("would carve a creek: %s" % json.dumps(info))
        return 0, info, warns
    wd2 = dict(wd)
    gg_terrain.save_heights(project, new, wd2, drop=("water.json", "water_mask.png", "water_dist.f32"))
    cr["id"] = "creek1"
    json.dump({"heights_sha": wd2["heights_sha"], "creeks": [cr]}, open(os.path.join(gg_terrain.world_dir(project), "creeks.json"), "w"), indent=1)
    return (1 if clear < 0.9 or max_depth > max(2.0 * depth, 2.0) else 0), info, warns


def analyse(project, dry_run=False):
    prof = gg_project.load_profile(project)
    if prof["dimension"] != "3d":
        raise gg_godot.Refused("water is 3D only")
    h, wd = load_heights(project)
    cell = wd["cell_m"]
    creeks = load_creeks(project, wd)
    mask = water_mask(h, wd, creeks)
    frac = float(mask.mean())
    warns = []
    if frac < 0.02:
        warns.append("water covers %.1f%% of the map: no sea (sea level %.1f m is below the terrain, min %.1f m) and no creek" % (frac * 100, wd["sea_level_m"], h.min()))
    if frac > 0.9:
        warns.append("water covers %.0f%% of the map: the terrain is almost all under the sea level" % (frac * 100))
    shore = mask & ~(np.roll(mask, 1, 0) & np.roll(mask, -1, 0) & np.roll(mask, 1, 1) & np.roll(mask, -1, 1))
    land_shore = (~mask) & (np.roll(mask, 1, 0) | np.roll(mask, -1, 0) | np.roll(mask, 1, 1) | np.roll(mask, -1, 1))
    gy, gx = np.gradient(h, cell)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    shore_slope = float(slope[land_shore].mean()) if land_shore.any() else 0.0
    dist = edt(mask, cell) if mask.any() else np.full(h.shape, np.inf)
    info = {"schema": 1, "heights_sha": wd["heights_sha"], "sea_level_m": wd["sea_level_m"], "water_fraction": round(frac, 4), "creeks": len(creeks),
            "shore_cells": int(land_shore.sum()), "shore_length_m": float(land_shore.sum() * cell), "shore_slope_deg": round(shore_slope, 1),
            "max_distance_to_water_m": float(dist[np.isfinite(dist)].max()) if np.isfinite(dist).any() else None}
    code = 0
    if creeks:
        reg = creek_registration(h, wd, creeks)
        info["creek_registered"] = round(reg, 3)
        if reg < 0.9:
            code = 1
            warns.append("only %.0f%% of the creek lies in a carved trench (need 90%%): creeks.json does not match the heights (mirrored, shifted or edited); run gg_terrain.py heights and gg_water.py creek again" % (reg * 100))
    if shore_slope > 40:
        warns.append("the shore is steep (%.0f degrees on average): cliffs, not a beach" % shore_slope)
    if dry_run:
        print("would write water_mask.png, water_dist.f32, water.json: %s" % json.dumps(info))
        return code, info, warns
    from PIL import Image
    d = gg_terrain.world_dir(project)
    Image.fromarray((mask * 255).astype(np.uint8)).save(os.path.join(d, "water_mask.png"))
    np.where(np.isfinite(dist), dist, 1e9).astype("<f4").tofile(os.path.join(d, "water_dist.f32"))
    json.dump(dict(info, ok=(code == 0)), open(os.path.join(d, "water.json"), "w"), indent=1)
    return code, info, warns


def shore_band(exp, radius=2):
    """Cells within `radius` cells of a water/land boundary: where a mirror, swap or offset of the water shows up. No wrap-around at the edges."""
    e = exp.astype(bool)
    nz, nx = e.shape
    pw = np.pad(e, radius, constant_values=False)
    pl = np.pad(~e, radius, constant_values=False)
    near_water = np.zeros_like(e)
    near_land = np.zeros_like(e)
    for dj in range(2 * radius + 1):
        for di in range(2 * radius + 1):
            near_water |= pw[dj:dj + nz, di:di + nx]
            near_land |= pl[dj:dj + nz, di:di + nx]
    return near_water & near_land


def check_view(project, prof, style, mask, out, run=gg_godot.run, inland=None):
    """Top view of terrain + water: observed water/land classes (measured colours) against the mask; fails on uniform, mirrored or colourless water."""
    from PIL import Image
    st = json.loads(json.dumps(style))
    st["post"]["fog"]["on"] = False
    sx, sz = prof["world"]["size_m"]
    size = tuple(st["render"]["window"])
    ortho = max(sz, sx * size[1] / size[0])
    view = {"name": "top", "kind": "3d", "position": [sx / 2, max(sx, sz), sz / 2], "look_at": [sx / 2, 0, sz / 2], "fov": 50, "ortho_size": ortho}
    extra = {"ctx": {"style": st, "scenes": ["res://levels/%s/terrain.tscn" % prof["level"], "res://levels/%s/water.tscn" % prof["level"]]}}
    if st["render"].get("internal"):
        extra["internal"] = st["render"]["internal"]
    code, rep = gg_verify.shot(project, builder="res://addons/gg/probe/level_preview.gd", out=out, views=[view], size=size, frames=st["capture_frames"],
                               renderer=st["renderer"], run=run, extra_args=extra)
    if code not in (0, 1) or not rep["views"]:
        return code or 5, {"why": rep["why"]}
    img = np.asarray(Image.open(rep["views"][0]["png"]).convert("RGB"), dtype=np.float64)
    h, w, _ = img.shape
    ppm = h / ortho
    wpx, hpx = int(round(sx * ppm)), int(round(sz * ppm))
    x0, y0 = (w - wpx) // 2, (h - hpx) // 2
    crop = np.asarray(Image.fromarray(img[y0:y0 + hpx, x0:x0 + wpx].astype(np.uint8)).resize((64, 64), Image.BILINEAR), dtype=np.float64)
    exp = np.asarray(Image.fromarray((mask * 1).astype(np.uint8)).resize((64, 64), Image.NEAREST)).astype(int)
    refs, sep = gg_terrain.measured_refs(crop, exp)
    obs = gg_terrain.classify_by_chroma(crop, refs)
    ag, rec = gg_terrain.agreement(obs, exp, coverage_min=0.02)
    band = shore_band(exp)
    def band_ag(o):
        return float((o[band] == exp[band]).mean()) if band.any() else 0.0
    var = {"flip_x": band_ag(obs[:, ::-1]), "flip_z": band_ag(obs[::-1, :]), "transpose": band_ag(obs.T)}
    creek = None
    if inland is not None and inland.any():  # the creek is the asymmetric water feature: prove orientation on it at higher resolution
        R = 192
        crop2 = np.asarray(Image.fromarray(img[y0:y0 + hpx, x0:x0 + wpx].astype(np.uint8)).resize((R, R), Image.BILINEAR), dtype=np.float64)
        obs2 = gg_terrain.classify_by_chroma(crop2, refs)
        in2 = np.asarray(Image.fromarray(inland.astype(np.uint8) * 255).resize((R, R), Image.NEAREST)) > 127
        rc = lambda o: float((o[in2] == 1).mean())
        creek = {"cells": int(in2.sum()), "recall": rc(obs2), "variants": {"flip_x": rc(obs2[:, ::-1]), "flip_z": rc(obs2[::-1, :]), "transpose": rc(obs2.T)}}
    return 0, {"creek": creek, "agreement": ag, "band_agreement": band_ag(obs), "band_cells": int(band.sum()), "recall": {("water" if k else "land"): v for k, v in rec.items()}, "variants": var, "min_separation": sep, "png": rep["views"][0]["png"],
               "water_fraction": float(exp.mean())}


def build(project, dry_run=False, run=gg_godot.run, do_check=True):
    prof = gg_project.load_profile(project)
    style = gg_style.check_applied(project, prof)
    if prof["dimension"] != "3d":
        raise gg_godot.Refused("water is 3D only")
    h, wd = load_heights(project)
    ok = os.path.join(gg_terrain.world_dir(project), "build_ok.json")
    if not os.path.isfile(ok) or json.load(open(ok)).get("heights_sha") != wd["heights_sha"]:
        raise gg_godot.Refused("the terrain was not built and verified from the current heights: run gg_terrain.py layers and build (exit 0) first")
    code, info, warns = analyse(project, dry_run=dry_run)
    if code:
        return code, {"analyse": info, "warnings": warns, "why": "; ".join(w for w in warns if "carved trench" in w) or "analysis failed"}
    if dry_run:
        print("would build res://levels/%s/water.tscn: sea plane at %.2f m, %d creek(s)" % (prof["level"], wd["sea_level_m"], info["creeks"]))
        return 0, {"analyse": info, "warnings": warns}
    gg_terrain.forget(project, what=("water_ok.json",))
    creeks = load_creeks(project, wd)
    shallow = style["water"]["shallow"]
    shallow = [int(shallow[i:i + 2], 16) / 255 for i in (0, 2, 4)] if isinstance(shallow, str) else shallow
    args = {"level": prof["level"], "style": style, "world": {"size_m": wd["size_m"], "cell_m": wd["cell_m"], "size_px": wd["size_px"]},
            "sea_level_m": wd["sea_level_m"], "color": shallow, "creeks": creeks}
    r = run(project, "build_water", args, render=False, renderer=style["renderer"], timeout=300)
    if r.code:
        return r.code, {"why": r.why, "warnings": warns}
    out = {"build": r.result["data"], "analyse": info, "warnings": warns, "checked_view": do_check}
    d = out["build"]
    if abs(d["sea_y"] - wd["sea_level_m"]) > 1e-3:
        return 1, {**out, "why": "sea plane is at %.3f m but the sea level is %.3f m" % (d["sea_y"], wd["sea_level_m"])}
    if creeks and d["creek_vertices"] < 4:
        return 1, {**out, "why": "the creek mesh has %d vertices" % d["creek_vertices"]}
    if do_check:
        mask = np.asarray(__import__("PIL.Image", fromlist=["Image"]).open(os.path.join(gg_terrain.world_dir(project), "water_mask.png"))) > 127
        inland = mask & ~(h < wd["sea_level_m"])
        code, chk = check_view(project, prof, style, mask, os.path.join(project, "gg_data", "water_check"), run=run, inland=inland)
        out["top_check"] = chk
        if code:
            return code, {**out, "why": chk.get("why", "top view failed")}
        best = max(chk["variants"].items(), key=lambda kv: kv[1])
        wr = chk["recall"].get("water", 0.0) if chk["water_fraction"] >= 0.005 else 1.0  # no water on this terrain: nothing to recall
        cr = chk["creek"]
        creek_bad = bool(cr) and (cr["recall"] < 0.5 or max(cr["variants"].values()) > cr["recall"] - 0.2)
        mirrored = creek_bad
        dry = chk["water_fraction"] < 0.005
        if chk["agreement"] < 0.85 or (chk["band_agreement"] < 0.7 and not dry) or wr < 0.6 or (chk["min_separation"] < 0.02 and not dry) or creek_bad:
            why = "rendered water agrees %.2f with the water mask (need >= 0.85; shore band %.2f, need >= 0.7; water recall %.2f, need >= 0.6; water/land colour separation %.3f, need >= 0.02)" % (chk["agreement"], chk["band_agreement"], wr, chk["min_separation"])
            if chk["min_separation"] < 0.02:
                why += ": water and land render the same colour (change water.shallow in the preset overrides)"
            elif creek_bad:
                why += "; creek cells: %.2f of them render as water (need >= 0.5) and a mirrored variant scores %.2f (must be 0.2 lower): the creek is missing, mirrored or swapped against the terrain" % (cr["recall"], max(cr["variants"].values()))
            return 1, {**out, "why": why}
    if do_check:
        json.dump({"heights_sha": wd["heights_sha"], "agreement": chk["agreement"]}, open(os.path.join(gg_terrain.world_dir(project), "water_ok.json"), "w"))
    return 0, out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("creek"); c.add_argument("--project", required=True); c.add_argument("--auto", action="store_true"); c.add_argument("--waypoints")
    c.add_argument("--width-m", type=float, default=4.0); c.add_argument("--depth-m", type=float, default=1.5); c.add_argument("--dry-run", action="store_true")
    a_ = sub.add_parser("analyse"); a_.add_argument("--project", required=True); a_.add_argument("--dry-run", action="store_true")
    b = sub.add_parser("build"); b.add_argument("--project", required=True); b.add_argument("--dry-run", action="store_true"); b.add_argument("--no-check-view", action="store_true")
    a = ap.parse_args(argv)
    try:
        project = os.path.abspath(a.project)
        if a.cmd == "creek":
            code, info, warns = creek(project, a.auto, a.waypoints, a.width_m, a.depth_m, a.dry_run)
            for w in warns:
                print("WARNING " + w)
            print("creek: %s" % json.dumps(info))
            if not a.dry_run:
                print("now run gg_terrain.py layers and build again (the heights changed)")
            return code
        if a.cmd == "analyse":
            code, info, warns = analyse(project, a.dry_run)
            for w in warns:
                print("WARNING " + w)
            print("water: %s" % json.dumps(info))
            return code
        code, out = build(project, a.dry_run, do_check=not a.no_check_view)
        for w in out.get("warnings", []):
            print("WARNING " + w)
        if "build" in out:
            print("built %s: sea y %.2f, %d creek vertices" % (out["build"]["scene"], out["build"]["sea_y"], out["build"]["creek_vertices"]))
        if "top_check" in out and "agreement" in out["top_check"]:
            t = out["top_check"]
            print("top view agrees %.2f with the water mask (shore band %.2f over %d cells); recall %s; colour separation %.3f (%s)" % (t["agreement"], t["band_agreement"], t["band_cells"], {k: round(v, 2) for k, v in t["recall"].items()}, t["min_separation"], t["png"]))
            if t["creek"]:
                print("creek: %d cells, %.2f render as water; mirrored variants %s" % (t["creek"]["cells"], t["creek"]["recall"], {k: round(v, 2) for k, v in t["creek"]["variants"].items()}))
            else:
                print("NOTE no creek in this level: orientation of the water against the terrain is not proven by this check")
        if code:
            print("FAILED (exit %d): %s" % (code, out.get("why")))
        elif not a.dry_run and not out.get("checked_view"):
            print("WARNING top view NOT checked: the water is built but not marked verified")
        return code
    except (gg_godot.Refused, ValueError, OSError, KeyError, json.JSONDecodeError) as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
