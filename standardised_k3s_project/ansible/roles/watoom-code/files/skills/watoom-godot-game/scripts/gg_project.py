#!/usr/bin/env python3
"""Project profile (gg_project.json) and project setup. One profile + one preset describe the whole game.

  gg_project.py doctor                               what is installed (godot, xvfb, numpy, pillow, VRAM, selftest reports)
  gg_project.py init --project DIR --name N --dimension 3d|2d --view V --style PRESET [--size-m X Z] [--cell-m C] [--seed S] [--dry-run] [--adopt]
  gg_project.py validate --project DIR               profile schema, style resolves, godot version, runtime lock
  gg_project.py show --project DIR [--json]
  gg_project.py sync-runtime --project DIR [--dry-run]   re-copy addons/gg from the skill (after drift or a skill update)

init order: refuse unsafe dirs -> write seed files + runtime -> typed project settings through the engine (read back and compared)
-> build res://levels/_boot/boot.tscn through the save protocol -> render it and check the preset's probe targets.
Exit codes: 0 pass | 1 check failed | 2 refused | 3 engine log fatal | 4 no verdict | 5 runner failure.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

import gg_godot
import gg_schema as S
import gg_style
import gg_verify

VIEWS = ["first_person", "third_person", "top_down", "isometric", "side"]
VIEW_NODE = {"t": "obj", "open": True}
PROFILE_SCHEMA = {"t": "obj", "fields": {
    "schema": {"t": "int", "min": 1, "max": 1},
    "name": {"t": "str", "pattern": r"[a-z][a-z0-9_]{0,31}"},
    "title": {"t": "str", "pattern": r".{1,64}"},
    "godot_version": {"t": "str", "pattern": r"4\.\d+\.\d+"},
    "dimension": {"t": "str", "enum": ["2d", "3d"]},
    "view": {"t": "str", "enum": VIEWS},
    "style": {"t": "obj", "fields": {"preset": {"t": "str"}, "overrides": {"t": "obj", "open": True, "opt": True}}},
    "units": {"t": "obj", "fields": {"pixels_per_meter": {"t": "int", "min": 4, "max": 128, "opt": True}, "tile_px": {"t": "int", "enum": [8, 16, 32], "opt": True}}},
    "world": {"t": "obj", "fields": {
        "size_m": {"t": "list", "n": 2, "items": {"t": "float", "min": 16, "max": 8192}},
        "cell_m": {"t": "float", "min": 0.25, "max": 16}, "sea_level_m": {"t": "float"},
        "height_range_m": {"t": "list", "n": 2, "items": {"t": "float"}}, "seed": {"t": "int"}, "origin": {"t": "str", "enum": ["corner"]}}},
    "level": {"t": "str", "pattern": r"[a-z][a-z0-9_]{0,31}"},
    "capture": {"t": "obj", "fields": {
        "size": {"t": "list", "n": 2, "items": {"t": "int", "min": 64, "max": 1920}}, "frames": {"t": "int", "min": 3, "max": 120},
        "views": {"t": "list", "items": VIEW_NODE}}},
    "player": {"t": "obj", "open": True, "opt": True},
    "camera": {"t": "obj", "open": True, "opt": True},
    "input": {"t": "obj", "fields": {"scheme": {"t": "str", "enum": ["wasd_mouse", "wasd_topdown", "platformer"]}}},
    "export": {"t": "obj", "fields": {"presets": {"t": "list", "items": {"t": "str", "enum": ["linux", "windows", "pck"]}}}},
}}


def profile_errors(p):
    errs = S.check(p, PROFILE_SCHEMA)
    if isinstance(p, dict):
        if p.get("dimension") == "2d" and p.get("view") not in (None, "top_down", "side"):
            errs.append("$.view: a 2d project allows top_down or side, got %r" % p.get("view"))
        w = p.get("world") or {}
        if isinstance(w.get("height_range_m"), list) and len(w["height_range_m"]) == 2 and w["height_range_m"][0] >= w["height_range_m"][1]:
            errs.append("$.world.height_range_m: lo %s must be < hi %s" % tuple(w["height_range_m"]))
        if isinstance(w.get("sea_level_m"), (int, float)) and isinstance(w.get("height_range_m"), list) and len(w["height_range_m"]) == 2 \
                and not w["height_range_m"][0] <= w["sea_level_m"] <= w["height_range_m"][1]:
            errs.append("$.world.sea_level_m: %s is outside height_range_m %s" % (w["sea_level_m"], w["height_range_m"]))
        if isinstance(p.get("capture"), dict):
            try:
                gg_verify.validate_views(p["capture"].get("views"))
            except gg_godot.Refused as e:
                errs.append("$.capture.views: %s" % e)
    return errs


def load_profile(project):
    path = os.path.join(project, "gg_project.json")
    if not os.path.isfile(path):
        raise gg_godot.Refused("%s has no gg_project.json: run gg_project.py init (or this is not a watoom-godot-game project)" % project)
    with open(path) as f:
        p = json.load(f)
    errs = profile_errors(p)
    if errs:
        raise gg_godot.Refused("gg_project.json invalid:\n  " + "\n  ".join(errs))
    return p


def default_views(dimension, size_m):
    if dimension == "2d":
        return [{"name": "hero", "kind": "2d", "center": [size_m[0] / 2, size_m[1] / 2], "zoom": 1.0}]
    cx, cz = size_m[0] / 2, size_m[1] / 2
    return [{"name": "hero", "kind": "3d", "position": [cx, 3.0, cz + 12], "look_at": [cx, 1.0, cz], "fov": 60},
            {"name": "overview", "kind": "3d", "position": [cx + size_m[0] * 0.6, size_m[0] * 0.4, cz + size_m[1] * 0.6], "look_at": [cx, 0, cz], "fov": 50},
            {"name": "top", "kind": "3d", "position": [cx, size_m[0], cz], "look_at": [cx, 0, cz], "fov": 50, "ortho_size": size_m[0]}]


def godot_version(godot=None):
    g = godot or gg_godot.find_godot()
    if not g:
        return None
    out = subprocess.run([g, "--version"], capture_output=True, text=True).stdout.strip()
    return out.split(".stable")[0].split(".custom")[0] if out else None


def doctor(state_dir=None):
    rows = []
    g = gg_godot.find_godot()
    rows.append(("godot", bool(g), "%s (%s)" % (g, godot_version(g)) if g else "not found: set GG_GODOT"))
    rows.append(("xvfb-run", bool(shutil.which("xvfb-run")), shutil.which("xvfb-run") or "missing: render ops need it"))
    for mod in ("numpy", "PIL"):
        try:
            __import__(mod)
            rows.append((mod, True, "ok"))
        except ImportError:
            rows.append((mod, False, "missing"))
    nv = shutil.which("nvidia-smi")
    if nv:
        out = subprocess.run([nv, "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout.strip()
        rows.append(("gpu memory", True, out.replace(",", " of") + " MiB used (shared with the LLM servers)" if out else "unknown"))
    tpl = os.path.expanduser("~/.local/share/godot/export_templates")
    rows.append(("export templates", os.path.isdir(tpl) and bool(os.listdir(tpl)), tpl if os.path.isdir(tpl) and os.listdir(tpl) else "none: only .pck export is possible"))
    for r in ("forward_plus", "gl_compatibility"):
        msg = gg_verify.selftest_gate(r, state_dir=state_dir)
        rows.append(("selftest " + r, msg is None, "passed" if msg is None else msg))
    return rows


def _write(path, text, dry):
    if not dry:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)


def check_dir(project, adopt):
    if os.path.exists(project) and not os.path.isdir(project):
        raise gg_godot.Refused("%s exists and is not a directory" % project)
    if not os.path.isdir(project):
        return
    entries = [e for e in os.listdir(project) if e not in (".git", ".gitignore")]
    if not entries:
        return
    if os.path.exists(os.path.join(project, "gg_project.json")):
        raise gg_godot.Refused("%s is already a gg project (gg_project.json exists); use gg_style.py apply to change style" % project)
    if "project.godot" in entries and not adopt:
        raise gg_godot.Refused("%s has a project.godot not created by gg; pass --adopt to take it over (project.godot will be rewritten)" % project)
    if "project.godot" not in entries:
        raise gg_godot.Refused("%s is not empty (%s ...) and has no project.godot: use an empty directory" % (project, ", ".join(sorted(entries)[:3])))


def build_profile(a):
    style = gg_style.load_preset(a.style)
    if a.dimension not in style["dimensions"]:
        raise gg_godot.Refused("preset '%s' supports %s, not %s" % (style["name"], style["dimensions"], a.dimension))
    view = a.view or ("top_down" if a.dimension == "2d" else "third_person")
    size = a.size_m or [256.0, 256.0]
    prof = {
        "schema": 1, "name": a.name, "title": a.name.replace("_", " ").title(), "godot_version": (godot_version() or "4.7.2"),
        "dimension": a.dimension, "view": view, "style": {"preset": style["name"], "overrides": {}},
        "units": {"pixels_per_meter": 16, "tile_px": 16},
        "world": {"size_m": [float(size[0]), float(size[1])], "cell_m": float(a.cell_m if a.cell_m else style["geometry"]["terrain_cell_m"]),
                  "sea_level_m": 0.0, "height_range_m": [-20.0, 60.0], "seed": a.seed, "origin": "corner"},
        "level": "main",
        "capture": {"size": list(style["render"]["window"]), "frames": style["capture_frames"], "views": default_views(a.dimension, size)},
        "input": {"scheme": "wasd_topdown" if view == "top_down" else "wasd_mouse"},
        "export": {"presets": ["pck"]},
    }
    errs = profile_errors(prof)
    if errs:
        raise gg_godot.Refused("profile would be invalid:\n  " + "\n  ".join(errs))
    return prof, style


def apply_style(project, dry_run=False, run=gg_godot.run, build_scene=True):
    """Resolve the style, set typed project settings through the engine, read them back, rebuild the boot scene. -> exit code."""
    prof = load_profile(project)
    style = gg_style.resolve(prof)
    settings, actions = gg_style.settings_for(prof, style)
    if dry_run:
        print("would write %d typed settings, %d input actions, rebuild res://levels/_boot/boot.tscn; renderer %s" % (len(settings), len(actions), style["renderer"]))
        for s in settings:
            print("  %-70s %-7s %r" % (s["key"], s["type"], s["value"]))
        return 0
    gg_style.write_resolved(project, prof)
    gg_style.note_unconsumed(prof)
    main_scene = [x for x in settings if x["key"] == "application/run/main_scene"]
    settings = [x for x in settings if x["key"] != "application/run/main_scene"]  # set only after the scene exists
    args = {"settings": settings, "actions": actions}
    r = run(project, "project_apply", args, render=False, renderer=style["renderer"])
    if r.code:
        print("project_apply failed (exit %d): %s" % (r.code, r.why))
        return r.code
    r = run(project, "project_dump", args, render=False, renderer=style["renderer"])
    if r.code:
        print("project_dump failed (exit %d): %s" % (r.code, r.why))
        return r.code
    bad = r.result["data"]["mismatches"]
    for m in bad:
        print("MISMATCH %s: wanted %s, project.godot has %s" % (m["key"], m["want"], m["got"]))
    if bad:
        return 1
    if build_scene:
        r = run(project, "build_boot", {"style": style, "dimension": prof["dimension"], "out": "res://levels/_boot/boot.tscn"},
                render=False, renderer=style["renderer"])
        if r.code:
            print("build_boot failed (exit %d): %s" % (r.code, r.why))
            return r.code
        print("boot scene built: %s nodes" % r.result["data"]["nodes"])
        for op in ("project_apply", "project_dump"):
            r = run(project, op, {"settings": main_scene}, render=False, renderer=style["renderer"])
            if r.code:
                print("%s (main scene) failed (exit %d): %s" % (op, r.code, r.why))
                return r.code
        if r.result["data"]["mismatches"]:
            print("MISMATCH main_scene: %s" % r.result["data"]["mismatches"])
            return 1
    return 0


def setup_project(a, run=gg_godot.run, state_dir=None, check_gate=True):
    """init without the final render check. -> (exit code, profile). Used by init and by gg_style calibrate/matrix (real projects)."""
    project = os.path.abspath(a.project)
    prof, style = build_profile(a)
    check_dir(project, a.adopt)
    msg = gg_verify.selftest_gate(style["renderer"], state_dir=state_dir) if check_gate else None
    if msg:
        raise gg_godot.Refused(msg)
    os.makedirs(project, exist_ok=True)
    _write(os.path.join(project, "project.godot"), 'config_version=5\n\n[application]\n\nconfig/name="%s"\n' % prof["title"], False)
    _write(os.path.join(project, "gg_project.json"), json.dumps(prof, indent=1) + "\n", False)
    _write(os.path.join(project, ".gitignore"), ".godot/\ngg_data/jobs/\n*.new.tscn\n", False)
    gg_godot.install_runtime(project)
    return apply_style(project, run=run), prof


def init(a, run=gg_godot.run, state_dir=None):
    project = os.path.abspath(a.project)
    prof, style = build_profile(a)
    check_dir(project, a.adopt)
    msg = gg_verify.selftest_gate(style["renderer"], state_dir=state_dir)
    if msg and not a.dry_run:
        raise gg_godot.Refused(msg)
    if a.dry_run:
        print("dry run: would create in %s:" % project)
        for f in ("project.godot", "gg_project.json", "addons/gg/ (runtime + runtime.lock.json)", "gg_data/.gdignore", ".gitignore", "levels/_boot/boot.tscn"):
            print("  " + f)
        print("profile: " + json.dumps(prof)[:300] + " ...")
        print("selftest gate: " + (msg or "ok"))
        return 0
    code, prof = setup_project(a, run=run, state_dir=state_dir)
    if code:
        return code
    sty, _ = gg_style.write_resolved(project, prof)
    code, rep = gg_style.probe_shot(project, sty, prof["dimension"], os.path.join(project, "gg_data", "init_shot"), run=run, scene="res://levels/_boot/boot.tscn")
    gg_verify.print_report(rep)
    print("init %s: %s" % (project, "ok" if code == 0 else "FAILED at the first render check (exit %d)" % code))
    return code


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    i = sub.add_parser("init")
    i.add_argument("--project", required=True); i.add_argument("--name", required=True)
    i.add_argument("--dimension", required=True, choices=["2d", "3d"]); i.add_argument("--view")
    i.add_argument("--style", required=True); i.add_argument("--size-m", nargs=2, type=float)
    i.add_argument("--cell-m", type=float); i.add_argument("--seed", type=int, default=1)
    i.add_argument("--dry-run", action="store_true"); i.add_argument("--adopt", action="store_true")
    for n in ("validate", "show", "sync-runtime"):
        x = sub.add_parser(n); x.add_argument("--project", required=True)
        if n == "show":
            x.add_argument("--json", action="store_true")
        if n == "sync-runtime":
            x.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "doctor":
            rows = doctor()
            for n, ok, d in rows:
                print("%-4s %-22s %s" % ("ok" if ok else "FAIL", n, d))
            return 0 if all(ok for n, ok, _ in rows if n in ("godot", "xvfb-run", "numpy", "PIL")) else 1
        if a.cmd == "init":
            return init(a)
        project = os.path.abspath(a.project)
        if a.cmd == "sync-runtime":
            files = gg_godot.install_runtime(project, dry_run=a.dry_run)
            print("%s %d runtime files into %s/addons/gg" % ("would copy" if a.dry_run else "copied", len(files), project))
            return 0
        prof = load_profile(project)
        if a.cmd == "show":
            print(json.dumps(prof, indent=1) if a.json else "%s: %s %s, preset %s, world %s m" % (prof["name"], prof["dimension"], prof["view"], prof["style"]["preset"], prof["world"]["size_m"]))
            return 0
        if a.cmd == "validate":
            gg_style.resolve(prof)
            drift = gg_godot.runtime_drift(project)
            have, want = godot_version(), prof["godot_version"]
            problems = list(drift)
            if have and have != want:
                problems.append("godot is %s but the profile says %s" % (have, want))
            for p in problems:
                print("PROBLEM " + p)
            print("validate: %s" % ("ok" if not problems else "%d problems" % len(problems)))
            return 1 if problems else 0
    except (gg_godot.Refused, ValueError, OSError) as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
