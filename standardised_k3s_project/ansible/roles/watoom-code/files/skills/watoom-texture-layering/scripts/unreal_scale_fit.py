#!/usr/bin/env python3
"""watoom-texture-layering: make assets from different packs the same real-world scale (host-side; stdlib only).

Packs are modelled at different scales (a stylised house can be 18 m tall next to a 1.8 m human). Pick the reference
human (180 cm, UE mannequin) and give every class a target size; this turns measured sizes into scale factors.

  1. Measure each actor with the watoom-ue tool: level.get_actor_bounds {actorLabel} (boxExtent is half-size; double it) or
     asset.get_mesh_bounds {assetPath} for an asset. Write measurements.json:
       {"ZAS_House_1": {"class": "house", "height_cm": 1847, "longest_cm": 923, "scale": 1.0}, ...}
     ("scale" is the scale the actor currently has; measurements of a placed actor already include it.)
  2. unreal_scale_fit.py --measure measurements.json [--targets targets.json] --out scales.json
  3. Apply: level.set_actor_property / level.move_actor with the new scale, or put it in the recipe for
     unreal_scene_scatter.py (house_scale, prop_scale, foliage_scale) and place again. Measure again to confirm.

Targets are centimetres of "height" or of the "longest" side (metric), tuned to read right beside a 180 cm human.
"""
import argparse
import json
import sys

TARGETS = {
    "human": {"metric": "height_cm", "cm": 180}, "zombie": {"metric": "height_cm", "cm": 180}, "wizard": {"metric": "height_cm", "cm": 185},
    "boss_dragon": {"metric": "longest_cm", "cm": 1200}, "house": {"metric": "height_cm", "cm": 800}, "well": {"metric": "height_cm", "cm": 220},
    "campfire": {"metric": "longest_cm", "cm": 110}, "cart": {"metric": "longest_cm", "cm": 260}, "chest": {"metric": "longest_cm", "cm": 80},
    "sword": {"metric": "longest_cm", "cm": 105}, "pistol": {"metric": "longest_cm", "cm": 22}, "barrel": {"metric": "height_cm", "cm": 95},
    "crate": {"metric": "longest_cm", "cm": 70}, "tent": {"metric": "height_cm", "cm": 230}, "tower": {"metric": "height_cm", "cm": 900},
    "tree": {"metric": "height_cm", "cm": 1500}, "bush": {"metric": "height_cm", "cm": 130}, "rock": {"metric": "height_cm", "cm": 110},
    "boulder": {"metric": "height_cm", "cm": 220}, "grass_patch": {"metric": "longest_cm", "cm": 150}, "flower": {"metric": "height_cm", "cm": 45},
}


def fit(measure, targets=None, clamp=(0.05, 20.0)):
    t = dict(TARGETS)
    t.update(targets or {})
    out, problems = {}, []
    for name, m in measure.items():
        c = m.get("class")
        if c not in t:
            problems.append("%s: no target for class %r" % (name, c))
            continue
        cur = float(m.get(t[c]["metric"], 0))
        if cur <= 0:
            problems.append("%s: missing %s" % (name, t[c]["metric"]))
            continue
        base = float(m.get("scale", 1.0)) or 1.0
        factor = min(max(t[c]["cm"] / cur, clamp[0] / base), clamp[1] / base)
        out[name] = {"class": c, "from_scale": base, "scale": round(base * factor, 4), "target_cm": t[c]["cm"], "measured_cm": cur}
    return out, problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--measure", required=True)
    ap.add_argument("--targets")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    res, problems = fit(json.load(open(a.measure)), json.load(open(a.targets)) if a.targets else None)
    json.dump(res, open(a.out, "w"), indent=1)
    for k, v in res.items():
        print("%-18s %-12s %6.0f cm -> %5.0f cm  scale %.3f -> %.3f" % (k, v["class"], v["measured_cm"], v["target_cm"], v["from_scale"], v["scale"]))
    for p in problems:
        print("PROBLEM", p, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
