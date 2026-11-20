# gg-dungeon: modular kit catalog + procedural grid layout (T-0059)

A dungeon-crawler pipeline for the owned modular dungeon kits (dungeon-forge, dungeon-builder, modular-dungeon
x2, modular-castle-dungeon, ancient-ruins-temple, crownfall-cathedral). **All of these kits are Unreal
`.uasset`-only on disk today.** Converting one to `.glb`/`.tscn` through the `unreal-export` bridge is a
separate, rig-touching piece of work, tracked on its own, not part of this stage. `gg_dungeon.py` only builds the
parts that do not need the rig: the kit-catalog format/tooling and the layout generator itself, over
already-converted `res://` scene pieces. Until that export happens, build and validate a catalog against a small
synthetic/placeholder kit (a few empty `.tscn`/`.glb` stub files you classify by hand) to prove the pipeline; do
not claim a real kit works until it has gone through `unreal-export` and been classified here.

## Why this is not the Unreal dungeon tooling

`tools/watoom-toolkit/dungeon_*.py` and `tools/unreal/dungeon-*.py` are a separate, already-built system for the
Unreal side (abstract grid rooms/corridors with no real modular pieces or sockets; see
`docs/WATOOM_UNREAL_DUNGEON.md`). This stage is the Godot worker equivalent, and the two problems are shaped
differently: the Unreal pipeline lays out abstract room cells of a fixed size, where this stage must place real
kit PIECES (each its own footprint and door-opening positions) so neighbouring pieces' openings actually line up.
Do not conflate or merge the two; do not edit the Unreal-side files for this ticket.

## Catalog: `gg_dungeon.json`

Same shape as `gg_catalog.json` (named pieces, `init`/`list`/`validate` subcommands) but for modular room/
corridor/junction pieces instead of foliage: each piece carries a grid-cell **footprint** and **socket**
(door-opening) metadata instead of height/slope/water habitat rules.

```json
{"schema": 1, "cell_m": 4.0, "pieces": {
  "room_square": {"kind": "room", "scene": "res://assets/dungeon/room_square.tscn", "footprint": [2, 2],
                  "sockets": [{"edge": "north", "pos": 0}, {"edge": "south", "pos": 0}, {"edge": "east", "pos": 0}, {"edge": "west", "pos": 0}],
                  "notes": ""},
  "corridor_1x2": {"kind": "corridor", "scene": "res://assets/dungeon/corridor_1x2.tscn", "footprint": [1, 2],
                   "sockets": [{"edge": "north", "pos": 0}, {"edge": "south", "pos": 0}], "notes": ""}
}}
```

- `cell_m`: metres per grid cell (pick to match the kit's own module size, e.g. 4.0).
- `kind`: `room` | `corridor` | `junction` | `prop`. `room`/`corridor`/`junction` are placed by `layout`; `prop`
  pieces (decoration) are catalog-only for now and never placed procedurally.
- `footprint`: `[width_cells, depth_cells]`, the piece's own UNROTATED size along x (width) and z (depth).
- `sockets`: each `{"edge": "north"|"east"|"south"|"west", "pos": int}` is a door opening on that edge of the
  UNROTATED footprint, `pos` being its 0-based offset along the edge (`0..width_cells-1` for north/south,
  `0..depth_cells-1` for east/west). `layout` tries every 90-degree rotation of every piece, so you only ever
  describe sockets in the piece's own unrotated orientation.
- A `room`/`corridor`/`junction` piece needs at least one socket (otherwise it can never connect to anything);
  a `prop` piece does not.
- There is no `verified`/`verified_sha` binding and no `inspect` subcommand in this stage, unlike `gg_catalog.py`:
  there is nothing real to render yet. A render/visual check (black/glowing/scale/lying-down checks on a real
  converted piece, the `gg_catalog.py inspect` equivalent) is explicit follow-on work once the export exists —
  do not treat the absence of that check as "pieces are visually fine."

## Commands

```bash
python3 scripts/gg_dungeon.py catalog-init     --project P --pieces-dir res://assets/dungeon/kit1 [--dry-run]
python3 scripts/gg_dungeon.py catalog-list     --project P
python3 scripts/gg_dungeon.py catalog-validate --project P
python3 scripts/gg_dungeon.py layout           --project P --seed 1 --rooms 8 [--name layout]
python3 scripts/gg_dungeon.py verify           --project P [--name layout]
```

`catalog-init` scans `--pieces-dir` (a project-local `res://` folder, recursively) for every `.tscn`/`.glb` file
and writes one UNCLASSIFIED stub piece per file (`kind: "unclassified"`, `footprint: [1, 1]`, no sockets) — it
does not call the engine and does not guess a real footprint or sockets from the mesh, the same way
`gg_catalog.py add` does not guess habitat rules. Hand-edit `gg_dungeon.json` for each stub (kind, footprint,
sockets, same convention as `gg_catalog.json`'s own `_comment`: edit the file directly), then run
`catalog-validate` until it passes. Refuses if `gg_dungeon.json` already exists, or if the directory has no
`.tscn`/`.glb` files.

`catalog-validate` checks the schema above only (name shape, kind, footprint bounds, socket edge/pos bounds and
duplicates, connectable kinds needing a socket). It does not check that `scene` points at a file that exists, the
same as `gg_catalog.py validate`.

## Layout: the procedural generator

`layout --seed N --rooms N` is a deterministic, bounded randomized grower (same `numpy.random.default_rng(seed)`
convention as `gg_scatter.py`, so the SAME seed over the SAME catalog always produces byte-identical output):

1. Place the first `kind: "room"` piece (sorted by name, for determinism) at grid origin `(0, 0)`, rotation 0.
   This is the entrance (`instances[0]`, `entrance: 0` in the output).
2. Maintain a pool of every placed piece's still-open sockets. Repeatedly: pick one open socket at random (seeded),
   try every OTHER connectable piece (`room`/`corridor`/`junction` with at least one socket) at every rotation
   that has a socket facing the right way, in a seeded random order, and place the first candidate whose footprint
   does not collide with anything already placed. The piece just used to extend a `room`/`corridor`/`junction`
   that is itself a room counts toward `--rooms`.
3. Stop once `--rooms` room-kind pieces are placed, or no open socket can be extended further (a dead end is left
   open — not every doorway needs to lead somewhere), or a generous attempt bound is hit.

Output (`gg_data/dungeon/<name>.json`, default name `layout`): `instances` (`id`, `piece`, `x`, `z`, `rot` — `x`/`z`
are the piece's grid origin, `rot` is a 0..3 quarter-turn count clockwise) and `connections` (what the generator
believes it built, `a`/`a_edge`/`a_pos`/`b`/`b_edge`/`b_pos`). `layout` exits 1 (but still writes the file) if it
placed fewer than half the requested rooms: add catalog pieces (especially corridor/junction variety) or lower
`--rooms`. Needs a `catalog-validate`-clean catalog with at least one `room` piece and at least one connectable
piece with a socket (which may be the room piece itself — a catalog with only rooms that have sockets on every
edge can still lay out a dungeon, rooms directly touching rooms).

## Verify: the independent connectivity/overlap audit

`verify` NEVER trusts `layout`'s own `connections` field (the same "trust the artifact, not the plan" principle
as `gg_census.py` auditing a built scatter scene instead of trusting `gg_scatter.json`). It recomputes, from
`instances` alone:

- **No footprint overlaps**: every instance's rotated footprint cells, checked pairwise for collisions.
- **Every room reachable from the entrance**: an adjacency graph is derived fresh by checking, for EVERY socket
  of EVERY instance, whether the cell immediately outside it is exactly the matching (opposite-edge) socket's
  anchor cell of some OTHER instance — then BFS's from `entrance` over that graph and checks every `kind: "room"`
  instance is reached.

Exit 0 only if both pass. A failing row names what broke (how many rooms are unreachable and their ids, or how
many instance pairs overlap and which).

## Rotation geometry (if you need to hand-build or debug a layout file)

A piece's `footprint`/`sockets` are defined unrotated; `rot` is how many 90-degree clockwise turns are applied
before placing it at `(x, z)`. One clockwise turn: `(width, depth) -> (depth, width)`, and each socket's edge
cycles `north -> east -> south -> west -> north`; a socket's `pos` only changes on the `east -> south` and
`west -> north` steps, where it becomes `(the CURRENT footprint's depth at that step) - 1 - pos` (four turns is
always the identity). `gg_dungeon.py`'s `rotate_once`/`rotate` are the pure functions that do this; `socket_anchor`
gives a socket's inside cell at a given origin, `socket_outside` the cell just beyond it (what a connecting
piece's matching socket must occupy).

## Not built yet (be honest about this)

- No render/visual check (the `gg_catalog.py inspect` equivalent): nothing to render until a real kit is
  converted. `verify`'s connectivity/overlap audit is pure grid logic and proves nothing about what the dungeon
  actually looks like once built in Godot.
- No subcommand builds an actual `.tscn` level from a layout (the way `gg_scatter.py run` builds
  `scatter.tscn`); `layout`/`verify` work entirely on JSON. Building the real level scene from a verified layout
  is the natural next step once pieces exist to place.
- No automatic footprint/socket inference from mesh geometry: `catalog-init` writes stubs; a human (or the model,
  carefully) classifies each piece by hand, the same way `gg_catalog.py add` needs a human-chosen category.
- `unreal-export` of any of the owned dungeon kits is explicitly out of scope here and untouched by this ticket.
