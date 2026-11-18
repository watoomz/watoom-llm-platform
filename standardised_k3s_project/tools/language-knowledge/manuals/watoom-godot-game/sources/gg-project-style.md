# Project profile and style presets (stage b)

Style is data. A game is one `gg_project.json` plus one preset (`presets/<name>.json`) plus optional overrides. Nothing
about look is written in code: change the data, run `gg_style.py apply`, shoot, measure.

## Make a project

```bash
S=<skill>/scripts
python3 $S/gg_project.py doctor
python3 $S/gg_project.py init --project /path/to/game --name castaway_cove --dimension 3d --view third_person --style low-poly --size-m 400 400 --dry-run
python3 $S/gg_project.py init --project /path/to/game --name castaway_cove --dimension 3d --view third_person --style low-poly --size-m 400 400
```
`init` refuses: a non-empty directory with no `project.godot`; a `project.godot` it did not create (unless `--adopt`); a directory that already has `gg_project.json`; a preset that does not support the dimension (names both); no passing selftest for the preset's renderer. It then writes the seed files and the runtime (`addons/gg/` with `runtime.lock.json`), sets typed ProjectSettings through the engine and reads them back (a mismatch is exit 1 naming the key and both values), builds `res://levels/_boot/boot.tscn`, renders it and checks the preset's `probe_targets`.

## Choosing a style from a brief

| Brief says | preset | dimension | view |
|---|---|---|---|
| photoreal, realistic, PBR, cinematic | realistic | 3d | first_person or third_person |
| painterly, cel, toon, cartoon, storybook, outline | stylised-painterly | 3d | third_person |
| low-poly, flat-shaded, faceted, survival island | low-poly | 3d | third_person |
| pixel art, 16-bit, retro, tiles, top-down 2D farm | pixel-art | 2d | top_down (or side) |

`gg_style.py list` prints every preset with its renderer and dimensions.

## Profile fields (`templates/gg_project.example.json`)

`name` (lowercase, letters digits _), `title`, `godot_version` (4.x.y, checked against `godot --version`), `dimension` 2d|3d, `view` first_person|third_person|top_down|isometric|side (2d: top_down or side), `style.preset` + `style.overrides` (deep-merged over the preset, unknown keys are refused naming the path), `units`, `world` (`size_m` [x,z] 16..8192, `cell_m` 0.25..16, `sea_level_m`, `height_range_m` [lo,hi], `seed`), `level`, `capture` (`size`, `frames`, `views`), `input.scheme`, `export.presets`. `gg_project.py validate` prints every error with the field path.

## Preset groups

`renderer` (forward_plus | mobile | gl_compatibility; pinned in the preset and compared to what the engine reports), `capture_frames`, `render` (window, internal, texture_filter, msaa, fxaa, taa, snap_2d), `lighting` (sun, ambient, sky), `post` (tonemap, exposure, glow, ssao, fog, adjust), `material` (shading pbr|toon|flat|unshaded, palette, outline, terrain_shader), `geometry`, `water`, `targets` (numeric look of the hero view), `probe_targets` (numeric look of the style probe scene), `fix_hints` (which single knob to turn when a target fails), `calibration`.

Pixel art: `render.internal` is 320x180 and the window 1280x720 (k = 4). The project uses stretch mode `viewport` with integer scale; the palette quantiser is a full-screen canvas shader (`PalettePost`) that snaps every pixel to the 16-colour palette.

## The probe scene and the matrix (proof that style is data)

`gg_style.py probe --project P --out DIR` renders the SAVED boot scene (so it judges what `apply` built) and refuses with exit 2 when `gg_project.json` changed since the last `apply`. The scene is one fixed scene (ground layers, 18% grey card, white and black cards, six colour chips, sphere, faceted rock, tree, water, sky) through the project's style and checks `probe_targets`. `gg_style.py matrix --work W --out O` renders all 3D presets, each in its own freshly re-applied real project, and requires: every image passes its own preset's targets and fails every other preset's. Changing only `style.preset` and running `apply` flips the probe verdict; changing it WITHOUT `apply` is exit 2. The matrix covers the 3D probe; the pixel-art 2D tile probe has its own `probe_targets_2d` and is not in the matrix. With non-empty `style.overrides` the probe checks only the structural metrics (flat fraction, colour count, grid integrity, clipping), because look targets describe the unmodified preset.

## Rules

- Do not hand-edit `project.godot`, `levels/_boot/boot.tscn` or `addons/gg/`. Change `gg_project.json`, then `gg_style.py apply --project P`. A hand edit of `addons/gg/` is refused (runtime drift); `gg_project.py sync-runtime` restores it.
- `ProjectSettings.save()` only writes non-default values, so settings are verified by reading them back in a fresh engine process, not by reading the file text.

## Calibration (measured 2026-11-16 and 2026-11-17, Godot 4.7.2)

`gg_style.py calibrate --work W --out O --write` initialises a real project per preset, renders its boot scene and sets `probe_targets` to the measured value plus a margin (luma and saturation +-0.04..0.05, flat fraction +-0.06, colour count x0.5..x2, clip caps). Project settings such as MSAA change the pixels (the stylised preset measured about 2300 colours in a bare project and about 8300 in a real one), so calibration always runs in a real initialised project. The values below are the probe hero view. The `targets` group in each preset (the hero view of YOUR level) is NOT calibrated yet: initial design values, do not use them to judge a level until the lighting stage has re-measured them.

| preset | renderer | luma_p50 | sat_mean | unique_colors | flat_fraction | adapter used |
|---|---|---|---|---|---|---|
| low-poly | gl_compatibility | 0.288..0.368 | 0.436..0.536 | 1467..5870 | 0.88..1 | llvmpipe (LLVM 22.1.8, 256 bits) |
| pixel-art | gl_compatibility | 0.327..0.407 | 0.483..0.583 | ..32 | 0.932..1 | llvmpipe (LLVM 22.1.8, 256 bits) |
| realistic | forward_plus | 0.504..0.584 | 0.273..0.373 | 6699..26796 | 0.407..0.527 | NVIDIA GeForce GPU |
| stylised-painterly | forward_plus | 0.421..0.501 | 0.372..0.472 | 4131..16526 | 0.431..0.551 | NVIDIA GeForce GPU |

`gl_compatibility` renders ran on the `llvmpipe` software rasteriser here, `forward_plus` on the NVIDIA GPU: numbers measured on a different adapter can differ, so re-run `calibrate` after a driver or GPU change. Pixel art has a separate `probe_targets_2d` for the 2D tile probe.

## Known limits (do not rely on these)

- Keys accepted by the schema but not read by the runtime yet (an override changes nothing; `apply` prints a WARNING): material.normal_maps, normal_strength, terrain_shader, palette without palette_quantize, geometry.flat_normals, scatter_density, terrain_cell_m, water.style, water.deep, 3D texture_filter, input.scheme. `material.outline.px` is a thickness of px x 0.02 m, not pixels. Toon band count and shade floor are shader constants.
- `capture.size`, `capture.frames` and `world.cell_m` are copied from the preset at `init` and are not changed when you switch preset.
- The probe verifies shading only through luma, saturation, colour count and flatness. Outline, toon bands and SSAO are not measured separately, so realistic and stylised-painterly are separated by lighting and tonemap numbers only.
- `gl_compatibility` numbers were measured on the `llvmpipe` software renderer only.
