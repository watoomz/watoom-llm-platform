# Water: sea, coast, creeks, distance to water (stage d)

3D only. Run from `scripts/`. Order matters because every step that changes the heights invalidates what came after it:

```bash
python3 gg_terrain.py heights --project P --shape island --relief-m 40
python3 gg_water.py  creek    --project P --auto --width-m 8 --depth-m 1.5     # optional; --dry-run first; or --waypoints "20,30 60,80 120,200"
python3 gg_terrain.py layers  --project P
python3 gg_terrain.py build   --project P                                       # exit 0 needed
python3 gg_water.py  build    --project P                                       # exit 0 = water.tscn built and verified
python3 gg_water.py  analyse  --project P                                       # (build runs it) writes the masks below
```

## What it makes
- `res://levels/<level>/water.tscn`: a sea plane at `world.sea_level_m` over the whole world, plus one ribbon mesh per creek. The material comes from the style (flat, toon, unshaded, or translucent PBR) with colour `water.shallow`.
- `gg_data/world/water_mask.png` (255 = water: terrain below sea level, or inside a creek channel under the creek surface), `water_dist.f32` (exact distance in metres to the nearest water cell, 0 on water; little-endian float32, same grid as heights) and `water.json` (water fraction, shore length and slope, creek registration). The planting stage uses the distance map: wet plants are placed by distance to water, never by height.

## Creeks
- `--auto` takes the highest land cell at least 15% of the map from the sea and finds the cheapest downhill route to the sea (uphill steps are expensive), then smooths it. `--waypoints` takes x,z metres; the first must be on land and the last in the sea.
- The channel bed is the running minimum of the ground along the path minus `--depth-m`, so it never rises downstream. The banks rise at 0.6 m per metre. A berm (land beside the channel is raised to the water surface + 0.25 m) stops the water spilling sideways on cross-slopes.
- Refused: width under two cells (the channel would not resolve), width outside 1..40 m, depth outside 0.3..10 m, a second creek, waypoints outside the world, a last waypoint on land, no sea in the heights.
- Printed and checked: bank clearance (1.0 = cannot spill; exit 1 under 0.9) and the maximum water depth over the channel floor (exit 1 above max(2 x depth, 2 m): the surface would float over a trench).

## What `build` checks (exit 1 on any failure)
- Sea plane y equals the sea level after saving and reloading the scene.
- Creek registration: the creek lies in the trench that was carved for it (bank clearance of the ring beside it and terrain at its centre not above the surface). This is independent of the mask and the mesh, which both come from creeks.json, so a mirrored, shifted or edited creek fails. Measured: the real creek 1.0; mirrored in z 0.37, in x 0.02; shifted 12 m in z 0.10, in x 0.00.
- A top-down render is compared with the mask: overall agreement >= 0.85, shore-band agreement >= 0.7, water recall >= 0.6, water and land colours at least 0.02 apart (change `water.shallow` through the style overrides if they are not), and creek cells: at least 50% render as water and each mirrored variant scores at least 0.2 lower. A level with no creek prints a NOTE: the orientation of the water against the terrain is then not proven (a round island is nearly symmetric).
- A passing build writes `water_ok.json`; `gg_light.py` includes water in its renders only when it matches the current heights.

## Failure procedure
1. Exit 2 names the missing earlier step (terrain build, heights, creeks.json from older heights).
2. `gg_data/water_check/top.png` is the image that was judged; look at it.
3. Water missing or the same colour as the land: read the colour-separation number in the failure text.

## Verified vs not
Verified by running (Godot 4.7.2, lab, 256 m, 4 m cells): the whole chain on the low-poly island with an auto creek; the exact distance transform against brute force; four tampered creek files rejected. Not verified: more than one creek, waypoint creeks end to end, lakes (no inland basins), tides or animated water (the preset's `water.style` and `water.deep` are not consumed), world sizes other than 256 m.
