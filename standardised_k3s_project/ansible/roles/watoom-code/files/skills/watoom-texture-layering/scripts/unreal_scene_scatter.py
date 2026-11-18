#!/usr/bin/env python3
"""watoom-texture-layering: write the ue-mcp calls that dress a layered Unreal landscape with scenery (host-side; numpy + pillow).

Input is what unreal_landscape_export.py already wrote (`<layer>.u8` weights and `heightmap16.png`, N x N) plus a small recipe
that names the meshes. Output is scene_calls.json: ordered `phases`, each a list of `[method, args]` for the watoom-ue tool
(`foliage.create_type`, `foliage.set_settings`, `foliage.add_type_to_level`, `foliage.add_instances`, `level.place_actor`).
Run the phases in order, in batches of ~25 calls, and look at a capture after each phase.

  unreal_scene_scatter.py --ue-dir ue --size-m 4000 --min-z 3694.9 --max-z 18431.5 --recipe recipe.json --out scene_calls.json

--min-z is the world Z (cm) of raw height 0 and --max-z the world Z of raw 65535 (ground z = min_z + raw / 65535 * (max_z - min_z)):
pass --min-z <z0> --max-z <z0 + 65535 / raw_per_cm>. On a heightmap that unreal_landscape_export.py normalised to the terrain's own
range these equal the import minHeight / maxHeight; landscape.get_info bounds (minZ / maxZ) are only right in that case, never after
a carve or for live heights. --size-m is the terrain width in metres. This script does not read z0, raw_per_cm or sea_cm from the
--project profile (only size_m); the sea is kept free through island_under.u8, not through a sea level.
Every <name>.u8 in --ue-dir and --layers-dir must be N x N like the heightmap; a file of another size is refused (it used to be
skipped silently, which dropped the creek or sea mask and put scenery in the water).

recipe.json (all paths are /Game/... assets found with asset.search):
  {"package": "/Game/ZAS/Foliage", "grass": ["<mesh>", ...], "trees": [...], "bushes": [...], "flowers": [...], "rocks": [...],
   "village": {"houses": ["<BP path>_C", ...], "props": ["<BP path>_C", ...]}, "seed": 7,
   "foliage_scale": {"bushes": [0.3, 0.5], "rocks": [0.25, 0.6]}, "house_scale": 0.43, "prop_scale": 0.5,
   "grass_layers": ["grass"], "forest_layers": ["grass"], "grass_spacing_px": 7, "forest_count": 260, "rock_count": 140}

Rules this encodes (each cost a wrong picture once):
  * Trees, bushes and rocks are placed with alignToNormal OFF and a small negative Z offset: aligning to the slope tilts the
    trunk so one side floats and the other sinks. Instances keep the tilt they were placed with, so after changing a type's
    settings remove its instances (foliage.remove_type_from_level with force) and place again.
  * Grass must cover most of the green ground, so it is scattered on a regular grid over every pixel whose grass weight is
    over 40 % (not on a few sites). Test one mesh at eye level first: grass whose material uses landscape ground projection
    (Wildwood SM_Grass_01) renders black.
  * Creek banks (needs creek_mask.u8; creek_bank.u8 from unreal_creeks.py --bank-paint): trees and bushes are placed in a band
    just outside the channel (creek_tree_count 380, creek_tree_band_px 9; each add_instances call costs seconds on a full
    level, so raise creek_trees_per_call and lower creek_tree_calls / creek_tree_count for speed), rocks on the pebble and stone bank sections.
  * creek_biomes (needs creek_mask.u8): "interspersed natural planting" along the creeks. The creek is cut into square sections of
    `section_m`; each section is given one biome (palm_fern, reedy, bamboo, banana, pandanus, rocky, ...) so whole stretches read as
    one habitat, and `mix` (0..1) of the sites take a random other biome so the edges are not hard lines. Recipe:
      "creek_biomes": {"section_m": 150, "band_px": 8, "gap_px": 1, "count": 600, "sep_px": 2, "radius_cm": 800, "mix": 0.2,
                       "biomes": [{"name": "palm_fern", "meshes": ["/Game/.../SM_Fern"], "scale": [0.6, 1.1], "per_site": 4}, ...]}
    Every mesh of every biome gets its foliage type, upright (no align to normal) with a small sink, like trees and bushes.
  * Ground z comes from the heightmap, not from a guess; the village goes on the flattest large patch.
"""
import argparse
import json
import math
import os
import random
import sys

import numpy as np
from PIL import Image
from os.path import abspath as _abspath, dirname as _dirname  # noqa: E402
sys.path.insert(0, _dirname(_abspath(__file__)))  # so `python3 -I script.py` finds ue_project
import ue_project  # noqa: E402


def load_masks(ue_dir, n, layers_dir=None):
    """Every <name>.u8 in ue_dir (layer weights, creek_mask, creek_bank, island_under / beach / cliff); layers_dir (for example with_creeks) overrides the layer names."""
    masks = {}
    for d in [ue_dir] + ([layers_dir] if layers_dir else []):
        for f in os.listdir(d):
            if f.endswith(".u8"):
                a = np.frombuffer(open(os.path.join(d, f), "rb").read(), np.uint8)
                if a.size != n * n:
                    raise ValueError("%s holds %d bytes but the heightmap is %d x %d (%d bytes): regenerate the mask at the heightmap size or move the file away"
                                     % (os.path.join(d, f), a.size, n, n, n * n))
                masks[f[:-3]] = a.reshape(n, n) / 255.0
    return masks


def box(a, r):
    k = 2 * r + 1
    p = np.pad(a, r, mode="edge")
    s = np.lib.stride_tricks.sliding_window_view(p, (k, k))
    return s.mean(axis=(2, 3))


def grow(mask, r):
    """Boolean dilation by r pixels (square steps), used to get the band around a creek."""
    out = mask.copy()
    for _ in range(r):
        p = np.pad(out, 1)
        out = out | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
    return out


def pick(mask, count, minsep, rng):
    ys, xs = np.nonzero(mask)
    out = []
    for i in rng.permutation(len(ys)):
        y, x = int(ys[i]), int(xs[i])
        if all((y - b) ** 2 + (x - a) ** 2 >= minsep ** 2 for b, a in out):
            out.append((y, x))
        if len(out) >= count:
            break
    return out


def ftype(pkg, mesh):
    return "%s/FT_%s" % (pkg, mesh.rsplit("/", 1)[-1])


def build(ue_dir, size_m, min_z, max_z, recipe, seed=7, heights="heightmap16.png", layers_dir=None):
    img = np.asarray(Image.open(os.path.join(ue_dir, heights)), float) / 65535.0
    n = img.shape[0]
    cm = size_m * 100.0 / (n - 1)
    masks = load_masks(ue_dir, n, layers_dir)
    rng = np.random.default_rng(recipe.get("seed", seed))
    rnd = random.Random(recipe.get("seed", seed))
    pkg = recipe.get("package", "/Game/Scenery/Foliage")
    hm = img * (max_z - min_z)
    slope = np.degrees(np.arctan(np.hypot(*np.gradient(hm, cm))))
    edge = np.zeros((n, n), bool)
    edge[20:-20, 20:-20] = True

    def wsum(layers):
        return sum(masks[k] for k in layers if k in masks) if any(k in masks for k in layers) else np.zeros((n, n))

    def world(p):
        return {"x": float(p[1] * cm), "y": float(p[0] * cm)}

    def gz(p):
        return float(min_z + img[p[0], p[1]] * (max_z - min_z))

    creek = masks.get("creek_mask", np.zeros((n, n))) > 0.5  # written by unreal_creeks.py; keeps scenery out of the water
    under = masks.get("island_under", np.zeros((n, n))) > 0.5  # written by unreal_island.py: the sea, the beach and the cliff foot stay free of trees and grass
    beach = masks.get("island_beach", np.zeros((n, n))) > 0.5
    cliff = masks.get("island_cliff", np.zeros((n, n))) > 0.5
    edge = edge & ~creek & ~grow(under, 2) & ~beach & ~cliff
    kinds = {k: recipe.get(k, []) for k in ("grass", "trees", "bushes", "flowers", "rocks", "pebbles")}
    types = []
    for kind, meshes in kinds.items():
        for m in meshes:
            types.append((kind, m))
    cb = recipe.get("creek_biomes") or {}
    biomes = [b for b in cb.get("biomes", []) if b.get("meshes")]
    biome_scale = {}
    for b in biomes:
        for m in b["meshes"]:
            types.append(("biome", m))
            biome_scale[m] = b.get("scale", [0.6, 1.0])
    p_types = [["foliage.create_type", {"meshPath": m, "name": "FT_" + m.rsplit("/", 1)[-1], "packagePath": pkg, "onConflict": "skip"}] for _, m in types]
    p_settings = []
    for kind, m in types:
        s = {"AlignToNormal": "True" if kind in ("grass", "flowers") else "False"}
        if kind == "grass":
            s.update({"Scaling": "Uniform", "ScaleX": "(Min=%.1f,Max=%.1f)" % tuple(recipe.get("grass_scale", [1.4, 2.2])),
                      "CullDistance": "(Min=0,Max=%d)" % int(recipe.get("grass_cull_cm", 15000))})
        fs = (recipe.get("foliage_scale") or {}).get(kind)
        if fs and kind != "grass":
            s.update({"Scaling": "Uniform", "ScaleX": "(Min=%.2f,Max=%.2f)" % (fs[0], fs[1])})
        if kind == "biome":
            lo_s, hi_s = biome_scale[m]
            s.update({"Scaling": "Uniform", "ScaleX": "(Min=%.2f,Max=%.2f)" % (lo_s, hi_s), "RandomPitchAngle": "0.0", "ZOffset": "(Min=-10.0,Max=-2.0)"})
        if kind in ("trees", "bushes", "rocks", "pebbles"):
            lo, hi = (-40.0, -10.0) if kind == "rocks" else (-8.0, -2.0) if kind == "pebbles" else (-15.0, -5.0)
            s.update({"RandomPitchAngle": "0.0", "ZOffset": "(Min=%.1f,Max=%.1f)" % (lo, hi)})
        p_settings.append(["foliage.set_settings", {"foliageTypePath": ftype(pkg, m), "settings": s}])
    p_level = [["foliage.add_type_to_level", {"foliageTypePath": ftype(pkg, m)}] for _, m in types]
    p_clear = [["foliage.remove_type_from_level", {"foliageTypePath": ftype(pkg, m), "force": True}] for _, m in types] if recipe.get("clear_first") else []

    def add(kind, site, radius, count):
        m = rnd.choice(kinds[kind])
        return ["foliage.add_instances", {"foliageTypePath": ftype(pkg, m), "center": {"x": site["x"], "y": site["y"], "z": 0},
                                          "radius": radius, "count": count, "seed": rnd.randint(1, 10 ** 6)}]

    grass_w = wsum(recipe.get("grass_layers", ["grass"]))
    forest_w = wsum(recipe.get("forest_layers", ["grass"]))
    s20 = box(slope, min(20, n // 10))
    vi = np.unravel_index(np.argmin(np.where(edge & (hm > hm.min() + 5) & (hm < np.percentile(hm, 80)), s20, 99)), s20.shape)
    far = np.hypot(*(np.indices((n, n)) - np.array(vi)[:, None, None]))

    sp = int(recipe.get("grass_spacing_px", 7))
    p_grass = []
    if kinds["grass"]:
        for y in range(sp, n - sp, sp):
            for x in range(sp, n - sp, sp):
                if grass_w[y, x] > 0.4 and slope[y, x] < 30 and far[y, x] > 6 and not creek[y, x] and not under[y, x] and not beach[y, x]:
                    for _ in range(2):
                        p_grass.append(add("grass", world((y, x)), sp * cm * 0.6, int(recipe.get("grass_count", 350))))
    p_forest = []
    if kinds["trees"]:
        for p in pick(edge & (forest_w > 0.5) & (slope < 12) & (far > 40), int(recipe.get("forest_count", 260)), int(recipe.get("forest_sep_px", 11)), rng):
            s = world(p)
            for _ in range(int(recipe.get("tree_calls", 3))):
                p_forest.append(add("trees", s, 8000, int(recipe.get("trees_per_call", 7))))
            if kinds["bushes"]:
                for _ in range(int(recipe.get("bush_calls", 3))):
                    p_forest.append(add("bushes", s, 9000, int(recipe.get("bushes_per_call", 12))))
    p_rocks = []
    if kinds["rocks"]:
        for p in pick(edge & ((slope > 6) | (masks.get("rock", np.zeros((n, n))) > 0.4)), int(recipe.get("rock_count", 140)), 9, rng):
            for _ in range(2):
                p_rocks.append(add("rocks", world(p), 4500, int(recipe.get("rocks_per_call", 4))))
    # trees and bushes line the creek: a band just outside the carved channel; rocks sit on the pebble / stone bank sections
    p_creek_trees, p_creek_rocks, p_biomes = [], [], []
    bank = np.zeros((n, n), np.uint8)
    bf = os.path.join(ue_dir, "creek_bank.u8")
    if os.path.exists(bf) and os.path.getsize(bf) == n * n:
        bank = np.fromfile(bf, np.uint8).reshape(n, n)
    if creek.any():
        inner = grow(creek, int(recipe.get("creek_tree_gap_px", 1)))
        band = grow(creek, int(recipe.get("creek_tree_band_px", 9))) & ~inner & (slope < 28) & (far > 20)
        band[:20, :] = band[-20:, :] = False
        band[:, :20] = band[:, -20:] = False
        if kinds["trees"]:
            for p in pick(band, int(recipe.get("creek_tree_count", 380)), int(recipe.get("creek_tree_sep_px", 3)), rng):
                for _ in range(int(recipe.get("creek_tree_calls", 2))):
                    p_creek_trees.append(add("trees", world(p), 1500, int(recipe.get("creek_trees_per_call", 3))))
                if kinds["bushes"]:
                    p_creek_trees.append(add("bushes", world(p), 2000, int(recipe.get("creek_bushes_per_site", 6))))
        if kinds["rocks"]:
            rockbank = (bank == 2) | (bank == 5)  # pebble / stone sections; they lie inside the creek mask (channel + bank), never on the wet edge
            for p in pick(rockbank, int(recipe.get("creek_rock_count", 160)), 2, rng):
                p_creek_rocks.append(add("rocks", world(p), 1200, int(recipe.get("creek_rocks_per_site", 3))))
        if biomes:
            cell = max(2, int(cb.get("section_m", 150) * 100.0 / cm))
            bband = grow(creek, int(cb.get("band_px", 8))) & ~grow(creek, int(cb.get("gap_px", 1))) & (slope < 32) & (far > 20)
            bband[:20, :] = bband[-20:, :] = False
            bband[:, :20] = bband[:, -20:] = False
            section = {}

            def biome_at(p):
                key = (p[0] // cell, p[1] // cell)
                if key not in section:
                    section[key] = rnd.randrange(len(biomes))
                i = section[key]
                if rnd.random() < float(cb.get("mix", 0.2)):
                    i = rnd.randrange(len(biomes))
                return biomes[i]

            for p in pick(bband, int(cb.get("count", 600)), int(cb.get("sep_px", 2)), rng):
                b = biome_at(p)
                site = world(p)
                p_biomes.append(["foliage.add_instances", {"foliageTypePath": ftype(pkg, rnd.choice(b["meshes"])), "center": {"x": site["x"], "y": site["y"], "z": 0},
                                                          "radius": int(cb.get("radius_cm", 800)), "count": int(b.get("per_site", 4)), "seed": rnd.randint(1, 10 ** 6)}])
    p_coast, p_pebbles = [], []
    if kinds["rocks"]:  # boulders where the island meets the sea: the cliff foot and the beach edge, plus a scatter on the beach
        coast = (cliff | beach | (grow(under, 3) & ~under)) & ~creek
        coast[:12, :] = coast[-12:, :] = False
        coast[:, :12] = coast[:, -12:] = False
        for p in pick(coast, int(recipe.get("coast_rock_count", 160)), int(recipe.get("coast_rock_sep_px", 3)), rng):
            p_coast.append(add("rocks", world(p), 1800, int(recipe.get("coast_rocks_per_site", 3))))
    if kinds["pebbles"] and creek.any():  # small stones along the creek banks (any painted bank section), more on the pebble and stone sections
        banks = (bank > 0) | (grow(creek, 1) & ~grow(creek, 0))
        for p in pick(banks, int(recipe.get("bank_pebble_count", 220)), 2, rng):
            p_pebbles.append(add("pebbles", world(p), 900, int(recipe.get("pebbles_per_site", 6))))
    p_flowers = []
    if kinds["flowers"]:
        for p in pick(edge & (grass_w > 0.5) & (slope < 10), 90, 14, rng):
            p_flowers.append(add("flowers", world(p), 6500, 14))

    p_village = []
    v = recipe.get("village") or {}
    c = world(vi)
    cz = gz(vi)
    houses = v.get("houses", [])
    hs = float(recipe.get("house_scale", 1.0))
    ps = float(recipe.get("prop_scale", 1.0))
    for i, bp in enumerate(houses):
        a = i / max(1, len(houses)) * 2 * math.pi
        r = 3200 if i % 2 == 0 else 4300
        x, y = c["x"] + r * math.cos(a), c["y"] + r * math.sin(a)
        py, px = min(n - 1, max(0, int(y / cm))), min(n - 1, max(0, int(x / cm)))
        p_village.append(["level.place_actor", {"actorClass": bp, "label": "Village_House_%d" % (i + 1), "onConflict": "rename",
                                                  "location": {"x": x, "y": y, "z": gz((py, px)) + 5},
                                                  "rotation": {"pitch": 0, "yaw": math.degrees(a) + 180, "roll": 0},
                                                  "scale": {"x": hs, "y": hs, "z": hs}}])
    for i, bp in enumerate(v.get("props", [])):
        x, y = c["x"] + 900 * math.cos(i * 2.1), c["y"] + 900 * math.sin(i * 2.1)
        py, px = min(n - 1, max(0, int(y / cm))), min(n - 1, max(0, int(x / cm)))
        p_village.append(["level.place_actor", {"actorClass": bp, "label": "Village_Prop_%d" % (i + 1), "onConflict": "rename",
                                                  "location": {"x": x, "y": y, "z": gz((py, px)) + 5},
                                                  "scale": {"x": ps, "y": ps, "z": ps}}])
    return {"village_center": dict(c, z=cz), "pixel_cm": cm,
            "phases": ([{"name": "clear", "calls": p_clear}] if p_clear else []) + [{"name": "create_types", "calls": p_types}, {"name": "type_settings", "calls": p_settings},
                       {"name": "add_types_to_level", "calls": p_level}, {"name": "forest", "calls": p_forest},
                       {"name": "rocks", "calls": p_rocks}, {"name": "village", "calls": p_village},
                       {"name": "creek_trees", "calls": p_creek_trees}, {"name": "creek_rocks", "calls": p_creek_rocks}, {"name": "creek_biomes", "calls": p_biomes},
                       {"name": "coast_rocks", "calls": p_coast}, {"name": "bank_pebbles", "calls": p_pebbles},
                       {"name": "flowers", "calls": p_flowers}, {"name": "grass", "calls": p_grass}]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ue-dir", required=True)
    ap.add_argument("--size-m", type=float, required=True)
    ap.add_argument("--min-z", type=float, required=True)
    ap.add_argument("--max-z", type=float, required=True)
    ap.add_argument("--recipe", required=True)
    ap.add_argument("--heights", default="heightmap16.png", help="the heightmap now in the editor (island + creeks: heightmap16_creeks.png)")
    ap.add_argument("--layers-dir", default=None, help="final layer weights (with_creeks) overriding the <layer>.u8 files in --ue-dir")
    ap.add_argument("--out", required=True)
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    out = build(a.ue_dir, a.size_m, a.min_z, a.max_z, json.load(open(a.recipe)), heights=a.heights, layers_dir=a.layers_dir)
    json.dump(out, open(a.out, "w"), indent=1)
    print("wrote %s: %s" % (a.out, ", ".join("%s=%d" % (p["name"], len(p["calls"])) for p in out["phases"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
