"""Bounded explicit board topology for the existing dungeon pipeline; no executable input."""

import copy, hashlib, json, math


def validate(value):
    if not isinstance(value, dict) or set(value) - {
        "cols",
        "rows",
        "cell_cm",
        "rock_cells",
        "wall_edges",
        "door_edges",
    }:
        raise ValueError("Unknown fixed-layout field")
    cols = value.get("cols")
    rows = value.get("rows")
    cell = value.get("cell_cm", 200)
    if (
        type(cols) is not int
        or type(rows) is not int
        or not 2 <= cols <= 32
        or not 2 <= rows <= 32
        or type(cell) is not int
        or not 150 <= cell <= 400
    ):
        raise ValueError("Fixed board dimensions outside bounds")

    def point(v):
        if (
            not isinstance(v, list)
            or len(v) != 2
            or any(type(x) is not int for x in v)
            or not 0 <= v[0] < cols
            or not 0 <= v[1] < rows
        ):
            raise ValueError("Invalid board cell")
        return tuple(v)

    rocks = value.get("rock_cells", [])
    if not isinstance(rocks, list) or len(rocks) > cols * rows:
        raise ValueError("Invalid rock cells")
    rocks = [point(v) for v in rocks]
    if len(set(rocks)) != len(rocks):
        raise ValueError("Duplicate rock cell")
    covered = {(x, y) for x in range(cols) for y in range(rows)} - set(rocks)
    if len(covered) < 2:
        raise ValueError("At least two walkable cells required")
    result = {"cols": cols, "rows": rows, "cell_cm": cell, "rock_cells": [list(v) for v in sorted(rocks)]}
    for field in ("wall_edges", "door_edges"):
        values = value.get(field, [])
        if not isinstance(values, list) or len(values) > 2048:
            raise ValueError("Edge budget exceeded")
        edges = []
        for edge in values:
            if not isinstance(edge, list) or len(edge) != 2:
                raise ValueError("Invalid board edge")
            a, b = map(point, edge)
            if a not in covered or b not in covered or abs(a[0] - b[0]) + abs(a[1] - b[1]) != 1:
                raise ValueError("Edges must join adjacent walkable cells")
            edges.append(tuple(sorted((a, b))))
        if len(set(edges)) != len(edges):
            raise ValueError("Duplicate board edge")
        result[field] = [[list(a), list(b)] for a, b in sorted(edges)]
    return result


def assemble(base, options, adapters):
    board = validate(options)
    plan = copy.deepcopy(base)
    cols, rows, cell = board["cols"], board["rows"], board["cell_cm"]
    floor = {(x, y) for x in range(cols) for y in range(rows)} - {tuple(v) for v in board["rock_cells"]}
    cells = sorted(floor)
    ids = {v: i for i, v in enumerate(cells)}
    walls = {tuple(map(tuple, v)) for v in board["wall_edges"]}
    doors = {tuple(map(tuple, v)) for v in board["door_edges"]}
    placements = []
    rooms = []
    connections = []

    def place(role, position, yaw, room):
        adapter = adapters[room % len(adapters)]
        module = adapter["modules"][role][0]
        scale = cell / adapter["tile_cm"]
        parts = module.get("parts") or [
            {"object_path": module["object_path"], "position_cm": [0, 0, 0], "rotation": [0, 0, 0], "scale": [1, 1, 1]}
        ]
        pivot = module.get("pivot_offset_cm", [0, 0, 0])
        angle = math.radians(yaw)
        for part in parts:
            local = [(a + b) * scale for a, b in zip(part["position_cm"], pivot)]
            offset = [
                local[0] * math.cos(angle) - local[1] * math.sin(angle),
                local[0] * math.sin(angle) + local[1] * math.cos(angle),
                local[2],
            ]
            rotation = part["rotation"].copy()
            rotation[1] += yaw
            placements.append(
                {
                    "asset": part["object_path"],
                    "role": role,
                    "room": room,
                    "position": [round(a + b, 6) for a, b in zip(position, offset)],
                    "yaw": rotation[1],
                    "rotation": rotation,
                    "scale": [v * scale for v in part["scale"]],
                    "lod": module.get("lod", 0),
                }
            )
            if len(placements) > 4096:
                raise ValueError("Fixed board exceeds4096-piece budget")

    for c, r in cells:
        room = ids[(c, r)]
        center = [(c + 0.5) * cell, (r + 0.5) * cell, 0]
        rooms.append(
            {
                "id": room,
                "level": 0,
                "cell": [c, r],
                "position": center,
                "size": [cell, cell],
                "archetype": "start" if room == 0 else "ordinary",
            }
        )
        place("floor", center, 0, room)
        for dx, dy, yaw in [(1, 0, 90), (-1, 0, 270), (0, 1, 0), (0, -1, 180)]:
            neighbour = (c + dx, r + dy)
            edge = tuple(sorted(((c, r), neighbour)))
            boundary = neighbour not in floor
            if boundary or edge in walls or edge in doors:
                if not boundary and (c, r) > neighbour:
                    continue
                place(
                    "doorway" if edge in doors else "wall",
                    [center[0] + dx * cell / 2, center[1] + dy * cell / 2, 0],
                    yaw,
                    room,
                )
            if neighbour in floor and (c, r) < neighbour and (edge not in walls or edge in doors):
                connections.append(
                    {"from": room, "to": ids[neighbour], "kind": "door" if edge in doors else "corridor"}
                )
    plan.update(
        layout={"mode": "fixed-grid", "rooms": rooms, "connections": connections, "stairs": []},
        placements=placements,
        effective_options={
            "mode": "fixed-grid",
            "cols": cols,
            "rows": rows,
            "cell_cm": cell,
            "board_cm": [cols * cell, rows * cell],
        },
        fixed_layout=board,
    )
    plan["qa"]["logical_connectivity"] = "NOT TESTED; explicit disconnected regions preserved"
    stable = {k: v for k, v in plan.items() if k not in ("files", "plan_sha256")}
    stable["files"] = {
        name: {key: item[key] for key in ("id", "sha256", "bytes")} for name, item in plan["files"].items()
    }
    stable["portable_modules"] = [{k: v for k, v in item.items() if k != "file"} for item in plan["portable_modules"]]
    plan["plan_sha256"] = hashlib.sha256(json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return plan
