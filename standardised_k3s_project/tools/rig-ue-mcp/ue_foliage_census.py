#!/usr/bin/env python3
"""Census of the foliage in the live level, grouped by plant family, with where each family actually stands.

  ue_foliage_census.py --project profile.json --heights live_heights.png [--out census.json] [--catalog catalog.json]

Pages every foliage type (foliage.list_types + foliage.get_instances), groups the types into families (the trailing _01 / _Var02 numbers
are variants of one plant), and for each family reports the instance count, the metres above the sea surface the instances stand at
(5th / 50th / 95th percentile, from the live heights), how many stand in the sea, and the ground slope (rise/run over one heights pixel).
It is the data behind `references/asset-placement.md`: a model must know what family a plant belongs to and where it belongs BEFORE it
scatters it. With --catalog it also prints the families that are not yet classified in the catalog (see templates/asset_catalog.example.json)
and the families whose measured habitat contradicts the catalog.

Run it after a scatter, and before adding a new family: it shows what is already on the level.
"""
import argparse
import json
import os
import re
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SKILL = os.path.join(HERE, "..", "..", "ansible", "roles", "watoom-code", "files", "skills", "watoom-texture-layering", "scripts")
sys.path.insert(0, SKILL)
import ue_project  # noqa: E402
from ue_foliage_buried import ground_z  # noqa: E402


def family(type_name):
    """FT_SM_Tree_03 -> SM_Tree; FT_SM_GrassPatch_Var02 -> SM_GrassPatch; FT_banana_01_04 -> banana."""
    n = re.sub(r"^FT_", "", type_name.split(".")[0])
    for _ in range(2):
        n = re.sub(r"_(\d+|Var\d+)$", "", n)
    return n


def slope(raw, raw_per_cm, px_cm, x, y):
    """rise/run at x, y from the heights (central difference over one pixel)."""
    n, m = raw.shape
    j = int(min(max(round(x / px_cm), 1), m - 2))
    i = int(min(max(round(y / px_cm), 1), n - 2))
    dzdx = (float(raw[i, j + 1]) - float(raw[i, j - 1])) / raw_per_cm / (2 * px_cm)
    dzdy = (float(raw[i + 1, j]) - float(raw[i - 1, j])) / raw_per_cm / (2 * px_cm)
    return float((dzdx ** 2 + dzdy ** 2) ** 0.5)


def water_distance(raw, z0, raw_per_cm, sea_cm, mask=None):
    """Distance to the nearest water pixel, in pixels, for every pixel. Water is the sea (ground below sea_cm) plus any non-zero pixel of
    `mask` (a creek / lake mask the size of the heights). Two-pass 3-4 chamfer transform, numpy only."""
    n, m = raw.shape
    water = (raw.astype(float) / raw_per_cm + z0) < sea_cm
    if mask is not None:
        if mask.shape != raw.shape:
            raise ValueError("water mask is %dx%d but the heights are %dx%d" % (mask.shape[1], mask.shape[0], m, n))
        water = water | (mask > 0)
    inf = 1e9
    d = np.where(water, 0.0, inf)
    for i in range(n):                       # forward pass
        for j in range(m):
            v = d[i, j]
            if i > 0:
                v = min(v, d[i - 1, j] + 3, d[i - 1, j - 1] + 4 if j > 0 else inf, d[i - 1, j + 1] + 4 if j < m - 1 else inf)
            if j > 0:
                v = min(v, d[i, j - 1] + 3)
            d[i, j] = v
    for i in range(n - 1, -1, -1):           # backward pass
        for j in range(m - 1, -1, -1):
            v = d[i, j]
            if i < n - 1:
                v = min(v, d[i + 1, j] + 3, d[i + 1, j - 1] + 4 if j > 0 else inf, d[i + 1, j + 1] + 4 if j < m - 1 else inf)
            if j < m - 1:
                v = min(v, d[i, j + 1] + 3)
            d[i, j] = v
    return np.where(d >= inf, np.inf, d / 3.0)


def summarise(by_family, raw, z0, raw_per_cm, px_cm, sea_cm, dist_px=None):
    """by_family: {family: {"types": n, "points": [(x, y, z)]}} -> {family: stats}. dist_px: water_distance() result, adds near_water_m."""
    out = {}
    for fam, d in sorted(by_family.items()):
        pts = d["points"]
        above = np.array([(ground_z(raw, z0, raw_per_cm, px_cm, x, y) - sea_cm) / 100.0 for x, y, _ in pts]) if pts else np.zeros(0)
        slopes = np.array([slope(raw, raw_per_cm, px_cm, x, y) for x, y, _ in pts]) if pts else np.zeros(0)
        p = (lambda a, q: round(float(np.percentile(a, q)), 2)) if len(pts) else (lambda a, q: None)
        out[fam] = {"types": d["types"], "instances": len(pts),
                    "above_sea_m": {"p5": p(above, 5), "p50": p(above, 50), "p95": p(above, 95)},
                    "in_sea": int((above < 0).sum()), "slope_p95": p(slopes, 95)}
        if dist_px is not None and len(pts):
            n, m = dist_px.shape
            near = np.array([dist_px[min(max(int(round(y / px_cm)), 0), n - 1), min(max(int(round(x / px_cm)), 0), m - 1)] * px_cm / 100.0
                             for x, y, _ in pts])
            out[fam]["near_water_m"] = {"p5": p(near, 5), "p50": p(near, 50), "p95": p(near, 95)}
    return out


def audit(census, catalog):
    """Families with no catalog entry, and families standing where the catalog says they must not."""
    missing = sorted(f for f in census if f not in catalog)
    wrong = []
    for fam, st in census.items():
        c = catalog.get(fam)
        if not c or not st["instances"]:
            continue
        lo, hi = c.get("above_sea_m", [None, None])
        if st["in_sea"] and not c.get("allow_in_sea"):
            wrong.append((fam, "%d instances stand in the sea" % st["in_sea"]))
        if hi is not None and st["above_sea_m"]["p95"] is not None and st["above_sea_m"]["p95"] > hi:
            wrong.append((fam, "p95 height %.1f m is above the catalog limit %.1f m" % (st["above_sea_m"]["p95"], hi)))
        if lo is not None and st["above_sea_m"]["p5"] is not None and st["above_sea_m"]["p5"] < lo:
            wrong.append((fam, "p5 height %.1f m is below the catalog limit %.1f m" % (st["above_sea_m"]["p5"], lo)))
        nw = c.get("near_water_m")
        got = st.get("near_water_m")
        if nw and got and got["p50"] is not None:
            if nw[0] is not None and got["p5"] is not None and got["p5"] < nw[0] and nw[0] > 0:
                wrong.append((fam, "p5 distance to water %.0f m is closer than the catalog minimum %.0f m" % (got["p5"], nw[0])))
            if nw[1] is not None and got["p50"] > nw[1]:
                wrong.append((fam, "median distance to water %.0f m is beyond the catalog maximum %.0f m (wet plants away from water?)" % (got["p50"], nw[1])))
        ms = c.get("max_slope")
        if ms is not None and st["slope_p95"] is not None and st["slope_p95"] > ms:
            wrong.append((fam, "p95 slope %.2f is steeper than the catalog limit %.2f" % (st["slope_p95"], ms)))
    return missing, wrong


def main(argv=None):
    import ue_route
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--heights", required=True)
    ap.add_argument("--z0", type=float, required=True)
    ap.add_argument("--raw-per-cm", type=float, required=True)
    ap.add_argument("--size-m", type=float, required=True)
    ap.add_argument("--sea-cm", type=float, default=None)
    ap.add_argument("--water-mask", help="uint8 mask (n x n raw, same size as the heights; non-zero = creek/lake water) for near_water_m; the sea is always water")
    ap.add_argument("--out", help="write the census JSON here")
    ap.add_argument("--catalog", help="asset catalog JSON to audit against")
    ap.add_argument("--host", default="10.99.1.44")
    ap.add_argument("--port", type=int, default=2224)
    ap.add_argument("--user", default="uemcp")
    ap.add_argument("--key-dir", default=ue_route.DEFAULT_KEY_DIR)
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    if a.sea_cm is None:
        ap.error("--sea-cm (or a --project profile with sea_cm) is required")
    raw = np.asarray(Image.open(a.heights))
    px_cm = a.size_m * 100.0 / (raw.shape[0] - 1)

    def j(text):
        return json.loads(text[text.index("{"):])
    t = ue_route.SshTransport(ue_route.ssh_command(a.host, a.port, a.user, a.key_dir))
    by_family = {}
    try:
        types, cur = [], None
        while True:
            d = j(t.call("foliage", "list_types", dict({"limit": 100}, **({"cursor": cur} if cur else {})), 120))
            types += [x["path"] for x in d.get("foliageTypes", [])]
            cur = d.get("nextCursor")
            if not d.get("hasMore") or not cur:
                break
        for ty in types:
            fam = by_family.setdefault(family(ty.split("/")[-1]), {"types": 0, "points": []})
            fam["types"] += 1
            start = 0
            while True:
                d = j(t.call("foliage", "get_instances", {"foliageTypePath": ty, "limit": 3000, "startIndex": start, "includeTransforms": True}, 240))
                got = 0
                for blk in d.get("types", []):
                    for it in blk.get("instances", []):
                        got += 1
                        loc = it["location"]
                        fam["points"].append((loc["x"], loc["y"], loc["z"]))
                if not d.get("hasMore") or got == 0:
                    break
                start += got
    finally:
        t.close()
    mask = None
    if a.water_mask:
        mask = np.fromfile(a.water_mask, np.uint8)
        if mask.size != raw.size:
            ap.error("--water-mask has %d bytes but the heights have %d pixels" % (mask.size, raw.size))
        mask = mask.reshape(raw.shape)
    dist = water_distance(raw, a.z0, a.raw_per_cm, a.sea_cm, mask)
    census = summarise(by_family, raw, a.z0, a.raw_per_cm, px_cm, a.sea_cm, dist)
    print("%-38s %5s %8s %22s %6s %6s %s" % ("family", "types", "count", "m above sea p5/p50/p95", "in sea", "slope", "m to water p5/p50/p95"))
    for fam, st in sorted(census.items(), key=lambda kv: kv[1]["instances"]):
        h = st["above_sea_m"]
        w = st.get("near_water_m", {})
        print("%-38s %5d %8d %7s %6s %6s %6d %6s  %s %s %s" % (fam[:38], st["types"], st["instances"], h["p5"], h["p50"], h["p95"], st["in_sea"],
                                                         st["slope_p95"], w.get("p5"), w.get("p50"), w.get("p95")))
    if a.out:
        json.dump(census, open(a.out, "w"), indent=2)
        print("wrote", a.out)
    if a.catalog:
        catalog = json.load(open(a.catalog)).get("families", {})
        missing, wrong = audit(census, catalog)
        print("\nnot in the catalog (classify before using again):", ", ".join(missing) or "none")
        for fam, why in wrong:
            print("CONTRADICTS CATALOG  %-34s %s" % (fam, why))
    return 0


if __name__ == "__main__":
    sys.exit(main())
