#!/usr/bin/env python3
"""Read the live landscape heights into a 16-bit PNG (the `--heights` input of every unreal_*.py helper). Host-side; numpy + pillow.

  ue_heights_fetch.py --out live_heights.png [--landscape LABEL | --project FILE] [--size 505] [--tile 127]

--size is the landscape's vertex count per side (505 for a 4 km map at 8 m per vertex). Reads `landscape.get_height_region` tile by tile,
so it sees what is in the editor now, including carved creeks and lake beds.

The png holds the VISIBLE height: the plain merged reply (base `Layer` plus the additive `Water` layer). Do not rebuild it from an
editLayer:"Layer" read -- on this map that read is wrong along whole vertex lines (x=126 and y=126) while the merged read is right
(T-0049, 2026-11-18). It also reads the Water layer and prints how many vertices carry a Water offset (carved beds). Writing these
heights back is safe only through ue_run_phases.py, which subtracts the live Water offset before a base-layer write; any other path
writes the offset into the base terrain a second time.

Also writes `<out>.fingerprint.json` (sha256, shape, landscape, fetchedAt) next to the png -- unreal_lake_smooth.py's
heights_freshness.check_sidecar() uses it to catch a wrong/edited heights file; ue_stray_check.py / ue_foliage_buried.py
instead re-read a few live sample points (heights_freshness.check_live) since they already hold a transport.
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "ansible", "roles", "watoom-code", "files", "skills", "watoom-texture-layering", "scripts"))
import ue_project  # noqa: E402
from ue_ground_fetch import parse_blocks  # noqa: E402
from heights_freshness import write_fingerprint  # noqa: E402


def tile_ranges(size, tile):
    for y0 in range(0, size, tile):
        for x0 in range(0, size, tile):
            yield x0, y0, min(x0 + tile - 1, size - 1), min(y0 + tile - 1, size - 1)


WATER_MID = 32768  # the Water edit layer's neutral value (ue_lake_as_river.WATER_LAYER_MID)


def fetch_tile(landscape, region, run=subprocess.run):
    """One ue_route session per tile, two reads: merged (the png) and Water (offset count). Returns (merged uint16 array, offsets)."""
    calls = ["landscape.get_height_region " + json.dumps(dict({"actorLabel": landscape, "region": region}, **extra))
             for extra in ({}, {"editLayer": "Water"})]
    r = run([sys.executable, "-I", os.path.join(HERE, "ue_route.py"), "call"] + calls, capture_output=True, text=True, timeout=300)
    blocks = parse_blocks(r.stdout)
    if len(blocks) != 2 or not all(b.get("success") and "heights" in b for b in blocks):
        sys.exit("tile %d,%d failed: %s" % (region["minX"], region["minY"], (r.stdout + r.stderr)[-300:]))
    water = np.asarray(blocks[1]["heights"], np.int64)
    return np.asarray(blocks[0]["heights"], np.uint16), int((water != WATER_MID).sum())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, default=505)
    ap.add_argument("--tile", type=int, default=127)
    ap.add_argument("--landscape", required=True, help="landscape actor label (or set landscape in the --project profile)")
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    raw = np.zeros((a.size, a.size), np.uint16)
    offset = 0
    for x0, y0, x1, y1 in tile_ranges(a.size, a.tile):
        merged, n_offset = fetch_tile(a.landscape, {"minX": x0, "minY": y0, "maxX": x1, "maxY": y1})
        raw[y0:y1 + 1, x0:x1 + 1] = merged.reshape(y1 - y0 + 1, x1 - x0 + 1)
        offset += n_offset
    Image.fromarray(raw).save(a.out)
    fp = write_fingerprint(a.out, raw, a.landscape)
    print("wrote", a.out, raw.shape, int(raw.min()), int(raw.max()), "fingerprint", fp["sha256"][:12])
    print("%d vertices carry a Water-layer offset (carved beds); apply height calls only with ue_run_phases.py" % offset)


if __name__ == "__main__":
    main()
