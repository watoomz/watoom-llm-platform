"""Deterministic, bounded dungeon topology for the existing world pipeline.
Coordinates are Unreal centimetres. Module placement/rendering are separate gates.
"""
import collections, random

def layout(seed, rooms=12, levels=1, grid=8, cell_size=800, room_size=600, floor_height=400):
    if type(seed) is not int or not -(2**31) <= seed < 2**31:
        raise ValueError("seed must be a signed 32-bit integer")
    for value in (rooms, levels, grid, cell_size, room_size, floor_height):
        if type(value) is not int:
            raise ValueError("layout dimensions must be integers")
    if not 1 <= levels <= 4 or not 2*levels <= rooms <= 64 or not 2 <= grid <= 16:
        raise ValueError("rooms/levels/grid exceed supported bounds")
    if (rooms+levels-1)//levels > grid*grid:
        raise ValueError("grid cannot hold requested rooms per level")
    if not 200 <= room_size < cell_size <= 2000 or not 300 <= floor_height <= 1200:
        raise ValueError("unsupported centimetre dimensions")
    rng=random.Random(seed)
    nodes=[];edges=[];stairs=[]
    origin=(grid//2,grid//2)
    first=[]
    for level in range(levels):
        count=rooms//levels+(level < rooms%levels)
        cells={origin:len(nodes)}
        first.append(len(nodes))
        def add(cell):
            index=len(nodes)
            nodes.append({"id":index,"level":level,"cell":list(cell),
                          "position":[cell[0]*cell_size,cell[1]*cell_size,level*floor_height],
                          "size":[room_size,room_size]})
            return index
        add(origin)
        frontier=[]
        def extend(cell):
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                if levels>1 and cell==origin and (dx,dy)==(1,0):continue # reserve the east stair bay
                dest=(cell[0]+dx,cell[1]+dy)
                if 0 <= dest[0] < grid and 0 <= dest[1] < grid and dest not in cells:
                    frontier.append((cell,dest))
        extend(origin)
        while len(cells)<count:
            offset=rng.randrange(len(frontier))
            parent,cell=frontier.pop(offset)
            if cell in cells:
                continue
            index=add(cell)
            cells[cell]=index
            edges.append({"from":cells[parent],"to":index,"kind":"corridor"})
            extend(cell)
        if level:
            edge={"from":first[level-1],"to":first[level],"kind":"stairs"}
            edges.append(edge);stairs.append(edge.copy())
    graph=collections.defaultdict(list)
    for edge in edges:
        graph[edge["from"]].append(edge["to"]);graph[edge["to"]].append(edge["from"])
    distance={0:0};queue=collections.deque([0])
    while queue:
        source=queue.popleft()
        for dest in graph[source]:
            if dest not in distance:
                distance[dest]=distance[source]+1;queue.append(dest)
    assert len(distance)==rooms
    exit_room=max((n["id"] for n in nodes if n["level"]==levels-1),key=lambda n:(distance[n],n))
    return {"schema":1,"status":"LAYOUT_ONLY","seed":seed,"units":"centimetres",
            "rooms":nodes,"connections":edges,"stairs":stairs,"entrance":0,"exit":exit_room,
            "native_asset_placement_verified":False}


def main(argv=None):
    """CLI: write a layout as JSON (the input of watoom-unreal-combat/scripts/unreal_dungeon.py, T-0015)."""
    import argparse, json
    ap = argparse.ArgumentParser(description="Deterministic dungeon layout -> JSON")
    ap.add_argument("--seed", type=int, required=True)
    for name, default in (("rooms", 12), ("levels", 1), ("grid", 8), ("cell-size", 800), ("room-size", 600), ("floor-height", 400)):
        ap.add_argument("--" + name, type=int, default=default)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    r = layout(a.seed, rooms=a.rooms, levels=a.levels, grid=a.grid, cell_size=a.cell_size, room_size=a.room_size,
               floor_height=a.floor_height)
    with open(a.out, "w") as f:
        json.dump(r, f, indent=1)
    print("%s: %d rooms, %d connections, entrance %d, exit %d" % (a.out, len(r["rooms"]), len(r["connections"]), r["entrance"], r["exit"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
