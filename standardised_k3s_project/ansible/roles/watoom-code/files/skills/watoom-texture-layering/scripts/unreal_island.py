#!/usr/bin/env python3
"""watoom-texture-layering: turn a landscape heightmap into an island with a mountain (host-side; numpy + pillow).

Reshapes the heightmap that is already in the editor (default heightmap16.png in --ue-dir, the ORIGINAL map without creeks):
  - the world edge is randomised into a coast: a closed outline radius R(theta) with random harmonics, so the shape is never a circle,
  - the land falls to a sea floor outside the outline; the sea level is a flat plane (--sea-cm, default just under the 5th percentile),
  - the shore is a gentle concave BEACH over --beach-px pixels on most of the coast and a steep CLIFF (a raised lip over --cliff-px pixels)
    on --cliff-arcs random arcs, so the coast changes character as you walk round it,
  - a MOUNTAIN is raised in the middle (--mountain-cm high, --mountain-px wide, ridged noise on top),
  - layer weights are written for sand (seabed + beach), rock and stone (cliffs, steep slopes, mountain top) into <ue-dir>/island_layers/<layer>.u8
    on top of the existing grass/dry_grass/dirt/rock/mud weights, each pixel's weights summing to 1.

  unreal_island.py --ue-dir ue --size-m 4000 --z0 3677.7 --raw-per-cm 4.4387 --seed 5 --out island_calls.json

Outputs: heightmap16_island.png, island_layers/*.u8, island_preview.png (shaded relief, blue sea, tan beach, grey rock) and island_calls.json with phases
  carve   landscape.set_height_region tiles that differ from --baseline (the heightmap now in the editor; default heightmap16_pads.png)
  paint   landscape.add_layer (sand, stone) + landscape.set_layer_weight_region for every touched tile and layer
  ocean   one plane --ocean-km wide (default 30 km: it must reach the horizon, otherwise the sky starts at the island's edge) at the sea level with --ocean-material
Run order for a whole new island: island -> creeks (reads heightmap16_island.png and island_layers/, see unreal_creeks.py --heights/--layers-dir)
-> clear the old scenery (foliage.remove_type_from_level) -> scenery scatter -> ground fit for buildings.
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

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_LAYERS = ["grass", "dry_grass", "dirt", "rock", "mud"]
ISLAND_LAYERS = BASE_LAYERS + ["sand", "stone"]


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def value_noise(rng, n, cell):
    g = rng.random((n // cell + 3, n // cell + 3)).astype(np.float32)
    big = Image.fromarray((g * 255).astype(np.uint8)).resize((n + cell * 2, n + cell * 2), Image.BICUBIC)
    return np.asarray(big, float)[:n, :n] / 127.5 - 1.0


def coast_radius(theta, r0, wobble, rng, harmonics=11):
    """Closed outline radius with random harmonics (amplitude falls with the harmonic number): low ones make headlands and bays, high ones make a ragged shore."""
    r = np.ones_like(theta)
    for k in range(2, harmonics + 1):
        r += wobble * rng.uniform(0.4, 1.0) / (k ** 0.8) * np.cos(k * theta + rng.uniform(0, 2 * math.pi))
    return r0 * r


def soft_limit(r, knee, limit):
    """Identity below the knee, then a smooth approach to the limit (a hard clamp cuts straight edges, which is what made the island look square)."""
    over = np.maximum(r - knee, 0.0)
    return np.where(r <= knee, r, knee + (limit - knee) * np.tanh(over / max(limit - knee, 1e-6)))


def build(heights, size_m, z0, raw_per_cm, seed=5, sea_cm=None, radius=0.37, wobble=0.55, aspect=None, beach_px=14.0, cliff_px=3.0, cliff_cm=1100.0,
          cliff_arcs=2, mountain_cm=9000.0, mountain_px=80.0, mountain_xy=None, floor_cm=900.0, layers=None, beach_cm=450.0):
    """heights: N x N uint16 (original map). layers: {name: N x N float 0..1} base weights. Returns dict(heights, sea_cm, masks, layers, preview)."""
    rng = np.random.default_rng(seed)
    h = np.asarray(heights).astype(float)
    n = h.shape[0]
    cm = size_m * 100.0 / (n - 1)
    zb = h / raw_per_cm + z0
    sea = float(np.percentile(zb, 5) - 150.0) if sea_cm is None else float(sea_cm)
    yy, xx = np.mgrid[0:n, 0:n].astype(float)
    c = (n - 1) / 2.0
    # mountain first, so the coast and the creeks see it
    mx, my = (c + rng.uniform(-0.06, 0.06) * n, c + rng.uniform(-0.06, 0.06) * n) if mountain_xy is None else mountain_xy
    d = np.hypot(xx - mx, yy - my)
    ridge = 1.0 - np.abs(value_noise(rng, n, 9))
    fall = (1.0 - smoothstep(d / mountain_px)) ** 1.25
    zb = zb + mountain_cm * fall * (0.72 + 0.28 * ridge)
    # coast
    phi = rng.uniform(0, math.pi)  # the island is stretched along a random axis, so it is longer than it is wide
    asp = float(rng.uniform(1.0, 1.4)) if aspect is None else float(aspect)
    ca, sa = math.cos(phi), math.sin(phi)
    u = (xx - c) * ca + (yy - c) * sa
    v = (-(xx - c) * sa + (yy - c) * ca) * asp
    theta = np.arctan2(v, u)
    wob = value_noise(rng, n, 30) * 0.045 * n + value_noise(rng, n, 11) * 0.014 * n  # domain warp: bays and ragged shore, never a clean curve
    r = np.hypot(u, v) + wob
    R = soft_limit(coast_radius(theta, radius * n, wobble * 0.5, rng), 0.34 * n, 0.455 * n)  # the coast never reaches the map edge, without cutting straight edges
    d_in = R - r  # pixels inside the outline
    cliff = np.zeros_like(theta)
    for _ in range(cliff_arcs):
        a0, wd = rng.uniform(-math.pi, math.pi), rng.uniform(0.45, 0.9)
        dth = np.abs((theta - a0 + math.pi) % (2 * math.pi) - math.pi)
        cliff = np.maximum(cliff, smoothstep(1.0 - dth / wd))
    width = beach_px * (1.0 - cliff) + cliff_px * cliff
    s = smoothstep(d_in / np.maximum(width, 0.5))
    beach_z = sea + (zb - sea) * s ** 2.0  # concave: gentle at the waterline
    lip = cliff * cliff_cm * smoothstep(d_in / (cliff_px * 1.5)) * (1.0 - smoothstep((d_in - cliff_px * 6.0) / (cliff_px * 6.0)))
    land = np.maximum(beach_z, np.where(d_in > 0, sea - 40.0 * (1 - s), sea)) + np.where(d_in > 0, lip, 0.0)
    floor = sea - 120.0 - floor_cm * smoothstep(-d_in / 26.0)
    z = np.where(d_in > 0, land, floor)
    z = np.maximum(z, z0 + 20.0)
    gy, gx = np.gradient(z, cm)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    under = z < sea + 20.0
    beach = (~under) & (z < sea + beach_cm) & (cliff < 0.5)
    cliffm = (~under) & (d_in > 0) & (d_in < cliff_px * 5.0) & (cliff > 0.35)
    # layer weights
    layers = dict(layers or {})
    for nm in BASE_LAYERS:
        layers.setdefault(nm, np.zeros((n, n)) + (1.0 if nm == "grass" else 0.0))
    W = {nm: np.asarray(layers[nm], float).copy() for nm in BASE_LAYERS}
    W["sand"] = np.zeros((n, n))
    W["stone"] = np.zeros((n, n))
    over = {"sand": np.where(under, 1.0, np.where(beach, 1.0 - smoothstep((z - sea - 80.0) / max(1.0, beach_cm - 80.0)) * 0.7, 0.0)),
            "rock": np.maximum(np.where(cliffm, 1.0, 0.0), smoothstep((slope - 28.0) / 12.0)),
            "stone": np.where(cliffm, 0.4, 0.0) + 0.6 * smoothstep((slope - 42.0) / 8.0) + 0.5 * fall * smoothstep((z - (sea + 5200.0)) / 3000.0)}
    keep = np.ones((n, n))
    for nm in ("sand", "rock", "stone"):
        o = np.clip(over[nm], 0.0, 1.0)
        W[nm] = W[nm] + o
        keep = keep * (1.0 - o)
    for nm in BASE_LAYERS:
        if nm != "rock":
            W[nm] = W[nm] * keep
    tot = np.maximum(sum(W.values()), 1e-6)
    for nm in W:
        W[nm] = W[nm] / tot
    raw = np.clip(np.round((z - z0) * raw_per_cm), 0, 65535).astype(np.uint16)
    # preview
    shade = np.clip(0.5 + (gx - gy) * 2.2, 0.15, 1.0)
    rgb = np.zeros((n, n, 3))
    rgb[...] = np.array([0.35, 0.55, 0.28]) * shade[..., None]
    rgb[beach] = np.array([0.85, 0.78, 0.55]) * shade[beach][:, None]
    rgb[(W["rock"] + W["stone"]) > 0.5] = np.array([0.5, 0.5, 0.5]) * shade[(W["rock"] + W["stone"]) > 0.5][:, None]
    rgb[under] = np.array([0.1, 0.3, 0.6]) * (0.6 + 0.4 * np.clip((z[under] - (sea - floor_cm)) / floor_cm, 0, 1))[:, None]
    return {"heights": raw, "sea_cm": sea, "z": z, "slope": slope, "masks": {"under": under, "beach": beach, "cliff": cliffm}, "layers": W,
            "preview": np.clip(rgb * 255, 0, 255).astype(np.uint8), "mountain": (mx, my), "pixel_cm": cm}


def calls_for(res, baseline, ue_dir, n, landscape="Landscape", tile=127, ocean_material=None, size_m=4000.0, sea_label="Ocean", ocean_km=30.0):
    new, old = res["heights"], np.asarray(baseline)
    carve, paint = [], []
    for y0 in range(0, n, tile):
        for x0 in range(0, n, tile):
            y1, x1 = min(n - 1, y0 + tile - 1), min(n - 1, x0 + tile - 1)
            blk = new[y0:y1 + 1, x0:x1 + 1]
            if (blk != old[y0:y1 + 1, x0:x1 + 1]).any():
                carve.append(["landscape.set_height_region", {"actorLabel": landscape, "region": {"minX": x0, "minY": y0, "maxX": x1, "maxY": y1},
                                                              "heightsBase64": base64.b64encode(blk.astype("<u2").tobytes()).decode()}])
    paint.extend([["landscape.add_layer", {"layerName": nm, "landscapeName": landscape}] for nm in ("sand", "stone")])
    out = {nm: np.clip(np.round(res["layers"][nm] * 255), 0, 255).astype(np.uint8) for nm in ISLAND_LAYERS}
    # make every pixel sum to 255 exactly (rounding), the largest layer takes the remainder
    s = sum(out[nm].astype(int) for nm in ISLAND_LAYERS)
    big = np.argmax(np.stack([out[nm] for nm in ISLAND_LAYERS]), axis=0)
    for i, nm in enumerate(ISLAND_LAYERS):
        out[nm] = np.clip(out[nm].astype(int) + np.where(big == i, 255 - s, 0), 0, 255).astype(np.uint8)
    os.makedirs(os.path.join(ue_dir, "island_layers"), exist_ok=True)
    for nm in ISLAND_LAYERS:
        out[nm].tofile(os.path.join(ue_dir, "island_layers", nm + ".u8"))
    for y0 in range(0, n, tile):
        for x0 in range(0, n, tile):
            y1, x1 = min(n - 1, y0 + tile - 1), min(n - 1, x0 + tile - 1)
            for nm in ISLAND_LAYERS:
                paint.append(["landscape.set_layer_weight_region", {"layerName": nm, "actorLabel": landscape,
                                                                    "region": {"minX": x0, "minY": y0, "maxX": x1, "maxY": y1},
                                                                    "weightsBase64": base64.b64encode(out[nm][y0:y1 + 1, x0:x1 + 1].tobytes()).decode()}])
    ocean = []
    if ocean_material:
        c = size_m * 50.0
        ocean = [["level.place_actor", {"actorClass": "StaticMeshActor", "staticMesh": "/Engine/BasicShapes/Plane", "label": sea_label, "onConflict": "update",
                                        "location": {"x": c, "y": c, "z": float(res["sea_cm"])}, "scale": {"x": ocean_km * 1000.0, "y": ocean_km * 1000.0, "z": 1.0}}],  # a 100 cm plane: 30 km wide reaches the horizon
                 ["level.set_actor_material", {"actorLabel": sea_label, "materialPath": ocean_material, "slotIndex": 0}]]
    return [{"name": "carve", "calls": carve}, {"name": "paint", "calls": paint}, {"name": "ocean", "calls": ocean}]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ue-dir", required=True)
    ap.add_argument("--source", default="heightmap16.png")
    ap.add_argument("--baseline", default="heightmap16_pads.png")
    ap.add_argument("--size-m", type=float, required=True)
    ap.add_argument("--z0", type=float, required=True)
    ap.add_argument("--raw-per-cm", type=float, required=True)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--sea-cm", type=float, default=None)
    ap.add_argument("--radius", type=float, default=0.37, help="mean island radius as a fraction of the map width")
    ap.add_argument("--wobble", type=float, default=0.55)
    ap.add_argument("--aspect", type=float, default=None, help="stretch along a random axis (default random 1.0 to 1.4)")
    ap.add_argument("--beach-px", type=float, default=14.0)
    ap.add_argument("--cliff-px", type=float, default=3.0)
    ap.add_argument("--cliff-cm", type=float, default=1100.0)
    ap.add_argument("--cliff-arcs", type=int, default=2)
    ap.add_argument("--mountain-cm", type=float, default=9000.0)
    ap.add_argument("--mountain-px", type=float, default=80.0)
    ap.add_argument("--ocean-material", default=None)
    ap.add_argument("--ocean-km", type=float, default=30.0, help="ocean plane width; it must reach the horizon (and stay inside the sky dome, 20 km radius)")
    ap.add_argument("--landscape", required=True, help="landscape actor label (or set landscape in the --project profile)")
    ap.add_argument("--out", required=True)
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    img = np.asarray(Image.open(os.path.join(a.ue_dir, a.source)))
    n = img.shape[0]
    layers = {}
    for nm in BASE_LAYERS:
        f = os.path.join(a.ue_dir, nm + ".u8")
        if os.path.exists(f) and os.path.getsize(f) == n * n:
            layers[nm] = np.fromfile(f, np.uint8).reshape(n, n) / 255.0
    res = build(img, a.size_m, a.z0, a.raw_per_cm, a.seed, a.sea_cm, a.radius, a.wobble, a.aspect, a.beach_px, a.cliff_px, a.cliff_cm, a.cliff_arcs,
                a.mountain_cm, a.mountain_px, layers=layers)
    baseline = np.asarray(Image.open(os.path.join(a.ue_dir, a.baseline))) if os.path.exists(os.path.join(a.ue_dir, a.baseline)) else img
    Image.fromarray(res["heights"]).save(os.path.join(a.ue_dir, "heightmap16_island.png"))
    Image.fromarray(res["preview"]).resize((n * 2, n * 2), Image.NEAREST).save(os.path.join(a.ue_dir, "island_preview.png"))
    for nm in ("under", "beach", "cliff"):
        (res["masks"][nm] * 255).astype(np.uint8).tofile(os.path.join(a.ue_dir, "island_%s.u8" % nm))  # 0 / 255 like every other mask here
    phases = calls_for(res, baseline, a.ue_dir, n, a.landscape, ocean_material=a.ocean_material, size_m=a.size_m, ocean_km=a.ocean_km)
    json.dump({"sea_cm": res["sea_cm"], "mountain_px": list(res["mountain"]), "pixel_cm": res["pixel_cm"], "phases": phases}, open(a.out, "w"))
    print("island: sea %.0f cm, mountain at px (%.0f, %.0f), land %.0f%%, beach %.1f%%, cliff %.1f%%; wrote %s: %s" % (
        res["sea_cm"], res["mountain"][0], res["mountain"][1], 100 * (~res["masks"]["under"]).mean(), 100 * res["masks"]["beach"].mean(),
        100 * res["masks"]["cliff"].mean(), a.out, ", ".join("%s=%d" % (p["name"], len(p["calls"])) for p in phases)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
