#!/usr/bin/env python3
"""Find foliage and placed mesh actors that ended up somewhere wrong: in the sky, under the sea, under the ground or off the map.

  ue_stray_check.py --heights live_heights.png --project profile.json [--float-cm 500] [--sink-cm 80] [--classes StaticMeshActor,SkeletalMeshActor] [--types Tree,Bush] [--apply]

--heights must be the heights that are in the editor now (ue_heights_fetch.py). Read-only unless --apply. Two passes, one table
(label or foliage type, x, y, z, the ground or sea Z it was compared with, the difference, the verdict):
  foliage  every type (or --types substrings), paged with foliage.get_instances like ue_foliage_buried.py. An instance is
           `ocean` when it stands on sea floor, `sky` when its Z is more than --float-cm above the ground (above the sea surface
           over the sea), `buried` when its Z is more than --sink-cm below the ground.
  actors   every actor of --classes (level.get_actors_by_class), minus --skip-prefixes, measured with level.get_actor_bounds.
           `sky` when the LOWEST point of the bounds is more than --float-cm above the ground, `buried` when the HIGHEST point
           is more than --sink-cm below it, `ocean` when it is over the sea and the highest point is more than --sea-margin-cm
           under the surface, `off-map` when the bounds centre is outside the landscape. --no-actors / --no-foliage skip a pass.
The sea is the ground below --sea-cm that is connected to the map edge (unreal_ocean_depth.py's rule); --inland-low also counts
inland bowls and creek or lake beds below that level. Without a sea level (no --sea-cm, no profile sea_cm) there is no ocean check.

--apply does the least destructive thing: stray FOLIAGE instances are removed (foliage.remove_instances, as ue_foliage_buried.py
does); a `sky` or `buried` ACTOR is moved straight up or down so its lowest point sits --seat-cm below the ground (level.move_actor,
x/y/rotation/scale untouched). Actors are never deleted. `ocean` and `off-map` actors are only reported: the ground under an
ocean actor is the sea floor, so seating it there fixes nothing, and where it belongs is the owner's call. Nothing is saved:
look at the result, then level.save. A failed removal or move is reported and the exit code is 1.

--landscape LABEL re-reads a few live sample heights (landscape.get_height_region) and warns (not a failure) if they no longer match
--heights -- the landscape moved since the heights png was fetched. Skip with --skip-freshness-check; omit --landscape to skip entirely.

Rules: the bounds, not the actor's pivot, decide: a big mesh (a sky dome, a cliff) with its pivot high or low is not a stray
while its box still crosses the ground. Flat water actors hang over a carved bed on purpose (a Lake_ disc sits up to 9 m above
its bowl), so the fixed water labels Lake_, Creek_, CreekRibbon_ and Ocean are skipped by default (--skip-prefixes). An actor
with an empty mesh has extent 0 and is listed as `no-bounds`, never moved. Ground Z comes from ue_foliage_buried.ground_z and the
sea from its sea_mask / find_in_sea; this file only adds the floating test and the actor bounds test.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ue_foliage_buried as fb  # noqa: E402  (ground_z, find_buried, find_in_sea, sea_mask; puts the skill scripts on sys.path)
import ue_project  # noqa: E402
from ue_place_assets import actor_z_for_bottom  # noqa: E402
from heights_freshness import check_live  # noqa: E402

SKIP_PREFIXES = "Lake_,Creek_,CreekRibbon_,Ocean"


def surface_z(raw, z0, raw_per_cm, px_cm, x, y, sea_cm=None, mask=None):
    """(ground Z, True when x,y is over the sea). mask (fb.sea_mask) limits the sea to edge-connected ground below sea_cm."""
    g = fb.ground_z(raw, z0, raw_per_cm, px_cm, x, y)
    wet = sea_cm is not None and bool(fb.find_in_sea([{"index": 0, "x": x, "y": y, "z": g}], raw, z0, raw_per_cm, px_cm, sea_cm, mask=mask))
    return g, wet


def find_floating(instances, raw, z0, raw_per_cm, px_cm, float_cm=500.0, sea_cm=None):
    """Indices of instances whose Z is more than float_cm above the ground (above the sea surface where that is higher)."""
    out = []
    for i in instances:
        top = fb.ground_z(raw, z0, raw_per_cm, px_cm, i["x"], i["y"])
        if sea_cm is not None:
            top = max(top, sea_cm)
        if i["z"] > top + float_cm:
            out.append(i["index"])
    return out


def classify_foliage(instances, raw, z0, raw_per_cm, px_cm, float_cm=500.0, sink_cm=80.0, sea_cm=None, mask=None):
    """{index: verdict} for the stray instances. sky wins over ocean (a failed trace above the sea is a sky case), ocean over buried."""
    out = {i: "buried" for i in fb.find_buried(instances, raw, z0, raw_per_cm, px_cm, sink_cm)}
    if sea_cm is not None:
        out.update({i: "ocean" for i in fb.find_in_sea(instances, raw, z0, raw_per_cm, px_cm, sea_cm, mask=mask)})
    out.update({i: "sky" for i in find_floating(instances, raw, z0, raw_per_cm, px_cm, float_cm, sea_cm)})
    return out


def classify_actor(origin, extent, raw, z0, raw_per_cm, px_cm, float_cm=500.0, sink_cm=80.0, sea_cm=None, mask=None, sea_margin_cm=100.0):
    """(verdict or None, reference Z, delta cm) from the bounds of one actor. delta is positive above the reference, negative below it."""
    n, m = raw.shape
    x, y, bottom, top = origin["x"], origin["y"], origin["z"] - extent["z"], origin["z"] + extent["z"]
    if not (0 <= x <= (m - 1) * px_cm and 0 <= y <= (n - 1) * px_cm):
        return "off-map", None, None
    if extent["x"] == 0 and extent["y"] == 0 and extent["z"] == 0:
        return "no-bounds", None, None
    g, wet = surface_z(raw, z0, raw_per_cm, px_cm, x, y, sea_cm, mask)
    surface = max(g, sea_cm) if wet else g
    if bottom > surface + float_cm:
        return "sky", surface, bottom - surface
    if wet and top < sea_cm - sea_margin_cm:
        return "ocean", sea_cm, top - sea_cm
    if top < g - sink_cm:
        return "buried", g, top - g
    return None, surface, bottom - surface


def actor_rows(reply):
    """[{label, location or None}] from a level.get_actors_by_class / get_outliner reply (any list of objects that carry a label)."""
    rows = []

    def walk(v):
        if isinstance(v, dict):
            lab = v.get("label") or v.get("actorLabel")
            if isinstance(lab, str):
                loc = v.get("location")
                rows.append({"label": lab, "location": loc if isinstance(loc, dict) and "z" in loc else None})
                return
            for c in v.values():
                walk(c)
        elif isinstance(v, list):
            for c in v:
                walk(c)
    walk(reply)
    return rows


def row(name, x, y, z, ref, delta, verdict):
    f = lambda v: "%9.0f" % v if v is not None else "%9s" % "-"  # noqa: E731
    return "%-40s %s %s %s %s %s  %s" % (name[:40], f(x), f(y), f(z), f(ref), f(delta), verdict)


def main(argv=None):
    import ue_route
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--heights", required=True)
    ap.add_argument("--z0", type=float, required=True)
    ap.add_argument("--raw-per-cm", type=float, required=True)
    ap.add_argument("--size-m", type=float, required=True)
    ap.add_argument("--float-cm", type=float, default=500.0, help="sky: this far above the ground (or the sea surface)")
    ap.add_argument("--sink-cm", type=float, default=80.0, help="buried: this far below the ground")
    ap.add_argument("--sea-cm", type=float, default=None, help="sea surface Z (cm); from the project profile when given; without it there is no ocean check")
    ap.add_argument("--sea-margin-cm", type=float, default=100.0, help="ocean (actors): the top of the bounds is this far under the sea surface")
    ap.add_argument("--inland-low", action="store_true", help="count any ground below the sea level as sea, also inland bowls and creek or lake beds")
    ap.add_argument("--classes", default="StaticMeshActor,SkeletalMeshActor", help="comma separated actor classes to check")
    ap.add_argument("--skip-prefixes", default=SKIP_PREFIXES, help="comma separated actor label prefixes left alone (flat water actors)")
    ap.add_argument("--underground-prefixes", default="", help="comma separated label prefixes of actors that BELONG under the ground "
                    "(a dungeon: unreal_dungeon.py builds <prefix>Dgn_*); never reported as buried nor moved. Profile key "
                    "underground_label_prefixes")
    ap.add_argument("--types", default="", help="comma separated substrings of foliage type names (default: all)")
    ap.add_argument("--no-foliage", action="store_true")
    ap.add_argument("--no-actors", action="store_true")
    ap.add_argument("--max-rows", type=int, default=20, help="table rows printed per foliage type (the counts are always complete)")
    ap.add_argument("--seat-cm", type=float, default=20.0, help="--apply: a moved actor's lowest point goes this far below the ground")
    ap.add_argument("--apply", action="store_true", help="remove stray foliage instances; move sky/buried actors back onto the ground (never deletes an actor)")
    ap.add_argument("--out-removed", default=None, help="--apply: where to write the removed foliage instances receipt (default: stray_check_removed.json)")
    ap.add_argument("--landscape", default=None, help="landscape actor label; when given, re-reads a few live sample heights and warns if --heights is stale")
    ap.add_argument("--skip-freshness-check", action="store_true", help="skip the live --landscape freshness check even when --landscape is given")
    ap.add_argument("--host", default="10.99.1.44")
    ap.add_argument("--port", type=int, default=2224)
    ap.add_argument("--user", default="uemcp")
    ap.add_argument("--key-dir", default=ue_route.DEFAULT_KEY_DIR)
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    raw = np.asarray(Image.open(a.heights))
    px_cm = a.size_m * 100.0 / (raw.shape[0] - 1)
    geo = (raw, a.z0, a.raw_per_cm, px_cm)
    mask = fb.sea_mask(raw, a.z0, a.raw_per_cm, a.sea_cm) if a.sea_cm is not None and not a.inland_low else None
    want = [s for s in a.types.split(",") if s]
    skip = tuple(s for s in (a.skip_prefixes + "," + a.underground_prefixes).split(",") if s)

    def j(text):
        return json.loads(text[text.index("{"):]) if "{" in (text or "") else {}

    def ok(r):
        return ue_route.reply_ok(r, getattr(t, "is_error", False))

    def failed(r):
        return ue_route.reply_failed(r, getattr(t, "is_error", False))

    def call(cat, meth, cargs, timeout, what):
        r = t.call(cat, meth, cargs, timeout)
        if failed(r):
            raise RuntimeError("FAILED %s: %s" % (what, (r or "")[:300]))
        return j(r)
    counts = {"sky": 0, "ocean": 0, "buried": 0, "off-map": 0, "no-bounds": 0}
    read = fixed = failures = 0
    removed_receipt = []
    print("%-40s %9s %9s %9s %9s %9s  %s" % ("label / foliage type #index", "x", "y", "z", "ref z", "delta", "verdict"))
    t = ue_route.SshTransport(ue_route.ssh_command(a.host, a.port, a.user, a.key_dir))
    try:
        if a.landscape and not a.skip_freshness_check:
            try:
                mismatches = check_live(call, raw, a.landscape)
            except RuntimeError as e:
                print("NOTE: freshness check could not run: %s" % e, flush=True)
                mismatches = []
            if mismatches:
                print("WARNING: --heights looks stale -- %d live sample point(s) differ from the png (e.g. %r); re-fetch with ue_heights_fetch.py"
                      % (len(mismatches), mismatches[0]), flush=True)
        types, cur, types_failed = [], None, False
        while not a.no_foliage:
            r = t.call("foliage", "list_types", dict({"limit": 100}, **({"cursor": cur} if cur else {})), 120)
            if failed(r):
                print("LISTING foliage types FAILED: %s" % (r or "")[:200], flush=True)
                failures += 1
                types_failed = True
                break
            d = j(r)
            types += [x["path"] for x in d.get("foliageTypes", [])]
            cur = d.get("nextCursor")
            if not d.get("hasMore") or not cur:
                break
        if not a.no_foliage and not types_failed and not types:
            print("LISTING foliage types FAILED: list_types read zero types -- treated as a failed listing, not an empty level", flush=True)
            failures += 1
            types_failed = True
        for ty in [] if types_failed else types:
            if want and not any(w in ty for w in want):
                continue
            insts, start, page_failed = [], 0, False
            while True:
                r = ue_route.call_read(t, "foliage", "get_instances", {"foliageTypePath": ty, "limit": 3000, "startIndex": start, "includeTransforms": True}, 240)
                if failed(r):
                    print("LISTING %s instances FAILED: %s" % (ty, (r or "")[:200]), flush=True)
                    failures += 1
                    page_failed = True
                    break
                d = j(r)
                got = 0
                for blk in d.get("types", []):
                    for it in blk.get("instances", []):
                        insts.append({"index": it["index"], "x": it["location"]["x"], "y": it["location"]["y"], "z": it["location"]["z"],
                                      "rotation": it.get("rotation"), "scale": it.get("scale")})
                        got += 1
                if not d.get("hasMore") or got == 0:
                    break
                start += got
            if page_failed:
                continue
            read += len(insts)
            bad = classify_foliage(insts, *geo, float_cm=a.float_cm, sink_cm=a.sink_cm, sea_cm=a.sea_cm, mask=mask)
            name = ty.split("/")[-1].split(".")[0]
            shown = 0
            for i in insts:
                v = bad.get(i["index"])
                if not v:
                    continue
                counts[v] += 1
                if shown < a.max_rows:
                    g = fb.ground_z(*geo, i["x"], i["y"])
                    ref = a.sea_cm if v == "ocean" or (v == "sky" and a.sea_cm is not None and a.sea_cm > g) else g
                    print(row("%s #%d" % (name, i["index"]), i["x"], i["y"], i["z"], ref, i["z"] - ref, v), flush=True)
                    shown += 1
            if len(bad) > shown:
                print("  ... %d more stray %s instances (of %d)" % (len(bad) - shown, name, len(insts)), flush=True)
            if bad and a.apply:
                by_index = {i["index"]: i for i in insts}
                removed_receipt.append({"foliageTypePath": ty, "instances": [by_index[i] for i in sorted(bad)]})
                r = t.call("foliage", "remove_instances", {"foliageTypePath": ty, "instanceIndices": sorted(bad)}, 300)
                fixed += len(bad) if ok(r) else 0
                failures += 0 if ok(r) else 1
                print("  removed %d %s instances" % (len(bad), name) if ok(r) else "  REMOVAL FAILED: " + r[:200], flush=True)
        actors = {}
        for cls in ([] if a.no_actors else [c for c in a.classes.split(",") if c]):
            r = t.call("level", "get_actors_by_class", {"className": cls, "includeTransforms": True}, 240)
            if ue_route.reply_failed(r, getattr(t, "is_error", False)):
                print("LISTING %s FAILED: %s" % (cls, r[:200]), flush=True)
                failures += 1
                continue
            for it in actor_rows(j(r)):
                if not it["label"].startswith(skip):
                    actors.setdefault(it["label"], it)
        for lab in sorted(actors):
            read += 1
            b = j(t.call("level", "get_actor_bounds", {"actorLabel": lab}, 60))
            if not b.get("success") or "origin" not in b or "extent" not in b:
                print(row(lab, None, None, None, None, None, "bounds read FAILED"), flush=True)
                failures += 1
                continue
            o, e = b["origin"], b["extent"]
            v, ref, delta = classify_actor(o, e, *geo, float_cm=a.float_cm, sink_cm=a.sink_cm, sea_cm=a.sea_cm, mask=mask, sea_margin_cm=a.sea_margin_cm)
            if not v:
                continue
            counts[v] += 1
            print(row(lab, o["x"], o["y"], o["z"], ref, delta, v), flush=True)
            if not a.apply or v not in ("sky", "buried"):
                continue
            loc = actors[lab]["location"] or j(t.call("level", "get_actor_details", {"actorLabel": lab}, 60)).get("location")
            if not loc:
                print("  MOVE FAILED: no location for " + lab, flush=True)
                failures += 1
                continue
            nz = actor_z_for_bottom(loc["z"], o["z"], e["z"], fb.ground_z(*geo, o["x"], o["y"]), a.seat_cm)
            r = t.call("level", "move_actor", {"actorLabel": lab, "location": {"x": loc["x"], "y": loc["y"], "z": nz}}, 60)
            fixed += 1 if ok(r) else 0
            failures += 0 if ok(r) else 1
            print("  moved to the ground: actor z %.0f -> %.0f" % (loc["z"], nz) if ok(r) else "  MOVE FAILED: " + r[:200], flush=True)
    finally:
        t.close()
    if a.apply and removed_receipt:
        out_path = a.out_removed or "stray_check_removed.json"
        with open(out_path, "w") as f:
            json.dump({"removed": removed_receipt}, f)
        print("removed-instances receipt:", out_path, flush=True)
    strays = sum(counts.values())
    print("%d foliage instances and actors read, %d stray (%s)%s" % (
        read, strays, ", ".join("%s %d" % kv for kv in counts.items()),
        (", %d fixed%s; not saved: check, then level.save" % (fixed, ", %d step(s) FAILED" % failures if failures else "")) if a.apply
        else (", dry run" + (", %d read(s) FAILED" % failures if failures else ""))))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
