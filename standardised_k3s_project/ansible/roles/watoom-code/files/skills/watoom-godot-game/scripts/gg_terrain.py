#!/usr/bin/env python3
"""Terrain: heights, weight masks that sum to exactly 255, and a layered material in the level. Reuses layer_masks.py by reference.

  gg_terrain.py heights --project P --shape island|hills|plateau|flat|valley --relief-m R [--seed S] | --from FILE   [--dry-run]
  gg_terrain.py layers  --project P [--spec layers.json]     weights via watoom-texture-layering/scripts/layer_masks.py
  gg_terrain.py build   --project P [--dry-run]              res://levels/<level>/terrain.tscn + collider, then a top-view check

World facts (measured, see references/gg-terrain.md): +Y up, image column -> +X, image row -> +Z, vertex (i, j) at
(i*cell_m, height, j*cell_m), splat uv = (world.xz - origin) / size. heights.png is 16-bit, 0..65535 = height_range_m lo..hi.
Exit codes: 0 pass | 1 check failed | 2 refused | 3 engine log fatal | 4 no verdict | 5 runner failure.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "watoom-texture-layering", "scripts"))
import gg_godot  # noqa: E402
import gg_project  # noqa: E402
import gg_style  # noqa: E402
import gg_verify  # noqa: E402

SHAPES = ["island", "hills", "plateau", "flat", "valley", "ramp"]
MAX_LAYERS = 8


def _lm():
    try:
        import layer_masks
        return layer_masks
    except ImportError:
        raise gg_godot.Refused("watoom-texture-layering/scripts/layer_masks.py not found next to this skill (expected %s)" %
                               os.path.join(os.path.dirname(os.path.dirname(HERE)), "watoom-texture-layering", "scripts"))


def world_dir(project):
    return os.path.join(project, "gg_data", "world")


def sha_file(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


DERIVED_WATER = ("creeks.json", "water.json", "water_mask.png", "water_dist.f32")


def save_heights(project, h, info, drop=()):
    """Write heights.png (16-bit), heights.f32 and world.json (with the new hash); delete everything derived from the old heights."""
    from PIL import Image
    d = world_dir(project)
    os.makedirs(d, exist_ok=True)
    lo, hi = info["height_range_m"]
    Image.fromarray(np.round((h - lo) / (hi - lo) * 65535).astype(np.uint16)).save(os.path.join(d, "heights.png"))
    forget(project, what=("build_ok.json", "water_ok.json", "player_ok.json", "smoke_ok.json") + tuple(drop), layers=True)
    h.astype("<f4").tofile(os.path.join(d, "heights.f32"))
    info["heights_sha"] = sha_file(os.path.join(d, "heights.f32"))
    info["min_m"], info["max_m"] = float(h.min()), float(h.max())
    json.dump(info, open(os.path.join(d, "world.json"), "w"), indent=1)


def forget(project, what=("build_ok.json", "water_ok.json", "player_ok.json", "smoke_ok.json"), layers=False):
    """Delete derived results that a newer step makes stale (only inside gg_data/world)."""
    d = world_dir(project)
    for n in what:
        if os.path.exists(os.path.join(d, n)):
            os.remove(os.path.join(d, n))
    if layers and os.path.isdir(os.path.join(d, "layers")):
        shutil.rmtree(os.path.join(d, "layers"))


def grid(profile):
    w = profile["world"]
    cell = float(w["cell_m"])
    for axis, size in zip("xz", w["size_m"]):
        if abs(size / cell - round(size / cell)) > 1e-6:
            raise gg_godot.Refused("world.size_m %s is not a multiple of world.cell_m %s on %s (the mesh and the shader would disagree on the extent): change one of them in gg_project.json" % (w["size_m"], cell, axis))
    nx = int(round(w["size_m"][0] / cell)) + 1
    nz = int(round(w["size_m"][1] / cell)) + 1
    return nx, nz, cell


def make_heights(shape, nx, nz, cell, seed, relief_m):
    """Metres relative to sea level 0 (sea_level_m is applied by the caller). Deterministic for a seed."""
    if shape not in SHAPES:
        raise gg_godot.Refused("unknown shape '%s' (have %s)" % (shape, ", ".join(SHAPES)))
    lm = _lm()
    n1 = lm.fbm((nz, nx), cell, max(nx, nz) * cell / 3.0, seed)
    n2 = lm.fbm((nz, nx), cell, max(nx, nz) * cell / 9.0, seed + 1)
    n = 0.7 * n1 + 0.3 * n2
    n = (n - n.min()) / max(float(np.ptp(n)), 1e-9)
    u = np.linspace(0, 1, nx)[None, :]
    v = np.linspace(0, 1, nz)[:, None]
    r = np.hypot((u - 0.5) * 2, (v - 0.5) * 2)  # 0 centre .. ~1.41 corner
    if shape == "island":
        land = np.clip(1.0 - (r / 0.85) ** 2.4, 0.0, 1.0)
        h = -0.25 * relief_m + land * relief_m * 1.25 * (0.35 + 0.65 * n)
    elif shape == "hills":
        h = relief_m * (0.15 + 0.85 * n)
    elif shape == "plateau":
        t = np.clip(1.0 - (r / 0.9) ** 3, 0.0, 1.0)
        h = relief_m * (t * (0.85 + 0.15 * n)) + 0.02 * relief_m * n
    elif shape == "ramp":  # deliberately asymmetric: rises along +X and +Z (unequally), a bump in the low-X/low-Z corner. The orientation probe.
        bump = np.exp(-(((u - 0.25) / 0.12) ** 2 + ((v - 0.2) / 0.12) ** 2))
        h = relief_m * (0.1 + 0.7 * u + 0.25 * v + 0.3 * bump)
    elif shape == "valley":
        h = relief_m * (np.abs(u - 0.5) * 2) ** 1.4 * (0.6 + 0.4 * n) - 0.05 * relief_m
    else:
        h = 0.5 * n
    return np.asarray(h, dtype=np.float64)


def heights(project, shape=None, relief_m=None, seed=None, from_file=None, dry_run=False):
    prof = gg_project.load_profile(project)
    nx, nz, cell = grid(prof)
    lo, hi = prof["world"]["height_range_m"]
    sea = prof["world"]["sea_level_m"]
    seed = prof["world"]["seed"] if seed is None else seed
    if from_file:
        lm = _lm()
        arr = np.load(from_file).astype(np.float64) if from_file.endswith(".npy") else lm.load_height(from_file) * (hi - lo) + lo
        if arr.shape != (nz, nx):
            raise gg_godot.Refused("heights file is %dx%d but the project needs %dx%d (size_m %s / cell_m %s + 1)" %
                                   (arr.shape[1], arr.shape[0], nx, nz, prof["world"]["size_m"], cell))
        if not np.isfinite(arr).all():
            raise gg_godot.Refused("heights file contains NaN or infinite values")
        h = arr
        shape = "from_file"
    else:
        if not shape or relief_m is None:
            raise gg_godot.Refused("give --shape and --relief-m (or --from FILE)")
        if not (0 < relief_m <= hi - lo):
            raise gg_godot.Refused("relief %s m does not fit height_range_m [%s, %s] (span %s)" % (relief_m, lo, hi, hi - lo))
        h = make_heights(shape, nx, nz, cell, seed, relief_m) + sea
    clipped = float(np.mean((h < lo) | (h > hi)))
    h = np.clip(h, lo, hi)
    land = float(np.mean(h > sea))
    info = {"schema": 1, "shape": shape, "seed": seed, "relief_m": relief_m, "size_px": [nx, nz], "size_m": prof["world"]["size_m"], "cell_m": cell,
            "height_range_m": [lo, hi], "sea_level_m": sea, "min_m": float(h.min()), "max_m": float(h.max()), "land_fraction": round(land, 4),
            "clipped_fraction": round(clipped, 4)}
    warnings = []
    if land < 0.02 or land > 0.98:
        warnings.append("land_fraction %.3f: the sea level %s m is outside the terrain (min %.1f, max %.1f); adjust relief or world.sea_level_m" % (land, sea, h.min(), h.max()))
    if clipped > 0:
        warnings.append("%.1f%% of heights were clipped to height_range_m; raise the range or lower relief" % (clipped * 100))
    if dry_run:
        print("would write %s/heights.png (16-bit %dx%d), heights.f32, world.json" % (world_dir(project), nx, nz))
        print(json.dumps(info))
        return 0, info, warnings
    save_heights(project, h, info, drop=DERIVED_WATER)
    return 0, info, warnings


def load_world(project):
    p = os.path.join(world_dir(project), "world.json")
    if not os.path.isfile(p):
        raise gg_godot.Refused("no %s: run gg_terrain.py heights first" % p)
    return json.load(open(p))


def layers(project, spec=None, dry_run=False):
    prof = gg_project.load_profile(project)
    wd = load_world(project)
    spec_path = spec or os.path.join(os.path.dirname(HERE), "templates", "layers.%s.json" % prof["style"]["preset"])
    if not os.path.isfile(spec_path):
        raise gg_godot.Refused("layer spec %s not found" % spec_path)
    sp = json.load(open(spec_path))
    n = len(sp.get("layers", []))
    if not 2 <= n <= MAX_LAYERS:
        raise gg_godot.Refused("layer spec has %d layers; allowed 2..%d (one layer cannot be checked against a render)" % (n, MAX_LAYERS))
    if sum(1 for l in sp["layers"] if l.get("fallback")) != 1:
        raise gg_godot.Refused("layer spec needs exactly one layer with \"fallback\": true")
    for l in sp["layers"]:
        if "color" not in l:
            raise gg_godot.Refused("layer '%s' has no color (flat-colour layers are what the level material uses)" % l.get("name"))
    out = os.path.join(world_dir(project), "layers")
    if dry_run:
        print("would run layer_masks on heights.png (%dx%d) with %s -> %s" % (wd["size_px"][0], wd["size_px"][1], spec_path, out))
        return 0, None, []
    lm = _lm()
    forget(project)
    try:
        code = lm.main(["--heightmap", os.path.join(world_dir(project), "heights.png"), "--cell-size", str(wd["cell_m"]),
                    "--height-range", str(wd["height_range_m"][0]), str(wd["height_range_m"][1]), "--spec", spec_path, "--out", out])
    except SystemExit as e:
        raise gg_godot.Refused("layer_masks.py refused: %s" % e)
    if code:
        raise gg_godot.Refused("layer_masks.py exited %s" % code)
    json.dump({"heights_sha": wd["heights_sha"]}, open(os.path.join(out, "gg_source.json"), "w"))
    rep = json.load(open(os.path.join(out, "layer_report.json")))
    warnings = []
    if rep["input"]["size_px"] != [wd["size_px"][1], wd["size_px"][0]]:
        raise gg_godot.Refused("weight maps are %s (rows x cols) but heights are %dx%d" % (rep["input"]["size_px"], wd["size_px"][1], wd["size_px"][0]))
    for l in rep["layers"]:
        if l["coverage_pct"] < 0.5 or l["coverage_pct"] > 90:
            warnings.append("layer '%s' covers %.2f%% of the map: %s" % (l["name"], l["coverage_pct"],
                            "it never appears: widen its rule" if l["coverage_pct"] < 0.5 else "it covers almost everything: tighten its rule"))
    if not rep["sum_to_255_everywhere"]:
        return 1, rep, warnings + ["weights do not sum to 255 everywhere"]
    return 0, rep, warnings


def check_weights_match_heights(project, wd, rep, splats):
    """Recompute the weights from heights.png with the recorded spec and refuse if the splat files on disk differ
    (flipped, edited or from other heights). The top-view render only proves the shader reads these files correctly."""
    import contextlib
    import io
    import tempfile
    from PIL import Image
    lm = _lm()
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
        sp = os.path.join(tmp, "spec.json")
        json.dump(rep["spec"], open(sp, "w"))
        try:
            lm.main(["--heightmap", os.path.join(world_dir(project), "heights.png"), "--cell-size", str(wd["cell_m"]),
                     "--height-range", str(wd["height_range_m"][0]), str(wd["height_range_m"][1]), "--spec", sp, "--out", os.path.join(tmp, "o")])
        except SystemExit as e:
            raise gg_godot.Refused("layer_masks.py refused while re-deriving the weights: %s" % e)
        for i, path in enumerate(splats):
            fresh = np.asarray(Image.open(os.path.join(tmp, "o", "splat_%d.png" % i)).convert("RGBA"), dtype=np.int32)
            have = np.asarray(Image.open(path).convert("RGBA"), dtype=np.int32)
            if fresh.shape != have.shape or int(np.abs(fresh - have).max()) > 1:
                bad = float(np.mean(np.abs(fresh - have).max(axis=-1) > 1)) if fresh.shape == have.shape else 1.0
                raise gg_godot.Refused("%s does not match the weights derived from heights.png (%.0f%% of cells differ: flipped, edited or made from other heights): run gg_terrain.py layers again" % (path, bad * 100))


def build_args(project, prof, style):
    wd = load_world(project)
    ld = os.path.join(world_dir(project), "layers")
    rp = os.path.join(ld, "layer_report.json")
    if not os.path.isfile(rp):
        raise gg_godot.Refused("no %s: run gg_terrain.py layers first" % rp)
    rep = json.load(open(rp))
    src = os.path.join(ld, "gg_source.json")
    if not os.path.isfile(src) or json.load(open(src)).get("heights_sha") != wd.get("heights_sha"):
        raise gg_godot.Refused("the layer weights were not made from the current heights (heights were rewritten): re-run gg_terrain.py layers")
    if rep["input"]["size_px"] != [wd["size_px"][1], wd["size_px"][0]]:
        raise gg_godot.Refused("weight maps are %s (rows x cols) but heights are %dx%d: re-run layers" % (rep["input"]["size_px"], wd["size_px"][1], wd["size_px"][0]))
    if not rep["sum_to_255_everywhere"]:
        raise gg_godot.Refused("layer weights do not sum to 255 everywhere; fix the spec and re-run layers")
    splats = [os.path.join(ld, "splat_%d.png" % i) for i in range((len(rep["layers"]) + 3) // 4)]
    check_weights_match_heights(project, wd, rep, splats)
    colors = [l["color"] for l in rep["spec"]["layers"]]
    return {"level": prof["level"], "style": style, "dimension": prof["dimension"], "chunk": 64,
            "world": {"size_m": wd["size_m"], "cell_m": wd["cell_m"], "size_px": wd["size_px"]},
            "heights_f32": os.path.join(world_dir(project), "heights.f32"), "splats": splats, "colors": colors}, rep


def _expected_classes(project, n_layers, size=64, dominant=0.7):
    """Per 64x64 block: the layer with the largest AREA-AVERAGED weight, and whether it is dominant (>= `dominant` of the block).
    Row 0 = lowest Z, column 0 = lowest X. Mixed blocks are not judged: a blurred render cannot tell them apart."""
    from PIL import Image
    ld = os.path.join(world_dir(project), "layers")
    chans = []
    for m in range((n_layers + 3) // 4):
        a = np.asarray(Image.open(os.path.join(ld, "splat_%d.png" % m)).convert("RGBA"), dtype=np.float32) / 255.0
        for c in range(4):
            if m * 4 + c < n_layers:
                chans.append(np.asarray(Image.fromarray(a[..., c], mode="F").resize((size, size), Image.BOX)))
    w = np.stack(chans)
    return w.argmax(axis=0), w.max(axis=0) >= dominant


def measured_refs(img, exp, min_cells=8, mask=None):
    """Mean chroma of the rendered cells where each layer is expected (tone mapping and lighting move hues, so nominal colours are not used).
    Returns (refs dict layer->chroma, min pairwise distance between them)."""
    def chroma(x):
        s = x.sum(axis=-1, keepdims=True)
        return x / np.maximum(s, 1e-6)
    c = chroma(img)
    m = np.ones(exp.shape, bool) if mask is None else mask
    refs = {int(k): c[(exp == k) & m].mean(axis=0) for k in np.unique(exp[m]) if ((exp == k) & m).sum() >= min_cells}
    ks = list(refs)
    sep = min((float(np.linalg.norm(refs[a] - refs[b])) for i, a in enumerate(ks) for b in ks[i + 1:]), default=1.0)
    return refs, sep


def classify_by_chroma(img, refs):
    """Nearest measured reference by brightness-normalised colour. img float (h,w,3) -> int class map (layer indices)."""
    def chroma(x):
        s = x.sum(axis=-1, keepdims=True)
        return x / np.maximum(s, 1e-6)
    ks = sorted(refs)
    ref = np.array([refs[k] for k in ks])
    d = ((chroma(img)[..., None, :] - ref[None, None]) ** 2).sum(axis=-1)
    return np.array(ks)[d.argmin(axis=-1)]


def agreement(obs, exp, coverage_min=0.05, mask=None):
    """overall agreement and the per-layer recall among layers covering >= coverage_min of the judged blocks (all blocks, or those in `mask`)."""
    mk = np.ones(exp.shape, bool) if mask is None else mask
    if not mk.any():
        return 0.0, {}
    overall = float((obs[mk] == exp[mk]).mean())
    recalls = {}
    for k in np.unique(exp[mk]):
        m = (exp == k) & mk
        if m.sum() / mk.sum() >= coverage_min:
            recalls[int(k)] = float((obs[m] == k).mean())
    return overall, recalls


def top_check(project, prof, style, out, run=gg_godot.run):
    """Render the level from straight above (fog off) and compare per-cell layer classes with the weight maps.
    A uniform, black, mirrored or transposed render all fail: this is what proves the orientation and the splat mapping."""
    from PIL import Image
    sx, sz = prof["world"]["size_m"]
    st = json.loads(json.dumps(style))
    st["post"]["fog"]["on"] = False
    rep0 = json.load(open(os.path.join(world_dir(project), "layers", "layer_report.json")))
    colors = [l["color"] for l in rep0["spec"]["layers"]]
    size = tuple(st["render"]["window"])
    ortho = max(sz, sx * size[1] / size[0])  # vertical extent in metres: the whole terrain fits whatever the window aspect
    view = {"name": "top", "kind": "3d", "position": [sx / 2, max(sx, sz), sz / 2], "look_at": [sx / 2, 0, sz / 2], "fov": 50, "ortho_size": ortho}
    extra = {"ctx": {"style": st, "scenes": ["res://levels/%s/terrain.tscn" % prof["level"]]}}
    if st["render"].get("internal"):
        extra["internal"] = st["render"]["internal"]
    code, rep = gg_verify.shot(project, builder="res://addons/gg/probe/level_preview.gd", out=out, views=[view], size=size, frames=st["capture_frames"],
                               renderer=st["renderer"], run=run, extra_args=extra)
    if code not in (0, 1) or not rep["views"]:
        return code or 5, {"why": rep["why"]}
    img = np.asarray(Image.open(rep["views"][0]["png"]).convert("RGB"), dtype=np.float64)
    h, w, _ = img.shape
    ppm = h / ortho
    wpx, hpx = int(round(sx * ppm)), int(round(sz * ppm))
    x0, y0 = (w - wpx) // 2, (h - hpx) // 2
    crop = np.asarray(Image.fromarray(img[y0:y0 + hpx, x0:x0 + wpx].astype(np.uint8)).resize((64, 64), Image.BILINEAR), dtype=np.float64)
    exp, conf = _expected_classes(project, len(colors))
    if int(conf.sum()) < 40:
        return 0, {"agreement": 1.0, "recall": {}, "variants": {"flip_x": 0.0, "flip_z": 0.0, "transpose": 0.0}, "distinct_classes": 2, "min_separation": 1.0,
                   "luma_std": float(crop.mean(axis=-1).std()), "png": rep["views"][0]["png"], "confident_blocks": int(conf.sum()),
                   "too_mixed": True}
    refs, sep = measured_refs(crop, exp, mask=conf)
    obs = classify_by_chroma(crop, refs)
    overall, recalls = agreement(obs, exp, mask=conf)
    variants = {"flip_x": agreement(obs[:, ::-1], exp, mask=conf)[0], "flip_z": agreement(obs[::-1, :], exp, mask=conf)[0], "transpose": agreement(obs.T, exp, mask=conf)[0]}
    distinct = int(len(np.unique(obs[conf])))
    return 0, {"agreement": overall, "recall": {rep0["layers"][k]["name"]: v for k, v in recalls.items()}, "variants": variants, "distinct_classes": distinct, "min_separation": sep,
               "luma_std": float(crop.mean(axis=-1).std()), "png": rep["views"][0]["png"], "confident_blocks": int(conf.sum()), "too_mixed": False}


def build(project, dry_run=False, run=gg_godot.run, check_view=True):
    prof = gg_project.load_profile(project)
    style = gg_style.check_applied(project, prof)
    args, rep = build_args(project, prof, style)
    if not dry_run:
        forget(project)
    if dry_run:
        print("would build res://levels/%s/terrain.tscn: %dx%d vertices, cell %s m, chunk 64, %d layers, shader terrain_%s" %
              (prof["level"], args["world"]["size_px"][0], args["world"]["size_px"][1], args["world"]["cell_m"], len(args["colors"]), {"pbr": "pbr", "flat": "flat", "toon": "toon", "unshaded": "unshaded"}[style["material"]["shading"]]))
        return 0, {}
    r = run(project, "build_terrain", args, render=False, renderer=style["renderer"], timeout=300)
    if r.code:
        return r.code, {"why": r.why}
    data = r.result["data"]
    out = {"build": data, "checked_view": check_view}
    if data["raycast_misses"] or data["collider_max_err"] > 0.05:
        return 1, {**out, "why": "collider disagrees with the height data: max error %.3f m, %d raycast misses (limit 0.05 m / 0)" % (data["collider_max_err"], data["raycast_misses"])}
    if abs(data["mesh_y"][0] - data["data_y"][0]) > 0.01 or abs(data["mesh_y"][1] - data["data_y"][1]) > 0.01:
        return 1, {**out, "why": "mesh y range %s differs from height data %s" % (data["mesh_y"], data["data_y"])}
    if check_view:
        code, chk = top_check(project, prof, style, os.path.join(project, "gg_data", "terrain_check"), run=run)
        out["top_check"] = chk
        if code:
            return code, {**out, "why": chk.get("why", "top view failed")}
        worst = min(chk["recall"].values()) if chk["recall"] else 1.0
        if chk.get("too_mixed"):
            out["note"] = "layers are too mixed to judge by render (%d confident 64x64 blocks, need 40): only the exact re-derivation of the weights from the heights was checked" % chk["confident_blocks"]
        best = max(chk["variants"].items(), key=lambda kv: kv[1])
        mirrored = best[1] > chk["agreement"] + 0.02  # a flipped variant explains the render better than the real one
        if chk["agreement"] < 0.75 or worst < 0.4 or chk["distinct_classes"] < 2 or chk["min_separation"] < 0.02 or chk["luma_std"] < 3 or mirrored:
            why = "top view agrees %.2f with the weight maps (need >= 0.75; worst layer recall %.2f, need >= 0.4; %d distinct layers seen)" % (chk["agreement"], worst, chk["distinct_classes"])
            if chk["min_separation"] < 0.02:
                why += "; two layers render with the same colour (separation %.3f): the layer colours are too close or the material ignores the weights" % chk["min_separation"]
            elif mirrored:
                why += "; the %s variant agrees %.2f, better than the real %.2f: the axes are swapped or mirrored (check with --shape ramp and templates/layers.orientation_probe.json)" % (best[0], best[1], chk["agreement"])
            elif chk["luma_std"] < 3:
                why += "; the image is almost uniform: the material shows no layer colours (check the engine log and the shader)"
            return 1, {**out, "why": why}
        if best[1] > chk["agreement"] - 0.08:
            out["note"] = "this terrain is too symmetric for the render to prove orientation (a mirrored variant agrees %.2f vs %.2f); the weights were re-derived exactly from the heights, and orientation is proven by the ramp probe" % (best[1], chk["agreement"])
        stamp = {"heights_sha": load_world(project)["heights_sha"], "level": prof["level"], "agreement": chk["agreement"]}
        json.dump(stamp, open(os.path.join(world_dir(project), "build_ok.json"), "w"))
    return 0, out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("heights"); h.add_argument("--project", required=True); h.add_argument("--shape", choices=SHAPES); h.add_argument("--relief-m", type=float)
    h.add_argument("--seed", type=int); h.add_argument("--from", dest="from_file"); h.add_argument("--dry-run", action="store_true")
    l = sub.add_parser("layers"); l.add_argument("--project", required=True); l.add_argument("--spec"); l.add_argument("--dry-run", action="store_true")
    b = sub.add_parser("build"); b.add_argument("--project", required=True); b.add_argument("--dry-run", action="store_true"); b.add_argument("--no-check-view", action="store_true")
    a = ap.parse_args(argv)
    try:
        project = os.path.abspath(a.project)
        if a.cmd == "heights":
            code, info, warns = heights(project, a.shape, a.relief_m, a.seed, a.from_file, a.dry_run)
            for w in warns:
                print("WARNING " + w)
            if not a.dry_run:
                print("heights: %s %dx%d, %.1f..%.1f m, land %.1f%%" % (info["shape"], info["size_px"][0], info["size_px"][1], info["min_m"], info["max_m"], info["land_fraction"] * 100))
            return code
        if a.cmd == "layers":
            code, rep, warns = layers(project, a.spec, a.dry_run)
            for w in warns:
                print("WARNING " + w)
            if rep:
                print("layers: %s; sum_to_255_everywhere=%s" % (", ".join("%s %.1f%%" % (x["name"], x["coverage_pct"]) for x in rep["layers"]), rep["sum_to_255_everywhere"]))
            return code
        if a.cmd == "build":
            code, out = build(project, a.dry_run, check_view=not a.no_check_view)
            if "build" in out:
                b_ = out["build"]
                print("built %s: %d chunks, %d nodes, collider max error %.4f m, mesh y %s" % (b_["scene"], b_["chunks"], b_["nodes"], b_["collider_max_err"], [round(v, 2) for v in b_["mesh_y"]]))
            if "top_check" in out and "agreement" in out["top_check"]:
                t = out["top_check"]
                print("top view agrees %.2f with the weight maps; recall %s; mirrored variants %s (%s)" % (t["agreement"], {k: round(v, 2) for k, v in t["recall"].items()}, {k: round(v, 2) for k, v in t["variants"].items()}, t["png"]))
            if code:
                print("FAILED (exit %d): %s" % (code, out.get("why")))
            elif out.get("note"):
                print("NOTE " + out["note"])
            elif not a.dry_run and not out.get("checked_view"):
                print("WARNING top view NOT checked (--no-check-view): the level is built but not marked verified, gg_light.py will refuse it")
            return code
    except (gg_godot.Refused, ValueError, OSError, KeyError, json.JSONDecodeError) as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
