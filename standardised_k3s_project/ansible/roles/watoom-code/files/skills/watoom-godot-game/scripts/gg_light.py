#!/usr/bin/env python3
"""Lighting and exposure, measured. 3D only (2D looks are set by the palette and style preset).

  gg_light.py shoot     --project P [--out DIR]                 render the level overview + ground view, check the overview against the preset's `targets`
  gg_light.py tune      --project P [--max-steps 8] [--write]   change ONE lighting value per step from the failing metric's fix hint until the overview passes
  gg_light.py calibrate --work DIR [--write] [--names a,b]      derive each preset's level `targets` from measured reference terrains (needs the selftest)

The level must exist: gg_terrain.py build first. `tune` only touches lighting.* and post.exposure / post.adjust.*; it writes
overrides into gg_project.json (and re-applies the style) ONLY with --write. Each step is checked for a response in the expected direction.
Exit codes: 0 pass | 1 targets not met | 2 refused | 3 engine log fatal | 4 no verdict | 5 runner failure.
"""
import argparse
import copy
import datetime
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
import gg_terrain  # noqa: E402
import gg_verify  # noqa: E402
import gg_water  # noqa: E402

TUNABLE = re.compile(r"^(lighting\.(sun_energy|ambient_energy|sun_elevation_deg)|post\.exposure|post\.adjust\.(brightness|contrast|saturation))$")
PRIORITY = ["luma_p50", "luma_p95", "luma_p5", "clip_black", "clip_white", "sat_mean"]
LEVEL_MARGIN = {"luma_p5": 0.05, "luma_p50": 0.08, "luma_p95": 0.15, "sat_mean": 0.08}  # p95 is sky and highlight dominated: scene content moves it by up to 0.15 (measured on a no-sea plateau)
VERB = re.compile(r"\b(raise|lower)\b")
PAIR = re.compile(r"([a-z_]+(?:\.[a-z_]+)+) by ([0-9.]+)")


def refuse_2d(prof):
    if prof["dimension"] != "3d":
        raise gg_godot.Refused("lighting recipes are 3D only; this project is 2d (its look comes from style.preset and the palette)")


def level_views(project, prof):
    wd = gg_terrain.load_world(project)
    sx, sz = prof["world"]["size_m"]
    nx, nz = wd["size_px"]
    h = np.fromfile(os.path.join(gg_terrain.world_dir(project), "heights.f32"), "<f4").reshape(nz, nx)
    hc = float(h[nz // 2, nx // 2])
    return [{"name": "overview", "kind": "3d", "position": [sx / 2, 0.6 * max(sx, sz), sz * 1.15], "look_at": [sx / 2, hc * 0.5, sz / 2], "fov": 50},
            {"name": "ground", "kind": "3d", "position": [sx / 2, hc + 2.5, sz / 2], "look_at": [sx / 2, hc + 1.0, sz / 2 + 30], "fov": 60}]


def shoot_style(project, style, prof, out, run=gg_godot.run):
    """Render the views with an explicit style dict (tune passes modified copies). -> (code, report) with per-view metrics; target check is separate."""
    refuse_2d(prof)
    scene = os.path.join(project, "levels", prof["level"], "terrain.tscn")
    if not os.path.isfile(scene):
        raise gg_godot.Refused("no %s: run gg_terrain.py build first" % scene)
    ok = os.path.join(gg_terrain.world_dir(project), "build_ok.json")
    if not os.path.isfile(ok) or json.load(open(ok)).get("heights_sha") != gg_terrain.load_world(project).get("heights_sha"):
        raise gg_godot.Refused("the terrain was not built and verified from the current heights (no passing build_ok.json): run gg_terrain.py build and get exit 0")
    size = tuple(style["render"]["window"])
    scenes = ["res://levels/%s/terrain.tscn" % prof["level"]]
    wok = os.path.join(gg_terrain.world_dir(project), "water_ok.json")
    if os.path.isfile(wok) and json.load(open(wok)).get("heights_sha") == gg_terrain.load_world(project).get("heights_sha"):
        scenes.append("res://levels/%s/water.tscn" % prof["level"])  # only a verified water scene is included
    import gg_scatter
    if gg_scatter.stamp_valid(project, prof["level"], gg_terrain.load_world(project).get("heights_sha")):
        scenes.append("res://levels/%s/scatter.tscn" % prof["level"])  # and only an audited scatter
    extra = {"ctx": {"style": style, "scenes": scenes}}
    block = None
    if style["render"].get("internal"):
        extra["internal"] = style["render"]["internal"]
        block = size[0] // style["render"]["internal"][0] if size[0] % style["render"]["internal"][0] == 0 else None
    code, rep = gg_verify.shot(project, builder="res://addons/gg/probe/level_preview.gd", out=out, views=level_views(project, prof), size=size,
                               frames=style["capture_frames"], renderer=style["renderer"], run=run, block=block, extra_args=extra)
    # no targets were passed, so exit 1 here means a hard failure (blank or crushed frame). Keep the metrics, report the failure by view.
    rep["hard"] = ["%s: %s" % (v["name"], f if isinstance(f, str) else f.get("hint", f)) for v in rep["views"] for f in v["failures"]] if code == 1 else []
    return (0 if code == 1 and rep["views"] else code), rep


def failures(style, metrics):
    return gg_metrics.compare_targets(metrics, style["targets"], fix_hints=style.get("fix_hints"))


def shoot(project, out=None, run=gg_godot.run):
    prof = gg_project.load_profile(project)
    style = gg_style.check_applied(project, prof)
    out = out or os.path.join(project, "gg_data", "light")
    code, rep = shoot_style(project, style, prof, out, run)
    if code:
        return code, rep, []
    fails = failures(style, rep["views"][0]["metrics"])
    if rep.get("hard"):
        print("HARD FAILURE: " + "; ".join(rep["hard"]))
    return (1 if fails or rep.get("hard") else 0), rep, fails


def parse_hint(hint, dead=()):
    """First 'raise|lower KEY by N' in a fix hint whose KEY lighting may change and that has not been found dead. -> (sign, key, step) or None."""
    v = VERB.search(hint or "")
    if not v:
        return None
    for key, step in PAIR.findall(hint[v.end():]):
        if TUNABLE.match(key) and key not in dead:
            return (1 if v.group(1) == "raise" else -1), key, float(step)
    return None


def _get(d, dotted):
    for k in dotted.split("."):
        d = d[k]
    return d


def _set(d, dotted, v):
    ks = dotted.split(".")
    for k in ks[:-1]:
        d = d.setdefault(k, {})
    d[ks[-1]] = v


def pick(fails, dead=()):
    by = {f["metric"]: f for f in fails}
    for m in PRIORITY:
        if m in by and parse_hint(by[m]["hint"], dead):
            return by[m]
    return None


def tune(project, max_steps=8, write=False, run=gg_godot.run, out=None):
    """Hill-climb on one value per step. -> (code, report). Never writes unless write=True and the targets are met."""
    prof = gg_project.load_profile(project)
    refuse_2d(prof)
    gg_style.check_applied(project, prof)
    out = out or os.path.join(project, "gg_data", "light_tune")
    over = copy.deepcopy(prof["style"].get("overrides") or {})
    steps = []
    last = None
    dead = set()
    for i in range(3 * max_steps + 3):  # renders; undone dead changes cost one extra render each
        p2 = copy.deepcopy(prof)
        p2["style"]["overrides"] = over
        style = gg_style.resolve(p2)
        code, rep = shoot_style(project, style, prof, os.path.join(out, "step%d" % i), run)
        if code:
            return code, {"steps": steps, "why": rep["why"]}
        m = rep["views"][0]["metrics"]
        fails = failures(style, m)
        if last and last["metric"] in m:
            moved = (m[last["metric"]] - last["before"]) * last["sign"]
            steps[-1]["after"] = m[last["metric"]]
            if moved <= 0.002:
                steps[-1]["warning"] = "%s did not move in the expected direction (%.4f -> %.4f): %s has no effect here, not using it again" % (last["metric"], last["before"], m[last["metric"]], last["key"])
                dead.add(last["key"])
                _set(over, last["key"], last["old"])  # undo the dead change so it is not left in the overrides
                if last["old"] == last["default"]:
                    over_clean(over, last["key"])
                last = None
                continue  # judge only a render taken with the overrides we will actually keep
        if not fails:
            if rep.get("hard"):
                return 1, {"steps": steps, "overrides": over, "why": "targets met but a view has a hard failure: " + "; ".join(rep["hard"])}
            res = {"steps": steps, "overrides": over, "final": {k: m[k] for k in PRIORITY}, "why": "overview meets the preset targets after %d change(s)" % len(steps)}
            if write and steps:
                wc = write_overrides(project, prof, over, run)
                res["written"] = wc == 0
                if wc:
                    return wc, {**res, "why": "overrides were written to gg_project.json but gg_style.py apply failed (exit %d): run it yourself and read its output" % wc}
            return 0, res
        f = pick(fails, dead)
        if f is None:
            return 1, {"steps": steps, "overrides": over, "unfixable": [x["metric"] for x in fails],
                       "why": "remaining failures cannot be fixed by lighting: " + "; ".join("%s=%.3f %s" % (x["metric"], x["value"], x["hint"]) for x in fails)}
        if len(steps) >= max_steps:
            break
        sign, key, step = parse_hint(f["hint"], dead)
        lo, hi = f["range"]
        gap = (lo - f["value"]) if f["direction"] == "low" else (f["value"] - hi)
        n = int(max(1, min(12, round(abs(gap) / 0.02))))
        cur = _get(style, key)
        new = round(cur + sign * step * n, 4)
        if key.startswith("lighting.sun_energy") or key.startswith("lighting.ambient") or key == "post.exposure":
            new = max(0.0, new)
        _set(over, key, new)
        steps.append({"change": "%s %s -> %s" % (key, cur, new), "because": "%s %s (%.3f, want %s)" % (f["metric"], f["direction"], f["value"], f["range"]), "before": f["value"], "metric": f["metric"], "sign": (1 if f["direction"] == "low" else -1), "key": key, "old": cur, "default": _get(gg_style.resolve(prof_no_over(prof)), key)})
        last = steps[-1]
    return 1, {"steps": steps, "overrides": over, "why": "targets still not met after %d steps; last overview metrics %s" % (max_steps, {k: round(m[k], 3) for k in PRIORITY})}


def prof_no_over(prof):
    p = copy.deepcopy(prof)
    p["style"]["overrides"] = {}
    return p


def over_clean(over, dotted):
    """Remove an override key (and now-empty parents) so a reverted dead change leaves no trace."""
    ks = dotted.split(".")
    chain = [over]
    for k in ks[:-1]:
        chain.append(chain[-1].get(k, {}))
    chain[-1].pop(ks[-1], None)
    for i in range(len(ks) - 1, 0, -1):
        if not chain[i]:
            chain[i - 1].pop(ks[i - 1], None)


def write_overrides(project, prof, over, run):
    prof["style"]["overrides"] = over
    path = os.path.join(project, "gg_project.json")
    with open(path + ".new", "w") as f:
        json.dump(prof, f, indent=1)
    os.replace(path + ".new", path)
    return gg_project.apply_style(project, run=run)


def level_targets(ms):
    """ms: measured overview metrics of >= 1 reference terrains. Range = [min - margin, max + margin] so the recipe is not tied to one terrain."""
    ms = ms if isinstance(ms, list) else [ms]
    t = {k: [round(max(0.0, min(m[k] for m in ms) - mg), 3), round(min(1.0, max(m[k] for m in ms) + mg), 3)] for k, mg in LEVEL_MARGIN.items()}
    t["clip_black"] = [None, 0.02]
    t["clip_white"] = [None, 0.02]
    t["luma_std"] = [round(max(0.02, min(m["luma_std"] for m in ms) * 0.5), 3), None]
    return t


def calibrate(work, out, run=gg_godot.run, write=False, names=None, shot_kw=None):
    """Per preset: init a real project, build two reference terrains (island seed 1, hills seed 7); targets span both.
    A third held-out terrain (plateau seed 11) is measured against them and reported (does the recipe generalise?)."""
    report = {}
    pending = {}
    for n in names or gg_style.list_presets():
        p = gg_style.load_preset(n)
        if "3d" not in p["dimensions"]:
            continue
        proj = os.path.join(work, "%s_3d" % n)
        code, rep, _ = gg_style.real_probe(work, n, "3d", os.path.join(out, "%s_probe" % n), run, shot_kw)
        if code not in (0, 1):
            return code or 5, {"error": "setup of %s failed: %s" % (n, rep.get("why"))}
        res = {}
        for tag, shape, relief, seed in (("island", "island", 40.0, 1), ("hills", "hills", 30.0, 7), ("heldout", "plateau", 35.0, 11)):
            gg_terrain.heights(proj, shape, relief, seed)
            c, _r, _w = gg_terrain.layers(proj)
            if c:
                return c, {"error": "layers for %s failed" % n}
            c, o = gg_terrain.build(proj, run=run, check_view=True)
            if c:
                return c, {"error": "terrain build for %s failed: %s" % (n, o.get("why"))}
            c, o = gg_water.build(proj, run=run)  # the lit level has water: calibrate with it
            if c:
                return c, {"error": "water build for %s failed: %s" % (n, o.get("why"))}
            prof = gg_project.load_profile(proj)
            style = gg_style.resolve(prof)
            code, rep = shoot_style(proj, style, prof, os.path.join(out, "%s_%s" % (n, tag)), run)
            if code:
                return code, {"error": "shot %s %s: %s" % (n, tag, rep["why"])}
            res[tag] = rep["views"][0]["metrics"]
        t = level_targets([res["island"], res["hills"]])
        out_ = [f["metric"] for f in gg_metrics.compare_targets(res["heldout"], t)]
        pending[n] = (os.path.join(gg_style.PRESETS, n + ".json"), p, t)
        report[n] = {"targets": t, **{k: {m: round(v[m], 3) for m in PRIORITY} for k, v in res.items()}, "heldout_plateau_outside": out_}
    os.makedirs(out, exist_ok=True)
    json.dump(report, open(os.path.join(out, "light_calibration.json"), "w"), indent=1)
    bad = [n for n, r in report.items() if r["heldout_plateau_outside"]]
    if write and bad:
        return 1, {**report, "error": "not written: the held-out terrain is outside the targets for %s (the targets do not generalise; widen LEVEL_MARGIN or add a reference terrain)" % ", ".join(bad)}
    if write:  # only after every preset measured fine; each file replaced atomically
        for n, (path, p, t) in pending.items():
            p["targets"] = t
            p["calibration_level"] = {"date": datetime.date.today().isoformat(), "method": "targets = overview of two 256 m terrains with sea (island seed 1 relief 40 m, hills seed 7 relief 30 m; preset layer template) spanned +- margin; gg_light.py calibrate"}
            with open(path + ".new", "w") as f:
                json.dump(p, f, indent=1)
                f.write("\n")
            os.replace(path + ".new", path)
    return 0, report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("shoot"); s.add_argument("--project", required=True); s.add_argument("--out")
    t = sub.add_parser("tune"); t.add_argument("--project", required=True); t.add_argument("--max-steps", type=int, default=8); t.add_argument("--write", action="store_true")
    c = sub.add_parser("calibrate"); c.add_argument("--work", required=True); c.add_argument("--out"); c.add_argument("--write", action="store_true"); c.add_argument("--names")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "shoot":
            code, rep, fails = shoot(os.path.abspath(a.project), a.out)
            if rep["views"]:
                gg_verify.print_report(rep)
            else:
                print("exit %d: %s" % (code, rep["why"]))
            for f in fails:
                print("  TARGET FAIL %s=%.3f (%s of %s): %s" % (f["metric"], f["value"], f["direction"], f["range"], f["hint"]))
            return code
        if a.cmd == "tune":
            code, rep = tune(os.path.abspath(a.project), a.max_steps, a.write)
            for i, st in enumerate(rep["steps"], 1):
                print("step %d: %s  (%s) -> %s%s" % (i, st["change"], st["because"], st.get("after", "?"), "  WARNING " + st["warning"] if "warning" in st else ""))
            print("%s: %s" % ("PASS" if code == 0 else "FAIL", rep["why"]))
            if code == 0 and rep["steps"] and not a.write:
                print("overrides to put in gg_project.json style.overrides: %s (or re-run with --write)" % json.dumps(rep["overrides"]))
            return code
        if a.cmd == "calibrate":
            out = os.path.abspath(a.out or os.path.join(a.work, "light_out"))
            code, rep = calibrate(os.path.abspath(a.work), out, write=a.write, names=a.names.split(",") if a.names else None)
            print(json.dumps(rep, indent=1))
            return code
    except (gg_godot.Refused, gg_metrics.Refused, ValueError, OSError, KeyError, json.JSONDecodeError) as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
