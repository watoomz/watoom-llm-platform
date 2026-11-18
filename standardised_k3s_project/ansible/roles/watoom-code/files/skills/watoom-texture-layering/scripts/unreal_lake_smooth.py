#!/usr/bin/env python3
"""watoom-texture-layering: soften the sharp angle where a lake bowl meets the land, in a band along the shoreline only (host-side; numpy + pillow).

A carved lake (unreal_creeks.py --lakes, unreal_creek_profile.py --lake) cuts a bowl straight into the terrain, so the bank meets
the bowl in a hard crease, and on 8 m landscape pixels the waterline is a polygon with corners. This blurs the heights in a ring
around each lake's waterline and nowhere else:

  unreal_lake_smooth.py --heights live_heights.png --lake 148000,212000,6120,56 --z0 3677.7 --raw-per-cm 4.4387 --size-m 4000 \
      --landscape Landscape --band-m 24 --out lake_smooth_calls.json --out-heights heightmap16_lake_smooth.png [--out-revert lake_smooth_revert.json]

--heights must be the heights IN THE EDITOR now (ue_heights_fetch.py); keep that file, it is the "before" backup.
A lake is `--lake X,Y,Z,RADIUS_M` (repeatable): the centre and the water surface in world cm, the same numbers as the Lake_<n>
disc (level.get_actor_details location) and as unreal_creek_profile.py's --lake (a fifth DEEP_CM field is accepted and ignored).
Or `--lakes FILE`: a json list of {"x", "y", "z", "radius_m"}, or the json unreal_creeks.py wrote (its "lakes" list with px,
radius_px and water_cm is read directly). Lakes are given, not guessed from the pixels: a lake on a slope has ground below its
water level outside the bowl too, so a height threshold alone cannot tell the lake from the hillside.

For each lake: the water is the ground below Z that is connected to the centre and within --reach x the radius (the bowls are
not round, so the waterline is found from the heights, the radius only bounds the search). The smoothing weight is 1 on the
waterline and fades (smoothstep) to 0 at --band-m on the land side and at min(--band-m, half the radius) on the water side.
Then --passes times: height += weight * (box blur of radius --blur-px - height). Output: a `heights` phase of
landscape.set_height_region tiles (changed tiles only) for ue_run_phases.py, the new heights png, and with --out-revert a second
calls json that writes the old tiles back.

Rules learned writing it:
- A box blur barely moves a smooth slope or a smooth bowl and moves a crease a lot, so the band can be generous; what must be
  protected is the middle of the lake (weight 0 there, so depth and bed are bit-identical) and everything beyond the band.
- The blur lowers the bank and raises the bed next to it by about the same amount, so the waterline stays where it was (the
  wet area changes by a few percent); the water actor does not need to move. The first metres of water get shallower: a shelf.
- A small lake (radius 4 px) has no room for a wide band inside it: the water-side fade is capped at half the radius, otherwise
  the whole bowl is blurred shallower.
- Where the ground outside the bowl is below the water level (the downhill side of a lake without a bank rim) the "waterline"
  there is the --reach circle, not a real shore. Smoothing along it is harmless but does nothing useful; that side has no crease.
- A creek leaving the lake is water connected to the centre, so its banks inside the reach circle are softened too. A bank rim
  (unreal_creek_profile.py --lake-berm-cm) inside the band is lowered by the blur: check the rim still stands above the water,
  or use a smaller --band-m.
- Heights are rounded to raw units only where the weight is above 0; every other pixel is copied from the input, so a second
  run on an unchanged map changes nothing outside the bands. Running it twice on the same lake smooths twice.
- Trees and props near the shore were traced onto the old ground: after applying, refit them (ue_stray_check.py lists the ones
  left hanging or sunk; unreal_creek_foliage_fit.py refits the creek-side foliage).
- Refused, not silently misread: an 8-bit or RGB `--heights` (Image.open mode must be I;16 or I; an 8-bit png would np.clip into
  garbage tiles with no error), a non-square heightmap, `--raw-per-cm <= 0`, or a lake centre outside the map. `--out`/`--out-heights`
  are also not written when every lake is missed (previously they were written anyway with exit 1, leaving stale files that looked current).
- Refused when `--heights` no longer matches its own `<heights>.fingerprint.json` (written by ue_heights_fetch.py): the wrong file was
  passed, or it was edited/truncated after being fetched. No sidecar (an older fetch, or a hand-made heights file) is only a NOTE, not
  a refusal -- this script has no rig access of its own, so it cannot otherwise tell whether the landscape has moved since the fetch;
  ue_stray_check.py / ue_foliage_buried.py hold a transport and re-check a few live sample points instead (heights_freshness.check_live).
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # so `python3 -I script.py` finds the sibling modules
import ue_project  # noqa: E402
from unreal_coast import dist_to  # noqa: E402
from unreal_creek_profile import calls_for  # noqa: E402
from unreal_scene_scatter import box, grow  # noqa: E402


def check_sidecar(heights_path):
    """Compare <heights_path>.fingerprint.json (written by tools/rig-ue-mcp/ue_heights_fetch.py) against the file on disk now.
    No import from tools/rig-ue-mcp: this script is also synced standalone into the native-skills catalog, where that tree
    does not exist. Returns ("missing", None) with no sidecar (an older fetch, or a hand-made heights file -- not an error),
    ("stale", fp) when the sha256 no longer matches (wrong file, or edited/truncated since fetch -- refuse), or ("ok", fp)."""
    import hashlib
    path = heights_path + ".fingerprint.json"
    if not os.path.exists(path):
        return "missing", None
    fp = json.load(open(path))
    actual = hashlib.sha256(np.asarray(Image.open(heights_path)).tobytes()).hexdigest()
    return ("ok" if actual == fp.get("sha256") else "stale"), fp


def parse_lake(spec):
    """'X,Y,Z,RADIUS_M[,DEEP_CM]' -> {x, y, z, radius_m}."""
    v = [float(s) for s in spec.split(",")]
    if len(v) not in (4, 5):
        raise ValueError("--lake wants X,Y,Z,RADIUS_M: %r" % spec)
    return {"x": v[0], "y": v[1], "z": v[2], "radius_m": v[3]}


def load_lakes(path):
    """A list of {x, y, z, radius_m}, or the output of unreal_creeks.py ({"lakes": [{px: [row, col], radius_px, water_cm}], "pixel_cm"})."""
    data = json.load(open(path))
    if isinstance(data, dict):
        cm = data["pixel_cm"]
        return [{"x": k["px"][1] * cm, "y": k["px"][0] * cm, "z": k["water_cm"], "radius_m": k["radius_px"] * cm / 100.0} for k in data["lakes"]]
    return [{"x": float(k["x"]), "y": float(k["y"]), "z": float(k["z"]), "radius_m": float(k["radius_m"])} for k in data]


def lake_water(z, cx, cy, r_px, water_cm, reach=1.5):
    """Bool mask of the lake's water: ground below water_cm, within reach * r_px of the centre (cx, cy in pixels) and connected to the centre."""
    n, m = z.shape
    yy, xx = np.mgrid[0:n, 0:m]
    d = np.hypot(yy - cy, xx - cx)
    low = (z < water_cm) & (d <= r_px * reach)
    seen = low & (d <= max(1.0, 0.5 * r_px))
    while True:
        g = grow(seen, 1) & low
        if (g == seen).all():
            return seen
        seen = g


def shore_weight(z, cx, cy, r_px, water_cm, band_px, reach=1.5):
    """Smoothing weight (0..1) for one lake: 1 on the waterline, 0 from band_px outside it and from min(band_px, r_px / 2) inside it."""
    n, m = z.shape
    pad = int(np.ceil(r_px * reach + band_px)) + 2
    y0, y1, x0, x1 = max(0, int(cy) - pad), min(n, int(cy) + pad + 1), max(0, int(cx) - pad), min(m, int(cx) + pad + 1)
    w = np.zeros((n, m))
    if y0 >= y1 or x0 >= x1:
        return w
    wet = lake_water(z[y0:y1, x0:x1], cx - x0, cy - y0, r_px, water_cm, reach)
    if not wet.any() or wet.all():
        return w
    out_px = np.clip(1.0 - (dist_to(wet) - 0.5) / max(band_px, 1e-6), 0.0, 1.0)      # dry pixels: distance to the nearest water pixel
    in_px = np.clip(1.0 - (dist_to(~wet) - 0.5) / max(min(band_px, 0.5 * r_px), 1e-6), 0.0, 1.0)
    t = np.where(wet, in_px, out_px)
    w[y0:y1, x0:x1] = t * t * (3.0 - 2.0 * t)
    return w


def smooth(raw, lakes, z0, raw_per_cm, px_cm, band_cm=2400.0, blur_px=1, passes=2, reach=1.5):
    """Returns (new uint16 heights, weight map, lakes that had no water at their centre). Only pixels with weight > 0 can change."""
    z = raw.astype(float) / raw_per_cm + z0
    w = np.zeros(raw.shape)
    missed = []
    for k in lakes:
        wk = shore_weight(z, k["x"] / px_cm, k["y"] / px_cm, k["radius_m"] * 100.0 / px_cm, k["z"], band_cm / px_cm, reach)
        if not wk.any():
            missed.append(k)
        w = np.maximum(w, wk)
    new_z = z.copy()
    for _ in range(passes):
        new_z += w * (box(new_z, blur_px) - new_z)
    new = np.clip(np.round((new_z - z0) * raw_per_cm), 0, 65535).astype(np.uint16)
    return np.where(w > 0, new, raw).astype(np.uint16), w, missed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--heights", required=True)
    ap.add_argument("--lake", action="append", default=[], metavar="X,Y,Z,RADIUS_M", help="lake centre and water surface (world cm) and radius (m); repeatable")
    ap.add_argument("--lakes", default=None, metavar="FILE", help="json list of {x, y, z, radius_m}, or the json written by unreal_creeks.py --lakes")
    ap.add_argument("--z0", type=float, required=True)
    ap.add_argument("--raw-per-cm", type=float, required=True)
    ap.add_argument("--size-m", type=float, required=True)
    ap.add_argument("--band-m", type=float, default=24.0, help="how far from the waterline the smoothing fades to nothing")
    ap.add_argument("--blur-px", type=int, default=1, help="box blur radius in pixels (1 = 3 x 3)")
    ap.add_argument("--passes", type=int, default=2)
    ap.add_argument("--reach", type=float, default=1.5, help="water further than this x the radius from the centre is not the lake")
    ap.add_argument("--landscape", required=True, help="landscape actor label (or set landscape in the --project profile)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--out-heights", required=True)
    ap.add_argument("--out-revert", default=None, help="also write the calls that put the old heights back")
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    lakes = [parse_lake(s) for s in a.lake] + (load_lakes(a.lakes) if a.lakes else [])
    if not lakes:
        ap.error("give at least one --lake or a --lakes file")
    if a.raw_per_cm <= 0:
        print("REFUSED: --raw-per-cm must be > 0 (got %r)" % a.raw_per_cm)
        return 1
    img = Image.open(a.heights)
    if img.mode not in ("I;16", "I;16B", "I;16L", "I"):
        print("REFUSED: %s is %s, not a 16-bit heightmap (expected mode I;16 or I, got %r); "
              "an 8-bit or RGB png would silently produce garbage tiles" % (a.heights, img.mode, img.mode))
        return 1
    raw = np.asarray(img)
    if raw.ndim != 2 or raw.shape[0] != raw.shape[1]:
        print("REFUSED: %s is not a square single-channel heightmap (shape %r)" % (a.heights, raw.shape))
        return 1
    status, fp = check_sidecar(a.heights)
    if status == "stale":
        print("REFUSED: %s does not match its own ue_heights_fetch.py fingerprint (fetched %s) -- wrong file, or edited/truncated since"
              % (a.heights, fp.get("fetchedAt")))
        return 1
    if status == "missing":
        print("NOTE: no fingerprint for %s (older ue_heights_fetch.py run, or a hand-made heights file) -- freshness not checked" % a.heights)
    px_cm = a.size_m * 100.0 / (raw.shape[0] - 1)
    map_cm = (raw.shape[0] - 1) * px_cm
    outside = [k for k in lakes if not (0 <= k["x"] <= map_cm and 0 <= k["y"] <= map_cm)]
    if outside:
        print("REFUSED: lake centre(s) outside the %.0f x %.0f cm map: %s"
              % (map_cm, map_cm, ", ".join("%.0f,%.0f" % (k["x"], k["y"]) for k in outside)))
        return 1
    new, w, missed = smooth(raw, lakes, a.z0, a.raw_per_cm, px_cm, a.band_m * 100.0, a.blur_px, a.passes, a.reach)
    for k in missed:
        print("NO WATER at lake %.0f,%.0f: the ground at the centre is not below z %.0f (wrong Z, or stale heights); skipped" % (k["x"], k["y"], k["z"]))
    if len(missed) == len(lakes):
        print("REFUSED: every lake was missed; not writing %s / %s" % (a.out, a.out_heights))
        return 1
    Image.fromarray(new).save(a.out_heights)
    phases = calls_for(raw, new, a.landscape)
    json.dump({"phases": phases}, open(a.out, "w"))
    if a.out_revert:
        json.dump({"phases": calls_for(new, raw, a.landscape)}, open(a.out_revert, "w"))
    step = np.abs(new.astype(float) - raw) / a.raw_per_cm
    print("%d lake(s), %d skipped: band %.0f m (%.1f px), %d px in the bands, %d changed (largest change %.0f cm), wrote %s: %d tile calls"
          % (len(lakes), len(missed), a.band_m, a.band_m * 100.0 / px_cm, (w > 0).sum(), (new != raw).sum(), step.max(), a.out, len(phases[0]["calls"])))
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
