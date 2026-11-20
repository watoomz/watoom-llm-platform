# gg-destruction: breakable props for a first-person shooter (T-0066)

Godot 4 has no runtime fracture (nothing like Unreal's Chaos Destruction or a Nanite-backed fracture), so the pieces are
made OFFLINE and swapped in at runtime. Options weighed (2026-11-19):

| Approach | Good for | Why not the default |
|---|---|---|
| **Pre-fractured mesh + RigidBody3D swap** (chosen) | walls, crates, statues, props from owned packs | pieces are fixed per model (vary with `--seed`/`--focus`) |
| Voxel / chunk mesh (e.g. a voxel addon) | digging terrain, Minecraft-style worlds | a new art style and a plugin; owned packs are meshes, not voxels |
| GridMap blocks | grid buildings | blocky look; owned walls would have to be re-cut into cells |

## Pipeline

```bash
python3 scripts/gg_destruction.py fracture --source /path/SM_StoneWall.fbx --out P/assets/destruction/stone_wall.glb --pieces 24
python3 scripts/gg_destruction.py init  --project P              # the test wall: res://assets/destruction/test_wall.glb
python3 scripts/gg_destruction.py check --project P [--model res://assets/destruction/stone_wall.glb]
```

`fracture` runs `blender-simulation/scripts/fracture.py` headless (Blender 5.2, plain bmesh, no Cell Fracture add-on):
each Voronoi cell is the source cut by the bisecting planes to every other seed, the cut capped with `holes_fill` and
given the material "Inner". The glb holds `Intact` and `Piece_000`..; each piece's origin is its own centre, placed
where it sits in the intact mesh. It prints `volume_ratio` (pieces / intact): a closed mesh gives 1.00; far from 1
(exit 1, `warning`) means the source is open and the cuts could not be capped. Measured: test box 4 x 0.4 x 3 m and
the owned modular-castle `SM_StoneWall.fbx` (6.4 m3), 24 pieces each, ratio 1.00, ~35 s.

## Runtime: `addons/gg/game/destructible.gd`

A `StaticBody3D` with a child `Combat` (CombatComponent, team -1), so every gg_combat weapon damages it with no new
code (raycast hit -> `collider.get_node("Combat")` -> `try_ability`). Exports: `model` (the fractured glb),
`max_health`, `density`, `break_impulse` (m/s at the hit), `impulse_radius`, `debris_lifetime_s`, `hull_shrink`.
Call `hit_at(point, dir)` from the shot so the break pushes pieces from where it landed. Signal `broken(pieces)`.

## What `check` proves (12 checks, PASS on both walls)

Pieces sit inside the intact mesh; the gun ray hits the intact collider; below the threshold it stays whole; lethal
damage gives N RigidBody3D pieces; no jump at the swap (beyond one frame of a piece's own velocity); intact hidden;
pieces fall, are pushed along the shot, stay above the floor, 24/24 at rest after 4 simulated s; the same ray then
passes where the wall stood. Time is simulated (240 physics frames = 4 s) so host speed does not matter.

## First-person shooting: `addons/gg/game/fps_weapon.gd` + `gg_destruction.py fps`

A hitscan gun for the first-person player: a child of the `camera_rig.gd` Camera3D. It fires a real ray from the screen
centre through the gg_combat path (hit collider -> `Combat` -> `try_ability`, plus `hit_at` on destructibles), with
`fire_rate`, `magazine`, auto reload from the reserve (= the player's `CombatAttributes.ammo`, so ammo pickups refill
it), `spread_deg`, recoil (camera pitch kick, recovered at `recoil_return_dps`) and a model kick. It registers its own
actions when the project has none: `fire` = left mouse, `reload` = R. `camera_rig.gd` first_person now pitches with
vertical mouse motion (`add_pitch`, clamped to `max_look_deg` 85).

```bash
python3 scripts/gg_destruction.py fps --project P [--gun res://assets/weapons/rifle.glb] [--wall res://...glb]
```
12 checks through REAL input (`Input.action_press`, `parse_input_event`): actions exist, the gun uses the player's
Combat, the model is in view, mouse look 10 deg up and the 85 deg clamp, fire rate (4 shots in 0.5 s at 8/s), one round
per shot, the shots break the wall, recoil up and back, an empty magazine reloads from the reserve, a 90 deg mouse turn
aims at a dummy and one tap takes 25 off it. PASS with no model (11) and with the owned AK-47 glb (12).

### A playable range: `gg_destruction.py range`

```bash
python3 scripts/gg_destruction.py fracture --source .../SM_StoneWall.fbx --out P/assets/destruction/stone_wall.glb \
    --basecolor .../TilingMaterials/Stone/Stone_basecolor.tga --normal .../Stone_normal.tga --tint 0.55 0.5 0.44
python3 scripts/gg_destruction.py range --project P --wall res://assets/destruction/stone_wall.glb \
    --gun res://assets/weapons/ak47.glb --gun-rotation 0 180 0 --gun-offset 0.2 -0.25 -0.58
python3 scripts/gg_verify.py shot --project P --scene res://levels/fps_range/fps_range.tscn --out DIR \
    --view '{"name":"eye","kind":"3d","position":[0,1.6,0.01],"look_at":[0,1.4,-10]}'
```
Builds `res://levels/fps_range/fps_range.tscn` (14 nodes): sky, sun, a 60 m floor, the first-person player with the
gun under its `CameraRig` (fps_weapon.gd moves itself under the rig's Camera3D, which camera_rig.gd only makes in its
own `_ready` -- after the children's), and walls at 6/10/14 m. Every runtime part builds its children in `_ready`, so
the saved scene holds no generated nodes. Use a project made by `gg_project.py init` (it defines the move actions; a
`gg_ui.py init` project logs `InputMap action "move_forward" doesn't exist`).

Textures on fractured walls: the castle walls' Unreal material is triplanar, which glTF cannot carry, and a Godot
world-triplanar material would swim on falling pieces. `fracture.py --basecolor/--normal` bakes box-projected UVs in
the INTACT object's space into every face (cut faces too) and embeds the image, so the pattern is continuous on the
wall and stays on each piece; `--tint` multiplies the castle's near-white greyscale `Stone_basecolor.tga` (16 MB glb).
Gun models point their barrels along different axes: `--gun-rotation` (the owned AK-47: 0 180 0) and `--gun-offset`
(its pivot is not the grip). Both are first-person-view cosmetics until FPS arms exist.

FPS pitfalls (each measured):
- **Read `InputEventMouseMotion.screen_relative`, not `relative`, for mouse look.** `relative` is scaled by the viewport
  stretch transform: in a stretched 640x360 project a 90 deg turn came out as 180 and 10 deg of look as 56.
  `player_3d.look_delta` and `camera_rig` use `screen_relative`, falling back to `relative` for events that only set it.
- **Flush injected input** (`Input.flush_buffered_events()` after `parse_input_event`): otherwise it is dispatched on the
  next PROCESS frame, and with a heavy scene (the 123 MB AK-47) two physics frames later nothing had arrived.
- **Set `position` before `add_child`** for bodies that must not start inside each other: a dummy added at the origin
  sat inside the player for a frame and the player depenetrated up onto it (camera found at (6, 3.4, 0)).
- **`_ready` runs once per node**: after `reparent()` it is not called again; call the setup yourself.
- **A GDScript lambda captures a local int by value**: `fired.connect(func(h): n += 1)` leaves `n` at 0. Append to an Array.
- Recoil of 0.8 deg at 12 deg/s returns before the next shot at 8/s; sample the pitch during the burst, not after it.

## Pitfalls (each measured on the test wall)

- **Disable the intact collider immediately, not with `set_deferred`.** `shatter()` runs from `_physics_process`; a
  deferred disable leaves the intact hull in the break frame with every piece inside it. Pieces also get
  `add_collision_exception_with(self)`.
- **Give pieces a velocity, not `apply_central_impulse(v * mass)`.** On a RigidBody3D added this frame the impulse
  acted on the default 1 kg, not the mass just set: a 486 kg piece left at ~2000 m/s (34 m in one frame, pieces
  1.5 km below the floor). `linear_velocity = dir * speed` is mass-independent and is what was meant.
- **Shrink piece hulls a little** (`hull_shrink` 0.9): neighbouring cells share faces exactly; at 1.0 22/24 were at
  rest after 4 s, at 0.9 24/24.
- The first import of a NEW glb can end with `ERROR: Parameter "singleton" is null` at editor shutdown
  (`is_cmdline_mode`); the import itself is written (`.godot/imported/*.scn`). Run the check again.

## Not built yet

Partial damage (chunks breaking off one at a time), a destructible building made of several props, debris pooling,
multiplayer replication of the break (the server should decide and send the seed + hit), first-person ARMS with
animations (the owned FPS arms packs are uasset-only: unreal-export bridge first), muzzle flash/impact VFX on the gun
(gg_vfx recipes exist), and a rendered screenshot check of the FPS view.
