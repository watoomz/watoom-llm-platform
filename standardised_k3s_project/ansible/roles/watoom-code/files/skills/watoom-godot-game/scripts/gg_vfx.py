#!/usr/bin/env python3
"""GPUParticles3D VFX from small recipes (T-0069, part of T-0065), the Godot equivalent of watoom-unreal-
combat's Niagara generator (unreal_niagara_fx.py): the same recipe names (projectile, impact, muzzle, aura)
and the same per-damage-type HDR colour table, built from Godot's own particle material instead of copying
an engine template asset.

  gg_vfx.py check --project P --spec fx.json [--timeout 60]

spec: {"fx": {"Fireball_Trail":  {"recipe": "projectile", "element": "Fire"},
              "Fireball_Impact": {"recipe": "impact", "element": "Fire", "scale": 1.5},
              "Frost_Nova":      {"recipe": "aura", "element": "Frost", "radius": 4.0}}}
(same shape CombatComponent effects use for "element"/damage_type, so a weapon/spell spec's VfxRecipe field
can point at one of these names directly). `check` renders each recipe for real (a live GPUParticles3D in a
real scene with a real Camera3D) and verifies it actually draws non-flat pixels, not a blank/invisible
particle system -- see runtime/ops/vfx_check.gd and runtime/game/vfx.gd for what each recipe configures.
Exit codes (shared with the other gg_* stages): 0 pass | 1 a check failed | 2 refused | 3 fatal engine log
line | 4 no verdict | 5 runner failure.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
import gg_godot  # noqa: E402
import gg_verify  # noqa: E402

RENDERER = "gl_compatibility"      # same choice as gg_ui.py: the worker has no GPU, VFX is checked on software GL

DEFAULT_SPEC = {
    "fx": {
        "demo_projectile": {"recipe": "projectile", "element": "Fire"},
        "demo_impact": {"recipe": "impact", "element": "Frost"},
        "demo_muzzle": {"recipe": "muzzle", "element": "Lightning"},
        "demo_aura": {"recipe": "aura", "element": "Holy", "radius": 2.0},
    }
}


def check_project(project):
    if not os.path.isfile(os.path.join(project, "project.godot")):
        raise gg_godot.Refused("%s has no project.godot: run an init stage (e.g. gg_ui.py init / gg_player.py init) first" % project)
    if not os.path.isfile(os.path.join(project, "addons", "gg", "game", "vfx.gd")):
        raise gg_godot.Refused("%s has no addons/gg/game/vfx.gd: run gg_project.py sync-runtime first" % project)


def check(a):
    project = os.path.abspath(a.project)
    check_project(project)
    if a.spec:
        with open(a.spec) as f:
            spec = json.load(f)
    else:
        spec = DEFAULT_SPEC
    if not spec.get("fx"):
        raise gg_godot.Refused("spec has no 'fx' entries")
    msg = gg_verify.selftest_gate(RENDERER)
    if msg:
        raise gg_godot.Refused(msg)
    r = gg_godot.run(project, "vfx_check", {"fx": spec["fx"]}, render=True, renderer=RENDERER, timeout=a.timeout)
    d = (r.result or {}).get("data") or {}
    if r.code not in (0, 1, 5) or not d:
        print("gg_vfx check: exit %d: %s (job %s)" % (r.code, r.why, r.job_dir))
        return r.code
    for row in d["checks"]:
        print("  [%s] %s: %s" % ("ok" if row["ok"] else "FAIL", row["name"], row["detail"]))
    ok = all(row["ok"] for row in d["checks"])
    print("gg_vfx check: %s: %d recipe(s) (job %s)" % ("PASS" if ok else "FAIL", len(d["checks"]), r.job_dir))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check")
    p.add_argument("--project", required=True)
    p.add_argument("--spec", default=None, help="path to a {\"fx\": {...}} JSON spec; omit to use a small built-in demo spec (one of each recipe)")
    p.add_argument("--timeout", type=int, default=60)
    a = ap.parse_args(argv)
    try:
        return {"check": check}[a.cmd](a)
    except gg_godot.Refused as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
