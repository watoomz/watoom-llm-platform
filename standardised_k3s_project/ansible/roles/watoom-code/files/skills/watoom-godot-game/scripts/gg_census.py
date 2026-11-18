#!/usr/bin/env python3
"""Census and audit of the MultiMesh instances in the built scenes, against the catalog. Reads the saved scenes back through the engine, so it cannot be fooled by
the scatter script's own bookkeeping. It sees MultiMeshInstance3D nodes only (pass every scene that holds any with --scene); hand-placed single scene instances
and MeshInstance3D nodes are not counted.

  gg_census.py audit --project P [--scene res://levels/main/scatter.tscn ...]

Per family: instance count; metres above the sea, slope and distance to water at each instance (5th/50th/95th percentile); and the share of instances that
break the catalog rules: in the sea, outside the above-sea band, steeper than max_slope, closer to / farther from water than near_water_m (5 cm tolerance), standing in a creek or the sea when the family is a dry-land one, or not standing on the ground (more than 0.3 m off the terrain mesh). Also lists every family in the level that is NOT in the catalog.
Exit 0 = clean (no instance in the sea or a creek it must not stand in, at most 2% of a family's instances breaking any rules in total, at most 1% off the ground,
nothing unclassified or unverified, no MultiMesh without a gg_family tag). Exit 1 = findings. Exit 2 = refused.
"""
import argparse
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

VIOLATION_LIMIT = 0.02
DIST_TOL_M = 0.05
SLOPE_TOL = 0.01
BAND_TOL_M = 0.05
OFF_GROUND_LIMIT = 0.01
OFF_GROUND_M = 0.3


def analyse_family(world, fam, positions, ground_y, bilinear):
    """Pure given the helpers: -> stats dict. positions: list of [x, y, z]."""
    cell, sea = world.cell, world.sea
    rel, slope, dist, off = [], [], [], []
    viol = {"in_sea": 0, "in_water": 0, "below_band": 0, "above_band": 0, "too_steep": 0, "too_close_to_water": 0, "too_far_from_water": 0, "off_ground": 0}
    lo, hi = fam["above_sea_m"]
    nlo, nhi = fam["near_water_m"]
    for x, y, z in positions:
        gy = ground_y(world.h, x, z, cell)
        r = gy - sea
        s = bilinear(world.slope, x, z, cell)
        d = bilinear(world.dist, x, z, cell)
        rel.append(r), slope.append(s), dist.append(d), off.append(abs(y - gy))
        if not fam.get("allow_in_sea") and gy < sea - 0.005:
            viol["in_sea"] += 1
        if gg_catalog.stands_on_dry_land(fam) and d <= 0.5 * cell:
            viol["in_water"] += 1
        if lo is not None and r < lo - BAND_TOL_M:
            viol["below_band"] += 1
        if hi is not None and r > hi + BAND_TOL_M:
            viol["above_band"] += 1
        if s > fam["max_slope"] + SLOPE_TOL:
            viol["too_steep"] += 1
        if d < nlo - DIST_TOL_M:
            viol["too_close_to_water"] += 1
        if nhi is not None and d > nhi + DIST_TOL_M:
            viol["too_far_from_water"] += 1
        if abs(y - gy) > OFF_GROUND_M:
            viol["off_ground"] += 1
    n = max(len(positions), 1)

    def pct(a):
        return [round(float(v), 2) for v in np.percentile(a, [5, 50, 95])] if len(a) else None
    rules = sum(v for k, v in viol.items() if k != "off_ground")
    bad_rules = [k for k, v in viol.items() if k != "off_ground" and v / n > VIOLATION_LIMIT]
    if viol["in_sea"] or viol["in_water"]:
        bad_rules += [k for k in ("in_sea", "in_water") if viol[k] and k not in bad_rules]  # zero tolerance
    if rules / n > VIOLATION_LIMIT and not bad_rules:
        bad_rules = [k for k, v in viol.items() if k != "off_ground" and v]  # several small shares add up
    return {"count": len(positions), "above_sea_m": pct(rel), "slope": pct(slope), "water_dist_m": pct(np.minimum(dist, 9999)), "violations": viol,
            "violation_pct": {k: round(100.0 * v / n, 1) for k, v in viol.items() if v}, "bad_rules": bad_rules, "off_ground_bad": viol["off_ground"] / n > OFF_GROUND_LIMIT}


def audit(project, scenes=None, run=gg_godot.run):
    import gg_scatter
    prof = gg_project.load_profile(project)
    style = gg_style.check_applied(project, prof)
    cat = gg_catalog.load_catalog(project)
    errs = gg_catalog.validate(cat)
    if errs:
        raise gg_godot.Refused("catalog is invalid, run gg_catalog.py validate: " + errs[0])
    world = gg_scatter.World(project)
    gg_terrain.forget(project, what=("scatter_ok.json",))  # a stamp is written again only by a clean `gg_scatter.py run`
    scenes = scenes or ["res://levels/%s/scatter.tscn" % prof["level"]]
    out_json = os.path.join(project, "gg_data", "census.json")
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    if os.path.exists(out_json):
        os.remove(out_json)
    r = run(project, "census_scene", {"scenes": scenes, "out_json": out_json}, render=True, renderer=style["renderer"], size=(640, 360), timeout=300)  # headless drops MultiMesh transforms
    if r.code:
        return r.code, {"why": r.why}
    if not os.path.isfile(out_json):
        return 4, {"why": "the engine reported success but wrote no census file"}
    fams = json.load(open(out_json))
    out = {"scenes": scenes, "families": {}, "unclassified": [], "empty": []}
    problems = []
    for name, d in sorted(fams.items()):
        f = cat["families"].get(name)
        if f is None:
            out["unclassified"].append({"family": name, "count": d["count"]})
            problems.append("family '%s' (%d instances) is NOT in the catalog: classify it (gg_catalog.py add, then inspect)" % (name, d["count"]))
            continue
        if not d.get("classified"):
            problems.append("family '%s': the MultiMesh has no gg_family tag (it was not made by gg_scatter.py); it is judged by its node name" % name)
        if not f.get("verified"):
            problems.append("family '%s' is UNVERIFIED in the catalog: run gg_catalog.py inspect --family %s" % (name, name))
        st = analyse_family(world, f, d["positions"], gg_scatter.ground_y, gg_scatter.bilinear)
        out["families"][name] = st
        for k in st["bad_rules"]:
            problems.append("family '%s': %.1f%% of %d instances break %s" % (name, st["violation_pct"][k], st["count"], k))
        if st["off_ground_bad"]:
            problems.append("family '%s': %.1f%% of instances are more than %.1f m off the terrain surface (floating or buried)" % (name, st["violation_pct"].get("off_ground", 0), OFF_GROUND_M))
    if not fams:
        problems.append("the scenes %s hold no instances at all" % scenes)
    out["problems"] = problems
    with open(os.path.join(project, "gg_data", "census_report.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    return (1 if problems else 0), {**out, "why": "; ".join(problems)}


def print_audit(a):
    for n, st in a.get("families", {}).items():
        print("%-14s n=%5d above_sea %s  slope %s  water_dist %s  violations %s" % (n, st["count"], st["above_sea_m"], st["slope"], st["water_dist_m"], st["violation_pct"] or "none"))
    for u in a.get("unclassified", []):
        print("UNCLASSIFIED %s (%d instances)" % (u["family"], u["count"]))
    print("audit: %s" % ("CLEAN" if not a.get("problems") else "%d problem(s)" % len(a["problems"])))
    for p in a.get("problems", []):
        print("  - " + p)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("audit"); p.add_argument("--project", required=True); p.add_argument("--scene", action="append")
    a = ap.parse_args(argv)
    try:
        code, rep = audit(os.path.abspath(a.project), a.scene)
        if "families" in rep:
            print_audit(rep)
        else:
            print("FAILED (exit %d): %s" % (code, rep.get("why")))
        return code
    except (gg_godot.Refused, ValueError, OSError, KeyError, json.JSONDecodeError) as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
