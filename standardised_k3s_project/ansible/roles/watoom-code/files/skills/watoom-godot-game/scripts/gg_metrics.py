#!/usr/bin/env python3
"""Numeric look of a screenshot: how a model without eyes judges an image. numpy + pillow only.

  gg_metrics.py IMAGE [--targets FILE.json] [--block K] [--json]     exit 0 pass, 1 out of target, 2 refused

All values are 0..1 on the ENCODED 8-bit sRGB pixels (display referred, after tonemapping):
  luma_p1/p5/p50/p95/p99/mean/std   Y = 0.2126 R + 0.7152 G + 0.0722 B
  sat_mean, sat_p95                 HSV saturation (max-min)/max over pixels with max >= 0.08
  clip_black                        fraction with Y <= 2/255
  clip_white                        fraction with min(R,G,B) >= 250/255
  hist16                            16-bin luma histogram (fractions)
  mean_rgb, unique_colors (cap 65536), flat_fraction (pixel equals right AND down neighbour),
  local_contrast (mean |dY| to right/down), grid_integrity (fraction of KxK blocks that are one colour; --block K, else null)
Targets: {"luma_p50": [0.3, 0.5], "clip_black": [null, 0.01]}; null end = open. Hard failures regardless of targets:
luma_std < 0.01 (blank frame) or clip_black > 0.5 (black frame).
"""
import argparse
import json
import sys

import numpy as np
from PIL import Image

UNIQUE_CAP = 65536
DEFAULT_TOL = 0.01
CHANGED_THRESH = 2  # a pixel counts as changed when any channel differs by more than 2/255


class Refused(Exception):
    pass


def load_rgb(path):
    im = Image.open(path)
    if im.mode in ("I", "I;16", "I;16B", "I;16L", "F"):
        raise Refused("%s: %s image (16/32-bit); expected 8-bit RGB" % (path, im.mode))
    if im.mode == "RGBA":
        a = np.asarray(im)[..., 3]
        if a.min() != 255:
            raise Refused("%s: RGBA with transparent pixels; expected an opaque screenshot" % path)
    elif im.mode == "P":
        im = im.convert("RGB")
    elif im.mode == "L":
        im = im.convert("RGB")
    elif im.mode != "RGB":
        raise Refused("%s: unsupported mode %s" % (path, im.mode))
    return np.asarray(im.convert("RGB"), dtype=np.uint8)


def measure(rgb, block=None):
    h, w, _ = rgb.shape
    f = rgb.astype(np.float64) / 255.0
    y = 0.2126 * f[..., 0] + 0.7152 * f[..., 1] + 0.0722 * f[..., 2]
    mx, mn = f.max(axis=2), f.min(axis=2)
    lit = mx >= 0.08
    sat = np.where(lit, (mx - mn) / np.maximum(mx, 1e-9), 0.0)
    sv = sat[lit]
    pct = np.percentile(y, [1, 5, 50, 95, 99])
    hist = np.histogram(y, bins=16, range=(0.0, 1.0))[0] / y.size
    packed = (rgb[..., 0].astype(np.uint32) << 16) | (rgb[..., 1].astype(np.uint32) << 8) | rgb[..., 2]
    uniq = int(min(np.unique(packed).size, UNIQUE_CAP))
    same_r = np.all(rgb[:-1, :-1] == rgb[:-1, 1:], axis=2)
    same_d = np.all(rgb[:-1, :-1] == rgb[1:, :-1], axis=2)
    flat = float(np.mean(same_r & same_d)) if h > 1 and w > 1 else 1.0
    lc = float((np.abs(np.diff(y, axis=1)).mean() + np.abs(np.diff(y, axis=0)).mean()) / 2) if h > 1 and w > 1 else 0.0
    grid = None
    if block and block > 1:
        bh, bw = h // block, w // block
        b = rgb[: bh * block, : bw * block].reshape(bh, block, bw, block, 3)
        grid = float(np.mean(np.all(b == b[:, :1, :, :1, :], axis=(1, 3, 4))))
    return {
        "size": [w, h],
        "luma_p1": float(pct[0]), "luma_p5": float(pct[1]), "luma_p50": float(pct[2]),
        "luma_p95": float(pct[3]), "luma_p99": float(pct[4]),
        "luma_mean": float(y.mean()), "luma_std": float(y.std()),
        "sat_mean": float(sv.mean()) if sv.size else 0.0,
        "sat_p95": float(np.percentile(sv, 95)) if sv.size else 0.0,
        "clip_black": float(np.mean(y <= 2 / 255)),
        "clip_white": float(np.mean(mn >= 250 / 255)),
        "hist16": [float(v) for v in hist],
        "mean_rgb": [float(f[..., i].mean()) for i in range(3)],
        "unique_colors": uniq, "flat_fraction": flat, "local_contrast": lc, "grid_integrity": grid,
    }


def hard_failures(m, expect_size=None):
    out = []
    if m["luma_std"] < 0.01:
        out.append({"metric": "luma_std", "value": m["luma_std"], "range": [0.01, None], "direction": "low",
                    "hint": "blank frame: nothing is lit or visible; check camera position/look_at, lights and that the scene loaded (read the log)"})
    if m["clip_black"] > 0.5:
        out.append({"metric": "clip_black", "value": m["clip_black"], "range": [None, 0.5], "direction": "high",
                    "hint": "more than half the frame is black: camera inside geometry, no light, or a shader failed"})
    if expect_size and list(expect_size) != m["size"]:
        out.append({"metric": "size", "value": m["size"], "range": list(expect_size), "direction": "mismatch",
                    "hint": "image is %dx%d but %dx%d was requested" % (m["size"][0], m["size"][1], expect_size[0], expect_size[1])})
    return out


def validate_targets(targets):
    """Refuse malformed targets before any engine run: {metric: [lo, hi]} with lo <= hi, null = open."""
    for k, rng in (targets or {}).items():
        if k.startswith("_"):
            continue
        if not (isinstance(rng, list) and len(rng) == 2 and all(x is None or (isinstance(x, (int, float)) and not isinstance(x, bool)) for x in rng)):
            raise Refused("target '%s' must be [lo, hi] (null = open end), got %r" % (k, rng))
        if rng[0] is not None and rng[1] is not None and rng[0] > rng[1]:
            raise Refused("target '%s' has lo %s > hi %s" % (k, rng[0], rng[1]))


def compare_targets(m, targets, tol=DEFAULT_TOL, fix_hints=None):
    """targets {metric: [lo, hi]} -> list of failures {metric, value, range, direction, hint}."""
    validate_targets(targets)
    fix_hints = fix_hints or {}
    fails = []
    for name, rng in (targets or {}).items():
        if name.startswith("_") or rng is None:
            continue
        if name not in m:
            raise Refused("unknown metric '%s' in targets" % name)
        v = m[name]
        if v is None:
            continue  # e.g. grid_integrity without --block: not measured
        lo, hi = rng
        d = None
        if lo is not None and v < lo - tol:
            d = "low"
        elif hi is not None and v > hi + tol:
            d = "high"
        if d:
            hint = (fix_hints.get(name) or {}).get(d) or "%s is %s: %.4f not in [%s, %s]" % (name, d, v, lo, hi)
            fails.append({"metric": name, "value": v, "range": [lo, hi], "direction": d, "hint": hint})
    return fails


def compare_images(a, b, expect, min_delta=0.05):
    """(ok, detail) for a deliberate change. a, b are metric dicts from measure() plus 'rgb' arrays under key '_rgb'."""
    ma, mb = a, b
    dp50 = mb["luma_p50"] - ma["luma_p50"]
    dsat = mb["sat_mean"] - ma["sat_mean"]
    if a["_rgb"].shape != b["_rgb"].shape:
        raise Refused("size mismatch: A is %dx%d, B is %dx%d" % (a["size"][0], a["size"][1], b["size"][0], b["size"][1]))
    delta = np.abs(a["_rgb"].astype(np.int16) - b["_rgb"].astype(np.int16))
    diff = float(delta.mean() / 255.0)
    changed = float(np.mean(delta.max(axis=2) > CHANGED_THRESH))
    dmean = mb["luma_mean"] - ma["luma_mean"]
    def tint(k):
        r = lambda m: m["mean_rgb"][k] - np.mean([m["mean_rgb"][i] for i in range(3) if i != k])
        return r(mb) - r(ma)
    table = {
        "brighter": (dp50 >= min_delta or dmean >= min_delta, "p50 delta %+.4f, mean delta %+.4f (need one >= %.3f); changed pixels %.1f%%" % (dp50, dmean, min_delta, changed * 100)),
        "darker": (-dp50 >= min_delta or -dmean >= min_delta, "p50 delta %+.4f, mean delta %+.4f (need one <= -%.3f); changed pixels %.1f%%" % (dp50, dmean, min_delta, changed * 100)),
        "more-saturated": (dsat >= min_delta, "sat_mean delta %+.4f (need >= %.3f)" % (dsat, min_delta)),
        "less-saturated": (-dsat >= min_delta, "sat_mean delta %+.4f (need <= -%.3f)" % (dsat, min_delta)),
        "different": (changed >= 0.01, "%.2f%% of pixels changed (need >= 1%%); mean abs diff %.4f" % (changed * 100, diff)),
        "same": (changed <= 0.001, "%.3f%% of pixels changed (need <= 0.1%%); mean abs diff %.4f" % (changed * 100, diff)),
    }
    for k, name in enumerate("rgb"):
        t = tint(k)
        table["tint-" + name] = (t >= min_delta, "%s-dominance delta %+.4f (need >= %.3f)" % (name, t, min_delta))
    if expect not in table:
        raise Refused("unknown expectation '%s'; choose from %s" % (expect, ", ".join(sorted(table))))
    return table[expect]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("image")
    ap.add_argument("--targets")
    ap.add_argument("--block", type=int)
    ap.add_argument("--tol", type=float, default=DEFAULT_TOL)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        m = measure(load_rgb(a.image), a.block)
        tg = json.load(open(a.targets)) if a.targets else {}
        fails = hard_failures(m) + compare_targets(m, tg.get("targets", tg), a.tol, tg.get("fix_hints"))
    except (Refused, OSError, ValueError) as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps({"metrics": m, "failures": fails}, indent=1))
    else:
        for k, v in m.items():
            if k != "hist16":
                print("%-16s %s" % (k, ("%.4f" % v) if isinstance(v, float) else v))
        for f in fails:
            print("FAIL %s=%s %s: %s" % (f["metric"], f["value"], f["direction"], f["hint"]))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
