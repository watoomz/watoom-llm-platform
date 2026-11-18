#!/usr/bin/env python3
"""The verify loop: render, measure, compare, and prove the loop can see. Read references/gg-verify-loop.md.

  gg_verify.py shot    --project P (--scene res://x.tscn | --builder res://b.gd) --out DIR [--view NAME ...] [--size WxH]
                       [--frames N] [--renderer R] [--targets FILE] [--tol 0.01] [--strict-warnings] [--timeout S]
  gg_verify.py measure IMAGE [--targets FILE] [--block K]
  gg_verify.py compare A.png B.png --expect brighter|darker|more-saturated|less-saturated|tint-r|tint-g|tint-b|different|same
  gg_verify.py log FILE [--strict-warnings]
  gg_verify.py selftest [--work DIR] [--renderer R ...] [--report FILE]      run once per host / Godot change

Exit codes: 0 pass | 1 check failed | 2 refused | 3 fatal engine log | 4 no verdict | 5 runner failure. A view is only
real if the log is clean: a shader/script error keeps the old look, so ALWAYS read exit 3 before judging an image.
"""
import argparse
import datetime
import json
import os
import shutil
import sys
import tempfile

import gg_godot
import gg_log
import gg_metrics

STATE_DIR = os.environ.get("GG_STATE_DIR") or os.path.join(os.path.expanduser("~"), ".cache", "watoom-gg")


VIEW_KEYS = {"3d": {"name", "kind", "position", "look_at", "fov", "ortho_size"}, "2d": {"name", "kind", "center", "zoom"}}


def validate_views(views):
    """Refuse bad view dicts before launching: unknown kind/keys, duplicate or missing names. Names both the bad value and the allowed set."""
    seen = set()
    for i, v in enumerate(views or []):
        if not isinstance(v, dict):
            raise gg_godot.Refused("view %d must be an object, got %r" % (i, v))
        kind = v.get("kind", "3d")
        if kind not in VIEW_KEYS:
            raise gg_godot.Refused("view '%s': kind %r not one of %s" % (v.get("name", i), kind, sorted(VIEW_KEYS)))
        bad = set(v) - VIEW_KEYS[kind]
        if bad:
            raise gg_godot.Refused("view '%s': unknown key(s) %s (allowed for %s: %s)" % (v.get("name", i), sorted(bad), kind, sorted(VIEW_KEYS[kind])))
        n = v.get("name")
        if not isinstance(n, str) or not n.replace("_", "").replace("-", "").isalnum():
            raise gg_godot.Refused("view %d needs a name of letters, digits, - or _ (got %r)" % (i, n))
        if n in seen:
            raise gg_godot.Refused("duplicate view name '%s'" % n)
        seen.add(n)
        for k in ("position", "look_at"):
            if k in v and not (isinstance(v[k], list) and len(v[k]) == 3):
                raise gg_godot.Refused("view '%s': %s must be [x, y, z], got %r" % (n, k, v[k]))


def selftest_gate(renderer, godot=None, state_dir=None):
    """Refuse unless a PASSING selftest report exists for this renderer and this godot binary. -> None or message."""
    path = os.path.join(state_dir or STATE_DIR, "selftest_%s.json" % renderer)
    if not os.path.exists(path):
        return "no selftest report for %s at %s: run `gg_verify.py selftest` first (step 0)" % (renderer, path)
    rep = json.load(open(path))
    if not rep.get("pass"):
        return "selftest for %s FAILED (%s): the loop cannot be trusted; fix and re-run `gg_verify.py selftest`" % (renderer, path)
    g = godot or gg_godot.find_godot()
    if rep.get("godot") != g:
        return "selftest was run with godot %s but this run uses %s: re-run `gg_verify.py selftest`" % (rep.get("godot"), g)
    return None


def _size(s):
    try:
        w, h = s.lower().split("x")
        return int(w), int(h)
    except ValueError:
        raise gg_godot.Refused("size must look like 1280x720, got '%s'" % s)


def shot(project, scene=None, builder=None, out=".", views=None, size=(1280, 720), frames=8, renderer="forward_plus",
         targets=None, tol=gg_metrics.DEFAULT_TOL, strict_warnings=False, timeout=180, run=gg_godot.run, block=None, project_views=None, extra_args=None,
         require_selftest=True, state_dir=None):
    """-> (code, report dict). Writes out/<view>.png and out/verify_report.json."""
    out = os.path.abspath(out)
    vs = views if views is not None else project_views
    validate_views(vs)
    try:
        gg_metrics.validate_targets((targets or {}).get("targets", targets or {}))
    except gg_metrics.Refused as e:
        raise gg_godot.Refused(str(e))
    if require_selftest:
        msg = selftest_gate(renderer, state_dir=state_dir)
        if msg:
            raise gg_godot.Refused(msg)
    os.makedirs(out, exist_ok=True)
    # stale results must never be measurable after a failed run
    for old in os.listdir(out):
        if old == "verify_report.json" or old.endswith(".INVALID.png") or old in {"%s.png" % v["name"] for v in (vs or [])}:
            os.remove(os.path.join(out, old))
    args = {"frames": frames, "size": list(size), "out_dir": out, "views": vs or []}
    args.update(extra_args or {})
    if scene:
        args["scene"] = scene
    elif builder:
        args["builder"] = builder
    else:
        raise gg_godot.Refused("give --scene or --builder")
    r = run(project, "capture", args, render=True, renderer=renderer, size=size, timeout=timeout, strict_warnings=strict_warnings)
    # rename images from invalid runs so nothing downstream can measure them
    if r.code not in (0, 1):
        for v in vs or []:
            q = os.path.join(out, v["name"] + ".png")
            if os.path.exists(q):
                os.replace(q, os.path.join(out, v["name"] + ".INVALID.png"))
    rep = {"views": [], "warnings": list((r.result or {}).get("warnings", [])), "log": {"fatal": r.report["fatal"][:10], "warnings": r.report["warnings"][:10]},
           "engine": (r.result or {}).get("engine"), "exit": r.code, "why": r.why, "job_dir": r.job_dir}
    code = r.code
    if code == 0:
        want = (r.result or {}).get("engine", {}).get("rendering_method")
        if want and want != renderer:
            rep["why"] = "renderer mismatch: asked %s, engine used %s" % (renderer, want)
            code = 2
    if code == 0:
        tg = (targets or {}).get("targets", targets or {})
        hints = (targets or {}).get("fix_hints")
        for f in r.result["data"]["files"]:
            m = gg_metrics.measure(gg_metrics.load_rgb(f["path"]), block)
            fails = gg_metrics.hard_failures(m, size) + gg_metrics.compare_targets(m, tg, tol, hints)
            rep["views"].append({"name": f["name"], "png": f["path"], "metrics": m, "failures": fails})
            if fails:
                code = 1
        rep["exit"] = code
    with open(os.path.join(out, "verify_report.json"), "w") as fh:
        json.dump(rep, fh, indent=1)
    return code, rep


def print_report(rep):
    print("exit %d: %s" % (rep["exit"], rep["why"]))
    for w in rep.get("warnings", []):
        print("  WARNING (runner): %s" % w)
    for f in rep["log"]["fatal"]:
        print("  LOG %s line %d: %s" % (f["cls"], f["line_no"], f["text"]))
    for v in rep["views"]:
        m = v["metrics"]
        print("view %s -> %s" % (v["name"], v["png"]))
        print("  p5/p50/p95 %.3f/%.3f/%.3f  sat %.3f  clip_black %.4f clip_white %.4f  colors %d  flat %.3f" % (
            m["luma_p5"], m["luma_p50"], m["luma_p95"], m["sat_mean"], m["clip_black"], m["clip_white"], m["unique_colors"], m["flat_fraction"]))
        for f in v["failures"]:
            print("  FAIL %s=%s (%s of %s): %s" % (f["metric"], f["value"], f["direction"], f["range"], f["hint"]))


# ---------------------------------------------------------------- selftest

BUILDER = """extends RefCounted
func build(parent: Node, _ctx: Dictionary = {}) -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.5, 0.5, 0.5)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.3, 0.3, 0.3)
	env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	var we := WorldEnvironment.new()
	we.environment = env
	parent.add_child(we)
	var light := DirectionalLight3D.new()
	light.light_energy = %(LIGHT)s
	light.rotation_degrees = Vector3(-50, 30, 0)
	parent.add_child(light)
	var plane := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(10, 10)
	plane.mesh = pm
	var pmat := StandardMaterial3D.new()
	pmat.albedo_color = Color(0.5, 0.5, 0.5)
	plane.material_override = pmat
	parent.add_child(plane)
	var ball := MeshInstance3D.new()
	ball.mesh = SphereMesh.new()
	ball.position = Vector3(0, 0.5, 0)
	var bmat := StandardMaterial3D.new()
	bmat.albedo_color = Color(%(ALBEDO)s)
	ball.material_override = bmat
	parent.add_child(ball)
%(EXTRA)s
"""
VIEW = {"name": "main", "kind": "3d", "position": [0, 0.9, 1.9], "look_at": [0, 0.5, 0], "fov": 50}
QUAD = """	var q := MeshInstance3D.new()
	var qm := QuadMesh.new()
	qm.size = Vector2(60, 60)
	q.mesh = qm
	q.position = Vector3(0, 0, -3)
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.albedo_color = Color8(128, 64, 200)
	q.material_override = m
	parent.add_child(q)
"""
BAD_SHADER = """	var s := Shader.new()
	s.code = "shader_type spatial; void fragment() { ALBEDO = vec3(not_defined); }"
	var bm := ShaderMaterial.new()
	bm.shader = s
	var b := MeshInstance3D.new()
	b.mesh = BoxMesh.new()
	b.position = Vector3(0, 0.5, 0)
	b.material_override = bm
	parent.add_child(b)
"""
OFF_TREE = "\tvar loner := Node3D.new()\n\tloner.look_at(Vector3(1, 1, 1))\n\tloner.free()\n"
SYNTAX_ERROR = "extends RefCounted\nfunc build(parent: Node) -> void:\n\tvar x = = 3\n"


def _builder(light=1.0, albedo="0.5, 0.5, 0.5", extra="\tpass"):
    return BUILDER % {"LIGHT": light, "ALBEDO": albedo, "EXTRA": extra}


def selftest(work=None, renderer="forward_plus", run=gg_godot.run, keep=False, report_path=None):
    """Build a throwaway project and prove the loop sees brightness, tint, colour, and BROKEN things. -> (code, report)."""
    own = work is None
    work = os.path.abspath(work or tempfile.mkdtemp(prefix="gg_selftest_"))
    os.makedirs(work, exist_ok=True)
    proj = os.path.join(work, "proj")
    os.makedirs(os.path.join(proj, "st"), exist_ok=True)
    with open(os.path.join(proj, "project.godot"), "w") as f:
        f.write('config_version=5\n[application]\nconfig/name="gg_selftest"\n[rendering]\nrenderer/rendering_method="%s"\n' % renderer)
    gg_godot.install_runtime(proj)
    steps = []
    state = {}

    def cap(name, gd, view=None, timeout=120, scene=None):
        out = os.path.join(work, "out_" + name)
        if gd is not None:
            with open(os.path.join(proj, "st", name + ".gd"), "w") as f:
                f.write(gd)
        code, rep = shot(proj, scene=scene, builder=None if scene else "res://st/%s.gd" % name, out=out, views=[view or VIEW],
                         renderer=renderer, frames=4, timeout=timeout, run=run, require_selftest=False)
        return code, rep, os.path.join(out, "main.png")

    def img(path):
        rgb = gg_metrics.load_rgb(path)
        m = gg_metrics.measure(rgb)
        m["_rgb"] = rgb
        return m

    def step(n, name, proves, fn):
        try:
            ok, detail = fn()
        except Exception as e:  # a crashed step is a failed step, never a crashed selftest
            ok, detail = False, "exception %s: %s" % (type(e).__name__, e)
        steps.append({"n": n, "name": name, "proves": proves, "ok": bool(ok), "detail": detail})
        print("  [%s] %d %s: %s" % ("ok" if ok else "FAIL", n, name, detail))

    def s1():
        c, rep, p = cap("base", _builder())
        if c != 0:
            return False, "exit %d: %s" % (c, rep["why"])
        state["base"] = img(p)
        state["godot_version"] = (rep["engine"] or {}).get("version")
        state["adapter"] = (rep["engine"] or {}).get("adapter")
        return state["base"]["luma_std"] > 0.02, "luma_std %.3f p50 %.3f engine %s" % (state["base"]["luma_std"], state["base"]["luma_p50"], (rep["engine"] or {}).get("adapter"))
    step(1, "baseline shot", "real pixels", s1)

    def s2():
        c, rep, p = cap("base2", _builder())
        b = img(p)
        d = float(abs(b["_rgb"].astype(int) - state["base"]["_rgb"].astype(int)).mean() / 255.0)
        state["noise_p50"] = abs(b["luma_p50"] - state["base"]["luma_p50"])
        return c == 0 and d <= 0.004 and state["noise_p50"] <= 0.01, "mean diff %.5f, p50 noise %.4f" % (d, state["noise_p50"])
    step(2, "repeat shot is identical", "noise floor", s2)

    def s3():
        c, rep, p = cap("bright", _builder(light=2.0))
        ok, d = gg_metrics.compare_images(state["base"], img(p), "brighter", 0.08)
        return c == 0 and ok, d
    step(3, "light x2 reads brighter", "sees brightness", s3)

    def s4():
        c, rep, p = cap("tint", _builder(albedo="0.8, 0.1, 0.1"))
        n = img(p)
        ok, d = gg_metrics.compare_images(state["base"], n, "tint-r", 0.05)
        return c == 0 and ok, d
    step(4, "red albedo reads tint-r", "sees tint", s4)

    def s5():
        c, rep, p = cap("ident", _builder(extra=QUAD), view={"name": "main", "kind": "3d", "position": [0, 0, 0], "look_at": [0, 0, -1], "fov": 60})
        rgb = gg_metrics.load_rgb(p)
        h, w, _ = rgb.shape
        px = [int(v) for v in rgb[h // 2, w // 2]]
        delta = max(abs(a - b) for a, b in zip(px, (128, 64, 200)))
        state["colour_identity_delta"] = delta
        return c == 1 and {f["metric"] for f in rep["views"][0]["failures"]} == {"luma_std"} and delta <= 3, "(exit %d: a flat frame trips only the blank-frame check, expected) centre pixel %s vs (128, 64, 200): max delta %d" % (c, px, delta)
    step(5, "unshaded colour round trip", "colour pipeline identity", s5)

    def blind(name, gd, cls, want_codes=(3,)):
        def f():
            c, rep, _ = cap(name, gd)
            classes = sorted({x["cls"] for x in rep["log"]["fatal"]})
            if c in want_codes and (cls is None or cls in classes):
                return True, "exit %d, classes %s" % (c, classes)
            return False, "verify loop is BLIND to %s: exit %d classes %s why %s" % (cls, c, classes, rep["why"])
        return f
    step(6, "broken shader", "sees shader errors", blind("badshader", _builder(extra=BAD_SHADER), "shader_error"))
    step(7, "script syntax error", "sees script errors", blind("badscript", SYNTAX_ERROR, "script_error"))
    step(8, "look_at off the tree (engine exits 0)", "scans the log, not the exit code", blind("offtree", _builder(extra=OFF_TREE), "engine_error"))

    def s9():
        import time
        t = time.time()
        r = run(proj, "hang", {}, render=False, timeout=10)
        dt = time.time() - t
        return r.code == 4 and (r.why.startswith("timeout") or r.why.startswith("no verdict")) and dt < 20, "exit %d after %.1fs: %s" % (r.code, dt, r.why[:100])
    step(9, "hang op", "timeout gives exit 4", s9)

    def s10():
        c, rep, _ = cap("missing", None, scene="res://missing.tscn")
        return c == 3 and "missing.tscn" in json.dumps(rep), "exit %d: %s" % (c, rep["why"][:120])
    step(10, "missing scene", "sees missing resources", s10)

    passed = all(s["ok"] for s in steps)
    rep = {"schema": 1, "pass": passed, "renderer": renderer, "godot": gg_godot.find_godot(), "frames_per_shot": 4,
           "date": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "noise_p50": state.get("noise_p50"), "colour_identity_delta": state.get("colour_identity_delta"), "steps": steps}
    rep["godot_version"] = state.get("godot_version")
    rep["adapter"] = state.get("adapter")
    path = report_path or os.path.join(STATE_DIR, "selftest_%s.json" % renderer)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(rep, f, indent=1)
    rep["report_path"] = path
    if own and not keep:
        shutil.rmtree(work, ignore_errors=True)
    return (0 if passed else 1), rep


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("shot")
    s.add_argument("--project", required=True)
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--scene")
    g.add_argument("--builder")
    s.add_argument("--out", required=True)
    s.add_argument("--view", action="append", help="view JSON, e.g. '{\"name\":\"hero\",\"kind\":\"3d\",\"position\":[0,2,6],\"look_at\":[0,1,0]}' (repeatable)")
    s.add_argument("--views-file", help="JSON file with a list of views (avoids shell quoting)")
    s.add_argument("--size", default="1280x720")
    s.add_argument("--frames", type=int, default=8)
    s.add_argument("--renderer", default="forward_plus")
    s.add_argument("--targets")
    s.add_argument("--tol", type=float, default=0.01)
    s.add_argument("--block", type=int)
    s.add_argument("--strict-warnings", action="store_true")
    s.add_argument("--timeout", type=int, default=180)
    s.add_argument("--json", action="store_true")
    m = sub.add_parser("measure")
    m.add_argument("image")
    m.add_argument("--targets")
    m.add_argument("--block", type=int)
    c = sub.add_parser("compare")
    c.add_argument("a")
    c.add_argument("b")
    c.add_argument("--expect", required=True)
    c.add_argument("--min-delta", type=float, default=0.05)
    lg = sub.add_parser("log")
    lg.add_argument("file")
    lg.add_argument("--strict-warnings", action="store_true")
    st = sub.add_parser("selftest")
    st.add_argument("--work")
    st.add_argument("--renderer", action="append")
    st.add_argument("--report")
    st.add_argument("--keep", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "shot":
            tg = json.load(open(a.targets)) if a.targets else None
            views = [json.loads(v) for v in a.view] if a.view else (json.load(open(a.views_file)) if a.views_file else None)
            code, rep = shot(a.project, a.scene, a.builder, a.out, views, _size(a.size), a.frames, a.renderer, tg, a.tol,
                             a.strict_warnings, a.timeout, block=a.block)
            if a.json:
                print(json.dumps(rep, indent=1))
            else:
                print_report(rep)
            return code
        if a.cmd == "measure":
            return gg_metrics.main([a.image] + (["--targets", a.targets] if a.targets else []) + (["--block", str(a.block)] if a.block else []))
        if a.cmd == "compare":
            if os.path.abspath(a.a) == os.path.abspath(a.b):
                raise gg_metrics.Refused("A and B are the same file: %s" % a.a)
            ia, ib = (gg_metrics.load_rgb(x) for x in (a.a, a.b))
            ma, mb = gg_metrics.measure(ia), gg_metrics.measure(ib)
            ma["_rgb"], mb["_rgb"] = ia, ib
            ok, detail = gg_metrics.compare_images(ma, mb, a.expect, a.min_delta)
            print("%s expect=%s: %s" % ("PASS" if ok else "FAIL", a.expect, detail))
            return 0 if ok else 1
        if a.cmd == "log":
            return gg_log.main([a.file] + (["--strict-warnings"] if a.strict_warnings else []))
        if a.cmd == "selftest":
            worst = 0
            for r in a.renderer or ["forward_plus", "gl_compatibility"]:
                print("selftest renderer=%s" % r)
                rp = (a.report.replace(".json", "_%s.json" % r) if a.report and len(a.renderer or [1, 2]) > 1 else a.report)
                code, rep = selftest(a.work, r, keep=a.keep, report_path=rp)
                print("selftest %s: %s (report %s)" % (r, "PASS" if code == 0 else "FAIL", rep["report_path"]))
                worst = max(worst, code)
            return worst
    except (gg_godot.Refused, gg_metrics.Refused, OSError, ValueError) as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2
    except Exception as e:  # a bug here must never read as "check failed" (1)
        print("internal error (exit 4, no verdict): %s: %s" % (type(e).__name__, e), file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
