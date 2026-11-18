#!/usr/bin/env python3
"""watoom-texture-layering: prepare a terrain for an Unreal Landscape through ue-mcp (host-side; numpy + pillow only).

ue-mcp's landscape(import_heightmap) refuses 8-bit images and needs a 16-bit PNG (or raw16) whose size fits the landscape's
vertex grid, and landscape(set_layer_weight_region) takes one uint8 weight per vertex. The terrain builder writes a float EXR
and layer_masks.py writes splat maps, so this converts both to what ue-mcp accepts.

  heightmap  heightmap.exr + meta.json -> heightmap16.png (N x N, uint16 over the terrain's own range) + unreal_plan.json
  weights    layer_masks.py output dir  -> <layer>.u8 (N x N raw uint8) + tiles/<layer>/<y0>_<x0>.b64 + index.json

N must be a legal Unreal landscape vertex count: components x subsectionSizeQuads x numSubsections + 1, with
subsectionSizeQuads in 7/15/31/63/127/255 and numSubsections 1 or 2. Prefer the standard sizes 127, 253, 505, 1009, 2017,
4033 and 8129; other legal counts work but are unusual. The script refuses
anything else and lists the nearest legal sizes; it does not guess.

Orientation: row 0 of every image is written first, the same convention as the heightmap import, so weights and heights stay
aligned with each other. After the first import, read a corner back with landscape(get_height_region / get_layer_weight_region)
and compare it with the source; use --flip-y if the terrain is mirrored.

Example:
  unreal_landscape_export.py heightmap --heightmap terrain/heightmap.exr --meta terrain/meta.json --vertices 1009 --out ue
  unreal_landscape_export.py weights --layers terrain/layers --vertices 1009 --tile 128 --out ue
"""
import argparse
import base64
import hashlib
import json
import os
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import layer_masks as lm  # noqa: E402

QUADS = (7, 15, 31, 63, 127, 255)
STANDARD = (127, 253, 505, 1009, 2017, 4033, 8129)  # the sizes Unreal's own landscape tool offers


def legal_vertex_counts(limit=8129):
    out = set()
    for q in QUADS:
        for sub in (1, 2):
            for comps in range(1, 65):
                n = comps * q * sub + 1
                if n <= limit:
                    out.add(n)
    return sorted(out)


def require_legal(n):
    legal = legal_vertex_counts()
    if n not in legal:
        near = sorted(legal, key=lambda v: abs(v - n))[:6]
        raise SystemExit("%d is not a legal Unreal landscape vertex count (components x quads x subsections + 1). Nearest legal: %s. Standard sizes: %s" % (n, sorted(near), list(STANDARD)))


def resample(a, n):
    """Bilinear resample of a 2-D array to n x n with corners aligned (vertex grids, not pixel grids)."""
    h, w = a.shape
    ys, xs = np.linspace(0, h - 1, n), np.linspace(0, w - 1, n)
    y0, x0 = np.minimum(ys.astype(int), h - 2), np.minimum(xs.astype(int), w - 2)
    fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
    top = a[np.ix_(y0, x0)] * (1 - fx) + a[np.ix_(y0, x0 + 1)] * fx
    bot = a[np.ix_(y0 + 1, x0)] * (1 - fx) + a[np.ix_(y0 + 1, x0 + 1)] * fx
    return top * (1 - fy) + bot * fy


def cmd_heightmap(args):
    require_legal(args.vertices)
    norm = lm.load_height(args.heightmap)
    meta = json.load(open(args.meta)) if args.meta else {}
    lo = args.height_range[0] if args.height_range else meta.get("min_elev_m")
    hi = args.height_range[1] if args.height_range else meta.get("max_elev_m")
    size = args.size_m or meta.get("size_m")
    if None in (lo, hi, size):
        raise SystemExit("need elevation range and size: pass --meta (build_terrain.py) or --height-range and --size-m")
    if norm.min() < -1e-6 or norm.max() > 1.0 + 1e-6:
        raise SystemExit("heightmap is not normalised 0..1; pass the builder's heightmap.exr with its meta.json")
    g = resample(norm, args.vertices)
    if args.flip_y:
        g = g[::-1]
    u16 = np.clip(np.rint(g * 65535.0), 0, 65535).astype("<u2")
    from PIL import Image
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "heightmap16.png")
    Image.fromarray(u16).save(path)
    plan = {"heightmap": "heightmap16.png", "width": args.vertices, "height": args.vertices, "format": "png16",
            "plan_real_world_args": {"minElevationMeters": float(lo), "maxElevationMeters": float(hi), "realWorldSizeMeters": {"x": float(size), "y": float(size)},
                                     "sourcePath": os.path.abspath(path), "width": args.vertices, "height": args.vertices, "elevationEncoding": "full"},
            "metres_per_quad": float(size) / (args.vertices - 1),
            "vertical_step_m": (float(hi) - float(lo)) / 65535.0,
            "note": "Call landscape(plan_real_world) with plan_real_world_args first; it returns the create and import_heightmap parameters. "
                    "The PNG must be reachable by the machine running Unreal (a relative filePath resolves under the project's Saved directory)."}
    json.dump(plan, open(os.path.join(args.out, "unreal_plan.json"), "w"), indent=2)
    print("wrote", path, "%dx%d uint16, %.2f m per quad, %.4f m per height step" % (args.vertices, args.vertices, plan["metres_per_quad"], plan["vertical_step_m"]))
    return 0


def cmd_weights(args):
    require_legal(args.vertices)
    report = json.load(open(os.path.join(args.layers, "layer_report.json")))
    from PIL import Image
    chans = {}
    for layer in report["layers"]:
        img = np.asarray(Image.open(os.path.join(args.layers, layer["splat"])), np.float64)
        chans[layer["name"]] = img[..., "RGBA".index(layer["channel"])]
    names = list(chans)
    stack = np.stack([resample(chans[n], args.vertices) for n in names])
    stack = stack / np.maximum(stack.sum(axis=0), 1e-9)
    if args.flip_y:
        stack = stack[:, ::-1]
    q = lm.quantise(stack)  # exactly 255 across layers at every vertex
    os.makedirs(args.out, exist_ok=True)
    index = {"vertices": args.vertices, "tile": args.tile, "layers": {}, "sum_is_255_everywhere": bool((q.astype(np.int32).sum(axis=0) == 255).all()),
             "note": "weights are uint8, row-major from the top row; pass a tile's file content as weightsBase64 to landscape(set_layer_weight_region) with a region that covers x0..x0+width-1, y0..y0+height-1 (describe the action for the exact region object). Write EVERY layer for a region: the engine does not renormalise the others."}
    for i, name in enumerate(names):
        raw = q[i].tobytes()
        open(os.path.join(args.out, name + ".u8"), "wb").write(raw)
        tiles = []
        tdir = os.path.join(args.out, "tiles", name)
        os.makedirs(tdir, exist_ok=True)
        for y0 in range(0, args.vertices, args.tile):
            for x0 in range(0, args.vertices, args.tile):
                blk = np.ascontiguousarray(q[i][y0:y0 + args.tile, x0:x0 + args.tile])
                fn = "%d_%d.b64" % (y0, x0)
                open(os.path.join(tdir, fn), "w").write(base64.b64encode(blk.tobytes()).decode())
                tiles.append({"file": "tiles/%s/%s" % (name, fn), "x0": x0, "y0": y0, "width": blk.shape[1], "height": blk.shape[0]})
        index["layers"][name] = {"raw": name + ".u8", "sha256": hashlib.sha256(raw).hexdigest(), "tiles": tiles,
                                 "coverage_pct": round(float(q[i].astype(np.float64).sum() / (255.0 * q[i].size) * 100.0), 2)}
    json.dump(index, open(os.path.join(args.out, "index.json"), "w"), indent=2)
    for n, v in index["layers"].items():
        print("%-12s %6.2f%%  %d tiles" % (n, v["coverage_pct"], len(v["tiles"])))
    print("sum to 255 at every vertex:", index["sum_is_255_everywhere"])
    return 0 if index["sum_is_255_everywhere"] else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("heightmap")
    h.add_argument("--heightmap", required=True)
    h.add_argument("--meta")
    h.add_argument("--height-range", nargs=2, type=float, metavar=("MIN_M", "MAX_M"))
    h.add_argument("--size-m", type=float, help="terrain edge length in metres (overrides meta)")
    h.add_argument("--vertices", type=int, required=True)
    h.add_argument("--flip-y", action="store_true")
    h.add_argument("--out", required=True)
    h.set_defaults(fn=cmd_heightmap)
    w = sub.add_parser("weights")
    w.add_argument("--layers", required=True, help="layer_masks.py output directory")
    w.add_argument("--vertices", type=int, required=True)
    w.add_argument("--tile", type=int, default=128)
    w.add_argument("--flip-y", action="store_true")
    w.add_argument("--out", required=True)
    w.set_defaults(fn=cmd_weights)
    a = ap.parse_args(argv)
    if a.cmd == "weights" and not 8 <= a.tile <= 512:
        raise SystemExit("--tile must be 8..512")
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
