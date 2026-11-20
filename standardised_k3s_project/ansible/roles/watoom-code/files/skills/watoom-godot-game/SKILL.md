---
name: watoom-godot-game
description: Build a Godot 4.7 game of any style (realistic, stylised, low-poly, pixel/2D, top-down, first-person) from an empty project by running tested helper scripts, measuring every screenshot numerically and reading the engine log. Use when asked to make, style, light, texture, populate or verify a Godot level or game.
---

# watoom-godot-game

You build by running the scripts in `scripts/` and you check every step with numbers. You do not hand-edit `.tscn`
files, `project.godot` or the copied `addons/gg/` runtime. If a command exits non-zero, read its message, fix that one
thing, run it again. Run scripts as `python3 <skill>/scripts/NAME.py ...` (stdlib + numpy + pillow).
Exit codes everywhere: 0 pass, 1 check failed (a hint names the knob), 2 refused (bad input; the message names the bad value), 3 fatal engine log line (the image is not valid), 4 no verdict (timeout/crash/GPU; read `godot.log` in the printed job dir), 5 runner failure.
Read `references/gg-verify-loop.md` and `references/gg-project-style.md` before you start.

## Step -1: check what is already known (before any code, every session)
1. `watoom_memory_recall` with the task in a few words (for example "godot idle rpg overlay strip gg_ui worker jobs") and use what it returns: earlier results, known failures and fixes for this project.
2. Read this project's `.opencode/work/<task>/progress.md` and `BRIEF.md` if they exist: they say what is already done. Do not redo finished steps.
3. Open the skill reference for the stage you are about to run (`references/gg-ui.md` for a UI/overlay game, `references/gg-assets.md` for models, `references/gg-project-style.md` for the style) and the Godot 4 syntax list in `gg-ui.md` before you write GDScript. Look up an unfamiliar Godot class or method in the language-knowledge cards rather than guessing.
4. After a job passes or you fix a non-obvious failure, `watoom_memory_learn` (or `watoom_memory_record`) one short lesson: the cause and the fix, no secrets.

## Step 0: prove you can see (once per host, after any Godot change)

```bash
python3 scripts/gg_verify.py selftest
python3 scripts/gg_project.py doctor
```
Expected: `selftest forward_plus: PASS` and `selftest gl_compatibility: PASS`; doctor shows godot, xvfb-run, numpy, PIL as ok.
If a selftest step says BLIND, stop and report it: nothing after this can be trusted. Every `shot` refuses until the selftest has passed.

## Step 1: choose the style from the brief (style is data)

| Brief says | `--style` | `--dimension` | `--view` |
|---|---|---|---|
| photoreal, realistic, PBR | realistic | 3d | first_person / third_person |
| painterly, cel, toon, cartoon | stylised-painterly | 3d | third_person |
| low-poly, flat-shaded, faceted | low-poly | 3d | third_person |
| pixel art, 16-bit, retro, tile-based 2D | pixel-art | 2d (or 3d) | top_down / side |

## Step 2: create the project

```bash
python3 scripts/gg_project.py init --project /abs/path/game --name my_game --dimension 3d --view third_person --style low-poly --size-m 256 256 --dry-run
python3 scripts/gg_project.py init --project /abs/path/game --name my_game --dimension 3d --view third_person --style low-poly --size-m 256 256
```
Expected: `boot scene built: N nodes`, a hero view with no FAIL lines, and `init ...: ok`. The picture is `<project>/gg_data/init_shot/hero.png`.
If it fails: exit 2 = read the message (directory not empty, bad name, preset does not support the dimension, selftest missing); exit 1 = read the FAIL hint and `references/gg-project-style.md`; exit 3 = read the printed log line.

## Step 3: check or change the style

```bash
python3 scripts/gg_style.py probe --project /abs/path/game --out /abs/path/game/gg_data/probe     # exit 0 = the look matches the preset
python3 scripts/gg_style.py probe --project /abs/path/game --out /tmp/p2 --against realistic       # a different style must FAIL (exit 1)
```
To change the look edit only `gg_project.json` (`style.preset`, `style.overrides`), then `python3 scripts/gg_style.py apply --project P`, then probe again. `probe` exits 2 if you edited `gg_project.json` and did not run `apply`. After a deliberate change prove it with `gg_verify.py compare before.png after.png --expect ...`.
`gg_project.py validate --project P` checks the profile, the godot version and that `addons/gg` was not hand-edited (`gg_project.py sync-runtime` repairs it).

## Seeing, at any time

- `scripts/gg_verify.py shot ...` render named views, measure them, check them against targets (exit 1 prints a hint per failure).
- `scripts/gg_verify.py compare A.png B.png --expect brighter` run after every deliberate change.
- `scripts/gg_verify.py log godot.log` classify a log. Never judge an image while the log has fatal lines.

## Step 4: terrain (read `references/gg-terrain.md`)

```bash
python3 scripts/gg_terrain.py heights --project /abs/path/game --shape island --relief-m 40   # 0 = written; read any WARNING lines
python3 scripts/gg_terrain.py layers  --project /abs/path/game                                   # must print sum_to_255_everywhere=True
python3 scripts/gg_terrain.py build   --project /abs/path/game                                   # exit 0 = collider + top-view checks passed
```
Exit 2 = refused (read the message: it names both sizes). Exit 1 = the printed reason says what failed (collider error, mirrored axes, uniform colour). Add `--dry-run` to `heights`, `layers` and `build` to see what would happen first.

## Step 5: water (read `references/gg-water.md`, 3D only; do it BEFORE lighting)

```bash
python3 scripts/gg_water.py creek --project /abs/path/game --auto --width-m 8 --depth-m 1.5 --dry-run   # optional creek: look at the numbers first
python3 scripts/gg_water.py creek --project /abs/path/game --auto --width-m 8 --depth-m 1.5
python3 scripts/gg_terrain.py layers --project /abs/path/game && python3 scripts/gg_terrain.py build --project /abs/path/game   # the creek changed the heights
python3 scripts/gg_water.py build --project /abs/path/game        # exit 0 = sea plane and creek built and verified
```
Without a creek skip the first two lines. Exit 2 names the missing earlier step. Exit 1 prints why (water and land the same colour, creek not on its channel, water not matching the mask). `gg_data/world/water_dist.f32` is the distance-to-water map for planting.

## Step 6: lighting (read `references/gg-light.md`, 3D only)

```bash
python3 scripts/gg_light.py shoot --project /abs/path/game          # exit 0 = overview meets the preset targets
python3 scripts/gg_light.py tune  --project /abs/path/game          # first WITHOUT --write: prints each step and the overrides it would use
python3 scripts/gg_light.py tune  --project /abs/path/game --write  # then the same with --write once the steps look sensible
```
Exit 1 prints TARGET FAIL lines with a hint; `tune` follows them one change at a time. Exit 2 = refused (read the message). Re-run `shoot` after `tune --write` and confirm exit 0. Sizes verified so far are 256 m x 256 m at 4 m cells; other sizes are untested.

## Step 7: catalog and scatter (read `references/gg-catalog.md`, 3D only; after water, then re-run Step 6 `shoot`)

```bash
python3 scripts/gg_catalog.py init    --project /abs/path/game            # default families, each starts UNVERIFIED
python3 scripts/gg_catalog.py inspect --project /abs/path/game --family pine   # repeat for every family; look at the PNGs it prints
python3 scripts/gg_scatter.py plan    --project /abs/path/game
python3 scripts/gg_scatter.py run     --project /abs/path/game --dry-run
python3 scripts/gg_scatter.py run     --project /abs/path/game            # exit 0 = scene built AND the audit is CLEAN
```
Unknown pack: `gg_catalog.py add`, then `inspect`, fix what it reports, until VERIFIED. Never edit `verified` by hand.

## Step 8: player, camera and smoke test (read `references/gg-player.md`, 3D only; after Step 7)

```bash
python3 scripts/gg_player.py init  --project /abs/path/game             # writes the player and camera sections into gg_project.json
python3 scripts/gg_player.py build --project /abs/path/game --dry-run   # prints the start position it would choose
python3 scripts/gg_player.py build --project /abs/path/game             # exit 0 = player, colliders and level built, the capsule rests on the ground
python3 scripts/gg_player.py smoke --project /abs/path/game             # exit 0 = the level RAN: walked, turned, jumped, stayed on land, camera saw it
```
To change speed, jump or the camera edit only `player` / `camera` in gg_project.json, then `build`, then `smoke`. Never type start coordinates: change `player.start`. Exit 2 names the key or the earlier step; exit 1 prints one line per failed check. `gg_player.py status` shows what changed since the last pass. 2D players are not built yet.

## Step 8: export (3D, after a passing smoke)

```bash
python3 scripts/gg_export.py status --project /abs/path/game            # smoke stamp valid? export templates installed?
python3 scripts/gg_export.py build  --project /abs/path/game            # default preset pck; --preset linux also runs the binary; exit 0 = the export exists AND was proven
```
Read `references/gg-export.md`. Exit 2 = refused (names the missing smoke stamp, the preset not in `export.presets`, or the missing templates folder).

## Step 9: UI and overlay games (read `references/gg-ui.md`; menus, idle games, HUDs, a strip along the bottom of the screen)

```bash
python3 scripts/gg_ui.py init          --project /abs/path/game --name my_strip --width 1920 --height 240   # empty folder: overlay settings, runtime, main scene, tests/
python3 scripts/gg_ui.py test          --project /abs/path/game                                              # res://tests/test_*.gd; no tests = refused, no assertions = fail
python3 scripts/gg_ui.py shot          --project /abs/path/game --scene res://scenes/main.tscn --size 1920x240 --dock bottom --min-model-views 1
python3 scripts/gg_ui.py overlay-check --project /abs/path/game                                              # engine read-back of the overlay window
```
Models: do NOT read `asset-index.md`; `python3 scripts/gg_assets.py find --query dragon`, then `use` and `check` (read `references/gg-assets.md`).
Use `addons/gg/game/overlay_window.gd` to dock the window; do not write your own flag code. `shot` keeps transparency and measures coverage, clipping, button and text size and every 3D model view; look at the PNG too. `overlay-check` proves what the engine reports, not what a desktop compositor does: report that as NOT VERIFIED.

## Step 10: combat, items, effects and animation (read `references/gg-combat.md`; after Step 8, once there is a player)

```bash
python3 scripts/gg_combat.py init     --project /abs/path/game           # writes addons/gg/game/combat*.gd into the project (idempotent, refused if already present)
python3 scripts/gg_combat.py check    --project /abs/path/game           # pure CombatAttributes/Combat.apply_effect unit checks (damage, heal, cost, grant, death, team/cooldown gating)
python3 scripts/gg_combat.py slice    --project /abs/path/game           # a real CharacterBody3D player+dummy: sword (melee range), gun (real PhysicsServer raycast), spell (instant at range), cooldowns, death
python3 scripts/gg_combat.py pickups  --project /abs/path/game           # Area3D pickups granting/healing on overlap, one-shot and timed-respawn
python3 scripts/gg_combat.py mp       --project /abs/path/game           # TWO real concurrent godot processes over ENetMultiplayerPeer: proves a client's direct call is rejected and only its rpc_id(1,...) call changes the server's own health
python3 scripts/gg_combat.py spec     --project /abs/path/game --spec combat.json (--weapon NAME | --spell NAME)   # T-0075: load+validate a declarative weapon/spell spec (templates/combat_spec.example.json) and prove ONE named entry live -- its own delivery (melee/raycast/instant), cooldown, effect and cost, data-driven instead of hardcoded like `slice` above
python3 scripts/gg_vfx.py   check     --project /abs/path/game           # renders projectile/muzzle/impact/aura GPUParticles3D recipes and proves each one actually drew non-flat pixels
python3 scripts/gg_vfx.py   check     --project /abs/path/game --combat-spec combat.json   # T-0075: same render-and-measure check, fed every vfx recipe pulled straight out of a weapon/spell spec instead of a separately hand-written fx.json
python3 scripts/gg_anim.py  check     --project /abs/path/game --mesh res://... --states idle=res://...,walk=res://...   # merges separately-exported animation glbs onto a character's own skeleton and drives an AnimationNodeStateMachine across them
```
Exit codes match every other stage: 0 pass, 1 a check failed, 2 refused, 3 fatal engine log line, 4 no verdict, 5 runner failure. `gg_anim.py` is not available as a native-worker job step (its `--mesh`/`--states` carry `res://` asset paths the worker's token guard does not allow, like `gg_assets.py find`/`use`): run it in your own session. `gg_vfx.py check` has no engine process without a GPU-less render pass, so it goes through the same `selftest_gate`/renderer convention as `gg_ui.py shot`. `gg_combat.py spec`'s `--spec` is also not a native-worker job step, for the same reason `gg_vfx.py check --spec`/`--combat-spec` are not: the path is not an allowed worker token.

## Step 11: dungeon kit catalog and procedural layout (read `references/gg-dungeon.md`; pure logic, no engine needed)

```bash
python3 scripts/gg_dungeon.py catalog-init     --project /abs/path/game --pieces-dir res://assets/dungeon/kit1   # writes UNCLASSIFIED stubs; edit kind/footprint/sockets by hand
python3 scripts/gg_dungeon.py catalog-list     --project /abs/path/game
python3 scripts/gg_dungeon.py catalog-validate --project /abs/path/game
python3 scripts/gg_dungeon.py layout           --project /abs/path/game --seed 1 --rooms 8    # deterministic for a given (catalog, seed, rooms)
python3 scripts/gg_dungeon.py verify           --project /abs/path/game                        # independent connectivity/overlap audit; never trusts layout's own connections list
```
Pieces are already-converted project-local `res://` scenes: converting an owned Unreal dungeon kit to `.glb`/`.tscn` is a separate, rig-touching piece of work, not part of this stage. No render/visual check (the `gg_catalog.py inspect` equivalent) is built yet; `verify`'s pass is a statement about the grid graph only, not about what the dungeon looks like once built.

## Step 12: destructible props and the first-person gun (read `references/gg-destruction.md`; FPS games, after Step 10)

```bash
python3 scripts/gg_destruction.py fracture --source /abs/path/wall.fbx --out /abs/path/game/assets/destruction/wall.glb --pieces 24
python3 scripts/gg_destruction.py init  --project /abs/path/game     # the 24-piece test wall
python3 scripts/gg_destruction.py check --project /abs/path/game [--model res://assets/destruction/wall.glb]
python3 scripts/gg_destruction.py fps   --project /abs/path/game [--gun res://assets/weapons/rifle.glb]   # first-person gun slice
python3 scripts/gg_destruction.py range --project /abs/path/game --wall res://... --gun res://... [--gun-rotation X Y Z]   # playable range scene
```
`fracture` needs Blender (GG_BLENDER or /data/ai/toolchains/blender): run it in your own session, not as a worker step. Exit 1 with a `warning` = the source mesh is open (`volume_ratio` far from 1). `check` exits 0 only when real gun raycasts break the prop into rigid pieces that fall, settle on the floor and leave a hole; `fps` only when the first-person gun, driven by real input, looks, fires, reloads, recoils and breaks the wall. Place a prop in a level with `addons/gg/game/destructible.gd` (`model` = the glb) and put `addons/gg/game/fps_weapon.gd` under the player's camera (`CameraRig/Camera3D`); do not write your own break or shooting code.

## Running the steps through the native worker

Worker jobs, two helpers you can rely on: `"from_project": true` makes the worker copy your live project into `project_dir` itself (leaving out `.godot`, `.opencode` and `gg_data` job scratch; files over 30 MB are not copied into `project_dir` but sent to the worker directly and hash-checked, up to 8 GiB in total, and any beyond that are listed in result.json `skipped_large_files`; the folder must not exist yet), so you never stage files by hand; and a job whose first step is `gg_ui.py init` or `gg_project.py init` may name a `project_dir` that does not exist yet. Rules for submitting jobs (the tool enforces most of them):
1. Submit only your own CURRENT jobs: names you wrote a `request.json` for in this session. Never poll, wait on or resubmit another session's, another project's or an old job (the status shows `own_session` and a warning when it is not yours).
2. Projects with `gg_ui.json`/`gg_project.json` use operation `godot-game` only; `regression`, `import` and `capture` are for the legacy projects and just sit queued.
3. Every attempt gets a NEW job name and a NEW scratch `project_dir` (for example `.opencode/tmp/<job-name>`). A finished job (FAIL, FAILED, STALE_REQUEST, STALE_RESULT, RECONCILIATION_REQUIRED; a passed job reads COMPLETED or PASS) is never re-run.
4. `status` takes the job NAME you requested, never the 64-hex request_id.
5. A failed job is a result to fix, not a blocker: read `.opencode/godot-game-out/<job>/result.json` (failure_reason and the step log tail), fix the cause, resubmit under a new name. Do not finish with BLOCKED because a job failed.
6. QUEUED means wait: do not resubmit or poll in a loop; keep editing. Queued over 30 minutes: report the job name and age to the operator.
7. One request at a time: request, then read its status when notified, then decide the next job from that result.

From a game-project session you can request the same scripts as a typed job: write `.opencode/godot-game-jobs/<job>/request.json` (schema 1, `project_dir` under `.opencode/tmp/`, `steps` of `{script, sub, args}`) and request operation `godot-game` through `watoom_game_worker`. It runs on the Bazzite worker with software GL, so only the low-poly and pixel-art styles; results come back under `.opencode/godot-game-out/<job>/project/`. Give every argument as its own list element (`["--size-m","256","256"]`), never paths, and start a steep island with `gg_player.py init --runway-m 12`. For a UI/overlay game start the job with a `gg_ui.py init` step in an EMPTY `project_dir` (no style is needed; it runs on software GL by construction); the one place a path is allowed is `--scene` or `--dir` of a `gg_ui.py` step, as `res://...` (no `..`), for example `["--scene","res://scenes/main.tscn","--size","1920x240","--dock","bottom"]`. Screenshots come back as `.opencode/godot-game-out/<job>/project/gg_data/ui_shot/<name>.png` with a `.report.json` next to each. Details: `docs/NATIVE_GAME_WORKER.md`.

## Not built yet (do not use)

2D player and smoke test, the windows export preset (it refuses until its Godot export templates are installed; pck and linux work): later stages of this skill.
