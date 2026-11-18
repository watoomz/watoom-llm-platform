#!/usr/bin/env python3
"""watoom-texture-layering: lay out a proper village around a plaza and level a pad for it (host-side; numpy + pillow).

  unreal_village.py plan --heights live.png --z0 3677.7 --raw-per-cm 4.4387 --size-m 4000 --cx 270635 --cy 314285 \
      [--flat-m 95 --blend-m 55] --out-heights pad.png --out-layout village.json

Writes the levelled heights (a flat disc of --flat-m at the mean ground height, blended back to the old ground over --blend-m; never below --min-above-sea
if --sea-z is given) and the layout json: {"center": [x, y], "level_z": z, "existing": {label: {x, y, yaw}}, "instances": [{"mesh", "x", "y", "yaw", "sink"}]}.
Meshes are Advanced Village Pack names (SM_<mesh>): houses (House_Var01/02, extents about 5-6 m), sheds (House_Var01_Extra01), fences (3.6 m sections), hay,
carts, barrels, crates, pots, pumpkins, flowers, street lights, stonepath tiles along four lanes, logs and stumps. Rings around the plaza: existing
houses r=18 m, new houses r=33 m and r=52 m (no house within 12 degrees of a lane), street lights r=25 m and r=43 m, haystacks and logs outside.
Fronts: yaw makes the mesh +X axis point at the plaza; add --front-offset DEG if the front turns out to be another side. Foliage-instance driver: tools/rig-ue-mcp/ue_village_build.py.
"""
import argparse
import json
import math
import sys

import numpy as np
from PIL import Image
from os.path import abspath as _abspath, dirname as _dirname  # noqa: E402
sys.path.insert(0, _dirname(_abspath(__file__)))  # so `python3 -I script.py` finds ue_project
import ue_project  # noqa: E402

LANES = (0.0, 90.0, 180.0, 270.0)
HOUSES = ("House_Var01", "House_Var02")


def pol(cx, cy, r, deg):
    a = math.radians(deg)
    return cx + r * math.cos(a), cy + r * math.sin(a)


def face(cx, cy, x, y, off=0.0):
    return math.degrees(math.atan2(cy - y, cx - x)) + off


def near_lane(deg, margin=12.0):
    return any(abs((deg - l + 180.0) % 360.0 - 180.0) < margin for l in LANES)


def layout(cx, cy, seed=7, front_offset=0.0, prefix=""):
    rnd = np.random.RandomState(seed)
    ins = []

    def add(mesh, x, y, yaw, sink=8.0):
        ins.append({"mesh": mesh, "x": round(x, 1), "y": round(y, 1), "yaw": round(yaw, 1), "sink": sink})

    existing = {}
    labels = [prefix + "House_%d" % i for i in range(1, 9)]
    for i, lab in enumerate(labels):  # the original eight houses, on the inner ring
        a = 45.0 * i + 22.5
        x, y = pol(cx, cy, 1800.0, a)
        existing[lab] = {"x": round(x, 1), "y": round(y, 1), "yaw": round(face(cx, cy, x, y, front_offset), 1)}
    existing[prefix + "Well"] = {"x": cx, "y": cy, "yaw": 0.0}
    existing[prefix + "Campfire"] = {"x": cx + 700.0, "y": cy - 500.0, "yaw": 0.0}
    existing[prefix + "Cart"] = {"x": cx - 900.0, "y": cy + 700.0, "yaw": 40.0}
    existing[prefix + "Chest"] = {"x": cx + 300.0, "y": cy + 900.0, "yaw": 90.0}
    existing[prefix + "Player"] = {"x": cx + 450.0, "y": cy + 250.0, "yaw": 140.0}
    for ring, (r, n, kind) in enumerate(((3300.0, 11, "b"), (5200.0, 15, "c"))):
        for i in range(n):
            a = 360.0 * i / n + (13.0 if ring == 0 else 5.0)
            if near_lane(a):
                continue
            x, y = pol(cx, cy, r + float(rnd.uniform(-250, 250)), a)
            yaw = face(cx, cy, x, y, front_offset)
            add(HOUSES[(i + ring) % 2], x, y, yaw, 15.0)
            tx, ty = -math.sin(math.radians(a)), math.cos(math.radians(a))  # tangent
            if kind == "b":  # yard clutter beside the house
                for mesh, off in (("Barrel", 650.0), ("Crate_Closed", 760.0), ("Pumpkin_Var01", 880.0), ("Pot_Var01", -650.0), ("Flower_Var01", -780.0)):
                    add(mesh, x + tx * off, y + ty * off, float(rnd.uniform(0, 360)))
            else:  # fenced yard behind the house
                bx, by = pol(cx, cy, r + 900.0, a)
                for k in (-1, 0, 1):
                    add("Fence_Var01", bx + tx * 360.0 * k, by + ty * 360.0 * k, a + 90.0, 5.0)
                add("Hay_Small_Var01", x + tx * 700.0, y + ty * 700.0, float(rnd.uniform(0, 360)))
                add("Barrel", x - tx * 650.0, y - ty * 650.0, 0.0)
    for r, n in ((2500.0, 10), (4300.0, 14)):
        for i in range(n):
            a = 360.0 * i / n + 18.0
            x, y = pol(cx, cy, r, a)
            add("StreetLight", x, y, a, 5.0)
    for lane in LANES:  # stone path tiles along the four lanes
        r = 500.0
        while r < 5800.0:
            x, y = pol(cx, cy, r, lane)
            add("Stonepath_Var01", x, y, lane, 2.0)
            r += 180.0
    for a in np.linspace(0.0, 360.0, 7)[:-1] + 20.0:
        x, y = pol(cx, cy, 6900.0 + float(rnd.uniform(-300, 300)), float(a))
        add("Hay_Stack", x, y, float(rnd.uniform(0, 360)))
    for a in (30.0, 150.0, 260.0):
        x, y = pol(cx, cy, 4200.0, a)
        add("Cart_Var01", x, y, a + 90.0)
    for i in range(8):
        x, y = pol(cx, cy, 7600.0 + float(rnd.uniform(-300, 300)), 45.0 * i + 10.0)
        add(("Log_Var01", "Treestump_Var01")[i % 2], x, y, float(rnd.uniform(0, 360)))
    return existing, ins


def pad(raw, z0, raw_per_cm, px_cm, cx, cy, flat_cm, blend_cm, sea_z=None, min_above_cm=250.0):
    """Returns (new raw, level_z). The disc inside flat_cm is one height (mean of the ground within it), blended back over blend_cm."""
    n, m = raw.shape
    yy, xx = np.mgrid[0:n, 0:m]
    d = np.hypot(xx * px_cm - cx, yy * px_cm - cy)
    z = raw.astype(float) / raw_per_cm + z0
    level = float(z[d <= flat_cm].mean())
    if sea_z is not None:
        level = max(level, sea_z + min_above_cm)
    t = np.clip((d - flat_cm) / max(blend_cm, 1.0), 0.0, 1.0)
    s = t * t * (3.0 - 2.0 * t)
    new = level + (z - level) * s
    new = np.where(d <= flat_cm + blend_cm, new, z)
    return np.clip(np.round((new - z0) * raw_per_cm), 0, 65535).astype(np.uint16), level


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--heights", required=True)
    p.add_argument("--z0", type=float, required=True)
    p.add_argument("--raw-per-cm", type=float, required=True)
    p.add_argument("--size-m", type=float, required=True)
    p.add_argument("--cx", type=float, required=True)
    p.add_argument("--cy", type=float, required=True)
    p.add_argument("--flat-m", type=float, default=95.0)
    p.add_argument("--blend-m", type=float, default=55.0)
    p.add_argument("--sea-z", type=float, default=None)
    p.add_argument("--front-offset", type=float, default=0.0)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--prefix", default="", help="actor label prefix of the existing village actors, e.g. MyGame_ (or label_prefix in the --project profile)")
    p.add_argument("--out-heights", required=True)
    p.add_argument("--out-layout", required=True)
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    raw = np.asarray(Image.open(a.heights))
    px_cm = a.size_m * 100.0 / (raw.shape[0] - 1)
    new, level = pad(raw, a.z0, a.raw_per_cm, px_cm, a.cx, a.cy, a.flat_m * 100.0, a.blend_m * 100.0, a.sea_z)
    Image.fromarray(new).save(a.out_heights)
    ex, ins = layout(a.cx, a.cy, a.seed, a.front_offset, a.prefix)
    json.dump({"center": [a.cx, a.cy], "level_z": level, "existing": ex, "instances": ins}, open(a.out_layout, "w"))
    kinds = {}
    for i in ins:
        kinds[i["mesh"]] = kinds.get(i["mesh"], 0) + 1
    print("pad level %.0f cm, %d px changed; %d existing actors repositioned, %d new instances: %s" % (level, int((new != raw).sum()), len(ex), len(ins), kinds))
    return 0


if __name__ == "__main__":
    sys.exit(main())
