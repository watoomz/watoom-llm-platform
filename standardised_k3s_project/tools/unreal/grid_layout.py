"""Bounded grid-to-static-actor plan; no Unreal import or build toolchain needed."""

import hashlib, json

DIRECTIONS = {"n": (0, -1), "e": (1, 0), "s": (0, 1), "w": (-1, 0)}
OPPOSITE = {"n": "s", "s": "n", "e": "w", "w": "e"}


def prepare(layout):
    try:
        return _prepare(layout)
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("Malformed grid layout: " + type(error).__name__ + " " + str(error)[:120]) from error


def _prepare(layout):
    grid = layout["grid"]
    cols = grid["cols"]
    rows = grid["rows"]
    size = grid["cell_cm"]
    if type(cols) != int or type(rows) != int or not 2 <= cols <= 32 or not 2 <= rows <= 32 or not 150 <= size <= 400:
        raise ValueError("Bounded grid dimensions required")
    cells = {}
    for cell in layout["cells"]:
        key = (cell["col"], cell["row"])
        if any(type(x) != int for x in key):
            raise ValueError("Integer cell coordinates required")
        if (
            key in cells
            or not 0 <= key[0] < cols
            or not 0 <= key[1] < rows
            or type(cell["floor"]) != bool
            or set(cell["walls"]) != set(DIRECTIONS)
            or any(type(x) != bool for x in cell["walls"].values())
        ):
            raise ValueError("Invalid/duplicate grid cell")
        cells[key] = cell
    if len(cells) != cols * rows:
        raise ValueError("Incomplete grid")
    placements = []
    edges = set()
    walk = {key for key, c in cells.items() if c["floor"]}
    if not walk:
        raise ValueError("No floor")
    for (c, r), cell in sorted(cells.items()):
        placements.append(
            {
                "role": "floor" if cell["floor"] else "rock",
                "cell": [c, r],
                "position": [c * size, r * size, -5 if cell["floor"] else 150],
                "scale": [size / 100, size / 100, 0.1 if cell["floor"] else 3],
            }
        )
        if not cell["floor"]:
            continue
        for side, (dx, dy) in DIRECTIONS.items():
            other = (c + dx, r + dy)
            if other in walk and cell["walls"][side] != cells[other]["walls"][OPPOSITE[side]]:
                raise ValueError("Asymmetric wall")
            if not cell["walls"][side]:
                continue
            edge = tuple(sorted(((c, r), other)))
            if edge in edges:
                continue
            edges.add(edge)
            horizontal = dy != 0
            placements.append(
                {
                    "role": "wall",
                    "edge": [list(x) for x in edge],
                    "position": [(c + dx / 2) * size, (r + dy / 2) * size, 150],
                    "scale": [size / 100 if horizontal else 0.2, 0.2 if horizontal else size / 100, 3],
                }
            )
    # Every floor cell must be reachable through open sides; islands are rooms nobody can enter.
    regions = 0
    seen = set()
    for start in sorted(walk):
        if start in seen:
            continue
        regions += 1
        stack = [start]
        seen.add(start)
        while stack:
            c, r = stack.pop()
            for side, (dx, dy) in DIRECTIONS.items():
                other = (c + dx, r + dy)
                if other in walk and other not in seen and not cells[(c, r)]["walls"][side]:
                    seen.add(other)
                    stack.append(other)
    if regions > 1 and layout.get("allow_disconnected_floors") is not True:
        raise ValueError("%d disconnected floor regions; open a wall/door or set allow_disconnected_floors" % regions)
    doors = layout.get("door_edges", [])
    if not isinstance(doors, list) or any(
        not isinstance(d, list)
        or len(d) != 2
        or any(not isinstance(x, list) or len(x) != 2 or any(type(v) != int for v in x) for x in d)
        for d in doors
    ):
        raise ValueError("door_edges: [[[col,row],[col,row]], ...]")
    for a, b in doors:
        a = tuple(a)
        b = tuple(b)
        if a not in walk or b not in walk or abs(a[0] - b[0]) + abs(a[1] - b[1]) != 1 or tuple(sorted((a, b))) in edges:
            raise ValueError("Door is blocked or invalid")
    if len(placements) > 4096:
        raise ValueError("Actor budget exceeded")
    return {
        "schema": "grid-static-map/v1",
        "grid": grid,
        "placements": placements,
        "floor_cells": [list(x) for x in sorted(walk)],
        "door_edges": doors,
        "floor_regions": regions,
        "layout_sha256": hashlib.sha256(json.dumps(layout, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "navigation": "NOT TESTED",
    }
