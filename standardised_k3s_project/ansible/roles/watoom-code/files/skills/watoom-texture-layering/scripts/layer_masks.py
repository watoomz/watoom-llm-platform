#!/usr/bin/env python3
"""watoom-texture-layering: heightmap -> per-layer weight maps (splat maps) from slope / height / curvature / noise rules.

Reads the heightmap watoom-terrain-map already writes (heightmap.exr + meta.json), or a .npy / .png height field,
derives slope, normalised height, curvature and seeded macro noise, and turns a layer spec (JSON) into weight maps
that sum to exactly 1 per pixel. Output (all plain files; host-side, needs numpy + pillow only):

  splat_0.png, splat_1.png ...   RGBA 8-bit, 4 layers per image (layer i -> splat_{i//4}, channel i%4); every pixel's
                                 channels across all images sum to exactly 255 (largest-remainder quantisation)
  control_hint.png               R = base layer id, G = overlay (second strongest) layer id, B = blend 0-255 toward the
                                 overlay (the three values Terrain3D's control map encodes per pixel; this script does
                                 NOT write Terrain3D's packed control format, see SKILL.md)
  layer_preview.png              optional flat-colour composite using each layer's "color" (review aid, not a texture)
  layer_report.json              per-layer coverage, spec echo, input facts, and the sum-to-one check

Layer spec (JSON): {"layers": [ {name, ...rules}, ... ], "sharpness": 4.0, "seed": 1, "smooth_m": 0}
  Rules on a layer (all optional; a layer with none is "always on" and normally the fallback/base):
    "slope_deg":  [lo, hi, feather]      weight 1 for lo<=slope<=hi, smooth fall-off over `feather` degrees outside
    "height_m":   [lo, hi, feather]      metres above sea level (needs meta min/max or --height-range)
    "height_norm":[lo, hi, feather]      0..1 across the terrain's own relief
    "curvature":  {"kind": "convex"|"concave", "strength": 1.0}   convex = ridges/edges, concave = gullies/hollows
    "noise":      {"scale_m": 80, "amount": 0.25}   seeded fBm that pushes this layer's weight up/down (breaks straight edges)
    "fallback":   true                   the layer that takes whatever the others leave; exactly one is required
    "color":      [r, g, b]              0-1, only for layer_preview.png
  "smooth_m" (top level, default 0) blurs the heights over about this many metres BEFORE slope and curvature are derived
  (not for height rules). Open DEM data is quantised, which makes slope flicker pixel by pixel on gentle ground and shows up
  as speckle between layers; 2-3 cells' worth (e.g. 16-24 m at 7.8 m/sample) removes it without moving the big shapes.
  "sharpness" raises weights to a power before normalising: higher = crisper boundaries between layers (height-blend
  style), 1 = soft mix. Default 4.

Example:
  layer_masks.py --heightmap World/terrain/heightmap.exr --meta World/terrain/meta.json --spec layers.json --out World/terrain/layers
"""
import argparse
import json
import math
import os
import struct
import sys

import numpy as np


# ----------------------------------------------------------------------------- input

def read_exr_r_float(path):
    """Read the single-channel float, uncompressed, scanline EXR that build_terrain.py's writer produces."""
    data = open(path, "rb").read()
    if struct.unpack_from("<I", data, 0)[0] != 20000630:
        raise ValueError("not an EXR file")
    pos, width, height, compression = 8, None, None, None
    while data[pos] != 0:
        end = data.index(b"\x00", pos)
        name = data[pos:end].decode()
        end2 = data.index(b"\x00", end + 1)
        size = struct.unpack_from("<I", data, end2 + 1)[0]
        payload = data[end2 + 5:end2 + 5 + size]
        if name == "dataWindow":
            x0, y0, x1, y1 = struct.unpack("<4i", payload)
            width, height = x1 - x0 + 1, y1 - y0 + 1
        elif name == "compression":
            compression = payload[0]
        elif name == "channels" and not payload.startswith(b"R\x00"):
            raise ValueError("only a single 'R' float channel EXR is supported")
        pos = end2 + 5 + size
    if compression != 0:
        raise ValueError("only uncompressed EXR is supported (build_terrain.py writes NO_COMPRESSION)")
    pos += 1
    offsets = struct.unpack_from("<%dQ" % height, data, pos)
    out = np.empty((height, width), "<f4")
    for i, off in enumerate(offsets):
        y, n = struct.unpack_from("<iI", data, off)
        if n != width * 4:
            raise ValueError("unexpected scanline size")
        out[y] = np.frombuffer(data, "<f4", width, off + 8)
    return out.astype(np.float64)


def load_height(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".exr":
        return read_exr_r_float(path)
    if ext == ".npy":
        return np.load(path).astype(np.float64)
    if ext == ".png":
        from PIL import Image
        im = Image.open(path)
        arr = np.asarray(im, dtype=np.float64)
        if arr.ndim == 3:
            arr = arr[..., 0]
        return arr / (65535.0 if im.mode.startswith("I;16") or im.mode == "I" else 255.0)
    raise ValueError("unsupported heightmap type: " + ext)


# ----------------------------------------------------------------------------- derived fields

def smooth_field(a, radius):
    """Separable box blur, three passes (close to a Gaussian), edge-padded; radius in samples, 0 returns the input."""
    radius = int(radius)
    if radius <= 0:
        return a
    out = a.astype(np.float64)
    k = 2 * radius + 1
    for _ in range(3):
        for axis in (0, 1):
            pad = [(0, 0), (0, 0)]
            pad[axis] = (radius, radius)
            padded = np.pad(out, pad, mode="edge")
            c = np.cumsum(padded, axis=axis, dtype=np.float64)
            c = np.concatenate([np.zeros_like(np.take(c, [0], axis=axis)), c], axis=axis)
            hi = np.take(c, range(k, c.shape[axis]), axis=axis)
            lo = np.take(c, range(0, c.shape[axis] - k), axis=axis)
            out = (hi - lo) / k
    return out


def derive(norm, min_m, relief_m, cell_m, vscale=1.0, smooth_m=0.0):
    """Return slope_deg, height_m, height_norm, curvature (signed, +convex) for a normalised height field.
    smooth_m blurs the heights (metres) before slope/curvature only, so quantised DEM steps do not flicker the layers."""
    h = (min_m + norm * relief_m) * vscale
    full = h
    h = smooth_field(h, round(float(smooth_m) / cell_m / 2.0)) if smooth_m else h
    gy, gx = np.gradient(h, cell_m)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    lap = (np.roll(h, 1, 0) + np.roll(h, -1, 0) + np.roll(h, 1, 1) + np.roll(h, -1, 1) - 4.0 * h) / (cell_m * cell_m)
    lap[0, :], lap[-1, :], lap[:, 0], lap[:, -1] = 0, 0, 0, 0
    scale = np.percentile(np.abs(lap), 98) or 1.0
    curvature = np.clip(-lap / scale, -1.0, 1.0)  # +1 convex (ridge), -1 concave (hollow)
    return slope, full, norm, curvature


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def band(values, lo, hi, feather):
    """1 inside [lo, hi], smoothly 0 `feather` outside."""
    f = max(float(feather), 1e-9)
    return smoothstep((values - (lo - f)) / f) * smoothstep(((hi + f) - values) / f)


def fbm(shape, cell_m, scale_m, seed):
    """Seeded value-noise fBm in 0..1 (deterministic; periodic in nothing, built from upsampled random grids)."""
    rng = np.random.default_rng(seed)
    out = np.zeros(shape)
    amp, total = 1.0, 0.0
    for octave in range(5):
        cells = max(2, int(math.ceil(max(shape) * cell_m / max(scale_m / (2 ** octave), cell_m)))) + 1
        grid = rng.random((cells, cells))
        ys = np.linspace(0, cells - 1.001, shape[0])
        xs = np.linspace(0, cells - 1.001, shape[1])
        y0, x0 = ys.astype(int), xs.astype(int)
        fy, fx = smoothstep(ys - y0)[:, None], smoothstep(xs - x0)[None, :]
        a = grid[np.ix_(y0, x0)]
        b = grid[np.ix_(y0, x0 + 1)]
        c = grid[np.ix_(y0 + 1, x0)]
        d = grid[np.ix_(y0 + 1, x0 + 1)]
        out += amp * ((a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy)
        total += amp
        amp *= 0.5
    return out / total


# ----------------------------------------------------------------------------- weights

def layer_weights(spec, fields, cell_m, hrange):
    slope, height_m, height_norm, curvature = fields
    layers = spec["layers"]
    if not 1 <= len(layers) <= 8:
        raise ValueError("1-8 layers supported (two splat maps)")
    fb = [i for i, l in enumerate(layers) if l.get("fallback")]
    if len(fb) != 1:
        raise ValueError("exactly one layer must be marked \"fallback\": true")
    names = [l["name"] for l in layers]
    if len(set(names)) != len(names):
        raise ValueError("layer names must be unique")
    seed = int(spec.get("seed", 1))
    raw = []
    for i, l in enumerate(layers):
        if l.get("fallback"):
            raw.append(None)
            continue
        w = np.ones_like(slope)
        if "slope_deg" in l:
            w *= band(slope, *l["slope_deg"])
        if "height_m" in l:
            w *= band(height_m, *l["height_m"])
        if "height_norm" in l:
            w *= band(height_norm, *l["height_norm"])
        if "curvature" in l:
            c = l["curvature"]
            signed = curvature if c.get("kind", "convex") == "convex" else -curvature
            w *= smoothstep(signed * float(c.get("strength", 1.0)))
        if "noise" in l:
            n = l["noise"]
            field = fbm(slope.shape, cell_m, float(n.get("scale_m", 80.0)), seed + 101 * (i + 1))
            w *= np.clip(1.0 + (field - 0.5) * 2.0 * float(n.get("amount", 0.25)), 0.0, 2.0)
        raw.append(np.clip(w, 0.0, 1.0))
    others = np.zeros_like(slope)
    for w in raw:
        if w is not None:
            others = np.maximum(others, w)
    raw[fb[0]] = np.clip(1.0 - others, 0.0, 1.0)
    k = float(spec.get("sharpness", 4.0))
    stack = np.stack([np.power(w, k) if k != 1.0 else w for w in raw])
    total = stack.sum(axis=0)
    stack = np.where(total > 1e-9, stack / np.maximum(total, 1e-9), 0.0)
    stack[fb[0]] += np.where(total > 1e-9, 0.0, 1.0)  # a pixel nothing claimed goes to the fallback
    return names, stack


def quantise(stack):
    """float weights (L,H,W) summing to 1 -> uint8 summing to exactly 255 per pixel (largest remainder)."""
    scaled = stack * 255.0
    base = np.floor(scaled).astype(np.int32)
    short = 255 - base.sum(axis=0)
    order = np.argsort(-(scaled - base), axis=0)
    ranks = np.argsort(order, axis=0)
    base += (ranks < short[None]).astype(np.int32)
    return base.astype(np.uint8)


def write_outputs(out, names, q, layers, report):
    from PIL import Image
    os.makedirs(out, exist_ok=True)
    n = len(names)
    maps = []
    for m in range((n + 3) // 4):
        rgba = np.zeros(q.shape[1:] + (4,), np.uint8)
        for c in range(4):
            if m * 4 + c < n:
                rgba[..., c] = q[m * 4 + c]
        path = os.path.join(out, "splat_%d.png" % m)
        Image.fromarray(rgba, "RGBA").save(path)
        maps.append(os.path.basename(path))
    order = np.argsort(-q.astype(np.int16), axis=0)
    base, over = order[0], order[1] if n > 1 else order[0]
    qb = np.take_along_axis(q, base[None], 0)[0].astype(np.float64)
    qo = np.take_along_axis(q, over[None], 0)[0].astype(np.float64) if n > 1 else np.zeros_like(qb)
    blend = np.where(qb + qo > 0, np.round(255.0 * qo / np.maximum(qb + qo, 1.0)), 0).astype(np.uint8)
    hint = np.stack([base.astype(np.uint8), over.astype(np.uint8), blend], axis=-1)
    Image.fromarray(hint, "RGB").save(os.path.join(out, "control_hint.png"))
    if all("color" in l for l in layers):
        col = np.array([l["color"] for l in layers], np.float64)
        rgb = np.tensordot(q.astype(np.float64) / 255.0, col, axes=(0, 0))
        Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8), "RGB").save(os.path.join(out, "layer_preview.png"))
    report["files"] = maps + ["control_hint.png"]
    json.dump(report, open(os.path.join(out, "layer_report.json"), "w"), indent=2)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--heightmap", required=True, help=".exr (build_terrain.py), .npy or .png height field")
    ap.add_argument("--meta", help="build_terrain.py meta.json: min_elev_m, relief_m, meters_per_sample, height_scale")
    ap.add_argument("--cell-size", type=float, help="metres per pixel (overrides meta)")
    ap.add_argument("--height-range", nargs=2, type=float, metavar=("MIN_M", "MAX_M"), help="elevation of height 0 and 1 (overrides meta)")
    ap.add_argument("--spec", required=True, help="layer spec JSON")
    ap.add_argument("--out", required=True, help="output directory")
    args = ap.parse_args(argv)

    meta = json.load(open(args.meta)) if args.meta else {}
    cell = args.cell_size or meta.get("meters_per_sample")
    if not cell:
        raise SystemExit("need --cell-size or a --meta with meters_per_sample (slope depends on it)")
    norm = load_height(args.heightmap)
    lo, hi = args.height_range if args.height_range else (meta.get("min_elev_m", 0.0), meta.get("max_elev_m", 1.0))
    if not np.isfinite(norm).all():
        raise SystemExit("heightmap contains NaN/Inf")
    if norm.min() < -1e-6 or norm.max() > 1.0 + 1e-6:
        # a metres field, not a normalised one: normalise it and keep the real range
        lo, hi = float(norm.min()), float(norm.max())
        norm = (norm - lo) / max(hi - lo, 1e-9)
    spec = json.load(open(args.spec))
    fields = derive(norm, float(lo), float(hi) - float(lo), float(cell), float(meta.get("height_scale", 1.0)),
                    float(spec.get("smooth_m", 0.0)))
    names, stack = layer_weights(spec, fields, float(cell), (lo, hi))
    q = quantise(stack)
    sums = q.astype(np.int32).sum(axis=0)
    report = {
        "input": {"heightmap": os.path.basename(args.heightmap), "size_px": list(norm.shape), "cell_m": float(cell),
                  "elevation_m": [float(lo), float(hi)], "slope_deg_p50_p95_max": [float(np.percentile(fields[0], 50)), float(np.percentile(fields[0], 95)), float(fields[0].max())]},
        "sharpness": float(spec.get("sharpness", 4.0)), "seed": int(spec.get("seed", 1)),
        "layers": [{"name": n, "index": i, "splat": "splat_%d.png" % (i // 4), "channel": "RGBA"[i % 4],
                    "coverage_pct": round(float(q[i].astype(np.float64).sum() / (255.0 * q[i].size) * 100.0), 2)} for i, n in enumerate(names)],
        "sum_to_255_everywhere": bool((sums == 255).all()),
        "spec": spec,
    }
    write_outputs(args.out, names, q, spec["layers"], report)
    for layer in report["layers"]:
        print("%-14s %6.2f%%  -> %s.%s" % (layer["name"], layer["coverage_pct"], layer["splat"], layer["channel"]))
    print("sum-to-255 everywhere:", report["sum_to_255_everywhere"])
    return 0 if report["sum_to_255_everywhere"] else 1


if __name__ == "__main__":
    sys.exit(main())
