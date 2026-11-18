---
name: watoom-terrain-map
description: Generate a new game map / world terrain from a real-world location. Trigger whenever someone asks to "generate/make/build a new map", a "world map", or "game terrain" for a place or latitude/longitude — it fetches open elevation (DEM) data and emits a ready Godot terrain mesh + collision + rural material. Accepts a place name (geocoded) or raw lat/long. Not for city layouts, roads or satellite imagery.
---

# Real-world terrain pipeline (lat/long → Godot terrain)

Turn any latitude/longitude into a playable Godot terrain that replicates the real
landform. Elevation comes from **open DEM tiles** (AWS terrarium, SRTM/Copernicus
based) — factual, openly licensed data. **No Google or proprietary map data, no
satellite imagery, and no roads/buildings** are used; only the topography. This
keeps results rural by construction and clear of map-provider IP.

## Run it

```bash
# by place name (geocoded via OpenStreetMap):
python3 /path/to/skills/watoom-terrain-map/scripts/build_terrain.py \
    --place "Lake Manchester, Queensland" \
    --size 4000 --out /data/ai/projects/games/<project>/World/terrain

# or by exact coordinates:
python3 .../build_terrain.py --lat -27.3981546 --lon 152.9481812 \
    --size 4000 --out /data/ai/projects/games/<project>/World/terrain
```

Give either `--place "<name>"` **or** `--lat/--lon`.

Runs on the homelab host (needs `numpy` + `pillow`); it writes plain files, no
container or GPU. Key options:

- `--size` square map edge in metres (default 4000 = 4 km × 4 km).
- `--zoom` DEM tile zoom 12–15 (default 14; higher = finer source sampling, more tiles).
- `--grid` heightmap resolution per side (default 513).
- `--mesh-resolution` mesh quads per side (default 256; clamped to grid − 1).
- `--vscale` vertical exaggeration (default 1.0 = true to life).
- `--name` scene base name (default `terrain`).

## What it writes into `--out`

| File | Purpose |
|---|---|
| `heightmap.exr` | single-channel 32-bit float heightmap, **uncompressed** (value 0..1 ↔ `min_elev_m`..`max_elev_m`); Godot loads it at full precision |
| `heightmap_preview.png` | 8-bit preview for humans only — never derive heights from it |
| `meta.json` | centre lat/lon, size, grid, elevation range, metres/sample, data source |
| `terrain.gd` | generic `@tool` builder: ArrayMesh (normals+UVs) + `HeightMapShape3D` collider at true world scale, plus `height_at(x, z)` |
| `terrain_material.gdshader` | rural material — grass/dirt/rock by slope+elevation with procedural detail |
| `<name>.tscn` | ready scene with the heightmap path and real elevation range wired in |

## Use it in a project

Point `--out` inside the project's Godot tree (e.g. `World/terrain`) so the
pipeline writes correct `res://` paths. Then **instance `<name>.tscn`** in the game
scene, or in the editor select the Terrain node and tick **Build Now** to
regenerate. At runtime it builds in `_ready()`. The terrain is centred on its
origin, X/Z span `--size` metres, Y is real elevation (scaled by `--vscale`).

Only `heightmap.exr` + the `.tscn`'s elevation values change per location; the
`.gd` and shader are identical everywhere, so the same pipeline serves every
WatooM project. Re-run with a new `--lat/--lon` to retarget. Larger worlds: raise
`--size` and `--max-tiles`; keep `--mesh-resolution` within the engine's budget
and add streaming/LOD separately if needed.

## Placing things and capturing the terrain

- **Never hard-code or guess a ground Y.** Real terrain is not flat and the map
  origin is neither `min_elev_m` nor `max_elev_m`. After adding the terrain to the
  tree, ask it: `var gy: float = terrain.height_at(x, z)`, then put characters at
  `gy + small_offset` and aim cameras at `Vector3(x, gy + subject_height, z)`.
  Do not hand-decode the EXR or read the PNG preview to find heights.
- **Capture environment:** use the maintained `CaptureEnvironment.attach(self,
  CaptureEnvironment.LANDSCAPE_FOG_DENSITY)` for terrain views. Do not hand-roll
  fog, and never set `fog_height_density` — height fog buries everything below
  `fog_height` in one flat colour.
- **Wide views:** keep the camera's `far` beyond the view distance plus the part
  of the map you want visible (e.g. `far = 5000.0` for a 4 km map), and aim at
  the ground under the subject, not into the void.
- **"Flat single-colour field" in a capture** means the camera sees no terrain
  (underground, culled, fogged out or clipped by `far`), not that the terrain
  lacks detail. Check placement with `height_at()` before changing materials.
- **Regenerating:** re-run `build_terrain.py` to refresh an existing project's
  `terrain.gd`/shader from this template (the template fixed an upside-down mesh
  on 2026-11-06 — older copies render invisible from above).

## Alternative output: Terrain3D (multi-layer texture painting, foliage, streaming)

The `terrain.gd` path above is the default: one static mesh, good for most
projects. If a project specifically needs texture-painted layers, foliage
instancing or region streaming, bake the same heightmap into a native
**Terrain3D** (github.com/TokisanGames/Terrain3D, vendored under `vendor/`,
see `vendor/PROVENANCE.md` for version/license/trim details) instead:

```bash
python3 scripts/install_terrain3d.py --heightmap <out>/heightmap.exr \
    --min <min_elev_m from meta.json> --max <max_elev_m from meta.json> \
    --project /data/ai/projects/games/<project> \
    --out World/terrain/terrain3d_data
```

This installs the addon into the target project, bakes the heightmap into
Terrain3D's own region format headlessly, and writes a ready
`World/terrain/terrain3d.tscn` to instance. It does not touch `build_terrain.py`'s
own `terrain.gd`/`.tscn` output -- the two are independent; pick one per project
(or keep both and decide which to instance). Texture painting and foliage
placement still need the real Godot editor with a display/GPU (the rig) --
this script only gets the terrain's shape in place automatically.

## Notes

- A capture/visual review of the result still goes through the normal vision gate;
  the mesh is the deliverable, framing/lighting for review is the scene's job (see
  `watoom-engine-visual-diagnosis`).
- DEM source resolution is ~30 m; `--grid`/`--zoom` above that interpolate (smooth)
  rather than invent detail. Add erosion/decoration as a later pass if wanted.
- For an **Unreal** project, the `heightmap.png` this pipeline produces is a valid
  input to the owned `watoom-landscape-mesh-builder` (UE5 heightmap→static-mesh
  bake); this skill only builds the Godot side.
