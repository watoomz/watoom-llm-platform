#!/usr/bin/env python3
"""Measure how bright a level looks from several horizon views, optionally for several locked exposure values (any game).

  ue_look_probe.py --out-dir DIR [--at X Y Z] [--yaws 0 90 180 270] [--pitch -8]
  ue_look_probe.py --out-dir DIR --sweep-exposure 0.3 0.45 0.6 --post-process LABEL [--target 105]

Captures the owner's current view (unmoved) plus one view per yaw from --at (default: the current camera position) with
ue_viewport_shot.capture(), then puts the owner's camera back. For each picture it prints the mean sRGB luminance of the lower 45%
(the ground) and the clipped share of the top quarter (the sky). With --sweep-exposure it locks the PostProcessVolume's auto
exposure (Min = Max, via level.set_post_process_settings with enableOverrides) at each value in turn, captures the set, and
afterwards RESTORES the original Min/Max values and their override flags; it then names the value whose ground mean is closest to
--target. Nothing is saved.

Why (T-0027, 2026-11-18): "too bright" on the test game was auto exposure pinned at its brightest allowed value in every view,
which only a measurement across views showed (0.3 -> ground 135, 0.45 -> ~105, 0.6 -> 86; higher = darker). The right value is
different for every game's lights, so measure it here and put it in the profile's `exposure` key for unreal_atmosphere.py.
Views facing the sun read darker (backlit); judge the level on the non-backlit views and look at the pictures too.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "ansible", "roles", "watoom-code", "files", "skills", "watoom-texture-layering", "scripts"))
import ue_route  # noqa: E402
import ue_project  # noqa: E402

PP_KEYS = ("AutoExposureMinBrightness", "AutoExposureMaxBrightness")


def metrics(path):
    """-> {"ground": mean luminance of the lower 45%, "ground_p95", "sky_clip_pct": % of the top quarter at >= 250}."""
    import numpy as np
    from PIL import Image
    a = np.asarray(Image.open(path).convert("RGB")).astype(float)
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    h = lum.shape[0]
    g, s = lum[int(0.55 * h):], lum[:h // 4]
    return {"ground": round(float(g.mean()), 1), "ground_p95": round(float(np.percentile(g, 95)), 1),
            "sky_clip_pct": round(100.0 * float((s >= 250).mean()), 1)}


def summary(per_view):
    """per_view {name: metrics} -> (mean ground over views, spread max-min)."""
    gs = [m["ground"] for m in per_view.values()]
    return (round(sum(gs) / len(gs), 1), round(max(gs) - min(gs), 1)) if gs else (None, None)


def closest(results, target):
    """results {value: (mean, spread)} -> the value whose mean is nearest target."""
    return min((v for v in results if results[v][0] is not None), key=lambda v: abs(results[v][0] - target))


def probe_set(shoot, out_dir, tag, at, yaws, pitch):
    views = [("owner", None)] + [("y%g" % y, (at[0], at[1], at[2], pitch, y)) for y in yaws]
    per = {}
    for name, cam in views:
        path = os.path.join(out_dir, "%s_%s.png" % (tag, name))
        try:
            shoot(path, cam)
            per[name] = metrics(path)
        except SystemExit as e:
            print("FAILED %s %s: %s" % (tag, name, e))
    return per


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--at", nargs=3, type=float, metavar=("X", "Y", "Z"), help="camera position for the yaw views (default: current)")
    ap.add_argument("--yaws", nargs="+", type=float, default=[0, 90, 180, 270])
    ap.add_argument("--pitch", type=float, default=-8.0)
    ap.add_argument("--sweep-exposure", nargs="+", type=float, metavar="E")
    ap.add_argument("--post-process", help="PostProcessVolume label for --sweep-exposure (default: profile post_process_label)")
    ap.add_argument("--target", type=float, default=105.0, help="wanted ground mean luminance (the test game settled on ~105)")
    ap.add_argument("--host", default="10.99.1.44")
    ap.add_argument("--port", type=int, default=2224)
    ap.add_argument("--user", default="uemcp")
    ap.add_argument("--key-dir", default=ue_route.DEFAULT_KEY_DIR)
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    import ue_viewport_shot as vs
    os.makedirs(a.out_dir, exist_ok=True)
    pp = a.post_process or ue_project.get("post_process_label")
    if a.sweep_exposure and not pp:
        ap.error("--sweep-exposure needs --post-process (or post_process_label in the profile)")

    def call(cat, meth, args):
        t = ue_route.SshTransport(ue_route.ssh_command(a.host, a.port, a.user, a.key_dir))
        try:
            r = t.call(cat, meth, args, 120)
        finally:
            t.close()
        if ue_route.reply_failed(r, getattr(t, "is_error", False)):
            raise SystemExit("FAILED %s.%s: %s" % (cat, meth, r[:300]))
        return json.loads(r[r.index("{"):])

    state = call("editor", "get_viewport_state", {})
    at = a.at or (state["location"]["x"], state["location"]["y"], state["location"]["z"])
    shoot = lambda path, cam: vs.capture(path, cam)  # noqa: E731
    original = None
    results = {}
    try:
        if a.sweep_exposure:
            path = call("level", "get_actor_details", {"actorLabel": pp})["path"]
            original = {}
            for k in PP_KEYS:
                for prop in ("Settings." + k, "Settings.bOverride_" + k):
                    original[prop] = call("editor", "get_property", {"objectPath": path, "propertyName": prop})["value"]
            for e in a.sweep_exposure:
                call("level", "set_post_process_settings", {"actorLabel": pp, "enableOverrides": True,
                                                            "settings": {k: e for k in PP_KEYS}})
                per = probe_set(shoot, a.out_dir, "exp%g" % e, at, a.yaws, a.pitch)
                results[e] = summary(per)
                for n, m in per.items():
                    print("exposure %-5g %-6s ground %6.1f p95 %6.1f sky clipped %5.1f%%" % (e, n, m["ground"], m["ground_p95"], m["sky_clip_pct"]))
        else:
            per = probe_set(shoot, a.out_dir, "now", at, a.yaws, a.pitch)
            results["now"] = summary(per)
            for n, m in per.items():
                print("%-6s ground %6.1f p95 %6.1f sky clipped %5.1f%%" % (n, m["ground"], m["ground_p95"], m["sky_clip_pct"]))
    finally:
        if original is not None:
            for prop, v in original.items():
                call("editor", "set_property", {"objectPath": path, "propertyName": prop, "value": v})
        call("editor", "set_viewport", {"location": state["location"], "rotation": state["rotation"]})
    for k, (mean, spread) in results.items():
        print("%s: ground mean %s over the views, spread %s" % (k, mean, spread))
    if a.sweep_exposure:
        best = closest(results, a.target)
        print("closest to target %g: exposure %g (original values restored; put it in the profile's `exposure`)" % (a.target, best))
    return 0


if __name__ == "__main__":
    sys.exit(main())
