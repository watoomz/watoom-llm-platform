#!/usr/bin/env python3
"""Dungeon kit catalog + procedural grid layout. No engine needed: everything here is pure Python/numpy logic
over JSON files, so it runs the same with or without a real Godot worker. It is deliberately decoupled from
asset conversion: pieces are already-existing project-local res:// .tscn/.glb scenes (the Unreal->Godot export
of an owned dungeon kit is a separate, later piece of work; see references/gg-dungeon.md).

  gg_dungeon.py catalog-init     --project P --pieces-dir res://DIR [--dry-run]   scan DIR (recursively, under the
                                  project) for *.tscn/*.glb files and write gg_dungeon.json with one UNCLASSIFIED
                                  stub piece per file (kind "unclassified", footprint [1, 1], no sockets); hand-edit
                                  kind/footprint/sockets for each piece, then `catalog-validate`
  gg_dungeon.py catalog-list     --project P                                      one line per piece
  gg_dungeon.py catalog-validate --project P                                      schema and socket-geometry rules;
                                  exit 1 lists every problem
  gg_dungeon.py layout           --project P --seed N --rooms N [--name NAME]     deterministic procedural grid
                                  layout over the VALIDATED catalog: places a start room, then grows the dungeon by
                                  matching open sockets to other pieces' sockets (any rotation) until `rooms`
                                  room-kind pieces are placed or no open socket can be extended; writes
                                  gg_data/dungeon/<name>.json (default name "layout")
  gg_dungeon.py verify           --project P [--name NAME]                       independent connectivity/overlap
                                  audit of a layout: recomputes every socket connection from the raw instance
                                  positions/rotations (never trusts the layout file's own "connections" list),
                                  checks no two pieces' footprints overlap, and that every room-kind instance is
                                  reachable from the entrance by BFS over the recomputed graph

Catalog file: <project>/gg_dungeon.json, schema:
  {"schema": 1, "cell_m": 4.0, "pieces": {"<name>": {"kind": "room"|"corridor"|"junction"|"prop", "scene": "res://...",
   "footprint": [width_cells, depth_cells], "sockets": [{"edge": "north"|"east"|"south"|"west", "pos": int}, ...],
   "notes": "..."}}}
`footprint` is the piece's own (unrotated) grid-cell size: [width_cells, depth_cells] along x and z. A socket's `pos`
is its 0-based offset along that edge (0..width_cells-1 for north/south, 0..depth_cells-1 for east/west): the opening
through which another piece can connect. `room`/`corridor`/`junction` pieces (anything meant to be placed by `layout`)
need at least one socket; `prop` pieces (decoration, never placed by `layout`) do not.
Layout file (gg_data/dungeon/<name>.json), schema:
  {"schema": 1, "seed": N, "cell_m": 4.0, "entrance": 0, "requested_rooms": N, "placed_rooms": M,
   "instances": [{"id": 0, "piece": "<name>", "x": int, "z": int, "rot": 0|1|2|3}, ...],
   "connections": [{"a": id, "a_edge": "...", "a_pos": int, "b": id, "b_edge": "...", "b_pos": int}, ...]}
`x`/`z` are the instance's origin grid cell (its unrotated-footprint cell [0, 0] after rotation is applied); `rot` is
a quarter turn count clockwise (0..3). `connections` is what the generator believes it built; `verify` recomputes the
same thing independently from `instances` alone and does not trust it.
No render/visual check is built for this stage (unlike gg_catalog's inspect): there is no converted kit to render yet,
and connectivity/reachability correctness matters more for this ticket (T-0059) than a screenshot would. A render/
shot check (`gg_verify.py`/`gg_ui.py`-style) over a real converted kit is explicit follow-on work once the Unreal
export exists; do not infer visual correctness from anything in this module.
Exit codes: 0 pass | 1 check failed | 2 refused.
"""
import argparse
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
import gg_godot  # noqa: E402

EDGES = ("north", "east", "south", "west")
OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east"}
DIR = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
KINDS = {"room", "corridor", "junction", "prop"}
CONNECTABLE_KINDS = {"room", "corridor", "junction"}
PIECE_KEYS = {"kind", "scene", "footprint", "sockets", "notes"}
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
OUT_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
MAX_FOOTPRINT = 32
MAX_ROOMS = 300
MAX_INSTANCES = 2000


def catalog_path(project):
    return os.path.join(project, "gg_dungeon.json")


def layout_path(project, name):
    return os.path.join(project, "gg_data", "dungeon", "%s.json" % name)


def _atomic_json(path, obj, indent=1):
    with open(path + ".new", "w") as f:
        json.dump(obj, f, indent=indent)
        f.write("\n")
    os.replace(path + ".new", path)


def load_catalog(project):
    p = catalog_path(project)
    if not os.path.isfile(p):
        raise gg_godot.Refused("no %s: run gg_dungeon.py catalog-init (--pieces-dir res://...) first" % p)
    try:
        return json.load(open(p))
    except json.JSONDecodeError as e:
        raise gg_godot.Refused("%s is not valid JSON: %s" % (p, e))


def save_catalog(project, cat):
    _atomic_json(catalog_path(project), cat, indent=1)


# ----------------------------------------------------------------------------------------------- catalog schema (pure)
def piece_errors(name, piece):
    errs = []
    pre = "piece %s: " % name
    if not isinstance(name, str) or not NAME_RE.match(name):
        return [pre + "the name must match ^[a-z][a-z0-9_]{0,31}$ (lower case letters, digits, underscore)"]
    if not isinstance(piece, dict):
        return [pre + "must be an object"]
    unknown = set(piece) - PIECE_KEYS
    if unknown:
        errs.append(pre + "unknown key(s) %s (allowed: %s)" % (sorted(unknown), sorted(PIECE_KEYS)))
    kind = piece.get("kind")
    if kind not in KINDS:
        errs.append(pre + "kind %r is not one of %s (an 'unclassified' stub from catalog-init needs editing)" % (kind, sorted(KINDS)))
        kind = None
    if not str(piece.get("scene", "")).startswith("res://"):
        errs.append(pre + "scene must be a res:// path")
    fp = piece.get("footprint")
    if not (isinstance(fp, list) and len(fp) == 2 and all(isinstance(x, int) and not isinstance(x, bool) for x in fp)):
        errs.append(pre + "footprint must be [width_cells, depth_cells] (two integers)")
        return errs
    w, d = fp
    if not (1 <= w <= MAX_FOOTPRINT and 1 <= d <= MAX_FOOTPRINT):
        errs.append(pre + "footprint %s must be within 1..%d cells on each side" % (fp, MAX_FOOTPRINT))
        return errs
    sockets = piece.get("sockets")
    if not isinstance(sockets, list):
        errs.append(pre + "sockets must be a list (use [] for a piece with none)")
        return errs
    seen = set()
    for i, s in enumerate(sockets):
        spre = pre + "sockets[%d]: " % i
        if not (isinstance(s, dict) and set(s) == {"edge", "pos"}):
            errs.append(spre + "must be an object with exactly 'edge' and 'pos'")
            continue
        edge, pos = s.get("edge"), s.get("pos")
        if edge not in EDGES:
            errs.append(spre + "edge %r is not one of %s" % (edge, EDGES))
            continue
        if not (isinstance(pos, int) and not isinstance(pos, bool)):
            errs.append(spre + "pos must be an integer")
            continue
        limit = w if edge in ("north", "south") else d
        if not 0 <= pos < limit:
            errs.append(spre + "pos %d is outside 0..%d for a %s edge on a [%d, %d] footprint" % (pos, limit - 1, edge, w, d))
            continue
        if (edge, pos) in seen:
            errs.append(spre + "duplicate socket at edge %s pos %d" % (edge, pos))
        seen.add((edge, pos))
    if kind in CONNECTABLE_KINDS and not sockets:
        errs.append(pre + "kind %s needs at least one socket to ever connect to anything (a prop may have none)" % kind)
    return errs


def validate(cat):
    errs = []
    if cat.get("schema") != 1:
        errs.append("catalog schema must be 1")
    cell_m = cat.get("cell_m")
    if not (isinstance(cell_m, (int, float)) and not isinstance(cell_m, bool) and cell_m > 0):
        errs.append("cell_m must be a positive number")
    pieces = cat.get("pieces")
    if not isinstance(pieces, dict) or not pieces:
        return errs + ["catalog has no pieces"]
    for n, p in pieces.items():
        errs += piece_errors(n, p)
    return errs


# ----------------------------------------------------------------------------------------------- geometry (pure)
def rotate_once(footprint, sockets):
    """One 90-degree clockwise turn: (w, d) -> (d, w); edges cycle north->east->south->west->north."""
    w, d = footprint
    out = []
    for s in sockets:
        edge, pos = s["edge"], s["pos"]
        if edge == "north":
            ne, np_ = "east", pos
        elif edge == "east":
            ne, np_ = "south", d - 1 - pos
        elif edge == "south":
            ne, np_ = "west", pos
        else:
            ne, np_ = "north", d - 1 - pos
        out.append({"edge": ne, "pos": np_})
    return (d, w), out


def rotate(footprint, sockets, r):
    fp, sk = tuple(footprint), [dict(s) for s in sockets]
    for _ in range(r % 4):
        fp, sk = rotate_once(fp, sk)
    return fp, sk


def piece_at(cat, name, rotation):
    """-> (footprint, sockets) of catalog piece `name` after `rotation` quarter-turns clockwise."""
    piece = cat["pieces"].get(name)
    if piece is None:
        raise gg_godot.Refused("piece '%s' is not in the catalog" % name)
    return rotate(piece["footprint"], piece["sockets"], rotation)


def socket_anchor(origin, footprint, socket):
    """World cell INSIDE the footprint that the socket opens from."""
    ox, oz = origin
    w, d = footprint
    edge, pos = socket["edge"], socket["pos"]
    if edge == "north":
        return (ox + pos, oz)
    if edge == "south":
        return (ox + pos, oz + d - 1)
    if edge == "east":
        return (ox + w - 1, oz + pos)
    return (ox, oz + pos)  # west


def socket_outside(origin, footprint, socket):
    """World cell OUTSIDE the footprint, through the socket: what a connecting piece must occupy there."""
    ax, az = socket_anchor(origin, footprint, socket)
    dx, dz = DIR[socket["edge"]]
    return (ax + dx, az + dz)


def footprint_cells(origin, footprint):
    ox, oz = origin
    w, d = footprint
    return {(ox + i, oz + j) for i in range(w) for j in range(d)}


# ----------------------------------------------------------------------------------------------- catalog-init (pure scan)
def scan_pieces_dir(project, pieces_dir):
    """-> sorted res:// paths of every *.tscn/*.glb found recursively under the project-local res:// pieces_dir."""
    if not str(pieces_dir).startswith("res://") or ".." in pieces_dir.split("/"):
        raise gg_godot.Refused("--pieces-dir must be a res:// path without .., got %r" % pieces_dir)
    rel = pieces_dir[len("res://"):]
    abs_dir = os.path.join(project, rel)
    if not os.path.isdir(abs_dir):
        raise gg_godot.Refused("%s does not exist in the project" % pieces_dir)
    out = []
    for base, _, files in os.walk(abs_dir):
        for f in files:
            if f.endswith(".tscn") or f.endswith(".glb"):
                relp = os.path.relpath(os.path.join(base, f), project).replace(os.sep, "/")
                out.append("res://" + relp)
    return sorted(out)


def stub_name(scene, used):
    stem = re.sub(r"[^a-z0-9_]", "_", os.path.splitext(os.path.basename(scene))[0].lower())
    stem = re.sub(r"^[^a-z]+", "", stem)[:32] or "piece"
    if not NAME_RE.match(stem):
        stem = "piece"
    name, n = stem, 2
    while name in used:
        suffix = "_%d" % n
        name = stem[:max(1, 32 - len(suffix))] + suffix
        n += 1
    return name


def catalog_init(project, pieces_dir, dry_run=False):
    if os.path.exists(catalog_path(project)):
        raise gg_godot.Refused("%s already exists: edit it, or delete it to start over" % catalog_path(project))
    scenes = scan_pieces_dir(project, pieces_dir)
    if not scenes:
        raise gg_godot.Refused("no .tscn/.glb files found under %s" % pieces_dir)
    if dry_run:
        return 0, {"would_add": scenes}
    pieces, used = {}, set()
    for sc in scenes:
        name = stub_name(sc, used)
        used.add(name)
        pieces[name] = {"kind": "unclassified", "scene": sc, "footprint": [1, 1], "sockets": [], "notes": "UNCLASSIFIED stub from catalog-init: edit kind/footprint/sockets"}
    cat = {"schema": 1, "cell_m": 4.0, "_comment": "Edit kind/footprint/sockets for each piece (see references/gg-dungeon.md), then run catalog-validate.", "pieces": pieces}
    errs = validate(cat)
    non_kind_errs = [e for e in errs if "is not one of" not in e or "unclassified" not in e]
    # every stub is deliberately 'unclassified' (fails kind validation until hand-edited); any OTHER error means a bug here
    if non_kind_errs:
        raise gg_godot.Refused("catalog-init would write an invalid catalog: " + "; ".join(non_kind_errs))
    save_catalog(project, cat)
    return 0, {"pieces": list(pieces)}


# ----------------------------------------------------------------------------------------------- layout (pure)
def build_layout(cat, seed, rooms, max_attempts_factor=80):
    """Deterministic for a given (catalog, seed, rooms): same inputs -> byte-identical instances/connections."""
    pieces = cat["pieces"]
    room_names = sorted(n for n, p in pieces.items() if p["kind"] == "room")
    if not room_names:
        raise gg_godot.Refused("catalog has no kind='room' piece: layout needs a start room")
    connector_names = sorted(n for n, p in pieces.items() if p["kind"] in CONNECTABLE_KINDS and p["sockets"])
    if not connector_names:
        raise gg_godot.Refused("no catalog piece has any sockets: layout cannot connect anything")
    rng = np.random.default_rng(seed)
    start = room_names[0]
    fp0, sk0 = piece_at(cat, start, 0)
    instances = [{"id": 0, "piece": start, "x": 0, "z": 0, "rot": 0}]
    occupied = footprint_cells((0, 0), fp0)
    open_sockets = [(0, s) for s in sk0]
    connections = []
    room_count = 1
    attempts = 0
    max_attempts = max(200, max_attempts_factor * rooms)
    while room_count < rooms and open_sockets and attempts < max_attempts and len(instances) < MAX_INSTANCES:
        attempts += 1
        idx = int(rng.integers(len(open_sockets)))
        inst_id, sock = open_sockets.pop(idx)
        inst = instances[inst_id]
        fp_i, _ = piece_at(cat, inst["piece"], inst["rot"])
        outside = socket_outside((inst["x"], inst["z"]), fp_i, sock)
        needed = OPPOSITE[sock["edge"]]
        candidates = []
        order = rng.permutation(len(connector_names))
        for ci in order:
            pname = connector_names[int(ci)]
            piece = pieces[pname]
            for r in range(4):
                fp_c, sk_c = rotate(piece["footprint"], piece["sockets"], r)
                for s2 in sk_c:
                    if s2["edge"] == needed:
                        candidates.append((pname, r, fp_c, sk_c, s2))
        if candidates:
            corder = rng.permutation(len(candidates))
            candidates = [candidates[int(i)] for i in corder]
        placed = False
        for pname, r, fp_c, sk_c, s2 in candidates:
            local_anchor = socket_anchor((0, 0), fp_c, s2)
            origin2 = (outside[0] - local_anchor[0], outside[1] - local_anchor[1])
            cells2 = footprint_cells(origin2, fp_c)
            if cells2 & occupied:
                continue
            new_id = len(instances)
            instances.append({"id": new_id, "piece": pname, "x": origin2[0], "z": origin2[1], "rot": r})
            occupied |= cells2
            connections.append({"a": inst_id, "a_edge": sock["edge"], "a_pos": sock["pos"], "b": new_id, "b_edge": s2["edge"], "b_pos": s2["pos"]})
            if pieces[pname]["kind"] == "room":
                room_count += 1
            for s3 in sk_c:
                if s3 is not s2:
                    open_sockets.append((new_id, s3))
            placed = True
            break
        # an unmatched socket is simply left as a dead end (not every opening needs to connect)
        if not placed:
            continue
    return {"schema": 1, "seed": int(seed), "cell_m": cat["cell_m"], "entrance": 0, "requested_rooms": rooms, "placed_rooms": room_count,
            "instances": instances, "connections": connections}


def layout_cmd(project, seed, rooms, name="layout"):
    if not (isinstance(rooms, int) and not isinstance(rooms, bool) and 1 <= rooms <= MAX_ROOMS):
        raise gg_godot.Refused("--rooms must be an integer 1..%d" % MAX_ROOMS)
    if not OUT_NAME_RE.match(name):
        raise gg_godot.Refused("--name must match %s" % OUT_NAME_RE.pattern)
    cat = load_catalog(project)
    errs = validate(cat)
    if errs:
        raise gg_godot.Refused("catalog is invalid, run gg_dungeon.py catalog-validate: " + errs[0])
    manifest = build_layout(cat, seed, rooms)
    p = layout_path(project, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    _atomic_json(p, manifest, indent=1)
    placed = manifest["placed_rooms"]
    if placed < max(2, rooms // 2) and placed < rooms:
        return 1, {**manifest, "path": p, "why": "placed only %d of %d requested rooms: the catalog has too few connectable pieces, or their sockets/footprints collide too often; add pieces or lower --rooms" % (placed, rooms)}
    return 0, {**manifest, "path": p}


# ----------------------------------------------------------------------------------------------- verify (pure)
def derive_connections(cat, instances):
    """Recompute every socket-to-socket connection from raw instance positions/rotations alone (never from a
    layout file's own 'connections' list). -> (adjacency {id: set(id)}, list of (a_id, b_id, a_edge) tuples)."""
    geo = {i["id"]: piece_at(cat, i["piece"], i["rot"]) for i in instances}
    anchors = {}  # (x, z, edge) -> instance id  (the cell/edge a socket opens FROM)
    for i in instances:
        fp, sk = geo[i["id"]]
        for s in sk:
            anchors[(socket_anchor((i["x"], i["z"]), fp, s)[0], socket_anchor((i["x"], i["z"]), fp, s)[1], s["edge"])] = i["id"]
    adjacency = {i["id"]: set() for i in instances}
    found = []
    for i in instances:
        fp, sk = geo[i["id"]]
        for s in sk:
            outside = socket_outside((i["x"], i["z"]), fp, s)
            other = anchors.get((outside[0], outside[1], OPPOSITE[s["edge"]]))
            if other is not None and other != i["id"]:
                adjacency[i["id"]].add(other)
                adjacency[other].add(i["id"])
                found.append((i["id"], other, s["edge"]))
    return adjacency, found


def verify_layout(cat, layout):
    """-> (rows [(name, ok, detail)], ok). Pure; does not touch the filesystem."""
    rows = []
    instances = layout.get("instances") or []
    if not instances:
        return [("has instances", False, "the layout has no instances")], False
    by_id = {i["id"]: i for i in instances}
    missing = sorted({i["piece"] for i in instances} - set(cat["pieces"]))
    if missing:
        return [("every instance's piece is in the catalog", False, "piece(s) not in the catalog: %s" % ", ".join(missing))], False
    occupied = {}
    overlaps = set()
    for i in instances:
        fp, _ = piece_at(cat, i["piece"], i["rot"])
        for c in footprint_cells((i["x"], i["z"]), fp):
            if c in occupied:
                overlaps.add((occupied[c], i["id"]))
            else:
                occupied[c] = i["id"]
    rows.append(("no footprint overlaps", not overlaps, "ok" if not overlaps else "%d overlapping instance pair(s): %s" % (len(overlaps), sorted(overlaps)[:5])))
    adjacency, _ = derive_connections(cat, instances)
    entrance = layout.get("entrance", instances[0]["id"])
    rows.append(("entrance is a real instance", entrance in by_id, "entrance id %r" % entrance))
    reachable = set()
    if entrance in by_id:
        frontier = [entrance]
        reachable = {entrance}
        while frontier:
            cur = frontier.pop()
            for n in adjacency.get(cur, ()):
                if n not in reachable:
                    reachable.add(n)
                    frontier.append(n)
    room_ids = sorted(i["id"] for i in instances if cat["pieces"][i["piece"]]["kind"] == "room")
    unreachable = [r for r in room_ids if r not in reachable]
    rows.append(("every room reachable from the entrance", not unreachable, "ok" if not unreachable else "%d of %d room(s) unreachable: %s" % (len(unreachable), len(room_ids), unreachable[:10])))
    return rows, all(ok for _, ok, _ in rows)


def verify_cmd(project, name="layout"):
    cat = load_catalog(project)
    errs = validate(cat)
    if errs:
        raise gg_godot.Refused("catalog is invalid, run gg_dungeon.py catalog-validate: " + errs[0])
    p = layout_path(project, name)
    if not os.path.isfile(p):
        raise gg_godot.Refused("no %s: run gg_dungeon.py layout first" % p)
    try:
        layout = json.load(open(p))
    except json.JSONDecodeError as e:
        raise gg_godot.Refused("%s is not valid JSON: %s" % (p, e))
    rows, ok = verify_layout(cat, layout)
    return (0 if ok else 1), {"rows": rows, "path": p}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("catalog-init"); p.add_argument("--project", required=True); p.add_argument("--pieces-dir", required=True); p.add_argument("--dry-run", action="store_true")
    sub.add_parser("catalog-list").add_argument("--project", required=True)
    sub.add_parser("catalog-validate").add_argument("--project", required=True)
    p = sub.add_parser("layout"); p.add_argument("--project", required=True); p.add_argument("--seed", type=int, required=True); p.add_argument("--rooms", type=int, required=True); p.add_argument("--name", default="layout")
    p = sub.add_parser("verify"); p.add_argument("--project", required=True); p.add_argument("--name", default="layout")
    a = ap.parse_args(argv)
    try:
        project = os.path.abspath(a.project)
        if a.cmd == "catalog-init":
            code, rep = catalog_init(project, a.pieces_dir, a.dry_run)
            if a.dry_run:
                print("catalog-init --dry-run: would add %d piece(s): %s" % (len(rep["would_add"]), ", ".join(rep["would_add"])))
            else:
                print("catalog-init: wrote %d UNCLASSIFIED piece stub(s) to %s: %s (edit kind/footprint/sockets for each, then catalog-validate)" % (len(rep["pieces"]), catalog_path(project), ", ".join(rep["pieces"])))
            return code
        if a.cmd == "catalog-list":
            cat = load_catalog(project)
            for n, p in cat["pieces"].items():
                print("%-20s %-14s footprint %-8s sockets %-2d %s" % (n, p.get("kind"), p.get("footprint"), len(p.get("sockets") or []), p.get("scene")))
            return 0
        if a.cmd == "catalog-validate":
            errs = validate(load_catalog(project))
            for e in errs:
                print("ERROR " + e)
            print("catalog valid" if not errs else "%d problem(s)" % len(errs))
            return 1 if errs else 0
        if a.cmd == "layout":
            code, rep = layout_cmd(project, a.seed, a.rooms, a.name)
            print("layout: placed %d/%d room(s), %d instance(s), %d connection(s) -> %s" % (rep["placed_rooms"], rep["requested_rooms"], len(rep["instances"]), len(rep["connections"]), rep["path"]))
            if code:
                print("FAILED (exit %d): %s" % (code, rep.get("why")))
            return code
        code, rep = verify_cmd(project, a.name)
        for name, ok, detail in rep["rows"]:
            print("  [%s] %s: %s" % ("ok" if ok else "FAIL", name, detail))
        print("gg_dungeon verify: %s (%s)" % ("PASS" if code == 0 else "FAIL", rep["path"]))
        return code
    except (gg_godot.Refused, ValueError, OSError, KeyError, json.JSONDecodeError) as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
