# gg-player: a player, a camera, and a smoke test that runs the level (3D)

A level is not playable until it ran. Screenshots of a static scene say nothing about collision, input or the camera. `gg_player.py smoke` runs the level with scripted input and measures what happened. 2D players are not built yet.

## Commands

```bash
python3 scripts/gg_player.py init   --project /abs/path/game            # player + camera sections in gg_project.json, from `view`
python3 scripts/gg_player.py init   --project /abs/path/game --runway-m 12  # same, with player.start.runway_m set (the lab island needed 12)
python3 scripts/gg_player.py build  --project /abs/path/game --dry-run  # shows the start it would choose, the solids and the scenes the level will instance
python3 scripts/gg_player.py build  --project /abs/path/game            # exit 0 = colliders, player and level built; the capsule rests on the ground at 64 probe points
python3 scripts/gg_player.py smoke  --project /abs/path/game            # exit 0 = the level RAN
python3 scripts/gg_player.py status --project /abs/path/game            # which stamp is stale and what to run
```
Exit 2 = refused (names the key or the earlier step). Exit 1 = a check failed (one line per failed check with the number and the key to change). Exit 3 = engine log error or warning. Exit 4 = no verdict (the tick count did not match, so no number can be trusted). Run order: terrain, water, lighting, catalog and scatter, then `init`, `build`, `smoke`. `build` includes the scatter only while its stamp is valid; run it after the scatter, and run it again if you scatter again.

## World and yaw conventions (measured)

+Y is up, column goes to +X, row goes to +Z. Yaw 0 faces -Z; forward is (-sin yaw, 0, -cos yaw); a turn to the right is a negative yaw. A mouse move of dx pixels turns the player by -dx x `camera.mouse_sens_deg_per_px` degrees. The origin of the player is its feet. top_down and isometric cameras do not turn the player: W moves along -Z and D along +X.

## Profile keys

`player`: `height_m` 0.5..3, `radius_m` 0.15..1 (at most half the height), `speed_mps` 0.5..20, `accel_mps2` 5..200, `jump_height_m` 0..5 (0 disables the jump), `gravity_mps2` 1..50, `max_slope_deg` 10..60. `player.start`: `rule` auto|fixed, `min_above_sea_m`, `max_slope` (gradient, below tan of max_slope_deg), `min_water_m`, `clear_m`, `runway_m` (at least 2 + 1.2 x speed), `edge_margin_m`, `prefer` near_center|near_water, `face` land|water|uphill; with rule fixed also `position_xz` and `yaw_deg`. `camera`: `mode` (must match `view`), `eye_height_m` (below the player height), `fov_deg`, `distance_m` (third person and the top views), `pitch_deg`, `ortho_size_m` (isometric), `near_m`, `far_m` (at least the world diagonal), `mouse_sens_deg_per_px`. Every refusal names the key, the value and the range.

## The start is a rule

Never type coordinates. `auto` picks dry ground (above the sea, under max_slope, away from water, inside the edge margin, clear of trees and rocks) with a clear runway: a forward leg of `runway_m` and a second leg of 7 m starting 2 m before its end (90 degrees to the right of the facing, or +X for the top views). The smoke walk is as long as the runway allows. When nothing fits, the refusal names the rule that removed most cells. On a steep island with many trees expect to lower `runway_m` (the lab island needed 12 m for first and third person and 8 m for the top views) or to scatter fewer trees.

## What is solid

The terrain (the existing height-map collider; it is checked against the data at 64 points, vertices within 5 cm and cell interiors within 15 cm, measured worst 7.8 cm). Upland and riparian trees: one cylinder each (radius 0.3 x scale, 4 m tall). Rocks: a box from 70% of the inspected size. Grass, flowers, shrubs, reeds and everything else never collide: a MultiMesh has no collision.

## The smoke script (60 physics ticks per second)

Settle 1 s, walk forward, turn 90 degrees with one injected mouse event (top views: step right instead), walk 1 s, jump, wait 1.5 s. Verdicts are computed in Python from the per-tick trace against the height data, never from the collider under test.

## Checks, thresholds and the control that proves each can fail

| Check | Fails when | Control run |
|---|---|---|
| C0 ticks | physics ticks differ from the scripted count (exit 4) | unit test |
| C1 settle | not on the floor after 1 s | no terrain collider |
| C2 fall-through | feet more than 0.25 m below the ground, or more than 0.35 m above it on the floor | no terrain collider: fell 156 m |
| C3 distance | walked / expected outside 0.85..1.05 or under 2 m (expected from the planned runway slope, never from where the player went) | no input; a solid cylinder on the runway (ratio 0.26) |
| C4 heading | first walk more than 10 degrees off the facing; the mouse turn off by more than 5 degrees; second walk more than 15 degrees off | unit tests |
| C5 jump | peak outside 0.8..1.2 x jump_height_m, or not back on the floor | no input |
| C6 sea | in or at the water | unit test |
| C7 camera | under 0.2 m above the ground, or no current camera | camera 3 m below the feet |
| C8 pictures | the start or end picture blank or crushed, or they differ by under 0.02 | no input (difference 0.0000) |
| C10 input | a scripted action or the mouse event never reached the player | no input |

C8 is weak by design: an underground camera still shows a picture (difference 0.117 in the control), which is why C7 checks the camera position. The 0.02 threshold sits between 0.0000 (no input, low-poly, no animated water) and the real walks (0.057 top down, 0.062 isometric, 0.119 third person, 0.175 first person); re-measure it for a style with animated water.

## Stamps

`build` writes `player_ok.json` (the heights, and hashes of the terrain, colliders, player, level and scatter scenes, start.json, the player and camera sections, the water distance map, the runtime lock and the [input] section of project.godot). `smoke` refuses unless every hash still matches ("the level changed since gg_player.py build (profile_player_camera): run build again") and writes `smoke_ok.json` only on exit 0. New heights remove both. Export must refuse without a valid `smoke_ok.json`.

## Measured pitfalls

- A physics tick runs once per rendered frame under xvfb (454 ticks for 454 scripted ticks); `--headless` has no fixed frame rate and no pixels, so smoke always renders.
- The mouse event is applied within one tick of the phase boundary: read the yaw from the tick before the turn to a few ticks after.
- The runner stops after a fixed number of frames: pass `frames` in the op arguments (probe and smoke do).
- Strict warnings: the only measured benign warning is "Could not set V-Sync mode" under xvfb; it is in the reviewed noise list in gg_log.py with its reason. Any other warning fails the smoke (exit 3).
- Level scenes instance terrain, water, scatter and colliders by reference; saving with every node owned would flatten them (the save protocol has a keep_instances mode for this).

## Verified and not verified

Verified by running (Godot 4.7.2, 256 m island, trees and boulders, DEFAULT physics engine): build and smoke pass in first person, third person, top down and isometric; the controls above fail with the stated checks. Not verified: 2D players; other physics engines (Jolt); a second style; world sizes or cell sizes other than 256 m / 4 m; ground above 45 degrees; moving platforms; a controller that is not WASD plus mouse.

## Failure message to fix

| Message starts with | Do this |
|---|---|
| no dry, gentle ground for the start | loosen the rule it names in player.start, or reshape the terrain |
| no candidate had a clear N m runway | lower player.start.runway_m or clear_m, or scatter fewer trees |
| the collider and the mesh disagree | the terrain build is wrong: rebuild it (gg_terrain.py build) and re-check |
| the level changed since gg_player.py build | run gg_player.py build again |
| C3 distance | something blocks the runway, or input did not move the player: check speed_mps and the start |
| C7 camera | raise camera.eye_height_m or distance_m |
