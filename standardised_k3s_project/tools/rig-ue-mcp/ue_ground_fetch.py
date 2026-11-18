#!/usr/bin/env python3
"""Read the live landscape layer weights (grass, dry_grass, dirt, mud, rock) into an npz for unreal_ground_paint.py plan.

  ue_ground_fetch.py --out live_weights.npz [--size 505] [--tile 127]
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "ansible", "roles", "watoom-code", "files", "skills", "watoom-texture-layering", "scripts"))
import ue_project  # noqa: E402
LAYERS = ("grass", "dry_grass", "dirt", "mud", "rock")


def parse_blocks(text):
    """Yield the JSON objects printed by `ue_route.py call` (one `[method] {...}` block per call)."""
    dec, i, out = json.JSONDecoder(), 0, []
    while True:
        j = text.find("] {", i)
        if j < 0:
            return out
        try:
            obj, end = dec.raw_decode(text, j + 2)
        except ValueError:
            i = j + 3
            continue
        out.append(obj)
        i = end


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, default=505)
    ap.add_argument("--tile", type=int, default=127)
    ap.add_argument("--landscape", required=True, help="landscape actor label (or set landscape in the --project profile)")
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    arrs = {k: np.zeros((a.size, a.size), np.uint8) for k in LAYERS}
    for y0 in range(0, a.size, a.tile):
        for x0 in range(0, a.size, a.tile):
            x1, y1 = min(x0 + a.tile - 1, a.size - 1), min(y0 + a.tile - 1, a.size - 1)
            calls = ["landscape.get_layer_weight_region " + json.dumps({"layerName": k, "actorLabel": a.landscape, "region": {"minX": x0, "minY": y0, "maxX": x1, "maxY": y1}, "includeWeights": True, "encoding": "base64"}) for k in LAYERS]
            r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "ue_route.py"), "call"] + calls, capture_output=True, text=True, timeout=300)
            blocks = parse_blocks(r.stdout)
            if len(blocks) != len(LAYERS) or not all(b.get("success") for b in blocks):
                sys.exit("tile %d,%d failed: %s" % (x0, y0, (r.stdout + r.stderr)[-300:]))
            for k, b in zip(LAYERS, blocks):
                w = np.frombuffer(base64.b64decode(b["weightsBase64"]), np.uint8).reshape(y1 - y0 + 1, x1 - x0 + 1)
                arrs[k][y0:y1 + 1, x0:x1 + 1] = w
    np.savez_compressed(a.out, **arrs)
    print("wrote", a.out, {k: round(float(v.mean()), 1) for k, v in arrs.items()})


if __name__ == "__main__":
    main()
