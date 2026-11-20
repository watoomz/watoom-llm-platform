#!/usr/bin/env python3
"""Destructible props for a first-person shooter (T-0066): pre-fractured models that break under the gg_combat gun.

  gg_destruction.py init     --project P [--force]                       copy the test wall (4 x 0.4 x 3 m, 24 pieces) to
                                                                         res://assets/destruction/test_wall.glb
  gg_destruction.py fracture --source MESH --out P/assets/destruction/NAME.glb [--pieces 24] [--seed 1] [--focus X Y Z]
                                                                         run blender-simulation/scripts/fracture.py (Blender,
                                                                         headless): Intact + Piece_NNN, volume-checked
  gg_destruction.py check    --project P [--model res://...glb] [--max-health 100] [--damage 40] [--timeout 120]
                                                                         ops/destruction_check.gd: real gun raycasts break it
                                                                         into RigidBody3D pieces with no jump; they fall, are
                                                                         pushed away from the shot, stay on the floor, settle,
                                                                         and the same ray then passes where the wall stood.
  gg_destruction.py fps      --project P [--wall res://...glb] [--gun res://...glb] [--magazine 6] [--timeout 120]
                                                                         ops/fps_check.gd: the first-person player
                                                                         (player_3d + camera_rig + game/fps_weapon.gd) driven by
                                                                         REAL input: mouse look/clamp, fire rate, magazine, auto
                                                                         reload from the reserve, recoil up and back, shots break
                                                                         the wall, a mouse turn aims at and hurts a dummy.
  gg_destruction.py range    --project P [--wall res://...glb] [--gun res://...glb] [--level fps_range] [--distances 6 10 14]
                                                                         build res://levels/<level>/<level>.tscn: a playable
                                                                         first-person range (player + gun + breakable walls);
                                                                         look at it with gg_verify.py shot --scene ...

Godot 4 has no runtime fracture (no Chaos/Nanite equivalent), so the pieces are made offline and the runtime
(addons/gg/game/destructible.gd, installed by gg_project.py sync-runtime) swaps them in when the prop's CombatComponent
health reaches 0. Read references/gg-destruction.md. Exit codes (shared with the other gg_* stages):
0 pass | 1 a check failed | 2 refused | 3 fatal engine log line | 4 no verdict | 5 runner failure.
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
import gg_godot  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "destruction_test_wall.glb")
TEST_MODEL = "res://assets/destruction/test_wall.glb"
FRACTURE = os.path.normpath(os.path.join(HERE, "..", "..", "blender-simulation", "scripts", "fracture.py"))


def find_blender():
    """GG_BLENDER, else the newest /data/ai/toolchains/blender/<v>/*/blender, else blender on PATH."""
    if os.environ.get("GG_BLENDER"):
        return os.environ["GG_BLENDER"]
    found = sorted(glob.glob("/data/ai/toolchains/blender/*/*/blender"))
    return found[-1] if found else shutil.which("blender")


def check_project(project):
    if not os.path.isfile(os.path.join(project, "project.godot")):
        raise gg_godot.Refused("%s has no project.godot: run an init stage first" % project)
    if not os.path.isfile(os.path.join(project, "addons", "gg", "game", "destructible.gd")):
        raise gg_godot.Refused("%s has no addons/gg/game/destructible.gd: run gg_project.py sync-runtime first" % project)


def init(a):
    project = os.path.abspath(a.project)
    check_project(project)
    dest = os.path.join(project, "assets", "destruction", "test_wall.glb")
    if os.path.exists(dest) and not a.force:
        raise gg_godot.Refused("%s already exists (pass --force to overwrite)" % dest)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copyfile(FIXTURE, dest)
    print("gg_destruction init: wrote %s (%s); run `gg_destruction.py check --project %s`" % (dest, TEST_MODEL, project))
    return 0


def fracture(a):
    blender = find_blender()
    if not blender:
        raise gg_godot.Refused("blender not found (set GG_BLENDER)")
    if not os.path.isfile(a.source):
        raise gg_godot.Refused("--source %s does not exist" % a.source)
    if not a.out.endswith(".glb"):
        raise gg_godot.Refused("--out must be a .glb")
    argv = [blender, "-b", "--factory-startup", "-P", FRACTURE, "--", "--source", os.path.abspath(a.source),
            "--pieces", str(a.pieces), "--seed", str(a.seed), "--out", os.path.abspath(a.out)]
    if a.focus:
        argv += ["--focus"] + [str(v) for v in a.focus]
    p = subprocess.run(argv, capture_output=True, text=True, timeout=a.timeout)
    line = next((l for l in p.stdout.splitlines() if l.startswith("@@JSON@@")), None)
    if not line:
        print("gg_destruction fracture: no result from blender (exit %d): %s" % (p.returncode, (p.stderr or p.stdout)[-400:]))
        return 5
    r = json.loads(line[len("@@JSON@@"):])
    print(json.dumps({k: r.get(k) for k in ("ok", "pieces", "volume_ratio", "intact_volume", "smallest_piece", "warning", "error") if k in r}))
    if not r.get("ok"):
        return 1
    return 1 if r.get("warning") else 0


def check(a):
    project = os.path.abspath(a.project)
    check_project(project)
    r = gg_godot.run(project, "destruction_check", {"model": a.model, "max_health": a.max_health, "damage": a.damage},
                     render=False, timeout=a.timeout)
    d = (r.result or {}).get("data") or {}
    if r.code not in (0, 1, 5) or not d.get("checks"):
        print("gg_destruction check: exit %d: %s (job %s)" % (r.code, r.why or (r.result or {}).get("error"), r.job_dir))
        return r.code if r.code else 1
    for row in d["checks"]:
        print("  [%s] %s: %s" % ("ok" if row["ok"] else "FAIL", row["name"], row["detail"]))
    ok = all(row["ok"] for row in d["checks"])
    print("gg_destruction check: %s: %d check(s), %d piece(s) (job %s)" % ("PASS" if ok else "FAIL", len(d["checks"]), d.get("pieces", 0), r.job_dir))
    return 0 if ok else 1


def fps(a):
    project = os.path.abspath(a.project)
    check_project(project)
    args = {"wall": a.wall, "magazine": a.magazine, "fire_rate": a.fire_rate, "damage": a.damage, "wall_health": a.wall_health}
    if a.gun:
        args["gun"] = a.gun
    r = gg_godot.run(project, "fps_check", args, render=False, timeout=a.timeout)
    d = (r.result or {}).get("data") or {}
    if r.code not in (0, 1, 5) or not d.get("checks"):
        print("gg_destruction fps: exit %d: %s (job %s)" % (r.code, r.why or (r.result or {}).get("error"), r.job_dir))
        return r.code if r.code else 1
    for row in d["checks"]:
        print("  [%s] %s: %s" % ("ok" if row["ok"] else "FAIL", row["name"], row["detail"]))
    ok = all(row["ok"] for row in d["checks"])
    print("gg_destruction fps: %s: %d check(s) (job %s)" % ("PASS" if ok else "FAIL", len(d["checks"]), r.job_dir))
    return 0 if ok else 1


def range_(a):
    project = os.path.abspath(a.project)
    check_project(project)
    args = {"level": a.level, "wall": a.wall, "distances": a.distances, "wall_health": a.wall_health,
            "gun_rotation": a.gun_rotation, "gun_scale": a.gun_scale}
    if a.gun_offset:
        args["gun_offset"] = a.gun_offset
    if a.gun:
        args["gun"] = a.gun
    r = gg_godot.run(project, "build_fps_range", args, render=False, timeout=a.timeout)
    d = (r.result or {}).get("data") or {}
    if r.code != 0 or not d.get("scene"):
        print("gg_destruction range: exit %d: %s (job %s)" % (r.code or 1, r.why or (r.result or {}).get("error"), r.job_dir))
        return r.code or 1
    print("gg_destruction range: built %s (%d nodes, walls %s); see it: gg_verify.py shot --project %s --scene %s --out DIR "
          "--view '{\"name\":\"eye\",\"kind\":\"3d\",\"position\":[0,1.6,0],\"look_at\":[0,1.4,-10]}'"
          % (d["scene"], d["nodes"], ", ".join(d["walls"]), project, d["scene"]))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("init")
    p.add_argument("--project", required=True)
    p.add_argument("--force", action="store_true")
    p = sp.add_parser("fracture")
    p.add_argument("--source", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--pieces", type=int, default=24)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--focus", nargs=3, type=float, default=None)
    p.add_argument("--timeout", type=int, default=600)
    p = sp.add_parser("check")
    p.add_argument("--project", required=True)
    p.add_argument("--model", default=TEST_MODEL)
    p.add_argument("--max-health", type=float, default=100.0)
    p.add_argument("--damage", type=float, default=40.0)
    p.add_argument("--timeout", type=int, default=120)
    p = sp.add_parser("fps")
    p.add_argument("--project", required=True)
    p.add_argument("--wall", default=TEST_MODEL)
    p.add_argument("--gun", default=None, help="res:// glb of the gun model (optional: the checks do not need one)")
    p.add_argument("--magazine", type=int, default=6)
    p.add_argument("--fire-rate", type=float, default=8.0)
    p.add_argument("--damage", type=float, default=25.0)
    p.add_argument("--wall-health", type=float, default=100.0)
    p.add_argument("--timeout", type=int, default=120)
    p = sp.add_parser("range")
    p.add_argument("--project", required=True)
    p.add_argument("--level", default="fps_range")
    p.add_argument("--wall", default=TEST_MODEL)
    p.add_argument("--gun", default=None)
    p.add_argument("--distances", nargs="+", type=float, default=[6.0, 10.0, 14.0])
    p.add_argument("--gun-rotation", nargs=3, type=float, default=[0.0, 0.0, 0.0], metavar=("X", "Y", "Z"),
                   help="degrees: turn the gun model so its barrel points -Z (the owned AK-47 glb: 0 90 0)")
    p.add_argument("--gun-scale", type=float, default=1.0)
    p.add_argument("--gun-offset", nargs=3, type=float, default=None, metavar=("X", "Y", "Z"),
                   help="metres in camera space (default 0.22 -0.2 -0.45; the owned AK-47 glb: 0.2 -0.25 -0.58)")
    p.add_argument("--wall-health", type=float, default=100.0)
    p.add_argument("--timeout", type=int, default=120)
    a = ap.parse_args(argv)
    try:
        return {"init": init, "fracture": fracture, "check": check, "fps": fps, "range": range_}[a.cmd](a)
    except gg_godot.Refused as e:
        print("gg_destruction %s: refused: %s" % (a.cmd, e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
