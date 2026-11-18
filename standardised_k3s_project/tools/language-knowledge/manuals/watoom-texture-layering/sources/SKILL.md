---
name: watoom-texture-layering
description: Professional layered texturing for terrain and props - slope/height/curvature/noise masks, splat maps, height-blend, anti-tiling, macro and detail variation, edge wear, triplanar cliffs. Builds splat weight maps from a heightmap (layer_masks.py), a layered PBR material in Blender (blender_layered_material.py) and a layered Godot terrain shader (terrain_layered.gdshader). Use when asked to texture a terrain or asset with several materials, apply layers (rock/dirt/snow/moss/wear), make materials look professional, or fix tiling, stretching, flat or washed-out texturing.
---

# WatooM texture layering

Use the existing watoom-workflow -> watoom-builder serial hierarchy. Load this skill on demand. It sits on top of
`watoom-terrain-map` (terrain shape), `blender-pbr-materials` (single material correctness) and
`blender-texture-baking` (bake for engines); it does not replace them. The rules behind every choice are in
`references/layering-rules.md` and in the `watoom-texture-layering` language-knowledge cards: read those (the
`wlk_*` tools, or ask watoom-investigator/watoom-researcher) when unsure how to layer something.

## Choose the path

| Job | Tool | Where it runs |
|---|---|---|
| Terrain: which texture goes where | `scripts/layer_masks.py` -> splat maps | host python (numpy + pillow), no GPU |
| Terrain: draw those layers in Godot | `templates/terrain_layered.gdshader` | any Godot 4.5+ project |
| Prop/asset: stacked material with wear, moss, snow | `scripts/blender_layered_material.py` | pinned Blender worker (see blender-pbr-materials/references/worker-execution.md) |
| Terrain: into an Unreal Landscape | `scripts/unreal_landscape_export.py` (16-bit heightmap + uint8 weight tiles), applied through the `watoom-ue` tools; then `unreal_creeks.py` and `unreal_scene_scatter.py` for creeks and scenery | host python, then the rig editor |
| Ship to an engine | bake with `blender-texture-baking`, then apply the engine material | worker |

## Terrain in four steps

1. Build the terrain: `watoom-terrain-map/scripts/build_terrain.py` writes `heightmap.exr` + `meta.json`.
2. Copy `templates/layers.example.json`, edit the layers (6 shown: grass fallback, rock, dirt, mud, sand, snow).
3. Generate the weights:
   ```bash
   python3 scripts/layer_masks.py --heightmap <terrain>/heightmap.exr --meta <terrain>/meta.json \
       --spec <terrain>/layers.json --out <terrain>/layers
   ```
   Output: `splat_0.png` (+ `splat_1.png` for layers 5-8), `control_hint.png`, `layer_preview.png`,
   `layer_report.json`. **Check the report**: every layer should have sensible coverage (a layer at 0.00 percent
   or one covering most of the map is a spec bug) and `sum_to_255_everywhere` must be true. Open
   `layer_preview.png` (flat colours) and look at it before going on.
4. In Godot, put `terrain_layered.gdshader` on the terrain material, assign `splat_0/1`, the two Texture2DArrays
   (`layer_albedo_height` = albedo RGB + height A; `layer_normal_rough` = normal RG, rough B, AO A, Non-Color) in
   the same layer order as the report, set `terrain_size`/`terrain_origin` and `layer_uv_scale_*`, and set
   `cliff_layer_mask` to the rock layer's bit. Terrain3D projects keep Terrain3D's painting; use
   `control_hint.png` as the per-pixel intent (the packed control map itself is not written here).

## A prop or asset in Blender

```bash
blender -b scene.blend -P scripts/blender_layered_material.py -- --spec material.json --objects SM_Rock --save out.blend
```
See `templates/material.example.json`. Mask types: slope, height, noise, vertex_color, ao, edges, uniform; every
mask takes `invert`, `contrast` and `noise`. Layers use flat colours or a texture folder (maps found by suffix:
basecolor/normal/roughness/ao, colour spaces set correctly). The script prints `@@JSON@@{ok, nodes, layers,
warnings}`; read `warnings` (a tangent-space normal under box projection is skipped, on purpose).

## Rules that are not optional

- A layered result is not finished until an image of it has been looked at (rules, section 6). Procedural masks
  can look right in the node graph and wrong on the mesh.
- Colour spaces: albedo sRGB, everything else Non-Color. Normals: OpenGL for Blender/Godot, DirectX for Unreal.
- Do not install addons or software to get layering. Everything here uses Blender, Godot and numpy/pillow that are
  already on the hosts. Procedural Blender materials do not export; bake them.
- Keep the layer table (names, order) identical across the mask spec, the splat channels, the texture arrays and
  the engine material.

## Unreal (through the watoom-ue tools)
`scripts/unreal_landscape_material.py` writes the layered-material calls (layer names set correctly) from `layer_report.json`. Full verified run order, the layer-sample `ParameterName` pitfall (use `properties`, not `parameterName`), the required save + level reload, and the viewport/capture notes are in `watoom-game-blueprint/references/engine-unreal.md` ("Verified recipe and gotchas"); read it before building a landscape.
`scripts/unreal_creeks.py` (find the lowest lines, carve creeks, lay water ribbons) and `scripts/unreal_scene_scatter.py` (dense grass, forest, bushes, rocks and a village from the layer weights, avoiding the creek) dress the finished landscape; run the creeks first. The Unreal helpers read the game's numbers (landscape label, height mapping, size, sea level) from one `--project FILE` profile (`templates/unreal_project.example.json`); which script reads which key, and the labels and layer names that are still fixed in the scripts, are listed in the "One project profile for any game" section of `references/unreal-scene.md`. `unreal_landscape_material.py --macro` breaks up a flat single-colour ground. `unreal_scene_scatter.py` also takes a `creek_biomes` recipe (see `templates/creek_biomes.example.json` and the "Planting the creeks in biome sections" section of `references/unreal-scene.md`) that plants whole creek sections as palm/fern, reedy, banana, pandanus, dry-rocky or riparian habitat. `scripts/unreal_island.py` makes an island with a mountain, beaches, cliffs and an ocean; `scripts/unreal_sky.py` makes the permanent nebula sky (sky light from a specified cubemap by default, because the star dome is not an Is-Sky material); `scripts/unreal_ground_fit.py` puts buildings on the ground with a terrain pad. `scripts/unreal_scale_fit.py` fits assets from different packs to one real-world scale. The verified procedure, order and pitfalls are in `references/unreal-scene.md`.

**Before placing any plants or props, read `references/asset-placement.md`**: classify every foliage family (category, habitat, slope, distance to water) in an asset catalog (`templates/asset_catalog.example.json`), look at one at eye level, scatter only with masks, then audit the live level with `tools/rig-ue-mcp/ue_foliage_census.py --catalog` and `ue_foliage_buried.py --in-sea`.

**Building a whole level: follow the "End to end: order, checks and what to do on failure" section at the end of `references/unreal-scene.md`** (profile and catalog first, then terrain, material, sky, land shaping, ground paint, village, scenery, audit, save). Three rules hold at every step: a helper that exits non-zero has not finished (fix the cause, never save over it); judge lighting, materials and colour only with `tools/rig-ue-mcp/ue_viewport_shot.py` and use `editor.capture_scene_png` only for geometry and placement; after any landscape-material change check `editor.get_log` for `Failed to compile` and do the save + reload recipe before looking.

Deep creeks, lakes and sea (read the "Deep creek channel, deep sea, and what actually draws the water" section of `references/unreal-scene.md` first): `scripts/unreal_creek_profile.py` carves a cross-section (deep in the middle, shallow sides, bank rim) along a water spline, or a round bowl for a lake; `scripts/unreal_creek_foliage_fit.py` plans the foliage fix after a carve (driver: `tools/rig-ue-mcp/ue_creek_foliage.py`, dry run first); `scripts/unreal_ocean_depth.py` ramps the flat sea floor down so the water gets deep and dark; `tools/rig-ue-mcp/ue_run_phases.py calls.json` applies any helper's calls with a server load guard. Each script's docstring has its exact command line and each has a `test_*.py`. Order: back up the live heights, run the helper, apply, `landscape.merge_edit_layers {updateNow:true}`, `level.rebuild_water_zone` (on the WaterZone actor), `level.save`, then check in the live viewport (a scene capture does not draw Water-plugin water). Lakes, several creeks, merges and sea mouths: `scripts/unreal_creek_river.py` (water spline from the real bed), `scripts/unreal_creek_extend.py` (`--sea` or `--join`, so no creek stops short of the ocean or a neighbour), `unreal_creek_profile.py --lake ... --spline a --spline b`, and `tools/rig-ue-mcp/ue_place_river.py` (create the WaterBodyRiver from a spline); the numbered sequence is in the "Lakes, all creeks, merging and reaching the sea" section of `references/unreal-scene.md`. Non-Unreal Fab items and placing imported meshes: `tools/fab/rig_vault_fetch.py` (copy FabLibrary downloads from the rig vault) and `tools/rig-ue-mcp/ue_place_assets.py` (manifest placement with ground snapping and tree clearing); procedure in the "Fab downloads that are not Unreal packs, and placing imported meshes" section of `references/unreal-scene.md`.

Round lakes with a Water-plugin body: `tools/rig-ue-mcp/ue_lake_as_waterbody.py` (a `WaterBodyLake`, never a closed-loop river), then `tools/rig-ue-mcp/ue_lake_check.py` on the bed and `tools/rig-ue-mcp/ue_viewport_shot.py --around` from several angles and distances; read the "Lakes as WaterBodyLake, and repairing a lake bed" section of `references/unreal-scene.md` first. Apply every height calls json only with `tools/rig-ue-mcp/ue_run_phases.py`: it subtracts the Water layer's offset before a base-layer write, so a carved lake bed is not carved twice. Give lakes the creeks' material (`--material /Game/ZAS/Water/MI_ZAS_River.MI_ZAS_River`; `--materials-only` switches an existing lake). Once every creek and lake exists, build berms so no water shows past its shape: `tools/rig-ue-mcp/ue_water_fetch.py` then `scripts/unreal_water_berms.py`, applied with `ue_run_phases.py`, then `ue_creek_foliage.py` (read the "Berms along creeks and around lakes" section of `references/unreal-scene.md` first).

1. `unreal_landscape_export.py heightmap ... --vertices 1009` writes `heightmap16.png` (16-bit; ue-mcp refuses 8-bit) and
   `unreal_plan.json`. The vertex count must be a legal landscape size (127, 253, 505, 1009, 2017, 4033, 8129); the script
   refuses others and lists neighbours.
2. In `watoom-ue`: `landscape.plan_real_world` with the plan's arguments, then `landscape.create`, then
   `landscape.import_heightmap`. Look up each action's card (`wlk_symbol`, product `ue-mcp`) and `describe` it before the first call.
3. `unreal_landscape_export.py weights --layers <layer_masks out> --vertices 1009` writes uint8 tiles that sum to 255 at every
   vertex. Register layers with `landscape.add_layer`, write EVERY layer per tile with `landscape.set_layer_weight_region`
   (the engine does not renormalise), read one back with `get_layer_weight_region` and compare.
4. Check a corner of heights and weights against the source; use `--flip-y` if the terrain is mirrored.
The route allows every action (opened by the owner 2026-11-14), so prefer the dedicated action over `execute_python`/console, and do not run builds, plugin or source-control actions unless the task asks for them.

## What is verified and what is not

Verified by tests (`scripts/test_*.py`, run on the lab): the heightmap reader against the real EXR writer, the
weight maths (sum-to-255, rules land where specified, deterministic), all mask types build in Blender 5.2, a render
shows grass/rock/snow where the masks say, colour spaces, the shader compiles in Godot 4.7.2 (parser, headless).
Not verified: the shader's rendered look and performance on a GPU and Terrain3D control-map import; those need a GPU and a visual review, say so in the handoff.
Unreal: every helper's output is unit-tested, and the steps in `references/unreal-scene.md` were each run on the rig (UE 5.8.4, since 2026-11-14) unless that page marks one as unverified; the whole sequence as one run and the look of the result still need a viewport picture and a review.
