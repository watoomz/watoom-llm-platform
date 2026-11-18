#!/usr/bin/env python3
"""watoom-texture-layering: raise berms (bank rims) along creeks and around lakes so their flat water cannot spill (host-side; numpy + pillow).

  unreal_water_berms.py --heights live_heights.png --water water.json --z0 3677.7 --raw-per-cm 4.4387 --size-m 4000 \
      --out berm_calls.json --out-heights berm_heights.png [--report berm_report.json]

A water body's surface is flat at its water level and the Water plugin draws it a little past its shape (each body's ShapeDilation,
4096 cm here, on 24 m water-mesh tiles); the ground is what hides that overhang. Wherever the ground just outside a creek or lake
is BELOW the water, the water shows there as a stepped sheet past the shape (Lake_3 and Lake_4 near their creek mouths, T-0049).
Carving only ever lowers ground, so it cannot fix that. This script raises it:

  for every pixel at distance d outside a body's water edge (creek: RiverWidth / 2 from its spline; lake: radius + its carved bank,
  so the carve's underwater shore ramp stays as it is):
      crest   = water_z + --crest-cm                         for d <= --crest-m      (covers the drawn overhang)
      outside = crest - (d - crest_m) * --slope              beyond it, down to the natural ground (no cliff)
  ground is raised to the highest such target of any body, and only where it is lower (never lowered), and NEVER inside any water
  body -- a creek channel and a lake interior are left open, so creek mouths, confluences and lake outlets stay connected.

Skipped: creek samples at sea level (water within 5 cm of `sea_z`), every pixel whose ground is below `sea_z` + 5 cm (that is the sea:
the ocean covers it anyway, and without this rule the last stretch of a creek, whose water is a few cm above the sea, built a 13 m
berm out into the ocean around its mouth -- first live plan, T-0049), raises under --min-raise-cm
(noise), and every raise is capped at --max-raise-m. A capped pixel means the berm there could not reach the crest: it is listed in the
report as `capped` (the water may still show there -- lower that body's water level instead).

--water is the json written by tools/rig-ue-mcp/ue_water_fetch.py: {"sea_z": Z, "creeks": [{"label", "points": [[x, y, z], ...],
"widths_cm": [...]}], "lakes": [{"label", "x", "y", "water_z", "radius_cm"}]}. Output: a `heights` phase of landscape.set_height_region
tiles (changed tiles only). Apply it ONLY with ue_run_phases.py (it subtracts the Water-layer offset of carved beds; any other path
sinks them again), then check with ue_lake_check.py and capture with ue_viewport_shot.py --around.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unreal_creek_profile import calls_for, hermite  # noqa: E402
import ue_project  # noqa: E402


def nearest(shape, px_cm, samples, reach_cm):
    """For pixels within reach of the samples' bounding box: (ys, xs, distance to the nearest sample, that sample's row)."""
    n, m = shape
    yy, xx = np.mgrid[0:n, 0:m]
    wx, wy = xx * px_cm, yy * px_cm
    sel = ((wx >= samples[:, 0].min() - reach_cm) & (wx <= samples[:, 0].max() + reach_cm)
           & (wy >= samples[:, 1].min() - reach_cm) & (wy <= samples[:, 1].max() + reach_cm))
    ys, xs = np.nonzero(sel)
    px, py = wx[ys, xs], wy[ys, xs]
    dist = np.full(len(ys), np.inf)
    idx = np.zeros(len(ys), int)
    for a in range(0, len(ys), 2000):
        d = np.hypot(px[a:a + 2000, None] - samples[None, :, 0], py[a:a + 2000, None] - samples[None, :, 1])
        j = d.argmin(axis=1)
        dist[a:a + 2000] = d[np.arange(len(j)), j]
        idx[a:a + 2000] = j
    return ys, xs, dist, idx


def bodies(water, px_cm, lake_bank_cm):
    """Yield (label, samples[x, y, water_z, edge_cm], start_cm): edge = distance from a sample to the water's edge, start = where
    the berm begins outside that edge (lakes: past the carved bank, widened to 2 px like carve_lake_bank)."""
    sea = water.get("sea_z")
    for c in water.get("creeks", []):
        p = np.asarray(c["points"], float)
        w = np.asarray(c.get("widths_cm") or [4800.0] * len(p), float)
        s = hermite(np.column_stack([p[:, :3], w / 2.0]))
        if sea is not None:
            s = s[s[:, 2] > sea + 5.0]  # no rim where the creek water is at sea level
        if len(s):
            yield c["label"], s, 0.0
    for lk in water.get("lakes", []):
        yield lk["label"], np.array([[lk["x"], lk["y"], lk["water_z"], lk["radius_cm"]]]), max(lake_bank_cm, 2.0 * px_cm)


def berm(raw, water, z0, raw_per_cm, px_cm, crest_cm=60.0, crest_m=24.0, slope=0.5, lake_bank_cm=350.0,
         max_raise_m=20.0, min_raise_cm=10.0):
    """Returns (new uint16 heights, report dict). Only raises; never inside any water body."""
    z = raw.astype(float) / raw_per_cm + z0
    target = np.full(raw.shape, -np.inf)
    inside = np.zeros(raw.shape, bool)
    owner = np.full(raw.shape, "", object)
    crest_w = crest_m * 100.0
    for label, s, start in bodies(water, px_cm, lake_bank_cm):
        height_room = crest_cm + max_raise_m * 100.0
        reach = s[:, 3].max() + start + crest_w + height_room / max(slope, 1e-6)
        ys, xs, dist, j = nearest(raw.shape, px_cm, s, reach)
        d = dist - s[j, 3]                     # distance outside the water's edge (negative = in the water)
        inside[ys[d < 0], xs[d < 0]] = True
        dd = d - start                          # distance outside where the berm begins
        t = s[j, 2] + crest_cm - np.clip(dd - crest_w, 0.0, None) * slope
        ok = (d >= 0) & (dd >= 0)
        ys, xs, t = ys[ok], xs[ok], t[ok]
        better = t > target[ys, xs]
        target[ys[better], xs[better]] = t[better]
        owner[ys[better], xs[better]] = label
    need = (target - z)
    raise_px = ~inside & (need >= min_raise_cm)
    sea = water.get("sea_z")
    if sea is not None:
        raise_px &= z >= sea + 5.0  # sea floor: never build on it
    capped = raise_px & (need > max_raise_m * 100.0)
    new = np.where(raise_px, np.minimum(target, z + max_raise_m * 100.0), z)
    new_raw = np.where(raise_px, np.clip(np.round((new - z0) * raw_per_cm), 0, 65535), raw).astype(np.uint16)
    per = {}
    for label in sorted(set(owner[raise_px])):
        sel = raise_px & (owner == label)
        per[label] = {"raised_px": int(sel.sum()), "max_raise_cm": round(float(need[sel].max()), 1),
                      "capped_px": int((sel & capped).sum())}
    cy, cx = np.nonzero(capped)
    report = {"raised_px": int(raise_px.sum()), "capped_px": int(capped.sum()), "bodies": per,
              "capped": [{"x": int(x), "y": int(y), "world": [round(x * px_cm), round(y * px_cm)], "body": owner[y, x],
                          "short_cm": round(float(need[y, x] - max_raise_m * 100.0), 1)} for y, x in zip(cy[:200], cx[:200])]}
    return new_raw, report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--heights", required=True)
    ap.add_argument("--water", required=True, help="json from ue_water_fetch.py")
    ap.add_argument("--z0", type=float, required=True)
    ap.add_argument("--raw-per-cm", type=float, required=True)
    ap.add_argument("--size-m", type=float, required=True)
    ap.add_argument("--crest-cm", type=float, default=60.0, help="berm crest height above the water level")
    ap.add_argument("--crest-m", type=float, default=24.0, help="crest width outside the water's edge (one 24 m water-mesh tile)")
    ap.add_argument("--slope", type=float, default=0.5, help="outer slope, rise per run, down to the natural ground")
    ap.add_argument("--lake-bank-cm", type=float, default=350.0, help="the lakes' carve bank (ue_lake_as_waterbody.py --bank-cm)")
    ap.add_argument("--max-raise-m", type=float, default=20.0)
    ap.add_argument("--min-raise-cm", type=float, default=10.0)
    ap.add_argument("--landscape", required=True, help="landscape actor label (or set landscape in the --project profile)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--out-heights", required=True)
    ap.add_argument("--report", default=None)
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    raw = np.asarray(Image.open(a.heights))
    px_cm = a.size_m * 100.0 / (raw.shape[0] - 1)
    water = json.load(open(a.water))
    new, rep = berm(raw, water, a.z0, a.raw_per_cm, px_cm, a.crest_cm, a.crest_m, a.slope, a.lake_bank_cm, a.max_raise_m, a.min_raise_cm)
    Image.fromarray(new).save(a.out_heights)
    phases = calls_for(raw, new, a.landscape)
    json.dump({"phases": phases}, open(a.out, "w"))
    if a.report:
        json.dump(rep, open(a.report, "w"), indent=1)
    for label, b in rep["bodies"].items():
        print("%-16s raised %5d px, highest raise %7.1f cm%s" % (label, b["raised_px"], b["max_raise_cm"],
                                                              ", %d px CAPPED" % b["capped_px"] if b["capped_px"] else ""))
    print("raised %d px (%d capped at %.0f m), wrote %s: %d tile calls -- apply with ue_run_phases.py only"
          % (rep["raised_px"], rep["capped_px"], a.max_raise_m, a.out, len(phases[0]["calls"])))
    return 1 if rep["capped_px"] else 0


if __name__ == "__main__":
    sys.exit(main())
