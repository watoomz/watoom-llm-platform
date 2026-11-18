#!/usr/bin/env python3
"""watoom-texture-layering: find the creek lines of a terrain and write the ue-mcp calls that carve and fill them (numpy + pillow).

From heightmap16.png (the same N x N uint16 that landscape.import_heightmap read; raw value == landscape raw height) it
  1. fills depressions and computes D8 flow accumulation (the lowest lines of the terrain are where water collects),
  2. keeps the strongest channels as creek paths from their source down to the sea / map edge,
  3. carves a smooth channel into the heights (written back as tiles for landscape.set_height_region),
  4. lays a ribbon of flat Plane actors with a water material along each creek, stepping down with the bed,
  5. writes creek_mask.u8 (255 near water) that unreal_scene_scatter.py reads to keep grass and trees out of the channel.

  unreal_creeks.py --ue-dir ue --size-m 4000 --z0 3677.7 --raw-per-cm 4.4387 --landscape MyLandscape --material /Game/AdvancedVillagePack/Materials/M_Inst_Water --out creek_calls.json

--landscape is the landscape actor label (profile key `landscape`). --material is a material that renders on a plain Plane actor
(profile key `plane_water_material`, NOT `water_material`: a Water-plugin river material does not render on planes).
The actor labels are fixed: Creek_<n>_<k> planes, CreekRibbon_<n>_<k> splines, Lake_<n> discs (not taken from the profile).
--z0 is the world Z of raw height 0 and --raw-per-cm the vertical scale; both come from landscape.get_height_region
(rawUnitsPerWorldCm, minZ/minRaw). Phases in creek_calls.json, run in order and save the level after each:
  carve  (landscape.set_height_region tiles: needs an edit layer; read a corner back after),  water (level.place_actor planes).
Place scenery AFTER this so the instances trace onto the carved ground.
"""
import argparse
import heapq
import json
import math
import os
import sys
import base64

import numpy as np
from PIL import Image
from os.path import abspath as _abspath, dirname as _dirname  # noqa: E402
sys.path.insert(0, _dirname(_abspath(__file__)))  # so `python3 -I script.py` finds ue_project
import ue_project  # noqa: E402
from unreal_ground_paint import round_to_total  # noqa: E402

N8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def fill_and_flow(h, sea_cells):
    """Priority-flood depression filling; returns filled heights and the downstream index of every cell (-1 = outlet)."""
    n = h.shape[0]
    filled = h.astype(float).copy()
    down = -np.ones(n * n, int)
    seen = np.zeros((n, n), bool)
    pq = []
    for y in range(n):
        for x in range(n):
            if y in (0, n - 1) or x in (0, n - 1) or sea_cells[y, x]:
                heapq.heappush(pq, (filled[y, x], y, x))
                seen[y, x] = True
    while pq:
        z, y, x = heapq.heappop(pq)
        for dy, dx in N8:
            yy, xx = y + dy, x + dx
            if 0 <= yy < n and 0 <= xx < n and not seen[yy, xx]:
                seen[yy, xx] = True
                if filled[yy, xx] <= z:
                    filled[yy, xx] = z + 1e-3
                down[yy * n + xx] = y * n + x
                heapq.heappush(pq, (filled[yy, xx], yy, xx))
    return filled, down


def accumulate(filled, down):
    n = filled.shape[0]
    order = np.argsort(-filled.ravel())
    acc = np.ones(n * n)
    for i in order:
        d = down[i]
        if d >= 0:
            acc[d] += acc[i]
    return acc.reshape(n, n)


def creek_paths(acc, down, sea, keep, min_len, margin):
    n = acc.shape[0]
    thr = np.sort(acc.ravel())[::-1][min(n * n - 1, keep)]
    stream = (acc >= max(thr, 20)) & ~sea
    stream[:margin, :] = stream[-margin:, :] = False
    stream[:, :margin] = stream[:, -margin:] = False
    has_up = np.zeros(n * n, bool)
    for i in np.nonzero(stream.ravel())[0]:
        d = down[i]
        if d >= 0 and stream.ravel()[d]:
            has_up[d] = True
    used = np.zeros(n * n, bool)
    paths = []
    sources = [i for i in np.nonzero(stream.ravel())[0] if not has_up[i]]
    sources.sort(key=lambda i: -acc.ravel()[i])
    flat = stream.ravel()
    for s in sources:
        p, i = [], s
        while i >= 0 and flat[i] and not used[i]:
            p.append((i // n, i % n))
            used[i] = True
            i = down[i]
        if i >= 0 and flat[i]:
            p.append((i // n, i % n))
        if len(p) >= min_len:
            paths.append(p)
    return stream, paths


def smooth(path, k=3):
    a = np.array(path, float)
    for _ in range(k):
        b = a.copy()
        b[1:-1] = (a[:-2] + 2 * a[1:-1] + a[2:]) / 4
        a = b
    return a


BASE_LAYERS = ["grass", "dry_grass", "dirt", "rock", "mud"]
BANK_LAYERS = {1: "rock", 2: "sand", 3: "mud", 4: "stone"}  # 0 = grass bank (left unpainted); rock = pebbles texture


def zw_start(paths, pi):
    return 0.0


def smooth1d(rng, n, k=9):
    v = np.convolve(rng.standard_normal(n + 2 * k), np.ones(k) / k, mode="same")[k:k + n]
    return np.clip(v / (np.abs(v).max() + 1e-9) * 1.6, -1, 1)


def noise2d(rng, n, cell=6):
    g = rng.random((n // cell + 3, n // cell + 3)).astype(np.float32)
    big = Image.fromarray((g * 255).astype(np.uint8)).resize((n + cell * 2, n + cell * 2), Image.BICUBIC)
    return np.asarray(big, float)[:n, :n] / 127.5 - 1.0


def section_types(rng, length, p_grass=0.2):
    """Bank sections: runs of 6-14 path points, each a pebble / sand / mud / stone bank, or 0 = plain grass bank."""
    types = np.zeros(length, int)
    i = 0
    while i < length:
        ln = int(rng.integers(6, 15))
        types[i:i + ln] = rng.choice([0, 1, 2, 3, 4], p=[p_grass, 0.25, 0.2, 0.2, 0.15 + (0.2 - p_grass)])
        i += ln
    return types


def build(ue_dir, size_m, z0, raw_per_cm, material, keep=700, min_len=30, sea_m=2.0, depth_cm=220.0, width_px=1.3,
          bank_px=3.5, max_creeks=4, tile=127, irregular=False, seed=11, baseline=None, clean_prefix=None, bank_paint=False,
          base_layers=None, ribbon_mesh=None, ribbon_section=30, heights="heightmap16.png", layers_dir=None, sea_cm=None,
          lakes=False, lake_material=None, lake_px=(4.0, 9.0), lake_depth_cm=(350.0, 900.0), lake_margin_px=24, rough=False, meander_px=2.5, landscape="Landscape"):
    """landscape: the landscape actor label written into every landscape.* call.
    meander_px: with irregular, the route wanders sideways by up to this many pixels around the flow line.
    irregular: width, depth, bank slope and bank edge vary along the creek (noise), so it stops looking like a uniform ditch.
    bank_paint: also split the banks into pebble / sand / mud / stone / grass sections and write the layer weights for them
    (needs the <layer>.u8 weights of base_layers in ue_dir); writes creek_bank.u8 (section code + 1) and with_creeks/<layer>.u8.
    baseline: the heightmap currently in the editor (default: heightmap16.png), so only changed tiles are written.
    clean_prefix: first delete the level actors whose label starts with it (the previous creek's water planes).
    ribbon_mesh: a static mesh asset (a plane carrying the water material) to lay as a continuous SplineMesh ribbon along each creek
    (level.create_spline_actor + level.build_spline_meshes, one spline per ~30 points so the width can follow the creek) instead of
    one separate plane per segment; the separate planes leave ragged joins and gaps.
    heights / layers_dir / sea_cm: read the terrain from another heightmap (the island's heightmap16_island.png) and the layer weights from another
    directory (island_layers); sea_cm marks every cell under that level as sea (creeks end there) instead of the lowest 2 m of the map.
    lakes: every creek whose head is inside the map (at least lake_margin_px from the edge and well above the sea) gets a lake of random radius
    (lake_px, pixels) and depth (lake_depth_cm) carved at its head, a disc of lake_material at the water level, and sand / mud painted on its shore.
    rough: stronger, two-scale bank edge noise and bank sections that interleave (patches of a neighbouring type) so banks are never straight lines."""
    img = np.asarray(Image.open(os.path.join(ue_dir, heights))).astype(np.int64)
    base_img = np.asarray(Image.open(os.path.join(ue_dir, baseline))).astype(np.int64) if baseline else img
    layers_dir = layers_dir or ue_dir
    n = img.shape[0]
    rng = np.random.default_rng(seed)
    nz = noise2d(rng, n) if irregular else np.zeros((n, n))
    if rough:
        nz = 1.6 * nz + 0.7 * noise2d(rng, n, 3)
    nz2 = noise2d(rng, n, 4) if rough else np.zeros((n, n))
    cm = size_m * 100.0 / (n - 1)
    zcm = img / raw_per_cm + z0
    sea = zcm < ((zcm.min() + sea_m * 100.0) if sea_cm is None else sea_cm + 30.0)
    filled, down = fill_and_flow(zcm, sea)
    acc = accumulate(filled, down)
    stream, paths = creek_paths(acc, down, sea, keep, min_len, 12)
    paths = sorted(paths, key=lambda p: -len(p))[:max_creeks]
    new = img.astype(float).copy()
    mask = np.zeros((n, n), np.uint8)
    btype = np.full((n, n), -1, int)
    bw = np.zeros((n, n))
    yy, xx = np.mgrid[0:n, 0:n]
    water = []
    ribbons = []
    levels = []
    for pi, raw in enumerate(paths):
        pts = smooth(raw, 4)
        if irregular and len(pts) > 12:  # sideways meander: the route wanders around the flow line instead of following it exactly
            tg = np.gradient(pts, axis=0); tg = tg / (np.hypot(tg[:, 0], tg[:, 1])[:, None] + 1e-9)
            off = smooth1d(rng, len(pts), 25) * meander_px * np.minimum(1.0, np.minimum(np.arange(len(pts)), np.arange(len(pts))[::-1]) / 8.0)
            pts = np.clip(pts + np.stack([-tg[:, 1], tg[:, 0]], axis=1) * off[:, None], 2, n - 3)
        bed = zcm[tuple(np.round(pts).astype(int).T)].copy()
        bed = np.minimum.accumulate(np.convolve(np.pad(bed, 3, mode="edge"), np.ones(7) / 7, mode="valid"))
        L = len(pts)
        # width: slow swell + pools (wide, slow stretches) + narrow runs; depth varies on its own scale so wide is not always deep
        wfac = np.clip(1 + 0.45 * smooth1d(rng, L) + 0.9 * np.maximum(smooth1d(rng, L, 21) - 0.35, 0) - 0.35 * np.maximum(-smooth1d(rng, L, 15) - 0.4, 0), 0.5, 2.4) if irregular else np.ones(L)
        dfac = np.clip(1 + 0.5 * smooth1d(rng, L, 7) + 0.3 * smooth1d(rng, L, 19), 0.45, 1.9) if irregular else np.ones(L)
        asym = smooth1d(rng, L) if irregular else np.zeros(L)
        types = section_types(rng, L) if bank_paint else np.zeros(L, int)
        tang = np.gradient(pts, axis=0)
        zw = bed - depth_cm * dfac * 0.35
        for k, ((py, px), wz) in enumerate(zip(pts, zw)):
            w_i, dep = width_px * wfac[k], depth_cm * dfac[k]
            reach = bank_px * 1.35 + 3
            y0, y1, x0, x1 = int(max(0, py - reach)), int(min(n, py + reach + 1)), int(max(0, px - reach)), int(min(n, px + reach + 1))
            dy, dx = yy[y0:y1, x0:x1] - py, xx[y0:y1, x0:x1] - px
            d = np.hypot(dy, dx)
            side = np.sign(tang[k][0] * dx - tang[k][1] * dy)
            bank_i = bank_px * (1 + 0.3 * asym[k] * side) if irregular else bank_px
            d_eff = d + nz[y0:y1, x0:x1] * 1.3
            t = np.clip((d_eff - w_i) / np.maximum(bank_i - w_i, 0.5), 0, 1) ** (2.0 if not irregular else 1.4 + 0.5 * (1 + asym[k]))
            target_cm = (wz - dep * 0.65) + t * (dep * 1.2)
            cur = new[y0:y1, x0:x1] / raw_per_cm + z0
            lower = np.where(d_eff <= bank_i, np.minimum(cur, np.maximum(target_cm, wz - dep * 0.65)), cur)
            new[y0:y1, x0:x1] = np.minimum(new[y0:y1, x0:x1], (lower - z0) * raw_per_cm)
            mask[y0:y1, x0:x1][d_eff <= bank_i + 2.5] = 255
            if bank_paint:
                wet = d_eff < w_i + 0.8
                b = np.clip((bank_i + 1.5 - d_eff) / 2.5, 0, 1)
                kind = np.where(wet, 3, types[k])
                if rough:
                    kind = np.where((~wet) & (nz2[y0:y1, x0:x1] > 0.25), types[(k + 9) % L], kind)
                b = np.where((kind == 0), 0.0, b)
                cur_bw = bw[y0:y1, x0:x1]
                upd = b > cur_bw
                cur_bw[upd] = b[upd]
                bt = btype[y0:y1, x0:x1]
                bt[upd] = kind[upd]
        if ribbon_mesh:
            idx = list(range(0, L, 2))
            if idx[-1] != L - 1:
                idx.append(L - 1)
            half = ribbon_section // 2
            for si in range(0, max(1, len(idx) - 1), half):
                sec = idx[max(0, si - 3):si + half + 4]  # each section runs 3 points into its neighbours so bends leave no gap
                if len(sec) < 2:
                    continue
                wk = float(max(wfac[k] for k in sec)) * width_px  # the widest point of the stretch: a wide plane under the banks is hidden, a narrow one leaves holes
                label = "CreekRibbon_%d_%02d" % (pi + 1, si // half)
                ribbons.append(["level.create_spline_actor", {
                    "label": label, "onConflict": "update", "pointType": "Curve",
                    "splinePoints": [{"x": float(pts[k][1] * cm), "y": float(pts[k][0] * cm), "z": float(zw[k])} for k in sec]}])
                ribbons.append(["level.build_spline_meshes", {
                    "actorLabel": label, "staticMesh": ribbon_mesh, "forwardAxis": "X", "spacing": float(2 * cm), "stretchToFit": True,
                    "scale": {"x": 1.0, "y": wk * 2 * cm * 1.35 / 100.0, "z": 1.0}, "collisionProfile": "NoCollision",
                    "generatorName": "CreekWater"}])
        step = 2
        for k in range(0, L - 1, step):
            if ribbon_mesh:
                break
            a, b2 = pts[k], pts[min(k + step, L - 1)]
            za, zb = zw[k], zw[min(k + step, L - 1)]
            dx, dy = (b2[1] - a[1]) * cm, (b2[0] - a[0]) * cm
            length = math.hypot(dx, dy)
            if length < 1:
                continue
            wk = float((wfac[k] + wfac[min(k + step, L - 1)]) / 2) * width_px
            water.append(["level.place_actor", {
                "actorClass": "StaticMeshActor", "staticMesh": "/Engine/BasicShapes/Plane", "material": material,
                "label": "Creek_%d_%03d" % (pi + 1, k), "onConflict": "rename",
                "location": {"x": float((a[1] + b2[1]) / 2 * cm), "y": float((a[0] + b2[0]) / 2 * cm), "z": float((za + zb) / 2)},
                "rotation": {"pitch": math.degrees(math.atan2(zb - za, length)), "yaw": math.degrees(math.atan2(dy, dx)), "roll": 0},
                "scale": {"x": length / 100.0 * 1.12, "y": wk * 2 * cm * 1.1 / 100.0, "z": 1}}])
        levels.append({"creek": pi + 1, "points": L, "start_px": [int(raw[0][0]), int(raw[0][1])], "end_px": [int(raw[-1][0]), int(raw[-1][1])],
                       "water_z_start_cm": float(zw[0]), "water_z_end_cm": float(zw[-1]),
                       "sections": {str(t): int((types == t).sum()) for t in range(5)} if bank_paint else {}})
    lake_calls = []
    lake_info = []
    if lakes:
        for pi, raw in enumerate(paths):
            sy, sx = int(raw[0][0]), int(raw[0][1])
            if min(sy, sx, n - 1 - sy, n - 1 - sx) < lake_margin_px or (sea_cm is not None and zcm[sy, sx] < sea_cm + 500.0):
                continue
            r = float(rng.uniform(*lake_px))
            depth = float(rng.uniform(*lake_depth_cm))
            reach = int(r * 1.6) + 3
            y0, y1, x0, x1 = max(0, sy - reach), min(n, sy + reach + 1), max(0, sx - reach), min(n, sx + reach + 1)
            dy, dx = yy[y0:y1, x0:x1] - sy, xx[y0:y1, x0:x1] - sx
            ang = np.arctan2(dy, dx)
            rr = r * (1 + 0.22 * np.cos(2 * ang + rng.uniform(0, 6.28)) + 0.14 * np.cos(3 * ang + rng.uniform(0, 6.28)) + 0.06 * nz[y0:y1, x0:x1])
            t = np.hypot(dy, dx) / np.maximum(rr, 0.5)
            cur = new[y0:y1, x0:x1] / raw_per_cm + z0
            ring = cur[(t > 1.0) & (t < 1.35)]
            wl = float(np.percentile(ring, 25)) if ring.size else float(zw_start(paths, pi))
            bowl = wl - depth * (1.0 - np.clip(t, 0, 1) ** 2)
            inside = t <= 1.0
            low = np.where(inside, np.minimum(cur, bowl), cur)
            new[y0:y1, x0:x1] = np.minimum(new[y0:y1, x0:x1], (low - z0) * raw_per_cm)
            mask[y0:y1, x0:x1][t <= 1.35] = 255
            if bank_paint:
                ring_w = np.clip((1.45 - t) / 0.4, 0, 1) * (t > 0.0)
                cur_bw = bw[y0:y1, x0:x1]
                upd = ring_w > cur_bw
                cur_bw[upd] = ring_w[upd]
                btype[y0:y1, x0:x1][upd] = np.where(inside, 3, 2)[upd]
            lake_info.append({"creek": pi + 1, "px": [sy, sx], "radius_px": r, "depth_cm": depth, "water_cm": wl})
            lake_calls.append(["level.place_actor", {
                "actorClass": "StaticMeshActor", "staticMesh": "/Engine/BasicShapes/Cylinder", "label": "Lake_%d" % (pi + 1), "onConflict": "update",
                "location": {"x": float(sx * cm), "y": float(sy * cm), "z": wl},
                "scale": {"x": 2.1 * r * cm / 100.0, "y": 2.1 * r * cm / 100.0, "z": 0.02}}])
    new16 = np.clip(np.round(new), 0, 65535).astype(np.uint16)
    Image.fromarray(new16).save(os.path.join(ue_dir, "heightmap16_creeks.png"))
    mask.tofile(os.path.join(ue_dir, "creek_mask.u8"))
    changed = np.argwhere(new16 != img.astype(np.uint16))
    carve = []
    for y0 in range(0, n, tile):
        for x0 in range(0, n, tile):
            y1, x1 = min(n - 1, y0 + tile - 1), min(n - 1, x0 + tile - 1)
            blk = new16[y0:y1 + 1, x0:x1 + 1]
            if (blk != base_img[y0:y1 + 1, x0:x1 + 1].astype(np.uint16)).any():
                carve.append(["landscape.set_height_region", {
                    "actorLabel": landscape, "region": {"minX": x0, "minY": y0, "maxX": x1, "maxY": y1},
                    "heightsBase64": base64.b64encode(blk.astype("<u2").tobytes()).decode()}])
    phases = [{"name": "carve", "calls": carve}]
    if bank_paint:
        phases.append(paint_phase(ue_dir, n, btype, bw, base_layers or (BASE_LAYERS + ["sand", "stone"] if layers_dir != ue_dir else BASE_LAYERS), tile, layers_dir, landscape))
        np.where(bw > 0.3, btype + 1, 0).astype(np.uint8).tofile(os.path.join(ue_dir, "creek_bank.u8"))
    if clean_prefix:
        water.insert(0, ["level.delete_actors", {"labelPrefix": clean_prefix}])
    if lake_material and lake_calls:
        lake_calls.append(["level.bulk_set_component_property", {"labelPrefix": "Lake_", "componentName": "StaticMeshComponent0", "propertyName": "OverrideMaterials", "value": [lake_material + "." + lake_material.rsplit("/", 1)[1]]}])
        lake_calls.append(["level.bulk_set_component_property", {"labelPrefix": "Lake_", "componentName": "StaticMeshComponent0", "propertyName": "CastShadow", "value": False}])
    water.extend(lake_calls)
    phases.append({"name": "water", "calls": water})
    if ribbon_mesh:
        phases.append({"name": "ribbon", "calls": ([["level.delete_actors", {"labelPrefix": "CreekRibbon_"}]] if clean_prefix else []) + ribbons})
    return {"creeks": levels, "lakes": lake_info, "pixel_cm": cm, "carved_vertices": int(len(changed)), "phases": phases}


def paint_phase(ue_dir, n, btype, bw, base_layers, tile, layers_dir=None, landscape="Landscape"):
    """Blend the bank section textures into the existing layer weights and return the add_layer + set_layer_weight_region calls.
    Every pixel sums to exactly 255 (largest-remainder rounding; the engine does not renormalise). A pixel whose source weights are
    all zero stays all zero."""
    names = list(base_layers) + [v for v in BANK_LAYERS.values() if v not in base_layers]
    W = np.zeros((len(names), n, n))
    for i, nm in enumerate(base_layers):
        f = os.path.join(layers_dir or ue_dir, nm + ".u8")
        W[i] = np.fromfile(f, np.uint8).reshape(n, n) / 255.0
    W[:len(base_layers)] *= (1 - bw)[None]
    for code, nm in BANK_LAYERS.items():
        W[names.index(nm)] += np.where(btype == code, bw, 0.0)
    total = W.sum(axis=0)
    W /= np.maximum(total, 1e-6)[None]
    out = round_to_total(W * 255.0, np.where(total > 0, 255.0, 0.0))
    os.makedirs(os.path.join(ue_dir, "with_creeks"), exist_ok=True)
    for i, nm in enumerate(names):
        out[i].tofile(os.path.join(ue_dir, "with_creeks", nm + ".u8"))
    calls = [["landscape.add_layer", {"layerName": nm, "landscapeName": landscape}] for nm in names if nm not in base_layers]
    for y0 in range(0, n, tile):
        for x0 in range(0, n, tile):
            y1, x1 = min(n - 1, y0 + tile - 1), min(n - 1, x0 + tile - 1)
            if bw[y0:y1 + 1, x0:x1 + 1].max() <= 0:
                continue
            for i, nm in enumerate(names):
                calls.append(["landscape.set_layer_weight_region", {
                    "layerName": nm, "actorLabel": landscape,
                    "region": {"minX": x0, "minY": y0, "maxX": x1, "maxY": y1},
                    "weightsBase64": base64.b64encode(out[i][y0:y1 + 1, x0:x1 + 1].tobytes()).decode()}])
    return {"name": "paint", "calls": calls, "layers": names}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ue-dir", required=True)
    ap.add_argument("--size-m", type=float, required=True)
    ap.add_argument("--z0", type=float, required=True)
    ap.add_argument("--raw-per-cm", type=float, required=True)
    ap.add_argument("--material", dest="plane_material", required=True,
                    help="water material for the plain Plane actors (or plane_water_material in the --project profile; never a Water-plugin material)")
    ap.add_argument("--landscape", required=True, help="landscape actor label (or set landscape in the --project profile)")
    ap.add_argument("--keep", type=int, default=700, help="approx. number of channel cells to keep (more = more creeks)")
    ap.add_argument("--max-creeks", type=int, default=4)
    ap.add_argument("--depth-cm", type=float, default=220.0)
    ap.add_argument("--width-px", type=float, default=1.3, help="creek half-width in landscape pixels")
    ap.add_argument("--bank-px", type=float, default=3.5, help="bank reach in landscape pixels")
    ap.add_argument("--meander-px", type=float, default=2.5, help="sideways wander of each creek around its flow line (with --irregular)")
    ap.add_argument("--irregular", action="store_true", help="vary width, depth, bank slope and bank edge along the creek")
    ap.add_argument("--bank-paint", action="store_true", help="paint pebble / sand / mud / stone / grass bank sections (needs the layer .u8 files)")
    ap.add_argument("--baseline", default=None, help="heightmap png currently in the editor, e.g. heightmap16_creeks.png")
    ap.add_argument("--clean", default=None, metavar="PREFIX", help="delete level actors with this label prefix first, e.g. Creek_")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--ribbon-mesh", default=None, help="static mesh asset (plane with the water material): lay a continuous spline ribbon instead of separate planes")
    ap.add_argument("--heights", default="heightmap16.png", help="source heightmap png (the island: heightmap16_island.png)")
    ap.add_argument("--layers-dir", default=None, help="directory with the base layer .u8 weights (the island: island_layers)")
    ap.add_argument("--sea-cm", type=float, default=None, help="sea level in cm; cells under it are sea and end the creeks")
    ap.add_argument("--lakes", action="store_true", help="a lake of random size and depth where a creek head is inside the map")
    ap.add_argument("--lake-material", default=None, help="water material for the lake discs, e.g. /Game/WaterMaterials/Materials/M_Lake")
    ap.add_argument("--lake-px", nargs=2, type=float, default=[4.0, 9.0], metavar=("MIN", "MAX"))
    ap.add_argument("--lake-depth-cm", nargs=2, type=float, default=[350.0, 900.0], metavar=("MIN", "MAX"))
    ap.add_argument("--rough", action="store_true", help="two-scale bank edge noise and interleaved bank sections (banks never straight)")
    ap.add_argument("--out", required=True)
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    out = build(a.ue_dir, a.size_m, a.z0, a.raw_per_cm, a.plane_material, keep=a.keep, max_creeks=a.max_creeks, depth_cm=a.depth_cm,
                width_px=a.width_px, bank_px=a.bank_px, irregular=a.irregular, bank_paint=a.bank_paint, baseline=a.baseline,
                clean_prefix=a.clean, seed=a.seed, ribbon_mesh=a.ribbon_mesh, heights=a.heights, layers_dir=a.layers_dir, sea_cm=a.sea_cm,
                lakes=a.lakes, lake_material=a.lake_material, lake_px=tuple(a.lake_px), lake_depth_cm=tuple(a.lake_depth_cm), rough=a.rough, meander_px=a.meander_px, landscape=a.landscape)
    json.dump(out, open(a.out, "w"))
    print("wrote %s: %d creeks %s, %d lakes, %d vertices carved, phases %s" % (a.out, len(out["creeks"]), [c["points"] for c in out["creeks"]],
          len(out["lakes"]), out["carved_vertices"], ", ".join("%s=%d" % (p["name"], len(p["calls"])) for p in out["phases"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
