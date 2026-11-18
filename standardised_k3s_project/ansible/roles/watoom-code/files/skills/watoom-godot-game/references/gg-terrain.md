# Terrain: heights, layer weights, material (stage c)

Run from `scripts/`. Needs an initialised project (`gg_project.py init`, `gg_style.py apply`).

1. `gg_terrain.py heights --project P --shape island --relief-m 40` writes `gg_data/world/heights.png` (16-bit), `heights.f32`, `world.json`. Shapes: island, hills, plateau, flat, valley, ramp. Same seed gives the same bytes. It warns when the sea level is outside the terrain.
2. `gg_terrain.py layers --project P` runs `watoom-texture-layering/scripts/layer_masks.py` with `templates/layers.<preset>.json`. Weights must sum to exactly 255 everywhere. It warns when a layer covers under 0.5% (never appears) or over 90%.
3. `gg_terrain.py build --project P` builds `res://levels/<level>/terrain.tscn` (chunked mesh, HeightMapShape3D collider, splat material) and then checks it.

## World facts (measured in Godot 4.7.2)
- +Y is up. Image column maps to +X, image row to +Z. Vertex (i, j) sits at (i*cell_m, height, j*cell_m). Splat uv = (world.xz - origin) / size, so image row 0 is the lowest Z.
- Layer colours are separate shader uniforms (`layer_color_0..7`). An array uniform read back as null after save and reload.
- Colour space: terrain shader layer colours are source_color (sRGB in the file).

## What `build` checks (exit 1 on any failure)
- Collider vs data: 64 raycasts at random vertices, max error <= 0.05 m and no misses.
- Mesh y range equals the data range.
- The weight maps on disk are re-derived from heights.png with the recorded spec; any difference (flipped, edited, made from other heights) is refused with exit 2 before the engine runs. `heights` deletes old layers and the build marker, and `layers` and `build` refuse stale inputs by heights hash.
- A passing build writes `gg_data/world/build_ok.json` (heights hash); `gg_light.py` refuses a level without it. `--no-check-view` skips the render check and does not write it.
- Top-down render (fog off): per-cell layer classes are compared with the weight maps. Needs agreement >= 0.75, every layer with 5% coverage recall >= 0.4, and the measured layer colours at least 0.02 apart. The check also fails when a mirrored or transposed variant agrees better (by more than 0.02) than the real render: the axes are swapped. If a variant is merely close (within 0.08) the build passes with a NOTE that this terrain is too symmetric to prove orientation by render.
- On an island the flipped variants score 0.74-0.77 against 0.90-0.93 for the real one (all four presets), so the island build passes with that NOTE. For a real orientation proof use `--shape ramp` with `--spec templates/layers.orientation_probe.json` (measured: agreement 0.99, flip_x 0.50, flip_z 0.76, transpose 0.62).

## Failure procedure
Black or uniform terrain with a clean log: read `gg_data/terrain_check/top.png`; check the layer colours and that `layers` ran after `heights`. Refusals name both sizes (heights vs weight maps). Re-run `heights`, then `layers`, then `build`.

## Verified vs not
Verified by running (Godot 4.7.2, lab): build + checks on low-poly, realistic, stylised-painterly and pixel-art 3D islands (256 m, 4 m cells); ramp orientation probe on low-poly; a deliberately flipped splat file is refused (exit 2). Not verified: other world sizes, a render-side mirror (the shader reading splats flipped) was not injected, pixel-art 2D (no terrain in 2D), water/creek cut (stage d).
