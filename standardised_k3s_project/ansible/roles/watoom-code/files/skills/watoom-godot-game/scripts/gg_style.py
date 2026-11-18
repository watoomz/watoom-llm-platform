#!/usr/bin/env python3
"""Style is data: a preset JSON (presets/NAME.json) plus per-project overrides decide how everything looks.

  gg_style.py list | show NAME | validate FILE
  gg_style.py resolve --project P                 preset + style.overrides -> P/gg_data/style.resolved.json
  gg_style.py apply   --project P [--dry-run]     typed project settings + res://levels/_boot/boot.tscn from the resolved style
  gg_style.py probe   --project P --out DIR [--against PRESET]   render the style probe scene and check the preset's probe_targets
  gg_style.py calibrate --work DIR --out DIR [--write]   derive each preset's probe_targets from its own measured probe image
  gg_style.py matrix  --work DIR --out DIR        every preset x the probe: each passes its own targets and fails the others'

Exit codes as everywhere: 0 pass | 1 check failed | 2 refused | 3 engine log fatal | 4 no verdict | 5 runner failure.
"""
import argparse
import copy
import json
import os
import sys

import gg_godot
import gg_schema as S
import gg_verify

HERE = os.path.dirname(os.path.abspath(__file__))
PRESETS = os.path.join(os.path.dirname(HERE), "presets")
OBJ, F, I, B, STR, RGB = "obj", "float", "int", "bool", "str", "rgb"


def _o(**fields):
    return {"t": "obj", "fields": fields}


def _rng(lo, hi):
    return {"t": "list", "n": 2, "items": {"t": "float", "nullable": True}}


METRICS = ["luma_p1", "luma_p5", "luma_p50", "luma_p95", "luma_p99", "luma_mean", "luma_std", "sat_mean", "sat_p95", "clip_black", "clip_white",
           "unique_colors", "flat_fraction", "local_contrast", "grid_integrity"]
SKY = _o(kind={"t": "str", "enum": ["procedural", "color"]}, color={"t": "rgb"}, top={"t": "rgb"}, horizon={"t": "rgb"})
COLOR_OR_HEX = {"t": "any"}
PRESET_SCHEMA = _o(
    schema={"t": "int", "min": 1, "max": 1}, name={"t": "str", "pattern": r"[a-z][a-z0-9-]{0,31}"}, description={"t": "str"},
    dimensions={"t": "list", "min_len": 1, "items": {"t": "str", "enum": ["2d", "3d"]}},
    renderer={"t": "str", "enum": ["forward_plus", "mobile", "gl_compatibility"]}, capture_frames={"t": "int", "min": 3, "max": 120},
    render=_o(window={"t": "list", "n": 2, "items": {"t": "int", "min": 64, "max": 1920}},
              internal={"t": "list", "n": 2, "nullable": True, "items": {"t": "int", "min": 16, "max": 1920}},
              texture_filter={"t": "str", "enum": ["nearest", "linear", "linear_mipmap", "linear_mipmap_aniso"]},
              msaa={"t": "int", "enum": [0, 2, 4]}, fxaa={"t": "bool"}, taa={"t": "bool"}, snap_2d={"t": "bool"}),
    lighting=_o(sun_energy={"t": "float", "min": 0, "max": 8}, sun_color={"t": "rgb"}, sun_elevation_deg={"t": "float", "min": 0, "max": 90},
                sun_azimuth_deg={"t": "float", "min": 0, "max": 360}, shadows={"t": "bool"}, shadow_blur={"t": "float", "min": 0, "max": 4},
                ambient_source={"t": "str", "enum": ["sky", "color"]}, ambient_color={"t": "rgb"}, ambient_energy={"t": "float", "min": 0, "max": 4}, sky=SKY),
    post=_o(tonemap={"t": "str", "enum": ["linear", "reinhard", "filmic", "aces", "agx"]}, exposure={"t": "float", "min": 0.1, "max": 4},
            white={"t": "float", "min": 1, "max": 16},
            glow=_o(on={"t": "bool"}, intensity={"t": "float", "min": 0, "max": 2}, threshold={"t": "float", "min": 0, "max": 4}),
            ssao={"t": "bool"}, ssil={"t": "bool"}, sdfgi={"t": "bool"},
            fog=_o(on={"t": "bool"}, density={"t": "float", "min": 0, "max": 0.1}, aerial={"t": "float", "min": 0, "max": 1}),
            adjust=_o(brightness={"t": "float", "min": 0.5, "max": 2}, contrast={"t": "float", "min": 0.5, "max": 2}, saturation={"t": "float", "min": 0, "max": 3})),
    material=_o(shading={"t": "str", "enum": ["pbr", "toon", "flat", "unshaded"]}, normal_maps={"t": "bool"}, normal_strength={"t": "float", "min": 0, "max": 1},
                roughness={"t": "float", "min": 0, "max": 1}, specular={"t": "float", "min": 0, "max": 1},
                palette={"t": "list", "nullable": True, "min_len": 2, "items": {"t": "hex"}}, palette_quantize={"t": "bool"},
                outline=_o(on={"t": "bool"}, px={"t": "float", "min": 0, "max": 8}, color={"t": "hex"}),
                toon_softness={"t": "float", "min": 0, "max": 1},
                terrain_shader={"t": "str", "enum": ["layered_pbr", "layered_toon", "layered_flat", "tile2d"]}),
    geometry=_o(terrain_cell_m={"t": "float", "min": 0.25, "max": 16}, flat_normals={"t": "bool"}, scatter_density={"t": "float", "min": 0, "max": 2},
                mesh_segments={"t": "int", "min": 4, "max": 96}),
    water=_o(style={"t": "str", "enum": ["pbr_reflective", "toon_bands", "flat_color", "tile_animated"]}, shallow={"t": "any"}, deep={"t": "any"}),
    targets={"t": "obj", "open": True}, probe_targets={"t": "obj", "open": True}, probe_targets_2d={"t": "obj", "open": True, "opt": True}, fix_hints={"t": "obj", "open": True},
    calibration={"t": "obj", "open": True}, calibration_level={"t": "obj", "open": True})


def preset_errors(p):
    errs = S.check(p, PRESET_SCHEMA)
    for key in ("targets", "probe_targets", "probe_targets_2d"):
        for m, rng in (p.get(key) or {}).items():
            if m not in METRICS:
                errs.append("$.%s.%s: unknown metric (known: %s)" % (key, m, ", ".join(METRICS)))
            elif not (isinstance(rng, list) and len(rng) == 2 and all(x is None or isinstance(x, (int, float)) for x in rng)):
                errs.append("$.%s.%s: expected [lo, hi] with null for an open end, got %r" % (key, m, rng))
            elif rng[0] is not None and rng[1] is not None and rng[0] > rng[1]:
                errs.append("$.%s.%s: lo %s > hi %s" % (key, m, rng[0], rng[1]))
    for k in ("shallow", "deep"):
        v = (p.get("water") or {}).get(k)
        if v is not None and not (isinstance(v, str) and len(v) == 6 or isinstance(v, list) and len(v) == 3):
            errs.append("$.water.%s: expected [r,g,b] or 6 hex digits, got %r" % (k, v))
    L = p.get("lighting") or {}
    if L.get("ambient_source") == "sky" and (L.get("sky") or {}).get("kind") == "color":
        errs.append("$.lighting.ambient_source is 'sky' but lighting.sky.kind is 'color' (no sky to light from): use ambient_source 'color'")
    pal = (p.get("material") or {}).get("palette")
    if (p.get("material") or {}).get("palette_quantize") and not pal:
        errs.append("$.material.palette_quantize is true but material.palette is empty")
    if pal and len(pal) > 32:
        errs.append("$.material.palette: at most 32 colours, got %d" % len(pal))
    return errs


def list_presets():
    return sorted(f[:-5] for f in os.listdir(PRESETS) if f.endswith(".json"))


def load_preset(name_or_path):
    path = name_or_path if name_or_path.endswith(".json") or os.sep in name_or_path else os.path.join(PRESETS, name_or_path + ".json")
    if not os.path.isfile(path):
        raise gg_godot.Refused("no preset '%s' (have: %s)" % (name_or_path, ", ".join(list_presets())))
    with open(path) as f:
        p = json.load(f)
    errs = preset_errors(p)
    if errs:
        raise gg_godot.Refused("preset %s invalid:\n  %s" % (path, "\n  ".join(errs)))
    return p


def resolve(profile, preset=None):
    """profile style.preset + style.overrides -> resolved style dict. Unknown override keys are refused naming the path."""
    st = profile["style"]
    p = preset or load_preset(st["preset"])
    try:
        out = S.merge(p, st.get("overrides") or {})
    except KeyError as e:
        raise gg_godot.Refused(str(e.args[0]))
    errs = preset_errors(out)
    if errs:
        raise gg_godot.Refused("style after overrides is invalid:\n  " + "\n  ".join(errs))
    if profile["dimension"] not in out["dimensions"]:
        raise gg_godot.Refused("preset '%s' supports %s but the project is %s" % (out["name"], out["dimensions"], profile["dimension"]))
    return out


FILTER2D = {"nearest": 0, "linear": 1, "linear_mipmap": 2, "linear_mipmap_aniso": 2}
MSAA = {0: 0, 2: 1, 4: 2}
ACTIONS = {"move_forward": ["W"], "move_back": ["S"], "move_left": ["A"], "move_right": ["D"], "jump": ["Space"], "interact": ["E"]}


def settings_for(profile, style):
    """Typed ProjectSettings list for the project_apply op."""
    r = style["render"]
    internal = r.get("internal")
    base = internal or r["window"]
    s = [
        ("application/config/name", "string", profile["title"]),
        ("application/run/main_scene", "string", "res://levels/_boot/boot.tscn"),
        ("display/window/size/viewport_width", "int", base[0]),
        ("display/window/size/viewport_height", "int", base[1]),
        ("display/window/size/window_width_override", "int", r["window"][0] if internal else 0),
        ("display/window/size/window_height_override", "int", r["window"][1] if internal else 0),
        ("display/window/stretch/mode", "string", "viewport" if internal else "disabled"),
        ("display/window/stretch/scale_mode", "string", "integer" if internal else "fractional"),
        ("rendering/renderer/rendering_method", "string", style["renderer"]),
        ("rendering/textures/canvas_textures/default_texture_filter", "int", FILTER2D[r["texture_filter"]]),
        ("rendering/textures/default_filters/anisotropic_filtering_level", "int", 3 if r["texture_filter"] == "linear_mipmap_aniso" else 2),
        ("rendering/anti_aliasing/quality/msaa_3d", "int", MSAA[r["msaa"]]),
        ("rendering/anti_aliasing/quality/screen_space_aa", "int", 1 if r["fxaa"] else 0),
        ("rendering/anti_aliasing/quality/use_taa", "bool", bool(r["taa"])),
        ("rendering/2d/snap/snap_2d_transforms_to_pixel", "bool", bool(r["snap_2d"])),
        ("rendering/2d/snap/snap_2d_vertices_to_pixel", "bool", bool(r["snap_2d"])),
    ]
    return [{"key": k, "type": t, "value": v} for k, t, v in s], ACTIONS


def check_applied(project, profile):
    """The probe judges the SAVED boot scene, so refuse when gg_project.json changed after the last apply (exit 2 names the fix)."""
    fresh = resolve(profile)
    path = os.path.join(project, "gg_data", "style.resolved.json")
    if not os.path.exists(path):
        raise gg_godot.Refused("no applied style yet: run gg_style.py apply --project %s" % project)
    if json.load(open(path)) != fresh:
        raise gg_godot.Refused("gg_project.json style changed since the last apply (the boot scene still has the old look): run gg_style.py apply --project %s" % project)
    return fresh


# Schema-valid keys that the runtime does not read yet. Overriding them changes nothing; apply warns.
UNCONSUMED = ["material.normal_maps", "material.normal_strength", "material.terrain_shader", "material.palette (without palette_quantize)", "geometry.flat_normals",
              "geometry.scatter_density", "geometry.terrain_cell_m", "water.style", "water.deep", "render.texture_filter (3d materials)",
              "input.scheme (actions are fixed WASD/Space/E)"]
STRUCTURAL = ["flat_fraction", "unique_colors", "grid_integrity", "clip_black", "clip_white"]


def note_unconsumed(profile):
    ov = profile["style"].get("overrides") or {}
    hit = [k for k in UNCONSUMED if k.split(" ")[0].split(".")[0] in ov and k.split(" ")[0].split(".")[-1] in json.dumps(ov)]
    if ov:
        print("note: style.overrides is set; only structural targets (%s) are checked because look targets describe the unmodified preset" % ", ".join(STRUCTURAL))
    if hit:
        print("WARNING: these overridden keys are not read by the runtime yet and change nothing: %s" % ", ".join(hit))


def write_resolved(project, profile):
    style = resolve(profile)
    path = os.path.join(project, "gg_data", "style.resolved.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(style, f, indent=1)
    return style, path


PROBE_VIEWS = {
    "3d": [{"name": "hero", "kind": "3d", "position": [0, 2.6, 10.5], "look_at": [0, 1.0, 0], "fov": 50},
           {"name": "overview", "kind": "3d", "position": [14, 12, 16], "look_at": [0, 0.5, 0], "fov": 50},
           {"name": "top", "kind": "3d", "position": [0, 30, 0], "look_at": [0, 0, 0], "fov": 50, "ortho_size": 30}],
    "2d": [{"name": "hero", "kind": "2d", "center": [160, 90], "zoom": 1.0}],
}


def probe_shot(project, style, dimension, out, run=gg_godot.run, timeout=180, view="hero", scene=None, against=None, overrides=False, **kw):
    """Render the probe from the `hero` view. -> (code, report)."""
    internal = style["render"].get("internal")
    window = tuple(style["render"]["window"])
    block = window[0] // internal[0] if internal and window[0] % internal[0] == 0 else None
    extra = {"ctx": {"style": style, "dimension": dimension}}
    if internal:
        extra["internal"] = internal
    views = [v for v in PROBE_VIEWS[dimension] if v["name"] == view]
    ref = load_preset(against) if against else style
    tg = {"targets": ref.get("probe_targets_2d") if dimension == "2d" and ref.get("probe_targets_2d") else ref["probe_targets"], "fix_hints": ref.get("fix_hints")}
    if overrides:
        tg["targets"] = {k: v for k, v in tg["targets"].items() if k in STRUCTURAL}
    where = {"scene": scene} if scene else {"builder": "res://addons/gg/probe/probe_scene.gd"}
    return gg_verify.shot(project, out=out, views=views, size=window, frames=style["capture_frames"], renderer=style["renderer"],
                          targets=tg, timeout=timeout, run=run, block=block, extra_args=extra, **where, **kw)


def matrix_verdict(results, presets):
    """results[a][b] = list of failures when preset a's image is held to preset b's probe_targets. -> (ok, problems)."""
    problems = []
    for a in presets:
        if results[a][a]:
            problems.append("%s fails its own probe_targets: %s" % (a, ", ".join(f["metric"] for f in results[a][a])))
        for b in presets:
            if a != b and not results[a][b]:
                problems.append("%s image passes %s's targets: styles are not distinguishable" % (a, b))
    return not problems, problems


def real_probe(work, name, dim, out, run, shot_kw, against=None):
    """Probe in a REAL initialised project (project settings such as MSAA change the pixels, so a bare project would mislead)."""
    import argparse
    import gg_project
    proj = os.path.join(work, "%s_%s" % (name, dim))
    prof_path = os.path.join(proj, "gg_project.json")
    if not os.path.exists(prof_path):
        a = argparse.Namespace(project=proj, name="probe_" + name.replace("-", "_"), dimension=dim, view=None, style=name, size_m=[256.0, 256.0],
                               cell_m=None, seed=1, dry_run=False, adopt=False)
        code, _ = gg_project.setup_project(a, run=run, check_gate=(shot_kw or {}).get("require_selftest", True))
        if code:
            return code, {"why": "project setup for %s %s failed (exit %d)" % (name, dim, code), "views": [], "engine": None}, proj
    prof = gg_project.load_profile(proj)
    if prof["style"]["preset"] != name or prof["style"].get("overrides"):
        prof["style"] = {"preset": name, "overrides": {}}
        json.dump(prof, open(prof_path, "w"), indent=1)
    code = gg_project.apply_style(proj, run=run)  # never trust an old work dir: re-apply the CURRENT preset before shooting
    if code:
        return code, {"why": "apply failed for %s %s (exit %d)" % (name, dim, code), "views": [], "engine": None}, proj
    style, _ = write_resolved(proj, prof)
    code, rep = probe_shot(proj, style, dim, out, run=run, scene="res://levels/_boot/boot.tscn", against=against, **(shot_kw or {}))
    return code, rep, proj


def matrix(work, out, run=gg_godot.run, names=None, shot_kw=None):
    names = names or list_presets()
    import gg_metrics
    images, metrics = {}, {}
    for n in names:
        p = load_preset(n)
        dim = "3d"
        if "3d" not in p["dimensions"]:
            continue
        code, rep, _ = real_probe(work, n, dim, os.path.join(out, n), run, shot_kw)
        if code not in (0, 1) or not rep["views"]:
            return code or 5, {"error": "probe of %s failed: %s" % (n, rep["why"]), "results": {}}
        images[n] = rep["views"][0]["png"]
        metrics[n] = rep["views"][0]["metrics"]
    results = {a: {} for a in metrics}
    for a in metrics:
        for b in metrics:
            pb = load_preset(b)
            results[a][b] = gg_metrics.compare_targets(metrics[a], pb["probe_targets"], gg_metrics.DEFAULT_TOL)
    ok, problems = matrix_verdict(results, list(metrics))
    rep = {"ok": ok, "problems": problems, "images": images, "metrics": {k: {m: v for m, v in d.items() if m != "hist16"} for k, d in metrics.items()},
           "results": {a: {b: [f["metric"] for f in r] for b, r in row.items()} for a, row in results.items()}}
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "style_matrix.json"), "w") as f:
        json.dump(rep, f, indent=1)
    _contact_sheet(images, os.path.join(out, "style_matrix.png"))
    return (0 if ok else 1), rep


MARGIN = {"luma_p5": 0.04, "luma_p50": 0.04, "luma_p95": 0.05, "sat_mean": 0.05, "flat_fraction": 0.06}


def calibrated_targets(m, grid_block=False):
    """Probe targets from a measured probe image: value +- margin for look metrics, x0.5..x2 for the colour count,
    open-ended caps for clipping. Pure; the result is what 'the probe scene should look like in this style'."""
    t = {}
    for k, mg in MARGIN.items():
        t[k] = [round(max(0.0, m[k] - mg), 3), round(min(1.0, m[k] + mg), 3)]
    t["clip_black"] = [None, 0.01]
    t["clip_white"] = [None, 0.02]
    u = m["unique_colors"]
    t["unique_colors"] = [max(3, u // 2), max(32, int(u * 2))] if u <= 32 else [max(1, int(u * 0.5)), int(u * 2)]
    t["luma_std"] = [round(max(0.02, m["luma_std"] * 0.5), 3), None]
    if grid_block and m.get("grid_integrity") is not None:
        t["grid_integrity"] = [0.98, None]
    return t


def calibrate(work, out, run=gg_godot.run, write=False, names=None, shot_kw=None):
    """Render each preset's probe (3d, plus 2d for presets that support it) and derive probe_targets from the image."""
    import datetime
    report = {}
    for n in names or list_presets():
        p = load_preset(n)
        path = os.path.join(PRESETS, n + ".json")
        for dim in ("3d", "2d"):
            if dim not in p["dimensions"]:
                continue
            code, rep, _ = real_probe(work, n, dim, os.path.join(out, "%s_%s" % (n, dim)), run, shot_kw)
            if code not in (0, 1) or not rep["views"]:
                return code or 5, {"error": "probe %s %s failed: %s" % (n, dim, rep["why"])}
            m = rep["views"][0]["metrics"]
            t = calibrated_targets(m, grid_block=bool(p["render"].get("internal")))
            key = "probe_targets" if dim == "3d" else "probe_targets_2d"
            report["%s/%s" % (n, dim)] = {"metrics": {k: v for k, v in m.items() if k != "hist16"}, key: t}
            p[key] = t
            if dim == "3d":
                p["calibration"] = {"date": datetime.date.today().isoformat(), "renderer": p["renderer"], "adapter": (rep["engine"] or {}).get("adapter"),
                                    "method": "probe_targets = measured value +- margin on the style probe hero view (gg_style.py calibrate)"}
        if write:
            with open(path, "w") as f:
                json.dump(p, f, indent=1)
                f.write("\n")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "calibration.json"), "w") as f:
        json.dump(report, f, indent=1)
    return 0, report


def _contact_sheet(images, path):
    from PIL import Image
    ims = [Image.open(p).convert("RGB").resize((640, 360), Image.NEAREST) for p in images.values()]
    sheet = Image.new("RGB", (1280, 720 if len(ims) > 2 else 360))
    for i, im in enumerate(ims):
        sheet.paste(im, ((i % 2) * 640, (i // 2) * 360))
    sheet.save(path)


def _load_profile(project):
    import gg_project
    return gg_project.load_profile(project)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sh = sub.add_parser("show"); sh.add_argument("name")
    va = sub.add_parser("validate"); va.add_argument("file")
    for n in ("resolve", "apply", "probe"):
        x = sub.add_parser(n); x.add_argument("--project", required=True)
        if n == "apply":
            x.add_argument("--dry-run", action="store_true")
        if n == "probe":
            x.add_argument("--out", required=True)
            x.add_argument("--timeout", type=int, default=180)
            x.add_argument("--against", help="hold the image to ANOTHER preset's probe targets (expect exit 1 for a different style)")
    cb = sub.add_parser("calibrate"); cb.add_argument("--work", required=True); cb.add_argument("--out", required=True); cb.add_argument("--write", action="store_true", help="rewrite presets/*.json probe_targets + calibration")
    mx = sub.add_parser("matrix"); mx.add_argument("--work", required=True); mx.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "list":
            for n in list_presets():
                p = load_preset(n)
                print("%-20s %-16s %-6s %s" % (n, p["renderer"], "/".join(p["dimensions"]), p["description"]))
            return 0
        if a.cmd == "show":
            print(json.dumps(load_preset(a.name), indent=1))
            return 0
        if a.cmd == "validate":
            with open(a.file) as f:
                errs = preset_errors(json.load(f))
            for e in errs:
                print("INVALID " + e)
            print("%s: %s" % (a.file, "valid" if not errs else "%d errors" % len(errs)))
            return 1 if errs else 0
        if a.cmd == "resolve":
            _, path = write_resolved(a.project, _load_profile(a.project))
            print("wrote " + path)
            return 0
        if a.cmd == "apply":
            import gg_project
            return gg_project.apply_style(a.project, dry_run=a.dry_run)
        if a.cmd == "probe":
            prof = _load_profile(a.project)
            style = check_applied(a.project, prof)
            code, rep = probe_shot(a.project, style, prof["dimension"], a.out, timeout=a.timeout, against=a.against,
                                   scene="res://levels/_boot/boot.tscn", overrides=bool((prof["style"].get("overrides") or {})))
            note_unconsumed(prof)
            gg_verify.print_report(rep)
            return code
        if a.cmd == "calibrate":
            code, rep = calibrate(a.work, a.out, write=a.write)
            print(json.dumps(rep, indent=1)[:3000] if code else "calibrated %d probes%s" % (len(rep), " and rewrote the presets" if a.write else " (dry: pass --write to rewrite the presets)"))
            return code
        if a.cmd == "matrix":
            code, rep = matrix(a.work, a.out)
            for pr in rep.get("problems", []) or [rep.get("error")] if code else []:
                print("MATRIX " + str(pr))
            print("matrix: %s (report %s)" % ("PASS" if code == 0 else "FAIL", os.path.join(a.out, "style_matrix.json")))
            return code
    except (gg_godot.Refused, ValueError, OSError) as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
