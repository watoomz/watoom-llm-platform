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

## Scope not covered by T-0065/67-73

The backlog proved the mechanics (damage math, a live melee/ranged/spell slice, pickups, multiplayer authority,
VFX, animation merging) against the real engine for ONE character (the rogue) and a handful of demo recipes. It
does **not** include a declarative per-weapon/per-spell data format generalised across the rest of the owned
packs (low-poly-weapons-set, weapons-free-low-poly, M4A1, Weapon_Pack_03, Mega_Spear, hero-squad, both wizards)
the way `watoom-unreal-combat`'s `combat_spec.zas.json` does on the Unreal side — that is real, separate scope
(data modelling across many differently-shaped weapons/spells, not just more engine-proving), tracked as its own
follow-on ticket rather than folded into this closing one.
