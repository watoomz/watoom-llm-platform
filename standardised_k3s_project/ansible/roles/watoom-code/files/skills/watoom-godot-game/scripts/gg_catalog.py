#!/usr/bin/env python3
"""Asset catalog: classify every plant, rock and prop BEFORE it is placed. 3D only.

  gg_catalog.py init     --project P [--dry-run]            default families (built from primitives in the project's style) + gg_catalog.json
  gg_catalog.py list     --project P
  gg_catalog.py validate --project P                        schema and category rules; exit 1 lists every problem
  gg_catalog.py add      --project P --family F --scene res://x.tscn|.glb --category C [--above-sea LO HI] [--max-slope S] [--near-water LO HI]
                          [--min-spacing M] [--scale-range LO HI] [--wind W] [--note TEXT]     unknown packs: classify first (see references/gg-catalog.md)
  gg_catalog.py inspect  --project P --family F [--out DIR]  look inside the scene, render it at eye level in sun and shade, flag black / white /
                          glowing / invisible / wrong-scale / lying-down assets; stamps `verified` ONLY when everything passes

Catalog file: <project>/gg_catalog.json. `verified_sha` binds a family to its category, scene, .import file and dependencies (verified_deps). Heights are metres above world.sea_level_m; near_water_m is the distance to the nearest water cell
(gg_water.py water_dist.f32); null = no limit. Scatter (gg_scatter.py) refuses a family that is unverified or whose scene file changed since.
Exit codes: 0 pass | 1 check failed | 2 refused | 3 engine log fatal | 4 no verdict | 5 runner failure.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
import gg_godot  # noqa: E402
import gg_metrics  # noqa: E402
import gg_project  # noqa: E402
import gg_style  # noqa: E402
import gg_verify  # noqa: E402

CATEGORIES = {
    "tree_upland": "Canopy trees on dry ground; never at the water line; thin on steep ground.",
    "tree_riparian": "Trees that want wet feet: creek banks and lake edges.",
    "shrub": "Bushes and mid-storey plants on dry ground.",
    "groundcover": "Low plants and ferns.",
    "grass": "Grass tufts and patches; the main density carrier.",
    "flower": "Flower patches, small clusters.",
    "wet_margin": "Marsh and emergent plants (reeds, sedges): creek banks, lake margins and the shallows.",
    "aquatic": "Floating or submerged plants: in the water only.",
    "dune_coast": "Beach and dune plants: sand, close above the sea.",
    "dry_scrub": "Drought plants: well-drained ground away from water.",
    "rock": "Boulders and pebbles: any ground, never floating.",
    "prop": "Authored props (houses, fences): placed once, never scattered.",
}
# plausible height (m) of one instance per category; outside 3x of this range the scale is almost certainly wrong (cm vs m export)
HEIGHT_M = {"tree_upland": (3, 40), "tree_riparian": (3, 30), "shrub": (0.3, 4), "groundcover": (0.1, 1.5), "grass": (0.05, 1.5), "flower": (0.05, 1.2),
            "wet_margin": (0.3, 3.5), "aquatic": (0.02, 1.5), "dune_coast": (0.3, 12), "dry_scrub": (0.3, 3), "rock": (0.1, 10), "prop": (0.3, 30)}
SINGLE_SIDED = ("grass", "groundcover", "wet_margin", "flower", "aquatic")
FAMILY_KEYS = {"category", "scene", "above_sea_m", "max_slope", "near_water_m", "allow_in_sea", "scale_range", "min_spacing_m", "wind", "notes", "verified", "verified_sha", "verified_deps"}
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")

# default families: kind is a build_assets.gd shape; layer = which terrain-layer colour the foliage borrows from the style's layer template
DEFAULTS = [
    {"name": "pine", "kind": "conifer", "height": 9.0, "radius": 1.6, "leaf": "grass", "dark": 0.55, "category": "tree_upland", "above_sea_m": [1.5, 60.0], "max_slope": 0.6, "near_water_m": [8, None], "min_spacing_m": 4.0, "wind": 0.3},
    {"name": "oak", "kind": "broadleaf", "height": 8.0, "radius": 2.2, "leaf": "grass", "dark": 0.75, "category": "tree_upland", "above_sea_m": [1.5, 50.0], "max_slope": 0.5, "near_water_m": [6, None], "min_spacing_m": 5.0, "wind": 0.3},
    {"name": "palm", "kind": "palm", "height": 7.0, "radius": 1.8, "leaf": "grass", "dark": 0.9, "category": "dune_coast", "above_sea_m": [0.3, 6.0], "max_slope": 0.4, "near_water_m": [0, 60], "min_spacing_m": 4.0, "wind": 0.6},
    {"name": "bush", "kind": "shrub", "height": 1.4, "radius": 0.9, "leaf": "grass", "dark": 0.8, "category": "shrub", "above_sea_m": [1.0, 60.0], "max_slope": 0.6, "near_water_m": [3, None], "min_spacing_m": 1.5, "wind": 0.2},
    {"name": "grass_tuft", "kind": "grass", "height": 0.5, "radius": 0.35, "leaf": "grass", "dark": 1.0, "category": "grass", "above_sea_m": [0.5, 60.0], "max_slope": 0.5, "near_water_m": [1, None], "min_spacing_m": 0.6, "wind": 0.7},
    {"name": "flower_patch", "kind": "flower", "height": 0.4, "radius": 0.1, "leaf": "sand", "dark": 0.7, "category": "flower", "above_sea_m": [1.0, 50.0], "max_slope": 0.4, "near_water_m": [2, None], "min_spacing_m": 0.8, "wind": 0.5},
    {"name": "reed", "kind": "reed", "height": 1.8, "radius": 0.6, "leaf": "grass", "dark": 0.9, "category": "wet_margin", "above_sea_m": [-0.3, None], "max_slope": 0.25, "near_water_m": [0, 12], "min_spacing_m": 0.9, "wind": 0.6},
    {"name": "boulder", "kind": "rock", "height": 1.6, "radius": 1.1, "leaf": "rock", "dark": 1.0, "category": "rock", "above_sea_m": [-0.5, 60.0], "max_slope": 1.0, "near_water_m": [0, None], "allow_in_sea": True, "min_spacing_m": 3.0, "wind": 0.0},
]


def catalog_path(project):
    return os.path.join(project, "gg_catalog.json")


def sha_of(project, scene):
    """sha256 of one file inside the project (res://a/b.tscn -> <project>/a/b.tscn); None when missing."""
    rel = scene[len("res://"):] if scene.startswith("res://") else scene
    p = os.path.join(project, rel)
    return hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.isfile(p) else None


def fingerprint(project, f):
    """What `verified` is bound to: the category, the scene file, its import settings and every file the scene depends on (textures, materials, meshes)."""
    h = hashlib.sha256()
    h.update(("category=%s\n" % f.get("category")).encode())
    scene = f.get("scene", "")
    for path in [scene, scene + ".import"] + list(f.get("verified_deps") or []):
        if path.startswith("res://"):
            h.update(("%s=%s\n" % (path, sha_of(project, path))).encode())
    return h.hexdigest()


def load_catalog(project):
    p = catalog_path(project)
    if not os.path.isfile(p):
        raise gg_godot.Refused("no %s: run gg_catalog.py init (or add a family)" % p)
    try:
        return json.load(open(p))
    except json.JSONDecodeError as e:
        raise gg_godot.Refused("%s is not valid JSON: %s" % (p, e))


def save_catalog(project, cat):
    p = catalog_path(project)
    with open(p + ".new", "w") as f:
        json.dump(cat, f, indent=1)
        f.write("\n")
    os.replace(p + ".new", p)


def _rng(v, what, errs, lo=None, hi=None, allow_null_hi=True):
    if not (isinstance(v, list) and len(v) == 2):
        errs.append("%s must be [low, high] (use null for no limit)" % what)
        return
    a, b = v
    if isinstance(a, bool) or isinstance(b, bool):
        errs.append("%s must hold numbers or null" % what)
        return
    if a is not None and not isinstance(a, (int, float)) or b is not None and not isinstance(b, (int, float)):
        errs.append("%s must hold numbers or null" % what)
        return
    if a is not None and b is not None and a > b:
        errs.append("%s is [%s, %s]: low is above high" % (what, a, b))
    if lo is not None and a is not None and a < lo:
        errs.append("%s low %s is under %s" % (what, a, lo))
    if hi is not None and b is not None and b > hi:
        errs.append("%s high %s is over %s" % (what, b, hi))
    if not allow_null_hi and b is None:
        errs.append("%s needs a high limit (a number)" % what)


def family_errors(name, f):
    errs = []
    pre = "family %s: " % name
    if not isinstance(name, str) or not NAME_RE.match(name):
        return [pre + "the name must match ^[a-z][a-z0-9_]{0,31}$ (lower case letters, digits, underscore: it becomes a node and a folder name)"]
    if not isinstance(f, dict):
        return [pre + "must be an object"]
    unknown = set(f) - FAMILY_KEYS
    if unknown:
        errs.append(pre + "unknown key(s) %s (allowed: %s)" % (sorted(unknown), sorted(FAMILY_KEYS)))
    cat = f.get("category")
    if cat not in CATEGORIES:
        errs.append(pre + "category '%s' is not one of %s" % (cat, sorted(CATEGORIES)))
        return errs
    if not str(f.get("scene", "")).startswith("res://"):
        errs.append(pre + "scene must be a res:// path")
    e = []
    _rng(f.get("above_sea_m"), "above_sea_m", e)
    _rng(f.get("near_water_m"), "near_water_m", e, lo=0)
    if not e and f["near_water_m"][0] is None:
        e.append("near_water_m low must be a number (use 0 for no minimum)")
    ms = f.get("max_slope")
    if not isinstance(ms, (int, float)) or not 0 < ms <= 2:
        e.append("max_slope must be a number in (0, 2] (rise over run)")
    sp = f.get("min_spacing_m")
    if not isinstance(sp, (int, float)) or sp <= 0:
        e.append("min_spacing_m must be a positive number")
    sr = f.get("scale_range", [0.8, 1.25])
    _rng(sr, "scale_range", e, lo=0.2, hi=4.0, allow_null_hi=False)
    w = f.get("wind", 0.0)
    if not isinstance(w, (int, float)) or not 0 <= w <= 1:
        e.append("wind must be a number 0..1")
    errs += [pre + x for x in e]
    if errs:
        return errs
    nw = f["near_water_m"]
    hi = f["above_sea_m"][1]
    if cat in ("wet_margin", "aquatic") and (nw[1] is None or nw[1] > 40):
        errs.append(pre + "a %s family needs near_water_m with a high limit of at most 40 m (distance to water is its axis, not height)" % cat)
    if cat == "aquatic" and nw[1] is not None and nw[1] > 4:
        errs.append(pre + "an aquatic family stands in the water: near_water_m high must be at most 4 m (one cell)")
    if cat in ("wet_margin", "aquatic") and hi is not None:
        errs.append(pre + "a %s family must not have an upper above_sea_m limit (creeks lie at any height): use null" % cat)
    if cat == "dune_coast" and (hi is None or hi > 15):
        errs.append(pre + "a dune_coast family needs above_sea_m high <= 15 m (coast plants stay close above the sea)")
    if cat == "tree_upland" and nw[0] < 4:
        errs.append(pre + "an upland tree needs near_water_m low >= 4 (keep back from the water line)")
    if cat == "dry_scrub" and nw[0] < 10:
        errs.append(pre + "dry scrub needs near_water_m low >= 10")
    if f.get("allow_in_sea") and cat not in ("rock", "aquatic"):
        errs.append(pre + "only rock and aquatic families may have allow_in_sea")
    if cat in ("rock", "prop") and w:
        errs.append(pre + "rock and prop families must have wind 0")
    return errs


def validate(cat):
    errs = []
    if cat.get("schema") != 1:
        errs.append("catalog schema must be 1")
    fams = cat.get("families")
    if not isinstance(fams, dict) or not fams:
        return errs + ["catalog has no families"]
    for n, f in fams.items():
        errs += family_errors(n, f)
    return errs


def stands_on_dry_land(f):
    """Families that must not stand in the sea or in a creek (everything except rock, wet margin and aquatic plants)."""
    return not f.get("allow_in_sea") and f["category"] not in ("wet_margin", "aquatic")


def default_colours(preset_name):
    """Foliage colours come from the style's own terrain-layer colours (so a palette style stays inside its palette)."""
    sp = json.load(open(os.path.join(os.path.dirname(HERE), "templates", "layers.%s.json" % preset_name)))
    return {l["name"]: l["color"] for l in sp["layers"] if "color" in l}


def asset_specs(preset_name):
    cols = default_colours(preset_name)
    specs = []
    for d in DEFAULTS:
        base = cols.get(d["leaf"], cols.get("grass"))
        leaf = [round(c * d["dark"], 4) for c in base]
        trunk = cols.get("dirt", [0.4, 0.3, 0.2])
        specs.append({"name": d["name"], "kind": d["kind"], "height": d["height"], "radius": d["radius"], "colors": {"leaf": leaf, "trunk": [round(c * 0.8, 4) for c in trunk]}})
    return specs


def init(project, dry_run=False, run=gg_godot.run):
    prof = gg_project.load_profile(project)
    if prof["dimension"] != "3d":
        raise gg_godot.Refused("the catalog and scatter are 3D only")
    style = gg_style.check_applied(project, prof)
    if os.path.exists(catalog_path(project)):
        raise gg_godot.Refused("%s already exists: edit it, or delete it to start over" % catalog_path(project))
    specs = asset_specs(prof["style"]["preset"])
    if dry_run:
        print("would build %d assets in res://assets/gg/ and write %s: %s" % (len(specs), catalog_path(project), ", ".join(s["name"] for s in specs)))
        return 0, None
    r = run(project, "build_assets", {"style": style, "out_dir": "res://assets/gg", "assets": specs}, render=False, renderer=style["renderer"], timeout=300)
    if r.code:
        return r.code, {"why": r.why}
    fams = {}
    for d, a in zip(DEFAULTS, r.result["data"]["assets"]):
        f = {k: d[k] for k in ("category", "above_sea_m", "max_slope", "near_water_m", "min_spacing_m", "wind") if k in d}
        f.update(scene=a["scene"], scale_range=[0.8, 1.3], verified=None, verified_sha=None, verified_deps=None, notes="default procedural asset: %.1f m tall, %.1f m wide" % (a["height_m"], a["width_m"]))
        if d.get("allow_in_sea"):
            f["allow_in_sea"] = True
        fams[d["name"]] = f
    cat = {"schema": 1, "_comment": "Edit habitat values for your level. `verified` is set only by gg_catalog.py inspect.", "categories": CATEGORIES, "families": fams}
    errs = validate(cat)
    if errs:
        return 1, {"why": "the default catalog is invalid: " + "; ".join(errs)}
    save_catalog(project, cat)
    return 0, {"families": list(fams)}


def asset_flags(data, category, family=""):
    """Static checks on the inspect_asset result. -> list of {level: error|warn|info, msg}. Pure."""
    out = []

    def add(level, msg):
        out.append({"level": level, "msg": msg})
    if not data.get("meshes"):
        add("error", "the scene has no mesh (empty, or only lights/colliders): nothing would render")
        return out
    h, w = data["aabb"]["size"][1], max(data["aabb"]["size"][0], data["aabb"]["size"][2])
    lo, hi = HEIGHT_M[category]
    if h < lo / 3 or h > hi * 3:
        add("error", "height %.2f m is far outside %.2f..%.2f m for category %s: wrong scale (an export in centimetres or millimetres?); scale the scene or the import" % (h, lo, hi, category))
    elif h < lo or h > hi:
        add("warn", "height %.2f m is outside the usual %.2f..%.2f m for %s" % (h, lo, hi, category))
    if category in ("tree_upland", "tree_riparian", "dune_coast", "shrub") and w > 3 * h:
        add("error", "the asset is %.1f m wide and %.1f m tall: probably Z-up (lying down); rotate it or fix the import up-axis" % (w, h))
    base = data["aabb"]["pos"][1]
    if abs(base) > 0.3 * max(h, 0.1):
        add("error", "the lowest point is %.2f m from the origin (height %.2f m): scatter puts the origin on the ground, so it would float or sink; move the mesh so its base is at y = 0" % (base, h))
    if data.get("lights"):
        add("warn", "the scene contains %d light(s): thousands of copies would each carry one" % data["lights"])
    if data.get("skeletons") or data.get("animation_players"):
        add("info", "skeleton/animation found: a MultiMesh scatter shows the rest pose only")
    if data.get("triangles", 0) > 20000:
        add("warn", "%d triangles per instance is heavy for a scatter (aim under 5000)" % data["triangles"])
    seen = set()
    for m in data.get("materials", []):
        tag = "%s/%s" % (m["node"], m["surface"])
        if m["kind"] == "none":
            add("error", "%s has no material: it renders default white" % tag)
            continue
        a = m.get("albedo")
        if a and not m.get("albedo_texture"):
            lum = 0.2126 * a[0] + 0.7152 * a[1] + 0.0722 * a[2]
            if lum < 0.03 and not m.get("emission"):
                add("error", "%s albedo is black (luma %.3f) and has no texture: it renders black" % (tag, lum))
            if lum > 0.95:
                add("warn", "%s albedo is white (luma %.3f) and has no texture: it will glare in sun" % (tag, lum))
            if a[3] < 0.05:
                add("error", "%s has alpha %.2f: invisible" % (tag, a[3]))
        if m.get("emission", 0) > 0.05:
            add("error", "%s glows (emission %.2f)" % (tag, m["emission"]))
        if category in SINGLE_SIDED and m.get("cull") == "back" and m["kind"] != "ShaderMaterial":
            seen.add(m["node"])
    if seen:
        add("warn", "%d part(s) (%s%s) are single-sided (back faces culled): thin %s geometry can vanish from behind; set the material to cull disabled" % (len(seen), ", ".join(sorted(seen)[:3]), ", ..." if len(seen) > 3 else "", category))
    return out


def view_set(prof, style, data):
    """Eye-level cameras: `sun` looks at the side the sun lights, `shade` at the side in shadow. Same distance, 1.6 m up."""
    h, w = data["aabb"]["size"][1], max(data["aabb"]["size"][0], data["aabb"]["size"][2])
    big = max(h, w)
    d = 1.7 * big + 1.5
    az = np.radians(style["lighting"]["sun_azimuth_deg"])
    src = np.array([np.sin(az), np.cos(az)])  # horizontal direction from the object toward the sun
    ty = min(max(h * 0.5, 0.2), 4.0)
    cy = min(1.6, max(h * 0.8, 0.5)) if big < 6 else 1.6
    views = []
    for name, sgn in (("sun", 1.0), ("shade", -1.0)):
        views.append({"name": name, "kind": "3d", "position": [float(sgn * src[0] * d), float(cy), float(sgn * src[1] * d)], "look_at": [0.0, float(ty), 0.0], "fov": 50})
    return views


def render_check(project, style, scene, data, out, run=gg_godot.run):
    """Render the empty stage and the stage with the asset from both views; the asset's pixels are where the two differ."""
    size = (640, 480)
    views = view_set(None, style, data)
    extra_base = {"ctx": {"style": style, "scene": ""}}
    internal = style["render"].get("internal")
    if internal:
        extra_base["internal"] = internal
    results = {}
    for tag, sc in (("empty", ""), ("asset", scene)):
        ex = json.loads(json.dumps(extra_base))
        ex["ctx"]["scene"] = sc
        code, rep = gg_verify.shot(project, builder="res://addons/gg/probe/asset_preview.gd", out=os.path.join(out, tag), views=views, size=size, frames=style["capture_frames"],
                                   renderer=style["renderer"], run=run, extra_args=ex)
        if code not in (0, 1) or len(rep["views"]) != 2:
            return code or 5, {"why": rep["why"]}
        results[tag] = rep
    report = {}
    for i, v in enumerate(views):
        a = gg_metrics.load_rgb(results["empty"]["views"][i]["png"]).astype(np.float64) / 255.0
        b = gg_metrics.load_rgb(results["asset"]["views"][i]["png"]).astype(np.float64) / 255.0
        mask = np.abs(a - b).sum(axis=-1) > 0.06
        cov = float(mask.mean())
        px = b[mask]
        if len(px):
            lum = px @ np.array([0.2126, 0.7152, 0.0722])
            report[v["name"]] = {"coverage": cov, "luma_mean": float(lum.mean()), "black_fraction": float((lum < 0.05).mean()), "white_fraction": float((lum > 0.96).mean()),
                                 "png": results["asset"]["views"][i]["png"]}
        else:
            report[v["name"]] = {"coverage": cov, "luma_mean": 0.0, "black_fraction": 0.0, "white_fraction": 0.0, "png": results["asset"]["views"][i]["png"]}
    return 0, report


def render_flags(report):
    out = []
    if all(r["coverage"] < 0.003 for r in report.values()):
        out.append({"level": "error", "msg": "the asset is not visible in either eye-level view (coverage %s): too small, too far, culled or invisible" % {k: round(r["coverage"], 4) for k, r in report.items()}})
        return out
    for k, r in report.items():
        if r["coverage"] >= 0.003 and r["black_fraction"] > 0.5:
            out.append({"level": "error", "msg": "%.0f%% of the asset's pixels are black in the %s view: a material, normal or lighting problem" % (r["black_fraction"] * 100, k)})
        if r["coverage"] >= 0.003 and r["white_fraction"] > 0.4:
            out.append({"level": "error", "msg": "%.0f%% of the asset's pixels are white in the %s view: glowing or blown-out" % (r["white_fraction"] * 100, k)})
    return out


def _stamp(project, family, verified, sha, deps):
    """Change only this family's stamp in a freshly read catalog (another inspect or an edit may have changed the file while the engine ran)."""
    cat = load_catalog(project)
    if family not in cat["families"]:
        raise gg_godot.Refused("family '%s' vanished from the catalog while it was being inspected" % family)
    f = cat["families"][family]
    f["verified"], f["verified_sha"], f["verified_deps"] = verified, sha, deps
    if verified:
        f["verified_sha"] = fingerprint(project, f)
    save_catalog(project, cat)


def inspect(project, family, out=None, run=gg_godot.run):
    prof = gg_project.load_profile(project)
    style = gg_style.check_applied(project, prof)
    cat = load_catalog(project)
    errs = validate(cat)
    if errs:
        raise gg_godot.Refused("catalog is invalid, run gg_catalog.py validate: " + errs[0])
    if family not in cat["families"]:
        raise gg_godot.Refused("family '%s' is not in the catalog (have: %s)" % (family, ", ".join(sorted(cat["families"]))))
    f = cat["families"][family]
    root = os.path.realpath(os.path.join(project, "gg_data"))
    out = os.path.realpath(out) if out else os.path.join(root, "catalog", family)
    if not (out + os.sep).startswith(root + os.sep):
        raise gg_godot.Refused("--out must be inside %s (the renders in it are replaced)" % root)
    r = run(project, "inspect_asset", {"scene": f["scene"]}, render=False, renderer=style["renderer"], timeout=180)
    if r.code:
        return r.code, {"why": r.why}
    data = r.result["data"]
    flags = asset_flags(data, f["category"], family)
    report = {"family": family, "scene": f["scene"], "inspect": data, "flags": flags}
    if not any(x["level"] == "error" for x in flags):
        code, rr = render_check(project, style, f["scene"], data, out, run)
        if code:
            return code, {**report, "why": rr["why"]}
        report["render"] = rr
        flags += render_flags(rr)
    errors = [x for x in flags if x["level"] == "error"]
    os.makedirs(out, exist_ok=True)
    json.dump(report, open(os.path.join(out, "inspect.json"), "w"), indent=1)
    if errors:
        _stamp(project, family, None, None, None)
        return 1, {**report, "why": "; ".join(x["msg"] for x in errors)}
    _stamp(project, family, datetime.date.today().isoformat(), "x", [d for d in data.get("dependencies", []) if d.startswith("res://") and d != f["scene"]])
    return 0, report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("init", "list", "validate", "add", "inspect"):
        p = sub.add_parser(n); p.add_argument("--project", required=True)
        if n == "init":
            p.add_argument("--dry-run", action="store_true")
        if n == "add":
            p.add_argument("--family", required=True); p.add_argument("--scene", required=True); p.add_argument("--category", required=True)
            p.add_argument("--above-sea", nargs=2, type=float, metavar=("LO", "HI")); p.add_argument("--near-water", nargs=2, type=float, metavar=("LO", "HI"))
            p.add_argument("--max-slope", type=float, default=0.5); p.add_argument("--min-spacing", type=float, default=1.0)
            p.add_argument("--scale-range", nargs=2, type=float, default=[0.8, 1.25]); p.add_argument("--wind", type=float, default=0.0); p.add_argument("--note", default="")
        if n == "inspect":
            p.add_argument("--family", required=True); p.add_argument("--out")
    a = ap.parse_args(argv)
    try:
        project = os.path.abspath(a.project)
        if a.cmd == "init":
            code, rep = init(project, a.dry_run)
            if code:
                print("FAILED (exit %d): %s" % (code, rep.get("why")))
            elif rep:
                print("catalog: %s -> %s (run gg_catalog.py inspect for each family before scattering it)" % (", ".join(rep["families"]), catalog_path(project)))
            return code
        if a.cmd == "list":
            cat = load_catalog(project)
            for n, f in cat["families"].items():
                print("%-16s %-14s above_sea %-14s near_water %-12s slope %-4s %s" % (n, f["category"], f["above_sea_m"], f["near_water_m"], f["max_slope"], "verified " + f["verified"] if f.get("verified") else "UNVERIFIED"))
            return 0
        if a.cmd == "validate":
            errs = validate(load_catalog(project))
            for e in errs:
                print("ERROR " + e)
            print("catalog valid" if not errs else "%d problem(s)" % len(errs))
            return 1 if errs else 0
        if a.cmd == "add":
            cat = load_catalog(project) if os.path.exists(catalog_path(project)) else {"schema": 1, "categories": CATEGORIES, "families": {}}
            if a.family in cat["families"]:
                raise gg_godot.Refused("family '%s' is already in the catalog" % a.family)
            if a.above_sea is None or a.near_water is None:
                raise gg_godot.Refused("give --above-sea LO HI and --near-water LO HI (use a large HI such as 9999 for no limit; the catalog JSON can hold null)")
            f = {"category": a.category, "scene": a.scene, "above_sea_m": [a.above_sea[0], None if a.above_sea[1] >= 9999 else a.above_sea[1]],
                 "near_water_m": [a.near_water[0], None if a.near_water[1] >= 9999 else a.near_water[1]], "max_slope": a.max_slope, "min_spacing_m": a.min_spacing,
                 "scale_range": a.scale_range, "wind": a.wind, "notes": a.note, "verified": None, "verified_sha": None, "verified_deps": None}
            errs = family_errors(a.family, f)
            if errs:
                raise gg_godot.Refused("; ".join(errs))
            cat["families"][a.family] = f
            save_catalog(project, cat)
            print("added %s (UNVERIFIED): now run gg_catalog.py inspect --family %s" % (a.family, a.family))
            return 0
        code, rep = inspect(project, a.family, a.out)
        for x in rep.get("flags", []):
            print("%-5s %s" % (x["level"].upper(), x["msg"]))
        for k, r in (rep.get("render") or {}).items():
            print("view %-5s coverage %.3f luma %.2f black %.2f white %.2f -> %s" % (k, r["coverage"], r["luma_mean"], r["black_fraction"], r["white_fraction"], r["png"]))
        print("%s %s" % ("VERIFIED" if code == 0 else "NOT VERIFIED (exit %d):" % code, a.family if code == 0 else rep.get("why")))
        return code
    except (gg_godot.Refused, gg_metrics.Refused, ValueError, OSError, KeyError, json.JSONDecodeError) as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
