# gg-combat: damage, items, effects, animation (T-0065)

The Godot-side equivalent of the Unreal GAS combat work (`watoom-unreal-combat`). Four runtime library files
land under `addons/gg/game/` via `gg_combat.py init`: `combat.gd` (pure data + effect math), `combat_attributes.gd`
(health/shield/stamina/mana/ammo, clamp-on-set, team, resist, dead flag), `combat_component.gd` (cooldown- and
team-gated abilities plus a multiplayer-authority RPC wrapper), `pickup.gd` (an `Area3D` that applies an effect
on overlap). `vfx.gd` is a standalone particle-recipe builder; it does not need `gg_combat.py init` and is driven
through `gg_vfx.py` instead.

## The effect model

Every ability, pickup and spell is one `Dictionary`: `{"kind": "damage"|"heal"|"cost"|"grant", "amount": float,
"resource": "health"|"shield"|"stamina"|"mana"|"ammo" (cost/grant only), "element": String (damage only, used by
`resist`)}`. `Combat.apply_effect(attrs, effect)` dispatches on `kind` and returns `{"ok": bool, ...}` plus a
`dealt`/`healed`/`spent`/`granted` field. All resource setters on `CombatAttributes` clamp at 0 and at their own
max, so an effect can never push a resource out of range; `grant` is `cost`'s mirror (adds instead of subtracts).

## `CombatComponent.try_ability` / `request_ability`

`try_ability(ability_id, effect, target, cooldown_s, now, allow_friendly_fire)` is the single gate every attack
goes through: cooldown lookup by `ability_id`, then (unless `allow_friendly_fire`) a `team` check between the
caster's attributes and the target's, before `Combat.apply_effect` ever runs. `request_ability` is the
`@rpc("any_peer", "call_local", "reliable")` wrapper added for T-0072: it checks `is_multiplayer_authority()`
BEFORE calling `try_ability` at all, so a non-authoritative peer's call (direct or over the wire) is a silent
no-op, never a path into `try_ability`. Call `try_ability` directly for single-player/local combat; call
`request_ability` (via `rpc_id` from a client, or directly on the authority) once a `MultiplayerPeer` is set.

## What's proven live, and how (`gg_combat.py`)

- `check`: pure `CombatAttributes`/`Combat.apply_effect` unit checks (damage, heal, cost, grant, death at 0
  health, team gating, cooldown gating). No scene tree.
- `slice`: a real `CharacterBody3D` player + dummy, both with `CollisionShape3D`, added to the tree BEFORE their
  `global_position` is set (setting it earlier throws `"!is_inside_tree()"`). Sword is melee-range math; gun is a
  REAL `PhysicsServer3D` raycast (`PhysicsRayQueryParameters3D.create`, `query.exclude` must be an `Array[RID]` via
  `node.get_rid()`, and the ray origin must avoid the capsule's polar cap — aim at mid-torso height, e.g. `+0.5`,
  not `height/2`, or a straight-down/up ray can miss the tangent point); spell is instant-at-range. Also proves
  cooldowns block a repeat and death zeroes further damage.
- `pickups`: an `Area3D` pickup granting ammo (one-shot, `queue_free`s after) and healing mana (`respawn_s`-timed).
  Disabling `monitoring` inside its own `body_entered` signal must go through `set_deferred("monitoring", false)`
  (direct assignment throws `"Function blocked during in/out signal"`), and the respawn wait is real wall-clock
  (`Time.get_ticks_msec()`), not a frame count — frame-to-frame wall time is too variable in this environment for
  a frame-count wait to reliably span a few real seconds.
- `mp`: the one stage that needs TWO concurrent engine processes, which `gg_godot.run()` cannot do (it blocks on
  one `subprocess.Popen(...).communicate()`). `gg_combat.py mp` launches `ops/mp_server_check.gd` and
  `ops/mp_client_check.gd` itself (server first, then a 1s grace, then the client), reusing `gg_godot`'s
  `_new_job`/`build_argv`/`runtime_drift`/`find_godot` rather than duplicating them, and combines both sides'
  `result.json` checks into one verdict. Both ops build the IDENTICAL `/root/Dummy/Combat` NodePath so Godot's
  by-path RPC routing finds the matching node across peers. The client proves two things: a direct, no-`rpc_id`
  call to `request_ability` (the shape a client-side bug or cheat would take) leaves ITS OWN health untouched,
  since its peer id is never the authority regardless of whether the call reached the wire at all; and its
  `rpc_id(1, "request_ability", ...)` call is what the SERVER observes changing its own health, proven from the
  server's independent side, which never calls `try_ability` itself.

## VFX (`gg_vfx.py`, `vfx.gd`)

`VFX.build(recipe)` returns a configured `GPUParticles3D` for one of 4 kinds: `projectile` (looping, narrow
forward cone), `muzzle` (one-shot, tight cone, 0.15s lifetime), `aura` (looping, spherical emission), or the
`impact` default (one-shot, wide spread, gravity). Per-element HDR colour comes from the same `ELEMENTS` table
used by the Unreal Niagara generator, normalised to 0..1 by dividing by its own peak so Godot's unshaded material
doesn't just render white. **A one-shot burst needs `GPUParticles3D.explosiveness = 1.0`** (a node property, NOT
a `ParticleProcessMaterial` property — `explosiveness_ratio` on the material throws) or its default `0.0`
staggers every particle's spawn across the whole (very short) lifetime, so almost none exist at a single-frame
capture. `gg_vfx.py check` needs a real render pass (`gg_verify.selftest_gate(RENDERER)` gate, `renderer=
"gl_compatibility"`, mirroring `gg_ui.py shot`'s `_engine()` pattern) and a camera placed SIDE-ON to the effect's
travel axis — a front-on camera barely changes screen-space size for a small moving quad, so it is a much weaker
"did this draw non-flat pixels" luminance-variance check than a lateral view. **This environment also needs
`LIBGL_ALWAYS_SOFTWARE=1` exported before ANY engine op** (not just render ones — even `--headless --import`
fails with `"ERROR: Parameter \"singleton\" is null."` otherwise), and `gg_verify.py selftest --renderer <r>` is
keyed to the exact `GG_GODOT` binary path: switching binaries needs a fresh selftest run for that binary.

## Animation (`gg_anim.py`, `ops/anim_check.gd`)

For the rogue character, the mesh's skeleton and its separately-exported `MM_*` animation glbs are the SAME
161-bone armature by name (checked directly in Blender first) — this is Unreal's export convention whenever a
mesh and its animations come from one Skeletal Mesh, so **no BoneMap/SkeletonProfile retargeting step was
needed**. The actual work is merging each animation glb's `Animation` resource onto the mesh's own
`AnimationPlayer` and driving an `AnimationNodeStateMachine` across them (`gg_anim.py check --mesh --states
--transitions`, generic over any character/state set, not rogue-specific). One real snag: the T-0067
Blender-rebound mesh and the never-reprocessed animation glbs nest their `Skeleton3D` under differently-named
wrapper nodes (`SKM_Rogue_Main/Skeleton3D` vs `Mesh/Skeleton3D`) even with identical bones, so a copied
animation's track paths do not resolve as-is. `ops/anim_check.gd` fixes this generally: it rewrites every track's
`NodePath` onto the REAL target skeleton's actual path (`character.get_path_to(skeleton)`), keeping only the
bone subname (`track_get_path(i).get_concatenated_subnames()`), rather than assuming the source hierarchy
matches. The check proves each state both `playback.travel()`s to correctly AND visibly moves the skeleton's
`pelvis` bone (root motion is usually baked there, not on the `root` bone) over several subsequent frames — a
state that "transitions" but leaves the pose frozen is a silent T-pose bug this check would otherwise miss.
`gg_anim.py` is NOT registered as a native-worker job step: its `--mesh`/`--states` carry `res://` asset paths,
which the worker's token guard forbids outside `gg_ui.py --scene`/`--dir` (the same reason `gg_assets.py find`/
`use` are excluded) — run it in your own session instead.

## Declarative weapon/spell specs (`gg_combat.py spec`, T-0075)

A JSON file, in the same spirit as `gg_project.json`/`gg_style.json` (one `"schema": 1` doc, checked with the
shared `gg_schema.check()` every other gg_*.py profile uses -- see `gg_project.py`'s `PROFILE_SCHEMA`), the
Godot-side equivalent of `watoom-unreal-combat`'s `combat_spec.zas.json`. `templates/combat_spec.example.json`
is both the worked example and the thing `test_gg_combat.py`'s `Spec`/`Engine` tests load. Top level: `"pack"`
(free-text, which owned fab pack this spec targets -- metadata only, not checked against the filesystem),
`"weapons"` and `"spells"`, each an open dict of `name -> ability`. At least one of the two must be non-empty.

Each ability:

| field | type | meaning |
|---|---|---|
| `display_name` | string, optional | human label |
| `mesh` | string, optional | a static-mesh/skeletal-mesh name from the exported pack, metadata only (nothing here loads it into the scene yet -- see "What this does NOT prove" below) |
| `delivery` | enum `melee`/`raycast`/`instant` | how the effect reaches its target (see the op, below) |
| `range_m` | float 0..10000 | melee: max distance between caster and target; raycast: ray length; instant: unused for a hit test but still required (keeps every ability's shape uniform) |
| `cooldown_s` | float 0..600 | fed straight into `CombatComponent.try_ability`'s existing cooldown gate -- no new cooldown mechanism |
| `effect` | object | `{"kind": "damage"/"heal"/"cost"/"grant", "amount": float, "resource": one of health/shield/stamina/mana/ammo (cost/grant only), "damage_type": string (damage only)}` |
| `cost` | object, optional | `{"resource": ..., "amount": float}` -- a resource paid once up front (e.g. a spell's mana cost), independent of `effect` and of the ability's own cooldown, mirroring the Unreal spec's separate `ManaCost` field |
| `vfx` | object, optional | `name -> recipe`, each recipe exactly `game/vfx.gd`'s own shape (`{"recipe": "projectile"/"impact"/"muzzle"/"aura", "element": ..., "scale"?, "radius"?}`) |
| `animation` | object, optional | free-form hookup metadata (e.g. `{"attack_state": "fire"}`); **recorded as data only** -- see below |

**`effect.damage_type`, not `"element"`.** The ticket that asked for this format (and this doc's own "effect
model" section above) describe the field informally as "element" because that is what both the Unreal side and
the gameplay-design conversation call it. The actual field `game/combat.gd`'s `apply_effect`/`deal_damage`
reads off the dict -- and the one `CombatAttributes.resist` is keyed by -- is `damage_type`. The schema and
`ops/combat_spec_check.gd` use the real field name; only this prose uses "element" as a human-readable gloss.

Validation lives in `gg_combat.py` itself (no new module, reusing `gg_schema` like every other gg_*.py profile):
`spec_errors(doc)` (schema + the "need at least one ability" rule) -> list of error strings; `load_spec(path)`
reads the file and raises `gg_godot.Refused` with all of them if invalid; `resolve_ability(doc, "weapons"/
"spells", name)` returns one ability dict or refuses by name, listing what IS in the spec.

```
gg_combat.py spec --project P --spec combat.json --weapon AssaultRifle
gg_combat.py spec --project P --spec combat.json --spell Fireball
```

`spec` loads+validates the file, resolves the one named ability, and runs it through a new engine op
(`ops/combat_spec_check.gd`) that is data-driven the way `combat_slice.gd` (T-0070) is NOT -- `slice` stays
exactly as it was, hardcoded sword/gun/spell, for backward compatibility; `spec` is the generalisation the
ticket asked for, as an additional subcommand, not a replacement. The op:

1. Builds the same bare `CharacterBody3D` player+dummy pair `combat_slice.gd` does (a `CapsuleShape3D`
   collider and a `CombatComponent` child each) -- no mesh.
2. If the ability has a `cost`, pays it once via `Combat.apply_effect(player.attrs, {"kind": "cost", ...})`
   up front and checks the resource actually dropped by the right amount.
3. Delivers the `effect` to the dummy according to `delivery`: `melee` is a plain distance check (dummy placed
   just inside `range_m`); `raycast` is a REAL `PhysicsServer3D` ray from the player, mid-torso height, against
   the dummy's real collider, exactly like `combat_slice.gd`'s gun case (see the raycast note above); `instant`
   applies at range with no collision test, like `combat_slice.gd`'s spell case. Checks the dummy's health
   moved by exactly the effect's signed amount.
4. Re-fires the SAME ability immediately afterward and checks `try_ability` refuses it (the cooldown gate).
5. For every recipe under `vfx`, calls `VFX.build(recipe)` and checks it returns a `GPUParticles3D` -- proves
   the spec's own recipe dict is well-formed and accepted by the VFX builder. This does **not** render a frame
   or measure pixels; `gg_vfx.py check` (below) is what proves a recipe draws non-flat pixels.
6. Records whether `animation` is present, as a straight data check.

**What this does NOT prove** (same honesty this doc already applies to T-0065/67-73): no mesh is loaded, no
skeleton exists in this test, and no animation actually plays -- `mesh` and `animation` are carried through as
declared data, not bound to anything live. Wiring an exported StaticMesh/SkeletalMesh onto the `CharacterBody3D`
and an `AnimationPlayer` state onto a real skeleton is `gg_assets.py`/`gg_anim.py` territory (see their own
sections), out of scope for this ticket's pilot.

Verified live (2026-11-19): the example spec's `AssaultRifle` weapon (raycast, physical damage) and `Fireball`
spell (instant, with a 20-mana cost) both ran this op against the real engine -- raycast hit the dummy's real
collider for -12 health, the mana cost dropped 100->80, cooldown blocked an immediate repeat on both, and every
named vfx recipe (`muzzle`/`impact` for the rifle, `cast`/`impact` for the fireball) built without error.

### `gg_vfx.py check --combat-spec` (one source of truth for recipes)

`gg_vfx.fx_from_combat_spec(doc)` walks every weapon/spell's `vfx` dict and collects the recipes into the same
`{"fx": {name: recipe}}` shape `check --spec` already consumes, under keys `"<ability>_<vfx-name>"` (e.g.
`AssaultRifle_muzzle`). `gg_vfx.py check --project P --combat-spec combat.json` validates the spec (via
`gg_combat.load_spec`) and renders every recipe named anywhere in it, instead of requiring a hand-maintained
second `fx.json` that could drift from the weapon/spell file. `--spec` and `--combat-spec` are mutually
exclusive. A name clash (the same `<ability>_<vfx-name>` key pointing at two different recipe dicts -- only
possible if a weapon and a spell share a name) is refused rather than silently picking one.

## T-0075 pilot: asset-export status correction

T-0075 was opened on a note claiming all 7 remaining owned weapon/character packs were still Unreal
`.uasset`-only, with only the rogue exported. That note was stale: `low-poly-weapons-set-0794c54e` was already
run through the unreal-export bridge on 2026-11-18 (`/data/ai/artifacts/unreal-export/combat-low-poly-weapons-
set-0794c54e-20261118`, `PORTABLE_EXPORT_PASS`, 8/8 `StaticMesh` exported, 0 failed, source hashes verified
unchanged) as part of that same day's 12-pack export run recorded in T-0065's own closing notes. `templates/
combat_spec.example.json`'s weapons (`AssaultRifle`/`PumpShotgun`/`TacticalKnife`) name that pack's real
exported mesh files (`SM_AssaultRifle_01`, `SM_PumpShotgun_01`, ...; it has no `SkeletalMesh`/`AnimSequence` --
it is static weapon props only). No new export job was run for this pilot; the existing artifact was read and
its `result.json`/mesh files verified in place rather than re-running the bounded worker job for no reason. The
other packs' export status (per T-0065's own closing note: AK-47, low-poly-weapons-set, weapons-free-low-poly,
seven-swords-v2, atris-swords, Mega_Spear, rogue, rpg-hero-squad, both wizards all `PORTABLE_EXPORT_PASS`; M4A1
and Weapon_Pack_03 `PARTIAL_EXPORT`, geometry/rig/animation clean, only some textures failed) should likewise be
re-checked against `/data/ai/artifacts/unreal-export/` before assuming any further export work is needed.

### Pilot finished (2026-11-19): from the export to a live spec with its models

1. The bridge export is FBX per StaticMesh (`exported/Meshes/SM_*.fbx`). Convert with
   `blender-export-pipelines/scripts/fbx_relink_to_glb.py --input <exported/Meshes> --output
   /data/ai/assets/fab/<pack>/glb/converted --no-recursive` (8/8, the flat colour materials come through as
   black shades; no texture files exist in this pack), then `tools/fab/build_model_index.py` so `gg_assets.py find`
   lists them (`converted: true`).
2. `gg_assets.py use --asset low-poly-weapons-set-0794c54e-sm-assaultrifle-01 --project P --slot ar_body` (and the
   magazine/trigger parts) puts them at `res://assets/library/<slot>.glb`.
3. The spec names them: `"mesh"` = the body glb, `"parts"` = the separately exported pieces. Every piece of a pack is
   exported on the body's pivot (the Unreal Blueprint attaches them at the origin), so no offsets are needed.
4. `gg_combat.py spec` adds: the body loads at a hand-held size (longest side 0.1-3 m) and every part's box touches the
   body's. Measured: AssaultRifle 0.85 m (+ magazine, trigger) 8/8, PumpShotgun 0.93 m (+ trigger) 7/7, TacticalKnife
   4/4, Fireball 6/6; `gg_vfx.py check --combat-spec` 7/7. `test_gg_combat.test_spec_models_from_the_converted_pack`
   repeats it when the converted glbs are on the host.

`gg_vfx.py check` gap found on the way: in a `gg_project.py init` 3D project (low-poly style, sky + sun) the stock
recipes read luma_std 0.003-0.008 and FAIL (aura passes); in a `gg_ui.py init` project the same recipes pass
(0.024-0.098). The measurement, not the recipes, depends on the project's environment: run `gg_vfx.py check` in a
UI-init scratch project until the check sets its own neutral environment.

### Pack specs (`templates/combat_specs/<pack>.json`, T-0075 follow-on)

One spec per owned pack, same format as the example; `test_gg_combat.Spec.test_every_pack_spec_is_valid` validates
every file there. Converting a StaticMesh pack whose export has a `Textures/` folder: add `--textures
<exported/Textures>` so the colours are relinked instead of coming through black.

| Spec | Pack | Abilities (proven live with their models) |
| --- | --- | --- |
| `weapons-free-low-poly.json` | weapons-free-low-poly-3d-models-pack-e4d37345 (12 StaticMesh, one texture) | Pistol (+ drum), Rifle (+ magazine), Shotgun (+ handguard), SniperRifle (+ sight): raycast, 7/7 each; Knife, Axe, BaseballBat, HockeyStick: melee, 5/5 each; `gg_vfx.py check --combat-spec` 12/12 |

Measured on 2026-11-20: the guns in weapons-free-low-poly are about twice real size (pistol 0.58 m, rifle 1.76 m,
shotgun 1.73 m, sniper 1.81 m; knife 0.55 m), while the bat (1.12 m), axe (1.15 m) and hockey stick (1.26 m) are close
to real. Scale the held node, not the glb, if a game needs real-size guns. `gg_assets.py check` reports the 0.09 m
pistol drum as a wrong-scale prop: the prop range (0.3-30 m) does not apply to a weapon part, which `gg_combat.py
spec` checks by its box touching the body.

## Scope not covered by T-0065/67-73/75

The backlog proved the mechanics (damage math, a live melee/ranged/spell slice, pickups, multiplayer authority,
VFX, animation merging) against the real engine for ONE character (the rogue) and a handful of demo recipes,
and T-0075 added one declarative, data-driven weapon/spell spec format (above) proven live for one weapon
(`AssaultRifle`, raycast) and one spell (`Fireball`, instant+mana-cost) from one pack (`low-poly-weapons-set`).
It does **not** yet cover: specs for the other packs (M4A1, Weapon_Pack_03, Mega_Spear,
hero-squad, both wizards -- explicitly left for a follow-on, per T-0075's own scope note); holding the spec's
model in a character's hand (the FPS side has `game/fps_weapon.gd` for a first-person gun); binding `animation` to a real
`AnimationPlayer`/skeleton; or extending `delivery` beyond melee/raycast/instant (e.g. a travelling projectile
with its own collision, as opposed to `instant`'s at-range apply).
