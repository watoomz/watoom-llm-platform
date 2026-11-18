#!/usr/bin/env python3
"""Find (and with --apply remove) foliage instances sunk into the ground, so they stop costing render time.

  ue_foliage_buried.py --heights live_heights.png --z0 3677.7 --raw-per-cm 4.4387 --size-m 4000 [--sink-cm 80] [--types Tree,Bush] [--apply]
  ue_foliage_buried.py --project profile.json --heights live_heights.png --in-sea [--sea-margin-cm 0] [--types ...] [--apply]

--heights must be the heights that are in the editor now (a 505 px png). An instance counts as buried when its Z is more than --sink-cm below the
ground there (bilinear on the heights). Pages every foliage type with foliage.get_instances (foliageTypePath + startIndex), prints a per-type table,
and with --apply calls foliage.remove_instances with the indices per type (do a level.save afterwards). A failed removal is reported and the exit code is 1.

--in-sea selects by ground height alone: ANY ground below the sea surface counts, including an inland bowl or a deep creek or lake bed that is not
connected to the sea, so it also removes plants standing in those. Add --edge-connected-sea to count only ground below the sea surface that is
connected to the map edge through such ground (the real sea, same rule as unreal_ocean_depth.py); inland bowls are then left alone.

A failed/timed-out/permission-denied `list_types` or `get_instances` call is a FAILURE (exit 1, no "0 buried, dry run" false-clean) -- checked with
ue_route.reply_failed, not just "does this parse as JSON" (an error reply can still contain a `{` and parse). Reading zero foliage types at all is
also a failure (--types that matches nothing legitimate still reads at least one type page; zero means the listing itself did not work).

--apply writes a removed-instances receipt (--out-removed, default foliage_buried_removed.json: type path, index, location/rotation/scale)
before removing each type's instances, so a bad call can be reversed with foliage.spawn_instances from that file -- the removal itself
has no undo on the engine side.

--landscape LABEL re-reads a few live sample heights (landscape.get_height_region) and warns (not a failure) if they no longer match
--heights -- the landscape moved since the heights png was fetched. Skip with --skip-freshness-check; omit --landscape to skip entirely.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SKILL = os.path.join(HERE, "..", "..", "ansible", "roles", "watoom-code", "files", "skills", "watoom-texture-layering", "scripts")
sys.path.insert(0, SKILL)
import ue_project  # noqa: E402
from unreal_ocean_depth import edge_connected  # noqa: E402
from heights_freshness import check_live  # noqa: E402


def ground_z(raw, z0, raw_per_cm, px_cm, x, y):
    n, m = raw.shape
    gx, gy = min(max(x / px_cm, 0), m - 1.001), min(max(y / px_cm, 0), n - 1.001)
    j, i = int(gx), int(gy)
    fx, fy = gx - j, gy - i
    z = raw.astype(float)
    v = z[i, j] * (1 - fx) * (1 - fy) + z[i, j + 1] * fx * (1 - fy) + z[i + 1, j] * (1 - fx) * fy + z[i + 1, j + 1] * fx * fy
    return v / raw_per_cm + z0


def find_buried(instances, raw, z0, raw_per_cm, px_cm, sink_cm=80.0):
    """instances: [{index, x, y, z}]; returns the indices whose Z is more than sink_cm below the ground."""
    return [i["index"] for i in instances if i["z"] < ground_z(raw, z0, raw_per_cm, px_cm, i["x"], i["y"]) - sink_cm]


def sea_mask(raw, z0, raw_per_cm, sea_cm, margin_cm=0.0):
    """Pixels below the sea surface that are connected to the map edge through such pixels (the real sea, not an inland bowl)."""
    return edge_connected(raw.astype(float) / raw_per_cm + z0 < sea_cm - margin_cm)


def find_in_sea(instances, raw, z0, raw_per_cm, px_cm, sea_cm, margin_cm=0.0, mask=None):
    """Indices of instances standing where the ground is below the sea surface (ground Z < sea_cm - margin_cm).
    mask (from sea_mask): also require the nearest height pixel to be edge-connected sea, so inland bowls do not count."""
    def in_mask(i):
        if mask is None:
            return True
        n, m = mask.shape
        return bool(mask[min(max(int(round(i["y"] / px_cm)), 0), n - 1), min(max(int(round(i["x"] / px_cm)), 0), m - 1)])
    return [i["index"] for i in instances if ground_z(raw, z0, raw_per_cm, px_cm, i["x"], i["y"]) < sea_cm - margin_cm and in_mask(i)]


def main(argv=None):
    import ue_route
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--heights", required=True)
    ap.add_argument("--z0", type=float, required=True)
    ap.add_argument("--raw-per-cm", type=float, required=True)
    ap.add_argument("--size-m", type=float, required=True)
    ap.add_argument("--sink-cm", type=float, default=80.0)
    ap.add_argument("--in-sea", action="store_true", help="select instances whose ground is below the sea level instead of buried ones")
    ap.add_argument("--sea-cm", type=float, default=None, help="sea surface Z (cm); from the project profile when given")
    ap.add_argument("--sea-margin-cm", type=float, default=0.0, help="--in-sea: only count ground this far below the sea surface")
    ap.add_argument("--edge-connected-sea", action="store_true", help="--in-sea: only ground connected to the map edge below sea level (leave inland bowls, creek and lake beds alone)")
    ap.add_argument("--types", default="", help="comma separated substrings of foliage type names (default: all)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--out-removed", default=None, help="--apply: where to write the removed-instances receipt (default: foliage_buried_removed.json)")
    ap.add_argument("--landscape", default=None, help="landscape actor label; when given, re-reads a few live sample heights and warns if --heights is stale")
    ap.add_argument("--skip-freshness-check", action="store_true", help="skip the live --landscape freshness check even when --landscape is given")
    ap.add_argument("--host", default="10.99.1.44")
    ap.add_argument("--port", type=int, default=2224)
    ap.add_argument("--user", default="uemcp")
    ap.add_argument("--key-dir", default=ue_route.DEFAULT_KEY_DIR)
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    if a.in_sea and a.sea_cm is None:
        ap.error("--in-sea needs --sea-cm (or a --project profile with sea_cm)")
    raw = np.asarray(Image.open(a.heights))
    px_cm = a.size_m * 100.0 / (raw.shape[0] - 1)
    want = [s for s in a.types.split(",") if s]
    mask = sea_mask(raw, a.z0, a.raw_per_cm, a.sea_cm, a.sea_margin_cm) if a.in_sea and a.edge_connected_sea else None

    def call(cat, meth, args, timeout, what):
        """Like t.call but raises (never silently returns {}) when the reply itself reports failure."""
        r = t.call(cat, meth, args, timeout)
        if ue_route.reply_failed(r, getattr(t, "is_error", False)):
            raise RuntimeError("FAILED %s: %s" % (what, (r or "")[:300]))
        return json.loads(r[r.index("{"):])

    t = ue_route.SshTransport(ue_route.ssh_command(a.host, a.port, a.user, a.key_dir))
    total = buried_total = failures = 0
    removed_receipt = []
    try:
        if a.landscape and not a.skip_freshness_check:
            mismatches = check_live(call, raw, a.landscape)
            if mismatches:
                print("WARNING: --heights looks stale -- %d live sample point(s) differ from the png (e.g. %r); re-fetch with ue_heights_fetch.py"
                      % (len(mismatches), mismatches[0]), flush=True)
        types, cur = [], None
        while True:
            d = call("foliage", "list_types", dict({"limit": 100}, **({"cursor": cur} if cur else {})), 120, "list_types")
            types += [x["path"] for x in d.get("foliageTypes", [])]
            cur = d.get("nextCursor")
            if not d.get("hasMore") or not cur:
                break
        if not types:
            raise RuntimeError("FAILED: list_types read zero foliage types -- that is a failed listing, not an empty level")
        for ty in types:
            if want and not any(w in ty for w in want):
                continue
            insts, start = [], 0
            while True:
                d = call("foliage", "get_instances", {"foliageTypePath": ty, "limit": 3000, "startIndex": start, "includeTransforms": True}, 240, "get_instances " + ty)
                got = 0
                for blk in d.get("types", []):
                    for it in blk.get("instances", []):
                        insts.append({"index": it["index"], "x": it["location"]["x"], "y": it["location"]["y"], "z": it["location"]["z"],
                                      "rotation": it.get("rotation"), "scale": it.get("scale")})
                        got += 1
                if not d.get("hasMore") or got == 0:
                    break
                start += got
            bad = (find_in_sea(insts, raw, a.z0, a.raw_per_cm, px_cm, a.sea_cm, a.sea_margin_cm, mask) if a.in_sea
                   else find_buried(insts, raw, a.z0, a.raw_per_cm, px_cm, a.sink_cm))
            total += len(insts)
            buried_total += len(bad)
            if bad:
                print("%-50s %5d of %5d buried" % (ty.split("/")[-1][:50], len(bad), len(insts)), flush=True)
            if bad and a.apply:
                by_index = {i["index"]: i for i in insts}
                removed_receipt.append({"foliageTypePath": ty, "instances": [by_index[i] for i in sorted(bad)]})
                with open(a.out_removed or "foliage_buried_removed.json", "w") as f:  # BEFORE the removal: a crash must not lose it
                    json.dump({"removed": removed_receipt}, f)
                r = t.call("foliage", "remove_instances", {"foliageTypePath": ty, "instanceIndices": sorted(bad)}, 300)
                ok = ue_route.reply_ok(r, getattr(t, "is_error", False))
                failures += 0 if ok else 1
                print("  removed" if ok else "  REMOVAL FAILED:", "ok" if ok else r[:200], flush=True)
    except RuntimeError as e:
        print(e, flush=True)
        return 1
    finally:
        t.close()
    if a.apply and removed_receipt:
        out_path = a.out_removed or "foliage_buried_removed.json"
        with open(out_path, "w") as f:
            json.dump({"removed": removed_receipt}, f)
        print("removed-instances receipt:", out_path)
    what = "in the sea (ground below %.0f cm)" % a.sea_cm if a.in_sea else "buried (> %.0f cm below ground)" % a.sink_cm
    print("%d instances read, %d %s%s" % (total, buried_total, what, (", removed" if not failures else ", %d removal(s) FAILED" % failures) if a.apply else ", dry run"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
