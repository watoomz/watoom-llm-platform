#!/usr/bin/env python3
"""Player, camera and a smoke test that RUNS the level (3D). 2D players are not built yet.

  gg_player.py init   --project P [--force] [--dry-run]    write the `player` and `camera` sections into gg_project.json (from dimension + view)
  gg_player.py build  --project P [--dry-run]              validate, choose the start by RULE, build colliders + player + level, probe the collider
  gg_player.py smoke  --project P [--walk-s 3] [--out DIR] RUN the level with scripted input; exit 0 only if every check below passes
  gg_player.py status --project P                          what changed since the last passing build / smoke

Start position is a rule (player.start), never typed coordinates by default. The smoke script (60 physics ticks per second): settle 1 s, walk forward, turn 90 degrees
with the mouse (a 3D body) or step sideways (top_down / isometric), walk, jump, land. Verdicts are computed from the per-tick trace against the height data, not
against the physics collider they test. Checks: C0 tick count, C1 settles on the floor, C2 never falls through, C3 walked distance, C4 headings, C5 jump height,
C6 stays out of the water, C7 camera above ground, C8 the start and end pictures show something and differ, C10 every scripted input reached the player.
Exit codes: 0 pass | 1 check failed | 2 refused | 3 engine log fatal or warning | 4 no verdict | 5 runner failure.
"""
import argparse
import copy
import hashlib
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
import gg_catalog  # noqa: E402
import gg_godot  # noqa: E402
import gg_metrics  # noqa: E402
import gg_project  # noqa: E402
import gg_scatter  # noqa: E402
import gg_style  # noqa: E402
import gg_terrain  # noqa: E402

MODES = {"first_person": "first_person", "third_person": "third_person", "top_down": "top_down", "isometric": "isometric"}
PLAYER_RANGES = {"height_m": (0.5, 3.0), "radius_m": (0.15, 1.0), "speed_mps": (0.5, 20.0), "accel_mps2": (5.0, 200.0), "jump_height_m": (0.0, 5.0),
                 "gravity_mps2": (1.0, 50.0), "max_slope_deg": (10.0, 60.0)}
PLAYER_FIX = {"speed_mps": "set it to 3..8 for walking", "height_m": "a person is 1.6..2.0", "radius_m": "0.3..0.4 for a person", "accel_mps2": "20..60", "jump_height_m": "0 disables the jump; 0.8..1.5 is normal",
              "gravity_mps2": "9.8 is Earth", "max_slope_deg": "35..50"}
START_RANGES = {"min_above_sea_m": (0.0, 100.0), "max_slope": (0.02, 1.0), "min_water_m": (0.0, 200.0), "clear_m": (0.5, 20.0), "runway_m": (6.0, 100.0), "edge_margin_m": (0.0, 200.0)}
CAMERA_RANGES = {"eye_height_m": (0.2, 3.0), "fov_deg": (30.0, 110.0), "distance_m": (1.0, 60.0), "pitch_deg": (-89.0, 30.0), "near_m": (0.01, 1.0), "mouse_sens_deg_per_px": (0.01, 1.0),
                 "ortho_size_m": (2.0, 200.0)}
PLAYER_KEYS = set(PLAYER_RANGES) | {"controller", "start"}
START_KEYS = set(START_RANGES) | {"rule", "prefer", "face", "position_xz", "yaw_deg"}
CAMERA_KEYS = set(CAMERA_RANGES) | {"mode", "far_m", "collide", "turn_deg_per_s"}
SHOT_DIFF_MIN = 0.02          # mean absolute difference (0..1) between the start and end pictures; calibrated by the zero-input run (see references/gg-player.md)
SETTLE_TICKS = 60
MAX_SOLIDS = 5000


class Refused(gg_godot.Refused):
    pass


def default_sections(prof):
    view = prof["view"]
    cam_pitch = {"first_person": 0.0, "third_person": -15.0, "top_down": -60.0, "isometric": -35.0}.get(view, -15.0)
    diag = math.hypot(*prof["world"]["size_m"])
    player = {"controller": "walk_3d", "height_m": 1.8, "radius_m": 0.35, "speed_mps": 5.0, "accel_mps2": 40.0, "jump_height_m": 1.2, "gravity_mps2": 9.8, "max_slope_deg": 45.0,
              "start": {"rule": "auto", "min_above_sea_m": 1.0, "max_slope": 0.25, "min_water_m": 8.0, "clear_m": 2.0, "runway_m": 20.0, "edge_margin_m": 12.0, "prefer": "near_center", "face": "land"}}
    camera = {"mode": MODES[view], "eye_height_m": 1.6, "fov_deg": 75.0, "distance_m": 5.0 if view in ("third_person",) else 22.0 if view in ("top_down", "isometric") else 5.0,
              "pitch_deg": cam_pitch, "near_m": 0.05, "far_m": float(round(diag * 1.5)), "mouse_sens_deg_per_px": 0.15, "turn_deg_per_s": 120.0, "collide": True}
    if view == "isometric":
        camera["ortho_size_m"] = 24.0
    return player, camera


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def validate_player(prof):
    """-> [error lines]. Each names the key, the value and a fix."""
    errs = []
    if prof.get("dimension") != "3d":
        return ["player: 2D players are not built yet; this pipeline builds the 3D player (dimension must be 3d)"]
    p, c = prof.get("player"), prof.get("camera")
    if not isinstance(p, dict) or not isinstance(c, dict):
        return ["the profile has no player / camera sections: run gg_player.py init"]
    for k in set(p) - PLAYER_KEYS:
        errs.append("player.%s is not a key (valid: %s)" % (k, ", ".join(sorted(PLAYER_KEYS))))
    for k, (lo, hi) in PLAYER_RANGES.items():
        v = p.get(k)
        if not _num(v) or not lo <= v <= hi:
            errs.append("player.%s = %r is outside %s..%s: %s" % (k, v, lo, hi, PLAYER_FIX.get(k, "pick a value inside the range")))
    s = p.get("start")
    if not isinstance(s, dict):
        return errs + ["player.start must be an object"]
    for k in set(s) - START_KEYS:
        errs.append("player.start.%s is not a key (valid: %s)" % (k, ", ".join(sorted(START_KEYS))))
    for k, (lo, hi) in START_RANGES.items():
        if not _num(s.get(k)) or not lo <= s[k] <= hi:
            errs.append("player.start.%s = %r is outside %s..%s" % (k, s.get(k), lo, hi))
    if s.get("rule") not in ("auto", "fixed"):
        errs.append("player.start.rule = %r must be auto or fixed" % s.get("rule"))
    if s.get("prefer") not in ("near_center", "near_water"):
        errs.append("player.start.prefer = %r must be near_center or near_water" % s.get("prefer"))
    if s.get("face") not in ("land", "water", "uphill"):
        errs.append("player.start.face = %r must be land, water or uphill" % s.get("face"))
    if s.get("rule") == "fixed":
        xz = s.get("position_xz")
        if not (isinstance(xz, list) and len(xz) == 2 and all(_num(x) for x in xz)):
            errs.append("player.start.position_xz must be [x, z] in metres when rule is fixed")
        if not _num(s.get("yaw_deg")):
            errs.append("player.start.yaw_deg must be a number when rule is fixed")
    for k in set(c) - CAMERA_KEYS:
        errs.append("camera.%s is not a key (valid: %s)" % (k, ", ".join(sorted(CAMERA_KEYS))))
    if c.get("mode") not in MODES:
        errs.append("camera.mode = %r must be one of %s" % (c.get("mode"), sorted(MODES)))
    elif c["mode"] != MODES.get(prof.get("view")):
        errs.append("camera.mode = %s does not match the project view %s: change `view` in gg_project.json, or the camera mode" % (c["mode"], prof.get("view")))
    for k, (lo, hi) in CAMERA_RANGES.items():
        if k == "ortho_size_m" and c.get("mode") != "isometric":
            continue
        if not _num(c.get(k)) or not lo <= c[k] <= hi:
            errs.append("camera.%s = %r is outside %s..%s" % (k, c.get(k), lo, hi))
    if errs:
        return errs
    if c["eye_height_m"] >= p["height_m"]:
        errs.append("camera.eye_height_m = %s must be below player.height_m = %s (the eye is inside the body)" % (c["eye_height_m"], p["height_m"]))
    if p["radius_m"] > p["height_m"] / 2:
        errs.append("player.radius_m = %s is more than half of player.height_m = %s: a capsule needs height >= 2 x radius" % (p["radius_m"], p["height_m"]))
    if s["max_slope"] >= math.tan(math.radians(p["max_slope_deg"])):
        errs.append("player.start.max_slope = %s is not below tan(player.max_slope_deg = %s) = %.2f: the start would be on ground the player cannot stand on" % (s["max_slope"], p["max_slope_deg"], math.tan(math.radians(p["max_slope_deg"]))))
    diag = math.hypot(*prof["world"]["size_m"])
    if not _num(c.get("far_m")) or c["far_m"] < diag:
        errs.append("camera.far_m = %r is under the world diagonal %.0f m: the far end of the level would be cut off" % (c.get("far_m"), diag))
    half = min(prof["world"]["size_m"]) / 2
    if s["runway_m"] < 2.0 + 1.2 * p["speed_mps"]:
        errs.append("player.start.runway_m = %s is too short for player.speed_mps = %s: the 1 s minimum walk needs at least %.1f m" % (s["runway_m"], p["speed_mps"], 2.0 + 1.2 * p["speed_mps"]))
    if s["runway_m"] + s["edge_margin_m"] > half:
        errs.append("player.start.runway_m + edge_margin_m = %s is over half the smaller world side (%s m): lower them" % (s["runway_m"] + s["edge_margin_m"], half))
    return errs


# ---------------------------------------------------------------- start rule
def _dry_ok(world, x, z, sea_margin, max_slope, water_min):
    y = gg_scatter.ground_y(world.h, x, z, world.cell)
    return (y - world.sea >= sea_margin and gg_scatter.bilinear(world.slope, x, z, world.cell) <= max_slope
            and gg_scatter.bilinear(world.dist, x, z, world.cell) > water_min)


def yaw_of(dx, dz):
    """yaw 0 faces -Z, forward = (-sin yaw, 0, -cos yaw)."""
    return math.degrees(math.atan2(-dx, -dz))


LEG2_M = 7.0


def choose_start(world, start, solids, radius_m=0.35, world_rel=False):
    """solids: [[x, z, r]]. -> {position, yaw_deg, runway, runway_m, removed_by, candidates}. Raises Refused naming the rule that removed most.
    The forward leg is runway_m long (walk 1); the second leg (LEG2_M) starts 2 m before its end: 90 degrees to the right of the facing, or +X for world-relative cameras."""
    cell = world.cell
    nz, nx = world.h.shape
    sx, sz = (nx - 1) * cell, (nz - 1) * cell
    arr = np.array(solids, dtype=float).reshape(-1, 3)

    def solid_clear(x, z, extra):
        return arr.size == 0 or bool((np.hypot(arr[:, 0] - x, arr[:, 1] - z) - arr[:, 2] > extra).all())

    def leg(x, z, dx, dz, length):
        pts, mind = [], 1e9
        for d in range(1, int(length) + 1):
            px, pz = x + dx * d, z + dz * d
            if not (0 <= px <= sx and 0 <= pz <= sz):
                return None, 0.0
            if not _dry_ok(world, px, pz, 0.3, start["max_slope"], 0.5 * cell) or not solid_clear(px, pz, radius_m + 0.5):
                return None, 0.0
            mind = min(mind, gg_scatter.bilinear(world.dist, px, pz, cell))
            pts.append([round(px, 2), round(pz, 2)])
        return pts, mind

    def runway(x, z, yaw):
        """Forward leg, then the second leg from 2 m before its end."""
        dx, dz = -math.sin(math.radians(yaw)), -math.cos(math.radians(yaw))
        pts, mind = leg(x, z, dx, dz, start["runway_m"])
        if pts is None:
            return None, 0.0
        ex, ez = x + dx * (start["runway_m"] - 2), z + dz * (start["runway_m"] - 2)
        d2 = (1.0, 0.0) if world_rel else (-math.cos(math.radians(yaw)), math.sin(math.radians(yaw)))   # facing yaw-90 degrees (right of the facing)
        pts2, mind2 = leg(ex, ez, d2[0], d2[1], LEG2_M)
        if pts2 is None:
            return None, 0.0
        return pts, min(mind, mind2)

    if start["rule"] == "fixed":
        x, z = start["position_xz"]
        if not (0 <= x <= sx and 0 <= z <= sz):
            raise Refused("player.start.position_xz [%s, %s] is outside the world (0..%s, 0..%s)" % (x, z, sx, sz))
        y = gg_scatter.ground_y(world.h, x, z, cell)
        if y - world.sea < start["min_above_sea_m"]:
            raise Refused("player.start.position_xz [%s, %s] is %.1f m above the sea; the rule needs %s: move it or use rule auto" % (x, z, y - world.sea, start["min_above_sea_m"]))
        sl = gg_scatter.bilinear(world.slope, x, z, cell)
        if sl > start["max_slope"]:
            raise Refused("player.start.position_xz [%s, %s] has slope %.2f over max_slope %s" % (x, z, sl, start["max_slope"]))
        d = gg_scatter.bilinear(world.dist, x, z, cell)
        if d < start["min_water_m"]:
            raise Refused("player.start.position_xz [%s, %s] is %.1f m from water; the rule needs %s" % (x, z, d, start["min_water_m"]))
        if not solid_clear(x, z, start["clear_m"]):
            raise Refused("player.start.position_xz [%s, %s] is inside a tree or rock clearance of %s m" % (x, z, start["clear_m"]))
        return {"position": [round(float(x), 3), round(float(y), 3), round(float(z), 3)], "yaw_deg": float(start["yaw_deg"]), "runway": [], "runway_m": float(start["runway_m"]), "removed_by": {}, "candidates": 1}

    rel = world.h - world.sea
    yy, xx = np.mgrid[0:nz, 0:nx]
    removed, m = {}, np.ones(world.h.shape, bool)
    for name, ok in (("min_above_sea_m", rel >= start["min_above_sea_m"]), ("max_slope", world.slope <= start["max_slope"]), ("min_water_m", world.dist >= start["min_water_m"]),
                     ("edge_margin_m", (xx * cell >= start["edge_margin_m"]) & (xx * cell <= sx - start["edge_margin_m"]) & (yy * cell >= start["edge_margin_m"]) & (yy * cell <= sz - start["edge_margin_m"]))):
        removed[name] = int((m & ~ok).sum())
        m &= ok
    cells = np.argwhere(m)
    if not len(cells):
        top = max(removed.items(), key=lambda kv: kv[1])
        raise Refused("no dry, gentle ground for the start: the rule that removed most cells is player.start.%s (%d of %d cells); loosen it or reshape the terrain" % (top[0], top[1], world.h.size))
    centre = np.array([sz / 2, sx / 2])
    key = (lambda c: float(np.hypot(c[0] * cell - centre[0], c[1] * cell - centre[1]))) if start["prefer"] == "near_center" else (lambda c: float(world.dist[c[0], c[1]]))
    cells = sorted((tuple(c) for c in cells), key=key)
    tried = 0
    for j, i in cells[:600]:
        x, z = i * cell, j * cell
        if not solid_clear(x, z, start["clear_m"]):
            removed["clear_m"] = removed.get("clear_m", 0) + 1
            continue
        r = int(math.ceil(start["clear_m"] / cell))
        j0, j1, i0, i1 = max(0, j - r), min(nz, j + r + 1), max(0, i - r), min(nx, i + r + 1)
        if not (m[j0:j1, i0:i1].all() or ((world.slope[j0:j1, i0:i1] <= start["max_slope"]) & (rel[j0:j1, i0:i1] >= start["min_above_sea_m"] * 0.5)).all()):
            continue
        tried += 1
        best = None
        for yaw in ([0] if world_rel else range(0, 360, 22)):
            pts, mind = runway(x, z, float(yaw))
            if pts is None:
                continue
            if start["face"] == "land":
                score = mind
            elif start["face"] == "water":
                score = -mind
            else:
                score = gg_scatter.ground_y(world.h, pts[-1][0], pts[-1][1], cell) - gg_scatter.ground_y(world.h, x, z, cell)
            if best is None or score > best[0]:
                best = (score, float(yaw), pts)
        if best:
            y = gg_scatter.ground_y(world.h, x, z, cell)
            return {"position": [round(float(x), 3), round(float(y), 3), round(float(z), 3)], "yaw_deg": best[1], "runway": best[2], "runway_m": float(start["runway_m"]), "removed_by": removed, "candidates": tried}
    raise Refused("no candidate had a clear %.0f m runway (dry, under slope %s, %.1f m from trees and rocks): tried %d candidates; lower player.start.runway_m or clear_m, or scatter fewer trees" % (start["runway_m"], start["max_slope"], radius_m + 0.5, tried))


# ---------------------------------------------------------------- colliders
def solids_from_scatter(project, level, cat):
    """-> (shapes [[kind,x,y,z,r,h]], solids [[x,z,r]], counts). Trees: one cylinder each (r = 0.3 x scale, 4 m); rocks: box from 70% of the inspected size; the rest never collide."""
    sj = os.path.join(project, "gg_data", "scatter", "%s.json" % level)
    if not os.path.isfile(sj):
        return [], [], {}
    fams = json.load(open(sj))["families"]
    shapes, solids, counts = [], [], {}
    for name, d in fams.items():
        f = cat["families"].get(name)
        if not f or f["category"] not in ("tree_upland", "tree_riparian", "rock"):
            continue
        base = [1.0, 1.0, 1.0]
        ip = os.path.join(project, "gg_data", "catalog", name, "inspect.json")
        if f["category"] == "rock":
            if os.path.isfile(ip):
                sz = json.load(open(ip))["inspect"]["aabb"]["size"]
                base = [sz[0], sz[1], sz[2]]
            else:
                base = [1.6, 1.2, 1.6]
        for x, y, z, _yaw, sc in d["instances"]:
            if f["category"] == "rock":
                r, h = 0.7 * 0.5 * max(base[0], base[2]) * sc, 0.7 * base[1] * sc
                shapes.append(["box", x, y, z, round(r, 3), round(h, 3)])
            else:
                r, h = 0.3 * sc, 4.0
                shapes.append(["cyl", x, y, z, round(r, 3), h])
            solids.append([x, z, r])
        counts[name] = len(d["instances"])
    if len(shapes) > MAX_SOLIDS:
        big = max(counts.items(), key=lambda kv: kv[1])
        raise Refused("%d solid scatter instances is over the %d limit (largest family %s: %d): lower its count in gg_scatter.json" % (len(shapes), MAX_SOLIDS, big[0], big[1]))
    return shapes, solids, counts


# ---------------------------------------------------------------- stamps
def _sha_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.isfile(p) else None


def _sha_obj(o):
    return hashlib.sha256(json.dumps(o, sort_keys=True).encode()).hexdigest()


def _input_section(project):
    p = os.path.join(project, "project.godot")
    if not os.path.isfile(p):
        return None
    out, on = [], False
    for line in open(p).read().splitlines():
        if line.startswith("["):
            on = line.strip() == "[input]"
        elif on:
            out.append(line)
    return hashlib.sha256("\n".join(out).encode()).hexdigest()


def level_scenes(project, prof, heights_sha):
    """Scenes the level instances: terrain always; water and scatter only while their stamps hold; colliders when the scatter is included."""
    level, wd = prof["level"], gg_terrain.world_dir(project)
    scenes = ["res://levels/%s/terrain.tscn" % level]
    wok = os.path.join(wd, "water_ok.json")
    if os.path.isfile(wok) and json.load(open(wok)).get("heights_sha") == heights_sha:
        scenes.append("res://levels/%s/water.tscn" % level)
    if gg_scatter.stamp_valid(project, level, heights_sha):
        scenes += ["res://levels/%s/scatter.tscn" % level, "res://levels/%s/colliders.tscn" % level]
    return scenes


def player_hashes(project, prof):
    level = prof["level"]
    lv = os.path.join(project, "levels", level)
    wd = gg_terrain.world_dir(project)
    return {"terrain_scene": _sha_file(os.path.join(lv, "terrain.tscn")), "colliders_scene": _sha_file(os.path.join(lv, "colliders.tscn")),
            "player_scene": _sha_file(os.path.join(lv, "player.tscn")), "level_scene": _sha_file(os.path.join(lv, "level.tscn")),
            "start_json": _sha_file(os.path.join(wd, "start.json")), "profile_player_camera": _sha_obj([prof.get("player"), prof.get("camera"), prof.get("view")]),
            "water_dist": _sha_file(os.path.join(wd, "water_dist.f32")), "scatter_scene": _sha_file(os.path.join(lv, "scatter.tscn")),
            "runtime_lock": _sha_file(os.path.join(project, "addons", "gg", "runtime.lock.json")), "project_input": _input_section(project)}


def stamp_state(project, prof, name, heights_sha):
    """-> (valid, [changed hash names])."""
    p = os.path.join(gg_terrain.world_dir(project), name)
    if not os.path.isfile(p):
        return False, ["no %s" % name]
    try:
        st = json.load(open(p))
    except (OSError, json.JSONDecodeError):
        return False, ["%s unreadable" % name]
    if st.get("heights_sha") != heights_sha:
        return False, ["heights_sha"]
    have = player_hashes(project, prof)
    changed = [k for k in have if st.get("hashes", {}).get(k) != have[k]]
    return not changed, changed


# ---------------------------------------------------------------- build
def _write_profile(project, prof):
    p = os.path.join(project, "gg_project.json")
    with open(p + ".new", "w") as f:
        json.dump(prof, f, indent=2)
        f.write("\n")
    os.replace(p + ".new", p)


def init(project, force=False, dry_run=False, runway_m=None):
    prof = gg_project.load_profile(project)
    if prof["dimension"] != "3d":
        raise Refused("2D players are not built yet (this stage builds the 3D player)")
    if ("player" in prof or "camera" in prof) and not force:
        raise Refused("gg_project.json already has player/camera sections: edit them, or pass --force to reset them")
    player, camera = default_sections(prof)
    if runway_m is not None:
        player["start"]["runway_m"] = float(runway_m)
    if dry_run:
        print(json.dumps({"player": player, "camera": camera}, indent=1))
        return 0
    prof = dict(prof, player=player, camera=camera)
    errs = validate_player(prof)
    if errs:
        raise Refused("the default sections are invalid: " + "; ".join(errs))
    _write_profile(project, prof)
    print("wrote player and camera sections (view %s -> camera mode %s)" % (prof["view"], camera["mode"]))
    return 0


def probe_points(world, start, rng_seed=1, n_cells=16):
    """Vertices, cell centres and points either side of the mesh diagonal on gentle dry cells: [[x, z, y_start]]."""
    cell = world.cell
    nz, nx = world.h.shape
    ok = (world.h - world.sea >= 1.0) & (world.slope <= start["max_slope"])
    ok[-1, :] = ok[:, -1] = False
    cells = np.argwhere(ok[:-1, :-1])
    if len(cells) < 4:
        return []
    rng = np.random.default_rng(rng_seed)
    pick = cells[rng.permutation(len(cells))[:n_cells]]
    pts = []
    for j, i in pick:
        for tx, tz in ((0, 0), (0.5, 0.5), (0.4, 0.35), (0.6, 0.65)):
            x, z = (i + tx) * cell, (j + tz) * cell
            y = gg_scatter.ground_y(world.h, x, z, cell)
            pts.append([round(x, 3), round(z, 3), round(y + 1.0, 3), 1 if (tx, tz) == (0, 0) else 0])
    return pts


def build(project, dry_run=False, run=gg_godot.run):
    prof = gg_project.load_profile(project)
    errs = validate_player(prof)
    if errs:
        raise Refused("; ".join(errs[:6]))
    style = gg_style.check_applied(project, prof)
    cat = gg_catalog.load_catalog(project) if os.path.isfile(gg_catalog.catalog_path(project)) else {"families": {}}
    world = gg_scatter.World(project)
    level, wd = prof["level"], gg_terrain.world_dir(project)
    hs = world.wd["heights_sha"]
    scenes = level_scenes(project, prof, hs)
    with_scatter = len(scenes) > 1 and scenes[-1].endswith("colliders.tscn")
    shapes, solids, counts = solids_from_scatter(project, level, cat) if with_scatter else ([], [], {})
    start = choose_start(world, prof["player"]["start"], solids, prof["player"]["radius_m"], prof["camera"]["mode"] in ("top_down", "isometric"))
    pts = probe_points(world, prof["player"]["start"])
    if len(pts) < 8:
        raise Refused("only %d collider probe points: not enough gentle dry land (slope <= player.start.max_slope) to prove the collider; reshape the terrain" % len(pts))
    if dry_run:
        print("start %s yaw %.0f, runway %d m, %d candidates; solids: %s (%d shapes); level instances %s; %d probe points" % (start["position"], start["yaw_deg"], len(start["runway"]), start["candidates"], counts or "none", len(shapes), scenes, len(pts)))
        return 0, {"start": start}
    gg_terrain.forget(project, what=("player_ok.json", "smoke_ok.json"))
    atomic = gg_scatter.atomic_json
    atomic(os.path.join(wd, "start.json"), dict(start, heights_sha=hs))
    renderer = style["renderer"]
    r = run(project, "build_colliders", {"level": level, "shapes": shapes}, render=False, renderer=renderer, timeout=300)
    if r.code:
        return r.code, {"why": "colliders: " + r.why}
    p, c = prof["player"], prof["camera"]
    r = run(project, "build_player", {"level": level, "player": p, "camera": c}, render=False, renderer=renderer, timeout=200)
    if r.code:
        return r.code, {"why": "player: " + r.why}
    r = run(project, "build_level", {"level": level, "style": style, "scenes": scenes, "player_scene": "res://levels/%s/player.tscn" % level, "start": {"position": start["position"], "yaw_deg": start["yaw_deg"]}},
            render=False, renderer=renderer, timeout=300)
    if r.code:
        return r.code, {"why": "level: " + r.why}
    r = run(project, "collider_probe", {"scenes": ["res://levels/%s/terrain.tscn" % level], "player_scene": "res://levels/%s/player.tscn" % level, "points": [q[:3] for q in pts], "ticks": 150, "frames": len(pts) * 100},  # frames sets the runner's iteration cap
            render=False, renderer=renderer, timeout=600)
    if r.code:
        return r.code, {"why": "collider probe: " + r.why}
    res = r.result["data"]["points"]
    worst, bad = 0.0, []
    for q, got in zip(pts, res):
        err = got["rest_y"] - gg_scatter.ground_y(world.h, q[0], q[1], world.cell)
        worst = max(worst, abs(err))
        tol = 0.05 if q[3] else 0.15
        if not got["on_floor"] or abs(err) > tol:
            bad.append("(%.1f, %.1f) %s%.3f m %s" % (q[0], q[1], "+" if err >= 0 else "", err, "" if got["on_floor"] else "not on floor"))
    if bad:
        return 1, {"why": "the collider and the mesh disagree (diagonal or scale): %d of %d probe points off, e.g. %s; see references/gg-player.md" % (len(bad), len(pts), "; ".join(bad[:3])), "worst": worst}
    atomic(os.path.join(wd, "player_ok.json"), {"heights_sha": hs, "hashes": player_hashes(project, prof), "probe": {"points": len(pts), "max_err": round(worst, 4), "engine": r.result["data"]["physics_engine"]}})
    return 0, {"start": start, "probe_points": len(pts), "max_err": worst, "solids": counts, "scenes": scenes}


# ---------------------------------------------------------------- smoke
def effective_walk_s(prof, walk_s, runway_m):
    """The forward walk must end 2 m before the end of the runway: distance = speed x (t - speed / (2 x accel))."""
    p = prof["player"]
    fit = (runway_m - 2.0) / p["speed_mps"] + p["speed_mps"] / (2.0 * p["accel_mps2"])
    return max(1.0, min(walk_s, fit))


def make_script(prof, walk_s):
    """-> (steps for the op, phase tick ranges). 60 ticks per second."""
    c, w = prof["camera"], int(round(walk_s * 60))
    world_rel = c["mode"] in ("top_down", "isometric")
    steps = [{"ticks": SETTLE_TICKS}, {"ticks": w, "press": ["move_forward"]}]
    ph = {"settle": (0, SETTLE_TICKS), "walk1": (SETTLE_TICKS, SETTLE_TICKS + w)}
    t = SETTLE_TICKS + w
    dx = 0.0
    if world_rel:
        steps.append({"ticks": 60, "press": ["move_right"]})
        ph["walk2"] = (t, t + 60)
        t += 60
    else:
        dx = 90.0 / c["mouse_sens_deg_per_px"]
        steps.append({"ticks": 2, "mouse_dx": dx})
        ph["turn"] = (t, t + 2)
        t += 2
        steps.append({"ticks": 60, "press": ["move_forward"]})
        ph["walk2"] = (t, t + 60)
        t += 60
    steps.append({"ticks": 2, "press": ["jump"]})
    ph["jump"] = (t, t + 92)
    steps.append({"ticks": 90})
    return steps, ph, dx


def evaluate(rows, ph, mouse_dx, prof, world, start, evidence):
    """Pure. rows: [[tick, x, y, z, yaw, on_floor, vy, cx, cy, cz]]. -> [failure strings] each naming the check, the number and the key to change."""
    t = np.array(rows, dtype=float)
    p, c = prof["player"], prof["camera"]
    cell = world.cell
    gy = np.array([gg_scatter.ground_y(world.h, x, z, cell) for x, z in t[:, [1, 3]]])
    fails = []
    s_end = ph["settle"][1]
    if not t[:s_end, 5].astype(bool)[-1]:
        fails.append("C1 settle: the player is not on the floor after %d ticks: the terrain collider is missing or the start is in the air" % s_end)
    clr = t[:, 2] - gy
    below = int((clr < -0.25).sum())
    if below:
        fails.append("C2 fall-through: %d ticks with the feet more than 0.25 m below the ground (lowest %.2f m): the terrain has no working collider" % (below, clr.min()))
    floating = int(((clr > 0.35) & t[:, 5].astype(bool)).sum())
    if floating:
        fails.append("C2 floating: %d ticks on the floor with the feet more than 0.35 m above the ground (highest %.2f m): the collider and the mesh disagree" % (floating, clr.max()))
    w1 = ph["walk1"]
    d1 = float(np.hypot(*(t[w1[1], [1, 3]] - t[w1[0], [1, 3]])))
    secs = (w1[1] - w1[0]) / 60.0
    # slope factor from the PLANNED runway (start.json), never from where the player actually went: a blocked player must not shrink its own target
    path = [[start["position"][0], start["position"][2]]] + [list(q) for q in start.get("runway", [])]
    pg = [gg_scatter.ground_y(world.h, x, z, cell) for x, z in path]
    n_use = max(1, int(start.get("runway_m", 12) - 2))
    dyp = np.abs(np.diff(pg))[:n_use]
    cosm = float(np.mean(1.0 / np.sqrt(1.0 + dyp ** 2))) if len(dyp) else 1.0
    expected = p["speed_mps"] * (secs - p["speed_mps"] / (2 * p["accel_mps2"])) * cosm
    evidence["distance_m"], evidence["expected_m"] = round(d1, 2), round(expected, 2)
    if d1 < 2.0 or not 0.85 <= d1 / expected <= 1.05:
        fails.append("C3 distance: walked %.2f m in %.1f s, expected %.2f m (ratio %.2f, need 0.85..1.05, at least 2 m): input did not move the player, or something blocks the runway; check player.speed_mps and the start runway" % (d1, secs, expected, d1 / max(expected, 1e-9)))
    if d1 > 0.2:
        disp = t[w1[1], [1, 3]] - t[w1[0], [1, 3]]
        heading = yaw_of(disp[0], disp[1])
        want = start["yaw_deg"] if c["mode"] not in ("top_down", "isometric") else 0.0
        dh = (heading - want + 180) % 360 - 180
        evidence["walk1_heading_err_deg"] = round(dh, 1)
        if abs(dh) > 10:
            fails.append("C4 heading: the first walk went %.0f degrees off the facing (%.0f vs %.0f): the yaw convention or the input mapping is wrong" % (dh, heading, want))
    w2 = ph["walk2"]
    if c["mode"] not in ("top_down", "isometric"):
        tr = ph["turn"]
        yaw0, yaw1 = t[tr[0] - 1, 4], t[min(tr[1] + 4, len(t) - 1), 4]   # the mouse event is applied on the next process frame: read the yaw after it settled
        dyaw = (yaw1 - yaw0 + 180) % 360 - 180
        want_d = -mouse_dx * c["mouse_sens_deg_per_px"]
        evidence["turn_deg"] = round(dyaw, 1)
        if abs(dyaw - want_d) > 5:
            fails.append("C4 mouse turn: a %.0f px mouse move turned the player %.1f degrees, expected %.1f (camera.mouse_sens_deg_per_px = %s): mouse input did not reach the player" % (mouse_dx, dyaw, want_d, c["mouse_sens_deg_per_px"]))
        d2 = t[w2[1], [1, 3]] - t[w2[0], [1, 3]]
        if np.hypot(*d2) > 0.5:
            dh2 = (yaw_of(d2[0], d2[1]) - yaw1 + 180) % 360 - 180
            if abs(dh2) > 15:
                fails.append("C4 second walk: heading %.0f degrees off the new facing" % dh2)
        else:
            fails.append("C3 second walk: the player moved only %.2f m after the turn" % np.hypot(*d2))
    else:
        d2 = t[w2[1], [1, 3]] - t[w2[0], [1, 3]]
        if d2[0] < 0.5 * abs(d2[1]) or np.hypot(*d2) < 2.0:
            fails.append("C4 sideways walk: move_right went (%.1f, %.1f) m; expected +X" % (d2[0], d2[1]))
    if p["jump_height_m"] > 0:
        j0, j1 = ph["jump"]
        peak = float((t[j0:j1, 2] - gy[j0:j1]).max())
        evidence["jump_peak_m"] = round(peak, 2)
        if not 0.8 * p["jump_height_m"] <= peak <= 1.2 * p["jump_height_m"] + 0.05:
            fails.append("C5 jump: peak %.2f m above the ground, expected %.2f m +-20%% (player.jump_height_m, player.gravity_mps2)" % (peak, p["jump_height_m"]))
        if not t[j1 - 1, 5]:
            fails.append("C5 jump: the player is not back on the floor 90 ticks after the jump")
    wd = np.array([gg_scatter.bilinear(world.dist, x, z, cell) for x, z in t[:, [1, 3]]])
    sea_bad = int(((t[:, 2] < world.sea + 0.05) | (wd <= 0.5 * cell)).sum())
    if sea_bad:
        fails.append("C6 sea: %d ticks in or at the water: the walk crossed water (player.start.face, min_water_m)" % sea_bad)
    cgy = np.array([gg_scatter.ground_y(world.h, x, z, cell) for x, z in t[:, [7, 9]]])
    cam_clr = t[:, 8] - cgy
    evidence["min_camera_clearance_m"] = round(float(cam_clr.min()), 2)
    if (cam_clr < 0.2).any():
        fails.append("C7 camera: the camera is %.2f m from the ground (need 0.2): it is inside the terrain (camera.eye_height_m / distance_m)" % cam_clr.min())
    return fails


def image_checks(start_png, end_png):
    a = gg_metrics.load_rgb(start_png).astype(np.float64) / 255.0
    b = gg_metrics.load_rgb(end_png).astype(np.float64) / 255.0
    fails = []
    for tag, im in (("start", a), ("end", b)):
        luma = im @ np.array([0.2126, 0.7152, 0.0722])
        if luma.std() < 0.02 or not 0.03 < luma.mean() < 0.97:
            fails.append("C8 picture: the %s picture is blank or crushed (mean %.2f std %.3f): the camera sees nothing" % (tag, luma.mean(), luma.std()))
    diff = float(np.abs(a - b).mean()) if a.shape == b.shape else 1.0
    if diff < SHOT_DIFF_MIN:
        fails.append("C8 picture: the start and end pictures differ by %.4f (need %.3f): the camera did not see the player move" % (diff, SHOT_DIFF_MIN))
    return fails, round(diff, 4)


def smoke(project, walk_s=3.0, out=None, run=gg_godot.run, script_override=None):
    prof = gg_project.load_profile(project)
    errs = validate_player(prof)
    if errs:
        raise Refused("; ".join(errs[:4]))
    style = gg_style.check_applied(project, prof)
    world = gg_scatter.World(project)
    hs = world.wd["heights_sha"]
    ok, changed = stamp_state(project, prof, "player_ok.json", hs)
    if not ok:
        raise Refused("the level changed since gg_player.py build (%s): run gg_player.py build again and get exit 0" % ", ".join(changed))
    gg_terrain.forget(project, what=("smoke_ok.json",))
    out = os.path.realpath(out) if out else os.path.join(project, "gg_data", "smoke")
    root = os.path.realpath(os.path.join(project, "gg_data"))
    if not (out + os.sep).startswith(root + os.sep):
        raise Refused("--out must be inside %s" % root)
    os.makedirs(out, exist_ok=True)
    start0 = json.load(open(os.path.join(gg_terrain.world_dir(project), "start.json")))
    steps, ph, dx = script_override or make_script(prof, effective_walk_s(prof, walk_s, start0.get("runway_m", prof["player"]["start"]["runway_m"])))
    total = sum(s["ticks"] for s in steps)
    for n in ("trace.json", "start.png", "end.png"):
        if os.path.exists(os.path.join(out, n)):
            os.remove(os.path.join(out, n))
    r = run(project, "smoke_level", {"scene": "res://levels/%s/level.tscn" % prof["level"], "script": steps, "shots": {"start": os.path.join(out, "start.png"), "end": os.path.join(out, "end.png")},
                                     "trace": os.path.join(out, "trace.json"), "settle_ticks": SETTLE_TICKS, "frames": total}, render=True, renderer=style["renderer"], size=(640, 360),
            timeout=int(120 + total / 2), strict_warnings=True)
    if r.code:
        return r.code, {"why": r.why}
    d = r.result["data"]
    if d["physics_ticks"] != total or abs(d["process_frames"] - total) > 2:
        return 4, {"why": "C0 ticks: %d physics ticks ran for %d scripted (%d process frames): timing is unknown, no verdict" % (d["physics_ticks"], total, d["process_frames"])}
    rows = json.load(open(os.path.join(out, "trace.json")))
    start = json.load(open(os.path.join(gg_terrain.world_dir(project), "start.json")))
    evidence = {"ticks": total, "physics_engine": d["physics_engine"]}
    fails = evaluate(rows, ph, dx, prof, world, start, evidence)
    wanted = {a for s in steps for a in s.get("press", [])}
    seen = d.get("action_seen") or {}
    for a in sorted(wanted):
        if not seen.get(a):
            fails.append("C10 input: the scripted action %s never reached the player" % a)
    if dx and d.get("mouse_events", 0) < 1:
        fails.append("C10 input: the injected mouse motion never reached the player")
    if not d.get("camera_current"):
        fails.append("C7 camera: no Camera3D was current")
    img, diff = image_checks(os.path.join(out, "start.png"), os.path.join(out, "end.png"))
    fails += img
    evidence["shot_diff"] = diff
    if fails:
        return 1, {"why": " | ".join(fails), "fails": fails, "evidence": evidence, "out": out}
    gg_scatter.atomic_json(os.path.join(gg_terrain.world_dir(project), "smoke_ok.json"), {"heights_sha": hs, "hashes": player_hashes(project, prof), "evidence": evidence})
    return 0, {"evidence": evidence, "out": out}


def status(project):
    prof = gg_project.load_profile(project)
    hs = gg_terrain.load_world(project).get("heights_sha")
    for name, cmd in (("player_ok.json", "gg_player.py build"), ("smoke_ok.json", "gg_player.py smoke")):
        ok, changed = stamp_state(project, prof, name, hs)
        print("%-14s %s%s" % (name, "VALID" if ok else "STALE or missing", "" if ok else " (%s): run %s" % (", ".join(changed), cmd)))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("init", "build", "smoke", "status"):
        p = sub.add_parser(n)
        p.add_argument("--project", required=True)
        if n in ("init", "build"):
            p.add_argument("--dry-run", action="store_true")
        if n == "init":
            p.add_argument("--force", action="store_true")
            p.add_argument("--runway-m", type=float, help="player.start.runway_m (default 20; a steep tree-heavy island needs about 12)")
        if n == "smoke":
            p.add_argument("--walk-s", type=float, default=3.0)
            p.add_argument("--out")
    a = ap.parse_args(argv)
    try:
        project = os.path.abspath(a.project)
        if a.cmd == "init":
            return init(project, a.force, a.dry_run, a.runway_m)
        if a.cmd == "status":
            return status(project)
        if a.cmd == "build":
            r = build(project, a.dry_run)
            code, rep = r if isinstance(r, tuple) else (r, {})
            if code:
                print("FAILED (exit %d): %s" % (code, rep.get("why")))
            elif not a.dry_run:
                print("built: start %s yaw %.0f; collider probe %d points, worst error %.3f m; solids %s; level instances %s" % (rep["start"]["position"], rep["start"]["yaw_deg"], rep["probe_points"], rep["max_err"], rep["solids"] or "none", rep["scenes"]))
            return code
        code, rep = smoke(project, a.walk_s, a.out)
        if code:
            print("FAILED (exit %d): %s" % (code, rep.get("why")))
            for f in rep.get("fails", []):
                print("  - " + f)
        else:
            print("SMOKE PASS: " + json.dumps(rep["evidence"]))
        return code
    except (gg_godot.Refused, gg_metrics.Refused, ValueError, OSError, KeyError, json.JSONDecodeError) as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
