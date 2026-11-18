#!/usr/bin/env python3
"""Mask-driven scatter. Where a family may stand comes ONLY from the catalog (height above the sea, slope, distance to water) and the layer weights.

  gg_scatter.py plan --project P [--density-scale 1.0]   write gg_scatter.json: one entry per VERIFIED family with a count from its category's density
  gg_scatter.py run  --project P [--dry-run] [--exclude-mask FILE.png]   place, build res://levels/<level>/scatter.tscn, then audit the built scene

Writes only: gg_scatter.json (plan), res://levels/<level>/scatter.tscn, and under gg_data/: scatter/<level>.json, world/scatter_ok.json, census.json, census_report.json.
Needs: a verified terrain build (gg_terrain.py build), gg_water.py analyse/build (distance to water; with no water the distance is unlimited), a catalog with
VERIFIED families (gg_catalog.py inspect). `run` refuses unverified families, families whose scene file changed since they were verified, props, and masks whose
size differs from the heights (the message names both sizes). Exit codes: 0 pass | 1 check failed | 2 refused | 3 engine log fatal | 4 no verdict | 5 runner failure.
"""
import argparse
import hashlib
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
import gg_catalog  # noqa: E402
import gg_godot  # noqa: E402
import gg_project  # noqa: E402
import gg_style  # noqa: E402
import gg_terrain  # noqa: E402
import gg_water  # noqa: E402

DENSITY_PER_HA = {"tree_upland": 20, "tree_riparian": 15, "shrub": 40, "groundcover": 80, "grass": 250, "flower": 60, "wet_margin": 120, "aquatic": 40,
                  "dune_coast": 15, "dry_scrub": 30, "rock": 6}
MAX_COUNT = 200000


def plan_path(project):
    return os.path.join(project, "gg_scatter.json")


def ground_y(h, x, z, cell):
    """Height of the terrain MESH at (x, z): the mesh splits every cell along the diagonal between (i+1, j) and (i, j+1) (see build_terrain.gd)."""
    nz, nx = h.shape
    fx = np.clip(x / cell, 0, nx - 1.000001)
    fz = np.clip(z / cell, 0, nz - 1.000001)
    i, j = int(fx), int(fz)
    tx, tz = fx - i, fz - j
    ha, hb, hc, hd = h[j, i], h[j, i + 1], h[j + 1, i], h[j + 1, i + 1]
    if tx + tz <= 1.0:
        return ha + tx * (hb - ha) + tz * (hc - ha)
    return hd + (1 - tx) * (hc - hd) + (1 - tz) * (hb - hd)


def bilinear(a, x, z, cell):
    nz, nx = a.shape
    fx = np.clip(x / cell, 0, nx - 1.000001)
    fz = np.clip(z / cell, 0, nz - 1.000001)
    i, j = int(fx), int(fz)
    tx, tz = fx - i, fz - j
    return a[j, i] * (1 - tx) * (1 - tz) + a[j, i + 1] * tx * (1 - tz) + a[j + 1, i] * (1 - tx) * tz + a[j + 1, i + 1] * tx * tz


class World:
    """Everything a rule needs, on the heights grid."""

    def __init__(self, project):
        self.h, self.wd = gg_water.load_heights(project)
        self.cell = self.wd["cell_m"]
        self.sea = self.wd["sea_level_m"]
        wdir = gg_terrain.world_dir(project)
        for name, what in (("build_ok.json", "gg_terrain.py build"),):
            p = os.path.join(wdir, name)
            if not os.path.isfile(p) or json.load(open(p)).get("heights_sha") != self.wd["heights_sha"]:
                raise gg_godot.Refused("the terrain was not built and verified from the current heights: run %s (exit 0) first" % what)
        wj = os.path.join(wdir, "water.json")
        wi = json.load(open(wj)) if os.path.isfile(wj) else {}
        if wi.get("heights_sha") != self.wd["heights_sha"]:
            raise gg_godot.Refused("no distance-to-water for the current heights: run gg_water.py analyse (it also works without any water)")
        if wi.get("ok") is not True:
            raise gg_godot.Refused("the last gg_water.py analyse did not pass (exit 1, e.g. the creek does not lie in its trench): fix it and re-run gg_water.py analyse until exit 0")
        nz, nx = self.h.shape
        d = np.fromfile(os.path.join(wdir, "water_dist.f32"), "<f4")
        if d.size != nx * nz:
            raise gg_godot.Refused("water_dist.f32 has %d values but the heights grid is %dx%d = %d: run gg_water.py analyse again" % (d.size, nx, nz, nx * nz))
        self.dist = d.reshape(nz, nx).astype(np.float64)
        gy, gx = np.gradient(self.h, self.cell)
        self.slope = np.hypot(gx, gy)
        self._layers = None
        self.project = project

    def layer_weights(self):
        """{layer name: weights 0..1 on the heights grid} from the terrain layer report."""
        if self._layers is None:
            from PIL import Image
            ld = os.path.join(gg_terrain.world_dir(self.project), "layers")
            rep = json.load(open(os.path.join(ld, "layer_report.json")))
            out = {}
            for k, l in enumerate(rep["layers"]):
                a = np.asarray(Image.open(os.path.join(ld, "splat_%d.png" % (k // 4))).convert("RGBA"), dtype=np.float64) / 255.0
                out[l["name"]] = a[..., k % 4]
            self._layers = out
        return self._layers


def cell_mask(world, fam, entry, exclude=None):
    """Boolean mask on the grid + how many cells each rule removed (for the explanation when nothing fits)."""
    h, sea = world.h, world.sea
    m = np.ones(h.shape, bool)
    why = {}

    def apply(name, ok):
        nonlocal m
        why[name] = int((m & ~ok).sum())
        m = m & ok
    lo, hi = fam["above_sea_m"]
    rel = h - sea
    apply("above_sea_m", (rel >= (-1e9 if lo is None else lo)) & (rel <= (1e9 if hi is None else hi)))
    if not fam.get("allow_in_sea"):
        apply("not_in_sea", h > sea)
    apply("max_slope", world.slope <= fam["max_slope"])
    nlo, nhi = fam["near_water_m"]
    apply("near_water_m", (world.dist >= nlo) & (world.dist <= (1e18 if nhi is None else nhi)))
    if gg_catalog.stands_on_dry_land(fam):
        apply("not_in_water", world.dist > 0.5 * world.cell)
    if entry.get("on_layers"):
        w = world.layer_weights()
        apply("on_layers", np.maximum.reduce([w[n] for n in entry["on_layers"]]) >= entry.get("min_weight", 0.4))
    if exclude is not None:
        apply("exclude_mask", ~exclude)
    return m, why


def exact_ok(world, fam, entry, x, z, exclude=None):
    """The rules again at the exact position (cells are coarse): the instance must satisfy them where it really stands."""
    y = ground_y(world.h, x, z, world.cell)
    lo, hi = fam["above_sea_m"]
    rel = y - world.sea
    if (lo is not None and rel < lo) or (hi is not None and rel > hi):
        return None
    if not fam.get("allow_in_sea") and y <= world.sea:
        return None
    if bilinear(world.slope, x, z, world.cell) > fam["max_slope"]:
        return None
    d = bilinear(world.dist, x, z, world.cell)
    nlo, nhi = fam["near_water_m"]
    if d < nlo or (nhi is not None and d > nhi):
        return None
    if gg_catalog.stands_on_dry_land(fam) and d <= 0.5 * world.cell:
        return None
    if exclude is not None and exclude[min(exclude.shape[0] - 1, int(round(z / world.cell))), min(exclude.shape[1] - 1, int(round(x / world.cell)))]:
        return None
    return y


def place(world, fam, entry, count, rng, exclude=None):
    mask, why = cell_mask(world, fam, entry, exclude)
    cells = np.argwhere(mask)
    inst = []
    if not len(cells):
        return inst, why, 0
    s = float(fam["min_spacing_m"])
    grid = {}
    lo_s, hi_s = fam.get("scale_range", [0.8, 1.25])
    nz, nx = world.h.shape
    attempts = 0
    while len(inst) < count and attempts < 40 * count:
        attempts += 1
        j, i = cells[rng.integers(len(cells))]
        x = (i + rng.uniform(-0.5, 0.5)) * world.cell
        z = (j + rng.uniform(-0.5, 0.5)) * world.cell
        if not (0 <= x <= (nx - 1) * world.cell and 0 <= z <= (nz - 1) * world.cell):
            continue
        y = exact_ok(world, fam, entry, x, z, exclude)
        if y is None:
            continue
        gx, gz = int(x / s), int(z / s)
        if any((gx + a, gz + b) in grid and any((x - px) ** 2 + (z - pz) ** 2 < s * s for px, pz in grid[(gx + a, gz + b)]) for a in (-1, 0, 1) for b in (-1, 0, 1)):
            continue
        grid.setdefault((gx, gz), []).append((x, z))
        inst.append([round(float(x), 3), round(float(y), 3), round(float(z), 3), round(float(rng.uniform(0, 2 * np.pi)), 4), round(float(rng.uniform(lo_s, hi_s)), 3)])
    return inst, why, int(mask.sum())


def stamp_hashes(project, level):
    """What a passing scatter was built from. gg_light includes the scatter only while every one of these still matches."""
    def sha(p):
        return hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.isfile(p) else None
    wd = gg_terrain.world_dir(project)
    return {"scatter_scene": sha(os.path.join(project, "levels", level, "scatter.tscn")), "catalog": sha(gg_catalog.catalog_path(project)),
            "water_dist": sha(os.path.join(wd, "water_dist.f32")), "weights": sha(os.path.join(wd, "layers", "layer_report.json"))}


def stamp_valid(project, level, heights_sha):
    p = os.path.join(gg_terrain.world_dir(project), "scatter_ok.json")
    if not os.path.isfile(p):
        return False
    try:
        st = json.load(open(p))
    except (OSError, json.JSONDecodeError):
        return False
    return st.get("heights_sha") == heights_sha and st.get("hashes") == stamp_hashes(project, level)


def atomic_json(path, obj):
    with open(path + ".new", "w") as f:
        json.dump(obj, f)
    os.replace(path + ".new", path)


def load_plan(project):
    p = plan_path(project)
    if not os.path.isfile(p):
        raise gg_godot.Refused("no %s: run gg_scatter.py plan first" % p)
    try:
        plan = json.load(open(p))
    except json.JSONDecodeError as e:
        raise gg_godot.Refused("%s is not valid JSON: %s" % (p, e))
    if plan.get("schema") != 1 or not isinstance(plan.get("entries"), list) or not plan["entries"]:
        raise gg_godot.Refused("%s needs schema 1 and a non-empty entries list" % p)
    return plan


def check_plan(project, plan, cat, world):
    errs = []
    for e in plan["entries"]:
        n = e.get("family")
        f = cat["families"].get(n)
        if f is None:
            errs.append("family '%s' is not in the catalog (classify it first: gg_catalog.py add / inspect)" % n)
            continue
        if f["category"] == "prop":
            errs.append("family '%s' is a prop: props are placed once by hand, never scattered" % n)
        if not f.get("verified"):
            errs.append("family '%s' is UNVERIFIED: run gg_catalog.py inspect --family %s and get VERIFIED" % (n, n))
        elif gg_catalog.fingerprint(project, f) != f.get("verified_sha"):
            errs.append("family '%s': its category, scene file, import settings or a texture/material it uses changed (or vanished) since it was verified: run gg_catalog.py inspect --family %s again" % (n, n))
        c = e.get("count")
        if not isinstance(c, int) or not 1 <= c <= MAX_COUNT:
            errs.append("family '%s': count must be an integer 1..%d (got %r)" % (n, MAX_COUNT, c))
        for ln in e.get("on_layers", []) or []:
            if ln not in world.layer_weights():
                errs.append("family '%s': on_layers names '%s', not a terrain layer (have %s)" % (n, ln, sorted(world.layer_weights())))
    return errs


def plan_cmd(project, density_scale=1.0, force=False):
    if os.path.exists(plan_path(project)) and not force:
        raise gg_godot.Refused("%s already exists and may hold your edits: edit it directly, or pass --force to replace it" % plan_path(project))
    prof = gg_project.load_profile(project)
    cat = gg_catalog.load_catalog(project)
    world = gg_water.load_heights(project)[1]
    area_ha = world["size_m"][0] * world["size_m"][1] / 10000.0
    entries = []
    for n, f in cat["families"].items():
        if f["category"] == "prop" or not f.get("verified"):
            continue
        entries.append({"family": n, "count": max(1, int(round(DENSITY_PER_HA[f["category"]] * area_ha * density_scale)))})
    if not entries:
        raise gg_godot.Refused("no VERIFIED scatterable family in the catalog: run gg_catalog.py inspect for each family first")
    plan = {"schema": 1, "seed": 1, "entries": entries, "_comment": "Edit counts. Optional per entry: on_layers [\"grass\"] with min_weight 0.4 keeps a family on those terrain layers."}
    with open(plan_path(project) + ".new", "w") as f:
        json.dump(plan, f, indent=1)
    os.replace(plan_path(project) + ".new", plan_path(project))
    return plan


def load_exclude(project, path, world):
    if not path:
        return None
    from PIL import Image
    a = np.asarray(Image.open(path).convert("L"))
    if a.shape != world.h.shape:
        raise gg_godot.Refused("the exclude mask %s is %dx%d but the heights are %dx%d: regenerate it at the heights size" % (path, a.shape[1], a.shape[0], world.h.shape[1], world.h.shape[0]))
    return a > 127


def run_cmd(project, dry_run=False, exclude_mask=None, run=gg_godot.run):
    prof = gg_project.load_profile(project)
    if prof["dimension"] != "3d":
        raise gg_godot.Refused("scatter is 3D only")
    if not dry_run:
        gg_terrain.forget(project, what=("scatter_ok.json",))  # any run that does not finish clean leaves no stamp
    style = gg_style.check_applied(project, prof)
    cat = gg_catalog.load_catalog(project)
    errs = gg_catalog.validate(cat)
    if errs:
        raise gg_godot.Refused("catalog is invalid: " + errs[0])
    world = World(project)
    plan = load_plan(project)
    errs = check_plan(project, plan, cat, world)
    if errs:
        raise gg_godot.Refused("; ".join(errs))
    exclude = load_exclude(project, exclude_mask, world)
    rng = np.random.default_rng(int(plan.get("seed", 1)))
    fams, report, warns = {}, {}, []
    for e in plan["entries"]:
        f = cat["families"][e["family"]]
        inst, why, cells = place(world, f, e, e["count"], rng, exclude)
        report[e["family"]] = {"requested": e["count"], "placed": len(inst), "habitat_cells": cells, "habitat_pct": round(100.0 * cells / world.h.size, 2), "removed_by": why}
        if not inst:
            first = max(why.items(), key=lambda kv: kv[1])
            warns.append("%s: NOTHING placed. Habitat is %d cells; the rule that removed most is %s (%d cells). Loosen that rule in the catalog or pick another family" % (e["family"], cells, first[0], first[1]))
        elif len(inst) < 0.5 * e["count"]:
            warns.append("%s: placed %d of %d: the habitat is %.1f%% of the map or the spacing %.1f m is too wide for it" % (e["family"], len(inst), e["count"], report[e["family"]]["habitat_pct"], f["min_spacing_m"]))
        fams[e["family"]] = {"scene": f["scene"], "instances": inst}
    placed = {k: len(v["instances"]) for k, v in fams.items()}
    short = [k for k, v in report.items() if v["placed"] < max(1, 0.1 * v["requested"])]
    why_short = "families that placed under 10%% of the plan: %s (loosen their habitat in the catalog, lower their counts, or remove them from gg_scatter.json)" % ", ".join("%s %d/%d" % (k, report[k]["placed"], report[k]["requested"]) for k in short)
    if dry_run:
        return (1 if short else 0), {"report": report, "warnings": warns, **({"why": why_short} if short else {})}
    if short:
        gg_terrain.forget(project, what=("scatter_ok.json",))
        return 1, {"report": report, "warnings": warns, "why": why_short}
    out_dir = os.path.join(project, "gg_data", "scatter")
    os.makedirs(out_dir, exist_ok=True)
    sj = os.path.join(out_dir, "%s.json" % prof["level"])
    atomic_json(sj, {"heights_sha": world.wd["heights_sha"], "families": fams})
    r = run(project, "build_scatter", {"level": prof["level"], "families": {k: v for k, v in fams.items() if v["instances"]}}, render=True, renderer=style["renderer"], size=(640, 360), timeout=600)  # a MultiMesh keeps its transforms in the rendering server: the headless dummy renderer would drop them
    if r.code:
        return r.code, {"report": report, "warnings": warns, "why": r.why}
    import gg_census
    code, aud = gg_census.audit(project, run=run)
    res = {"report": report, "warnings": warns, "build": r.result["data"], "audit": aud}
    if code:
        return code, {**res, "why": aud.get("why", "the audit of the built scene failed")}
    counted = {k: v["count"] for k, v in aud["families"].items()}
    want = {k: v for k, v in placed.items() if v}
    if counted != want:
        return 1, {**res, "why": "the built scene holds %s but %s were placed" % (counted, want)}
    atomic_json(os.path.join(gg_terrain.world_dir(project), "scatter_ok.json"),
                {"heights_sha": world.wd["heights_sha"], "placed": placed, "hashes": stamp_hashes(project, prof["level"])})
    return 0, res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan"); p.add_argument("--project", required=True); p.add_argument("--density-scale", type=float, default=1.0); p.add_argument("--force", action="store_true")
    r = sub.add_parser("run"); r.add_argument("--project", required=True); r.add_argument("--dry-run", action="store_true"); r.add_argument("--exclude-mask")
    a = ap.parse_args(argv)
    try:
        project = os.path.abspath(a.project)
        if a.cmd == "plan":
            plan = plan_cmd(project, a.density_scale, a.force)
            print("plan: " + ", ".join("%s x%d" % (e["family"], e["count"]) for e in plan["entries"]) + " -> " + plan_path(project))
            return 0
        code, res = run_cmd(project, a.dry_run, a.exclude_mask)
        for n, v in res.get("report", {}).items():
            print("%-14s requested %5d placed %5d  habitat %5.1f%% of the map  removed by %s" % (n, v["requested"], v["placed"], v["habitat_pct"], {k: c for k, c in v["removed_by"].items() if c}))
        for w in res.get("warnings", []):
            print("WARNING " + w)
        if "audit" in res:
            import gg_census
            gg_census.print_audit(res["audit"])
        if a.dry_run:
            print("dry run: nothing written")
        if code:
            print("FAILED (exit %d): %s" % (code, res.get("why")))
        return code
    except (gg_godot.Refused, ValueError, OSError, KeyError, json.JSONDecodeError) as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
