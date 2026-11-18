#!/usr/bin/env python3
"""UI / overlay games: project start, GDScript tests, transparent UI screenshots with numeric layout checks, and a read-back of the overlay window.

  gg_ui.py init          --project P --name N [--width 1920] [--height 240]   empty UI project (a brief, assets/ and .opencode/ may exist): overlay settings, runtime, scenes/main.tscn, tests/
  gg_ui.py test          --project P [--filter text]                          run res://tests/test_*.gd (each test_* method is a test)
  gg_ui.py shot          --project P --scene res://scenes/main.tscn [--size 1920x240] [--dock bottom --screen 1920x1080] [--min-model-views N] [--name strip]
  gg_ui.py overlay-check --project P [--scene res://...] [--max-height-frac 0.4]

`test` needs tests that extend res://addons/gg/lib/gg_test.gd (ok / eq / near / between / fail). A test with no assertions fails; zero tests is a refusal, not a pass.
`shot` renders the scene into a TRANSPARENT viewport, so the PNG keeps alpha: what the desktop shows through. It then measures: coverage, the opaque bounding box,
every Label/Button rectangle read back from the engine (clipped outside the image, buttons under 24 px, text under --min-font), and, for each SubViewportContainer
(a 3D model view), whether the pixels inside it are really drawn and not flat. `--dock bottom` also checks the window size against --screen (full width, at most
--max-height-frac of the height), and that the bottom edge is drawn; `--expect-see-through` also requires some fully transparent pixels in the image (a UI that must let the desktop show through inside its own window).
`overlay-check` runs the project's main scene and reads back borderless / always-on-top / transparent, the window rectangle against the screen, and the project
settings. It is the ENGINE's report: always-on-top stacking and per-pixel alpha against a real desktop compositor are NOT verified (the Xvfb worker has no desktop).
Exit codes (shared): 0 pass | 1 a check failed | 2 refused | 3 fatal engine log line | 4 no verdict | 5 runner failure.
"""
import argparse
import json
import os
import re
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gg_godot  # noqa: E402
import gg_verify  # noqa: E402

RENDERER = "gl_compatibility"      # the worker has no GPU: UI is checked on software GL
ALPHA_ON = 16                      # alpha at or above this counts as drawn
MIN_BUTTON_PX = 24
KEEP = {".opencode", "BRIEF.md", "AGENTS.md", "assets", "references"}   # a brief, notes and already-copied asset files may exist before init
MAIN_STUB = """[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://scripts/main.gd" id="1"]

[node name="Main" type="Control"]
layout_mode = 3
anchors_preset = 15
anchor_right = 1.0
anchor_bottom = 1.0
script = ExtResource("1")
"""
MAIN_GD = """extends Control
## Entry point of the overlay strip. Replace the body of _ready with the real UI; keep the dock call.
const Overlay := preload("res://addons/gg/game/overlay_window.gd")
const STRIP_HEIGHT := %d

func _ready() -> void:
\tOverlay.dock_bottom(get_window(), STRIP_HEIGHT, Overlay.windowed_requested())
"""
SAMPLE_TEST = """extends "res://addons/gg/lib/gg_test.gd"
const Overlay := preload("res://addons/gg/game/overlay_window.gd")

func test_strip_rect_sits_on_the_bottom_edge() -> void:
\tvar r := Overlay.strip_rect(Rect2i(0, 0, 1920, 1040), 240)
\teq(r.size, Vector2i(1920, 240), "size")
\teq(r.end.y, 1040, "bottom edge")
"""


def parse_size(s):
    m = re.fullmatch(r"(\d{2,5})x(\d{2,5})", str(s).lower())
    if not m:
        raise gg_godot.Refused("size must look like 1920x240, got '%s'" % s)
    w, h = int(m.group(1)), int(m.group(2))
    if not (16 <= w <= 8192 and 16 <= h <= 8192):
        raise gg_godot.Refused("size %dx%d is outside 16..8192" % (w, h))
    return w, h


def check_scene(project, scene):
    if not re.fullmatch(r"res://[A-Za-z0-9_./-]+\.tscn", scene or "") or ".." in scene:
        raise gg_godot.Refused("scene must be a res:// path to a .tscn without .., got %r" % scene)
    if not os.path.isfile(os.path.join(project, scene[6:])):
        raise gg_godot.Refused("scene %s does not exist in the project" % scene)


def check_project(project):
    if not os.path.isfile(os.path.join(project, "project.godot")):
        raise gg_godot.Refused("%s has no project.godot: run `gg_ui.py init` first" % project)


# ----------------------------------------------------------------------------------------------- pure analysis (unit tested)
def analyse_alpha(alpha):
    """alpha: 2-D uint8 array -> metrics of the drawn (opaque) pixels."""
    h, w = alpha.shape
    on = alpha >= ALPHA_ON
    rows, cols = np.where(on.any(axis=1))[0], np.where(on.any(axis=0))[0]
    return {"width": int(w), "height": int(h), "coverage": round(float(on.mean()), 4), "see_through": round(float((~on).mean()), 4),
            "bbox": [int(cols[0]), int(rows[0]), int(cols[-1]), int(rows[-1])] if len(rows) else None,
            "bottom_row_drawn": round(float(on[-1].mean()), 4)}


def rect_stats(rgba, rect):
    """Drawn fraction and luma spread inside rect = [x, y, w, h] of an RGBA array: a flat or empty 3D view is a fault."""
    h, w = rgba.shape[:2]
    x0, y0 = max(0, int(rect[0])), max(0, int(rect[1]))
    x1, y1 = min(w, int(rect[0] + rect[2])), min(h, int(rect[1] + rect[3]))
    if x1 - x0 < 2 or y1 - y0 < 2:
        return {"drawn": 0.0, "luma_std": 0.0, "pixels": 0}
    p = rgba[y0:y1, x0:x1].astype(float)
    luma = 0.2126 * p[..., 0] + 0.7152 * p[..., 1] + 0.0722 * p[..., 2]
    on = p[..., 3] >= ALPHA_ON
    return {"drawn": round(float(on.mean()), 4), "luma_std": round(float(luma[on].std()) if on.any() else 0.0, 2), "pixels": int((x1 - x0) * (y1 - y0))}


def shot_checks(rgba, census, *, dock=None, screen=(1920, 1080), max_frac=0.4, min_cov=0.02, min_views=0, min_font=11, see_through=False):
    """-> (metrics, [(name, ok, detail)])."""
    m = analyse_alpha(rgba[..., 3])
    rows = []
    rows.append(("drawn", m["coverage"] >= min_cov, "%.1f%% of the pixels are drawn (need >= %.1f%%)" % (100 * m["coverage"], 100 * min_cov)))
    if dock == "bottom":
        w, h = m["width"], m["height"]
        rows.append(("strip width", abs(w - screen[0]) <= 2, "window %d px wide, screen %d" % (w, screen[0])))
        rows.append(("strip height", h <= max_frac * screen[1], "window %d px high = %.0f%% of the screen (max %.0f%%)" % (h, 100.0 * h / screen[1], 100 * max_frac)))
        rows.append(("bottom edge drawn", m["bottom_row_drawn"] >= 0.5, "%.0f%% of the bottom row is drawn (need >= 50%%)" % (100 * m["bottom_row_drawn"])))
    if see_through:
        rows.append(("see-through", m["see_through"] >= 0.01, "%.1f%% of the image is transparent (need >= 1%%: the desktop must show through somewhere inside it)" % (100 * m["see_through"])))
    clipped = census.get("clipped", [])
    rows.append(("nothing clipped", not clipped, "%d control(s) reach outside the image%s" % (len(clipped), ": " + ", ".join(c["name"] for c in clipped[:5]) if clipped else "")))
    small = census.get("small_buttons", [])
    rows.append(("buttons big enough", not small, "%d button(s) under %d px%s" % (len(small), MIN_BUTTON_PX, ": " + ", ".join(c["name"] for c in small[:5]) if small else "")))
    tiny = [lb for lb in census.get("labels", []) if lb.get("font_size", 99) < min_font]
    rows.append(("text size", not tiny, "%d label(s) under %d px%s" % (len(tiny), min_font, ": " + ", ".join(lb["name"] for lb in tiny[:5]) if tiny else "")))
    views = census.get("model_views", [])
    if min_views:
        rows.append(("model views", len(views) >= min_views, "%d model view(s) (SubViewportContainer), need >= %d" % (len(views), min_views)))
    for v in views:
        s = rect_stats(rgba, v["rect"])
        rows.append(("model view " + v["name"], s["drawn"] >= 0.05 and s["luma_std"] >= 4.0, "drawn %.0f%%, luma spread %.1f (need >= 5%% and >= 4: a flat or empty view is a fault)" % (100 * s["drawn"], s["luma_std"])))
    m["census"] = {k: (len(v) if isinstance(v, list) else v) for k, v in census.items()}
    return m, rows


def overlay_checks(probe, max_frac=0.4, require_passthrough=False):
    """-> [(name, ok, detail)] from the overlay_probe op's data."""
    f, p, win, usable = probe["flags"], probe["project"], probe["window"], probe["screen"]["usable"]
    rows = []
    rows.append(("transparent", p["per_pixel_transparency"] and (f["transparent"] or p["size_transparent"]) and (probe["viewport_transparent_bg"] or p["transparent_background"]),
                 "per_pixel_transparency=%s, window flag=%s/setting=%s, viewport bg=%s/setting=%s" % (p["per_pixel_transparency"], f["transparent"], p["size_transparent"], probe["viewport_transparent_bg"], p["transparent_background"])))
    rows.append(("borderless", f["borderless"] or p["borderless"], "flag %s, setting %s" % (f["borderless"], p["borderless"])))
    rows.append(("always on top", f["always_on_top"] or p["always_on_top"], "flag %s, setting %s" % (f["always_on_top"], p["always_on_top"])))
    ux, uy, uw, uh = usable
    rows.append(("full width", abs(win["size"][0] - uw) <= 2, "window %d px wide, usable screen %d" % (win["size"][0], uw)))
    rows.append(("strip height", 0 < win["size"][1] <= max_frac * uh, "window %d px high = %.0f%% of the usable height (max %.0f%%)" % (win["size"][1], 100.0 * win["size"][1] / max(uh, 1), 100 * max_frac)))
    rows.append(("docked at the bottom", abs((win["position"][1] + win["size"][1]) - (uy + uh)) <= 2, "window bottom %d, usable bottom %d" % (win["position"][1] + win["size"][1], uy + uh)))
    if require_passthrough:
        rows.append(("mouse passthrough", probe["passthrough_points"] >= 3, "%d polygon point(s)" % probe["passthrough_points"]))
    return rows


def print_rows(rows):
    for name, ok, detail in rows:
        print("  [%s] %s: %s" % ("ok" if ok else "FAIL", name, detail))
    return all(ok for _, ok, _ in rows)


# ----------------------------------------------------------------------------------------------- commands
def init(a):
    project = os.path.abspath(a.project)
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_ -]{0,40}", a.name):
        raise gg_godot.Refused("name must be 1-41 letters, digits, space, _ or -, starting with a letter, got %r" % a.name)
    if os.path.exists(project) and any(n not in KEEP for n in os.listdir(project)):
        raise gg_godot.Refused("%s is not empty: init needs an empty folder (only %s may already be there)" % (project, ", ".join(sorted(KEEP))))
    w, h = a.width, a.height
    if not (16 <= h <= 1080 and 320 <= w <= 7680):
        raise gg_godot.Refused("width %d / height %d outside 320..7680 / 16..1080" % (w, h))
    for d in ("scenes", "scripts", "tests"):
        os.makedirs(os.path.join(project, d), exist_ok=True)
    pg = ('config_version=5\n\n[application]\n\nconfig/name="%s"\nrun/main_scene="res://scenes/main.tscn"\n\n[display]\n\nwindow/size/viewport_width=%d\nwindow/size/viewport_height=%d\n'
          'window/size/borderless=true\nwindow/size/always_on_top=true\nwindow/size/transparent=true\nwindow/per_pixel_transparency/allowed=true\n'
          'window/stretch/mode="canvas_items"\nwindow/stretch/aspect="ignore"\n\n[rendering]\n\nrenderer/rendering_method="%s"\nviewport/transparent_background=true\n') % (a.name, w, h, RENDERER)
    files = {"project.godot": pg, "scenes/main.tscn": MAIN_STUB, "scripts/main.gd": MAIN_GD % h, "tests/test_overlay.gd": SAMPLE_TEST,
             "gg_ui.json": json.dumps({"schema": 1, "kind": "ui-overlay", "name": a.name, "width": w, "height": h}, indent=1) + "\n"}
    for rel, text in files.items():
        with open(os.path.join(project, rel), "w") as f:
            f.write(text)
    wrote = gg_godot.install_runtime(project)
    print("gg_ui init: %s (%dx%d strip, %d runtime files); next: write scripts/, then `gg_ui.py test` and `gg_ui.py shot --scene res://scenes/main.tscn --size %dx%d --dock bottom`" % (project, w, h, len(wrote), w, h))
    return 0


def _engine(project, op, args, render, **kw):
    if render:
        msg = gg_verify.selftest_gate(RENDERER)
        if msg:
            raise gg_godot.Refused(msg)
    return gg_godot.run(project, op, args, render=render, renderer=RENDERER, **kw)


def test(a):
    project = os.path.abspath(a.project)
    check_project(project)
    tdir = os.path.join(project, a.dir[6:] if a.dir.startswith("res://") else a.dir)
    if not re.fullmatch(r"res://[A-Za-z0-9_/-]+", a.dir) or not os.path.isdir(tdir) or not any(n.startswith("test_") and n.endswith(".gd") for n in os.listdir(tdir)):
        raise gg_godot.Refused("no test_*.gd files in %s: write tests that extend res://addons/gg/lib/gg_test.gd (zero tests is not a pass)" % a.dir)
    r = _engine(project, "run_tests", {"dir": a.dir, "filter": a.filter}, False, timeout=a.timeout)
    d = (r.result or {}).get("data") or {}
    if r.code not in (0, 5) or not d:
        print("gg_ui test: exit %d: %s (job %s)" % (r.code, r.why, r.job_dir))
        return r.code
    for t in d["results"]:
        print("  [%s] %s::%s" % ("ok" if t["ok"] else "FAIL", t["file"], t["name"]))
        for line in t["failures"]:
            print("        " + line)
    ok = d["failed"] == 0 and d["tests"] > 0
    print("gg_ui test: %s: %d test(s), %d passed, %d failed, %d assertion(s) (job %s)" % ("PASS" if ok else "FAIL", d["tests"], d["passed"], d["failed"], d["checks"], r.job_dir))
    return 0 if ok else 1


def shot(a):
    project = os.path.abspath(a.project)
    check_project(project)
    check_scene(project, a.scene)
    size, screen = parse_size(a.size), parse_size(a.screen)
    out = os.path.abspath(a.out or os.path.join(project, "gg_data", "ui_shot"))
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", a.name):
        raise gg_godot.Refused("name must be 1-40 letters, digits, _ or -")
    os.makedirs(out, exist_ok=True)
    png = os.path.join(out, a.name + ".png")
    for stale in (png, os.path.join(out, a.name + ".report.json")):
        if os.path.exists(stale):
            os.remove(stale)
    r = _engine(project, "ui_shot", {"scene": a.scene, "size": list(size), "frames": a.frames, "out": png}, True, size=size, timeout=a.timeout)
    if r.code != 0 or not (r.result or {}).get("data") or not os.path.isfile(png):
        print("gg_ui shot: exit %d: %s (job %s)" % (r.code or 4, r.why, r.job_dir))
        return r.code or 4
    rgba = np.asarray(Image.open(png).convert("RGBA"))
    metrics, rows = shot_checks(rgba, r.result["data"]["census"], dock=a.dock, screen=screen, max_frac=a.max_height_frac, min_cov=a.min_coverage,
                                min_views=a.min_model_views, min_font=a.min_font, see_through=a.expect_see_through)
    ok = print_rows(rows)
    with open(os.path.join(out, a.name + ".report.json"), "w") as f:
        json.dump({"schema": 1, "scene": a.scene, "size": list(size), "metrics": metrics, "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in rows],
                   "engine": r.result.get("engine")}, f, indent=1)
    print("gg_ui shot: %s: %s (look at the PNG; the numbers do not replace looking) job %s" % ("PASS" if ok else "FAIL", png, r.job_dir))
    return 0 if ok else 1


def overlay_check(a):
    project = os.path.abspath(a.project)
    check_project(project)
    if a.scene:
        check_scene(project, a.scene)
    r = _engine(project, "overlay_probe", {"scene": a.scene or "", "frames": a.frames}, True, timeout=a.timeout)
    d = (r.result or {}).get("data")
    if r.code != 0 or not d:
        print("gg_ui overlay-check: exit %d: %s (job %s)" % (r.code or 4, r.why, r.job_dir))
        return r.code or 4
    ok = print_rows(overlay_checks(d, a.max_height_frac, a.require_passthrough))
    print("  engine read-back only: always-on-top stacking and per-pixel alpha on a real desktop are NOT verified here (no compositor on the worker): say so in the report.")
    print("gg_ui overlay-check: %s (job %s)" % ("PASS" if ok else "FAIL", r.job_dir))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("--project", required=True); p.add_argument("--name", required=True)
    p.add_argument("--width", type=int, default=1920); p.add_argument("--height", type=int, default=240)
    p = sub.add_parser("test"); p.add_argument("--project", required=True); p.add_argument("--dir", default="res://tests"); p.add_argument("--filter", default=""); p.add_argument("--timeout", type=int, default=180)
    p = sub.add_parser("shot"); p.add_argument("--project", required=True); p.add_argument("--scene", required=True); p.add_argument("--size", default="1920x240")
    p.add_argument("--screen", default="1920x1080"); p.add_argument("--dock", choices=["bottom"], default=None); p.add_argument("--max-height-frac", type=float, default=0.4)
    p.add_argument("--min-coverage", type=float, default=0.02); p.add_argument("--min-model-views", type=int, default=0); p.add_argument("--min-font", type=int, default=11)
    p.add_argument("--expect-see-through", action="store_true"); p.add_argument("--frames", type=int, default=12); p.add_argument("--name", default="ui"); p.add_argument("--out", default=None); p.add_argument("--timeout", type=int, default=180)
    p = sub.add_parser("overlay-check"); p.add_argument("--project", required=True); p.add_argument("--scene", default=""); p.add_argument("--frames", type=int, default=20)
    p.add_argument("--max-height-frac", type=float, default=0.4); p.add_argument("--require-passthrough", action="store_true"); p.add_argument("--timeout", type=int, default=180)
    a = ap.parse_args(argv)
    try:
        return {"init": init, "test": test, "shot": shot, "overlay-check": overlay_check}[a.cmd](a)
    except gg_godot.Refused as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
