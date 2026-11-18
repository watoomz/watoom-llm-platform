# Lighting and exposure (stage e)

3D only. The level must exist: `gg_terrain.py build`, and `gg_water.py build` if the level has water (do water first: it changes the picture; the renders include water only when its build passed). All commands run from `scripts/`.

```bash
python3 gg_light.py shoot --project /abs/game              # overview + ground view; the overview is checked against the preset's `targets`
python3 gg_light.py tune  --project /abs/game              # changes ONE value per step until the overview passes; prints each step
python3 gg_light.py tune  --project /abs/game --write      # same, then writes style.overrides into gg_project.json and re-applies the style
```

`shoot` exit 0 = the overview meets the targets. Exit 1 = a TARGET FAIL line names the metric, the value, the range and a fix hint. Exit 2 = refused (2D project, no level, style not applied). Exit 3/4/5 = engine log fatal / no verdict / runner failure (read the printed reason first).

## The recipe
1. `shoot`. If it passes, stop.
2. Otherwise `tune`. Each step takes the first failing metric in the order luma_p50, luma_p95, luma_p5, clip_black, clip_white, sat_mean, reads its fix hint, and changes the first lever in that hint by a multiple of the hint's step (more steps for a bigger gap). It re-renders and checks that the metric moved the right way. A lever that did not move the metric is undone, reported ("has no effect here, not using it again") and skipped for the rest of the run.
3. `tune` only touches lighting.sun_energy, lighting.ambient_energy, lighting.sun_elevation_deg, post.exposure and post.adjust.brightness/contrast/saturation. If only failures remain that lighting cannot fix (clip, luma_std, or a hard failure such as a blank frame) it stops with exit 1 and says so.
4. Without `--write` nothing on disk changes; the overrides to paste are printed.

## Targets
Each preset's `targets` (the level overview) come from `gg_light.py calibrate`: two reference terrains (256 m island seed 1, hills seed 7) measured with the preset's own layer template, the range spans both plus a margin, and a third held-out terrain (plateau seed 11) is measured against them. Calibrated 2026-11-17 on Godot 4.7.2, NVIDIA GPU (forward_plus) and llvmpipe (gl_compatibility). All four held-out terrains fell inside their targets. The targets were calibrated with terrain and sea (calibrate builds water; the held-out plateau has none). Plants and props are not in the frame yet: after they are added the ranges may need `calibrate` again.

## Engine facts measured here
- With `lighting.ambient_source` = `sky` (the realistic preset), `lighting.ambient_energy` has NO effect: energy 0 and 2 render identical images. With a colour ambient it works (mean luma 0.376 at 0, 0.539 at 2). The realistic preset's shadow hints therefore use post.adjust.brightness.
- In the overview about the upper part of the image is sky, so luma_p95 can be set by the sky and not move when sun_energy changes. `tune` then falls through to exposure.
- Measured proof: realistic with exposure 0.35 recovers in 5 steps; low-poly with exposure 2.6 recovers in 7 steps (`--write` then a fresh `shoot` passes).

## Verified vs not
Verified by running: shoot, tune (dark and bright cases), `--write`, calibrate on four presets, offline tests with a fake renderer. `shoot` was only shown to fail on exposure errors, not on a broken level (no such case was injected). `calibrate --write` now writes only if every preset's held-out terrain is inside its targets. Not verified: 2D lighting (refused by design), tune on pixel-art and stylised-painterly beyond the calibration shots, water and foliage in the frame (later stages).
