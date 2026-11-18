---
name: watoom-unreal-combat
description: Networked combat for Unreal 5.8 games on GAS - melee weapons, guns, magic spells, items/pickups, combat animation (generated anim blueprints, retargeted montages), Niagara VFX recipes and a server-authoritative damage system (shield then health, teams, death/ragdoll). One JSON spec -> ue-mcp call phases (unreal_combat.py, unreal_niagara_fx.py) on top of the WatooMCombat C++ plugin. Use when asked to add weapons, guns, spells, pickups, combat animations, hit/cast/impact effects or damage to an Unreal character or game, or to fix them.
---

# WatooM Unreal combat

Use the existing watoom-workflow -> watoom-builder hierarchy; the rig editor is reached through the `watoom-ue` tools /
`tools/rig-ue-mcp`. Everything is data: a combat spec JSON describes the game's weapons, spells, items, effects,
characters and test arena; the generators turn it into call phases; `ue_run_phases.py` applies them; the checks prove them.
Read `references/combat.md` before changing anything: procedure, measured results and every pitfall found so far.

## Parts

| Part | Where | What |
|---|---|---|
| Runtime | `plugin/WatooMCombat` (C++, GAS) | attribute set (Health/Shield/Stamina/Mana/Ammo/Team/Resists), damage execution, melee/gun/reload/spell abilities, projectile, pickup, combat character, stance anim instance. Server-authoritative, replicated. |
| Build/install the plugin | `tools/rig-ue-mcp/rig_build_plugin.py <plugin> --install --check-class ...` | standalone BuildPlugin, waits for the editor to exit, installs, restarts, verifies |
| Spec -> calls | `scripts/unreal_combat.py --spec <spec> --out calls.json` | tags, input (copy of the game's mapping context), anim sets (blend spaces + wired anim BP per skeleton), retarget, montages, fx, weapon/spell/item data assets, characters (measured bodies), game mode, arena map, dummies and pickups |
| Effects | `scripts/unreal_niagara_fx.py` (also the spec's `fx` section) | recipes projectile / impact / muzzle / area / aura or raw layers, coloured per damage element |
| Bodies | `tools/rig-ue-mcp/ue_mesh_body.py --out bodies.json <meshes>` | facing, capsule and mesh offset for any skeleton (biped, quadruped, dragon) |
| Apply | `tools/rig-ue-mcp/ue_run_phases.py calls.json` | runs the phases, stops on the first failure |
| Check effects | `tools/rig-ue-mcp/ue_fx_check.py --from-calls calls.json` | particles, colour and spread per emitter from the sim cache |
| Check combat | `tools/rig-ue-mcp/ue_combat_check.py --from-calls calls.json [--net]` | PIE: melee, every spell, consumable pickups, client authority and teams; PASS/FAIL with the numbers |
| Worked example | `templates/combat_spec.zas.json`, `templates/bodies.zas.json` | the ZAS battle royale slice: UE5 Manny + Hyper sets, sword/rifle/staff, Fireball/Frost Nova/Heal, pickups |

## Add combat to a game

1. Pick ONE character model animated for every combat style you need (the ZAS slice uses Hyper's UE5 Manny: Sword, Rifle,
   Staff, Unarmed and more on one skeleton). Check it: animations exist per stance, the skeleton matches, measure the body.
2. Copy `templates/combat_spec.zas.json`; set `content_root`, the input mapping context to copy, `anim_sets` (stance ->
   idle + jog anims), weapons (mesh, socket, montage, damage), spells, items, `fx`, characters and the test arena.
3. `ue_mesh_body.py` for each character mesh -> `bodies_file`.
4. Generate, apply, then run `ue_combat_check.py --from-calls calls.json --net`; for anything it does not cover, verify in PIE (standalone, then PlayNetMode listen server + 1 client): damage once per hit on the
   server, shield before health, teammates immune, death -> State.Dead + ragdoll, ammo/mana/cooldowns, pickups. Judge poses
   by `pie.anim_state` and two capture angles; judge effects with `ue_fx_check.py`, not screenshots.
5. Record measured numbers in `references/combat.md` and on the ticket.

## Rules

- Never hand-edit generated assets on the rig: change the spec or the generator and re-apply (data assets upsert,
  blueprints/tags/actions are idempotent, placed actors are skipped when they exist).
- Plugin changes: edit `plugin/WatooMCombat` here, rebuild with `rig_build_plugin.py`; never edit the copy on the rig.
- Damage and pickups run on the server only; clients see replicated attributes and multicast effects.
- Post on the coordination ticket before restarting the editor or running PIE (it stops whatever else uses the editor).
