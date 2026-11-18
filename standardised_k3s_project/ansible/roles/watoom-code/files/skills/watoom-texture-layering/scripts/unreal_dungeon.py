#!/usr/bin/env python3
"""A dungeon under the terrain from a layout + modular wall/arch/floor pieces, reached through portals -> ue-mcp calls.

  python3 tools/watoom-toolkit/dungeon_layout.py --seed 15 --rooms 6 --grid 4 --cell-size 2000 --room-size 1500 --out layout.json
  unreal_dungeon.py --layout layout.json --spec templates/dungeon.zas.json --out dungeon_calls.json \\
      [--heights live.png --project unreal_project.json]        (checks the ceiling stays under the ground)
  ue_run_phases.py dungeon_calls.json

Layout: the deterministic grid of rooms and corridors from dungeon_layout.py (shared with the Godot/Blender dungeon
pipeline). Spec (templates/dungeon.zas.json):
  origin        [x, y, z]: world point of the ENTRANCE room's floor top (centre); every room keeps its layout offset
  modules       wall / door (same footprint as a wall segment, with an opening) / floor (a 100 cm cube, scaled into slabs)
                / column (optional), and wall_len, wall_thick, wall_height in cm (measure with asset.get_mesh_bounds)
  light         {"intensity", "color": [r, g, b], "radius"} one point light per room (a closed dungeon is otherwise black)
  entrance      {"location", "yaw", "extent"}: the walk-in portal on the surface; it sends the player to the entrance room
  exit_to       [x, y, z, yaw]: where the portal in the exit room sends the player (back on the surface)
  portal_fx     optional looping Niagara system shown at both portals
  clearance_cm  how far the ceiling must stay below the ground (with --heights)
Geometry: rooms room_size square (an ODD number of wall segments per side, so the middle one is the doorway, centred on the
corridor); corridors one wall segment wide, (cell_size - room_size) long; floor and ceiling slabs from the cube. Labels are
<label_prefix>Dgn_* so a re-run skips what exists (place_actor onConflict skip) and the whole set is easy to find.
Why (T-0015, 2026-11-19): the owner's "small dungeon under the mountain-top artifact", built as the worked example. Below a
landscape heightfield there is nothing to collide with, so the dungeon simply sits under the ground; a hole in the terrain
would need the landscape material to route a visibility mask, so portals (AWatooMPortal, WatooMCombat plugin) connect it.
"""
import argparse
import json
import math
import sys
from os.path import abspath as _abspath, dirname as _dirname

sys.path.insert(0, _dirname(_abspath(__file__)))
import ue_project  # noqa: E402

PORTAL = "/Script/WatooMCombat.WatooMPortal"
SIDES = {"N": ((0, 1), (1, 0)), "S": ((0, -1), (1, 0)), "E": ((1, 0), (0, 1)), "W": ((-1, 0), (0, 1))}   # normal, tangent


def _yaw(tangent):
    return 0.0 if tangent[0] else 90.0


def check(layout, spec):
    m = spec["modules"]
    L = float(m["wall_len"])
    rooms = layout["rooms"]
    if len({r["level"] for r in rooms}) != 1:
        raise ValueError("one level only (stairs are not built yet)")
    R = float(rooms[0]["size"][0])
    n = R / L
    if abs(n - round(n)) > 1e-6 or round(n) % 2 == 0:
        raise ValueError("room_size %g must be an ODD multiple of wall_len %g (the middle segment is the doorway)" % (R, L))
    cell = [abs(b["position"][0] - a["position"][0]) + abs(b["position"][1] - a["position"][1])
            for c in layout["connections"] for a, b in [(rooms[c["from"]], rooms[c["to"]])]]
    for g in {c - R for c in cell}:
        if abs(g / L - round(g / L)) > 1e-6 or g <= 0:
            raise ValueError("corridor length %g (cell - room) must be a positive multiple of wall_len %g" % (g, L))
    return R, L


def bounds(layout, spec):
    """World box (x0, y0, x1, y1, floor_z, ceiling_top_z) the dungeon occupies, walls included."""
    R, L = check(layout, spec)
    m, ox, oy, oz = spec["modules"], *spec["origin"]
    e = layout["rooms"][layout["entrance"]]["position"]
    t = float(m["wall_thick"])
    xs = [ox + r["position"][0] - e[0] for r in layout["rooms"]]
    ys = [oy + r["position"][1] - e[1] for r in layout["rooms"]]
    half = R / 2 + t
    return min(xs) - half, min(ys) - half, max(xs) + half, max(ys) + half, oz - 50, oz + float(m["wall_height"]) + 50


def calls(layout, spec, prefix="ZAS_", rebuild=False):
    R, L = check(layout, spec)
    m = spec["modules"]
    t, H = float(m["wall_thick"]), float(m["wall_height"])
    ox, oy, oz = spec["origin"]
    rooms = layout["rooms"]
    e = rooms[layout["entrance"]]["position"]
    world = {r["id"]: (ox + r["position"][0] - e[0], oy + r["position"][1] - e[1]) for r in rooms}
    out = []
    P = prefix + "Dgn_"

    def put(name, mesh, x, y, z, yaw=0.0, scale=None):
        # labels say WHAT the piece is (room/corridor, side, segment), so a re-run skips exactly the pieces that exist
        a = {"actorClass": "StaticMeshActor", "label": P + name, "onConflict": "skip", "staticMesh": mesh,
             "location": {"x": round(x, 1), "y": round(y, 1), "z": round(z, 1)}, "rotation": {"pitch": 0, "yaw": yaw, "roll": 0}}
        if scale:
            a["scale"] = {"x": scale[0], "y": scale[1], "z": scale[2]}
        out.append(["level.place_actor", a])

    cube = float(m.get("floor_size", 100))

    def slab(tag, x, y, sx, sy):
        put(tag + "_Floor", m["floor"], x, y, oz - 25, scale=[round(sx / cube, 3), round(sy / cube, 3), 0.5])
        put(tag + "_Ceiling", m["floor"], x, y, oz + H + 25, scale=[round(sx / cube, 3), round(sy / cube, 3), 0.5])

    # which side of each room opens onto a corridor
    doors = {r["id"]: set() for r in rooms}
    for c in layout["connections"]:
        a, b = world[c["from"]], world[c["to"]]
        dx, dy = b[0] - a[0], b[1] - a[1]
        side = ("E" if dx > 0 else "W") if abs(dx) > abs(dy) else ("N" if dy > 0 else "S")
        doors[c["from"]].add(side)
        doors[c["to"]].add({"E": "W", "W": "E", "N": "S", "S": "N"}[side])
        # corridor: one segment wide, floor + ceiling + a wall run on each side
        (nx, ny) = SIDES[side][0]
        gap = math.hypot(dx, dy) - R
        mx, my = a[0] + nx * (R / 2 + gap / 2), a[1] + ny * (R / 2 + gap / 2)
        tag = "C%d_%d" % (c["from"], c["to"])
        slab(tag, mx, my, gap if nx else L, L if nx else gap)
        segs = int(round(gap / L))
        for k in range(segs):
            along = -gap / 2 + L * (k + 0.5)
            for s in (-1, 1):
                off = s * (L / 2 + t / 2)
                x = mx + nx * along + (0 if nx else off)
                y = my + ny * along + (off if nx else 0)
                put("%s_Wall%s%d" % (tag, "L" if s < 0 else "R", k), m["wall"], x, y, oz, yaw=90.0 if not nx else 0.0)
    segs = int(round(R / L))
    for r in rooms:
        cx, cy = world[r["id"]]
        tag = "R%d" % r["id"]
        # slabs reach over the wall ring, and a post fills each corner: wall segments only span the floor's width, so
        # the 155 cm square where two walls meet was open to the void (sky showed through, 2026-11-19 capture)
        slab(tag, cx, cy, R + 2 * t, R + 2 * t)
        for sx, sy in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
            put("%s_Post%s%s" % (tag, "W" if sx < 0 else "E", "S" if sy < 0 else "N"), m["floor"],
                cx + sx * (R / 2 + t / 2), cy + sy * (R / 2 + t / 2), oz + H / 2, scale=[round(t / cube, 3), round(t / cube, 3), round(H / cube, 3)])
        for side, (nrm, tan) in sorted(SIDES.items()):
            for k in range(segs):
                along = -R / 2 + L * (k + 0.5)
                x = cx + nrm[0] * (R / 2 + t / 2) + tan[0] * along
                y = cy + nrm[1] * (R / 2 + t / 2) + tan[1] * along
                door = side in doors[r["id"]] and k == segs // 2
                put("%s_%s%s%d" % (tag, "Door" if door else "Wall", side, k), m["door"] if door else m["wall"], x, y, oz, yaw=_yaw(tan))
        if m.get("column"):
            c = R / 2 - float(m.get("column_inset", 150))
            for sx, sy in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
                put("%s_Column%s%s" % (tag, "W" if sx < 0 else "E", "S" if sy < 0 else "N"), m["column"], cx + sx * c, cy + sy * c, oz)
        li = spec.get("light")
        if li:
            label = "%sLight_%02d" % (P, r["id"])
            out.append(["level.place_actor", {"actorClass": "PointLight", "label": label, "onConflict": "skip",
                                              "location": {"x": cx, "y": cy, "z": oz + H * 0.7}}])
            comp = li.get("component", "LightComponent0")
            col = li.get("color", [255, 170, 90])
            for prop, val in (("Intensity", float(li.get("intensity", 5000))), ("AttenuationRadius", float(li.get("radius", R))),
                              ("LightColor", "(R=%d,G=%d,B=%d,A=255)" % tuple(col))):
                out.append(["level.set_component_property", {"actorLabel": label, "componentName": comp, "propertyName": prop, "value": val}])
    # portals: surface -> entrance room; exit room -> surface
    en = spec["entrance"]
    ex, ey = world[layout["entrance"]]
    xx, xy = world[layout["exit"]]
    portals = [("%sPortal_In" % P, en["location"], en.get("extent", [150, 150, 200]), [ex, ey, oz + 120], float(en.get("arrive_yaw", 0))),
               ("%sPortal_Out" % P, [xx, xy, oz + 200], [120, 120, 200], spec["exit_to"][:3], float(spec["exit_to"][3]))]
    for label, loc, ext, dest, yaw in portals:
        out.append(["level.place_actor", {"actorClass": PORTAL, "label": label, "onConflict": "skip",
                                          "location": {"x": loc[0], "y": loc[1], "z": loc[2]},
                                          "rotation": {"pitch": 0, "yaw": float(en.get("yaw", 0)) if label.endswith("_In") else 0.0, "roll": 0}}])
        for prop, val in (("BoxExtent", "(X=%g,Y=%g,Z=%g)" % tuple(ext)), ("Destination", "(X=%g,Y=%g,Z=%g)" % tuple(dest)),
                          ("DestinationYaw", yaw)):
            out.append(["level.set_actor_property", {"actorLabel": label, "propertyName": prop, "value": val}])
        if spec.get("portal_fx"):
            out.append(["level.set_actor_property", {"actorLabel": label, "propertyName": "Fx", "value": spec["portal_fx"]}])
    phases = []
    first = [["level.load", {"levelPath": spec["map"], "saveFirst": True}]] if spec.get("map") else []
    if rebuild:
        # every piece carries the prefix, so a changed layout/geometry is rebuilt by removing them all first
        first.append(["level.delete_actors", {"labelPrefix": P}])
    if first:
        phases.append({"name": "dungeon map", "calls": first})
    phases.append({"name": "dungeon", "calls": out + [["level.save", {}]]})
    return {"phases": phases}


def ground_min(heights_png, box, z0, raw_per_cm, size_m):
    """Lowest landscape Z (cm) over the box, from the exported heights (16-bit PNG, one pixel per vertex)."""
    import numpy as np
    from PIL import Image
    h = np.array(Image.open(heights_png)).astype(float)
    px = size_m * 100.0 / (h.shape[0] - 1)
    i0, i1 = max(int(box[0] // px), 0), min(int(box[2] // px) + 1, h.shape[1] - 1)
    j0, j1 = max(int(box[1] // px), 0), min(int(box[3] // px) + 1, h.shape[0] - 1)
    return float(z0 + h[j0:j1 + 1, i0:i1 + 1].min() / raw_per_cm)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--layout", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--heights", help="landscape heights PNG: refuse a dungeon whose ceiling is not clearance_cm under the ground")
    ap.add_argument("--z0", type=float)
    ap.add_argument("--raw-per-cm", type=float)
    ap.add_argument("--size-m", type=float)
    ap.add_argument("--label-prefix", default="ZAS_")
    ap.add_argument("--rebuild", action="store_true", help="first delete every <prefix>Dgn_ actor (geometry or layout changed)")
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    with open(a.layout) as f:
        layout = json.load(f)
    with open(a.spec) as f:
        spec = json.load(f)
    box = bounds(layout, spec)
    if a.heights:
        if None in (a.z0, a.raw_per_cm, a.size_m):
            raise SystemExit("--heights needs --z0 --raw-per-cm --size-m (or --project)")
        g = ground_min(a.heights, box, a.z0, a.raw_per_cm, a.size_m)
        room = g - box[5]
        print("ground over the dungeon: lowest %.0f cm; ceiling top %.0f cm; cover %.0f cm" % (g, box[5], room))
        if room < float(spec.get("clearance_cm", 300)):
            raise SystemExit("REFUSED: the ceiling would be %.0f cm under the ground (< clearance_cm %s): lower origin z"
                             % (room, spec.get("clearance_cm", 300)))
    c = calls(layout, spec, a.label_prefix, a.rebuild)
    with open(a.out, "w") as f:
        json.dump(c, f, indent=1)
    n = sum(len(p["calls"]) for p in c["phases"])
    print("%s: %d rooms, %d corridors, %d calls; box x %.0f..%.0f y %.0f..%.0f z %.0f..%.0f"
          % (a.out, len(layout["rooms"]), len(layout["connections"]), n, box[0], box[2], box[1], box[3], box[4], box[5]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
