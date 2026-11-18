# Combat on the WatooMCombat plugin: procedure and pitfalls (T-0063)

Generic for any game and any creature: the C++ is the plugin (`plugin/WatooMCombat`), everything else is a spec JSON turned into
calls by `scripts/unreal_combat.py` and applied with `tools/rig-ue-mcp/ue_run_phases.py`. The ZAS battle royale slice is
`templates/combat_spec.zas.json` (+ `templates/bodies.zas.json`).

## Procedure
1. Plugin built and installed (tools/rig-ue-mcp/README.md "Building a C++ code plugin"). Check: `editor.get_property
   {"objectPath": "/Script/WatooMCombat.Default__WatooMCombatCharacter", "propertyName": "StartingMaxHealth"}` -> 100.
2. Pick a character model whose PACK IS ANIMATED FOR THE WEAPON (see "Choosing models"). Measure its body:
   `tools/rig-ue-mcp/ue_mesh_body.py --out bodies.json /Game/.../SK_Mesh` (any biped, quadruped, dragon ...), set
   `"bodies_file"` in the spec.
3. Write the spec (weapons/spells/items/characters/input/game_mode/map/place), `unreal_combat.py --spec S --out calls.json`,
   read every `NOTE` it prints, apply with `ue_run_phases.py calls.json`.
4. Verify in PIE (`editor.play_in_editor {"pieAction": "start"}`): `gas.get_attribute` on a dummy, `pie.inject_input` the
   attack action, read Shield/Health again; capture the view with `ue_viewport_shot.py` and LOOK at the pose and the weapon in
   the hand. Ask the owner not to click the rig editor during a test: any click/keypress there ends PIE ("No world available").

## Measured on the rig (2026-11-18, UE5 Manny + Hyper sets, templates/combat_spec.zas.json)
- One command since 2026-11-19: `tools/rig-ue-mcp/ue_combat_check.py --from-calls calls.json --net` -> 8 checks, 0 failed
  (melee 35; Fireball 30 / mana 20; Frost Nova 25 / 35; Heal +40 / 30; medkit 10 -> 60; mana potion 10 -> 60; client swing
  150 -> 115 on the server; client at the host (same team) 100 -> 100).
- Standalone: sword 35 -> dummy Shield 50 -> 15; rifle (18/round, no falloff at 6 m) 2 rounds -> Shield 50 -> 14, ammo 30 -> 28;
  fireball (30 fire, mana 20) -> Shield 15 -> 0 and Health 100 -> 85, mana 100 -> 80. Weapon switch (IA_NextWeapon) loads the
  magazine (Ammo 0 -> 30) and changes the anim stance (bStance_Rifle).
- Listen server + 1 client (PlayNetMode PIE_ListenServer, PlayNumberOfClients 2): the CLIENT's swing is applied on the server
  (dummy Shield 50 -> 15, the client pawn's stamina charged on the server) and replicates (client reads 15). A dummy behind the
  host's camera is hit too. Teammate (same TeamId) in the same spot: no damage; enemy control in that spot: hit. Four more
  swings: Health 80/45/10/0 (clamped), State.Dead, mesh profile Ragdoll + simulate physics.
- Generated anim BP ABP_Manny_Combat: 4 stance states + Air, 17 transitions, compile 0 errors / 0 warnings; captures in
  /data/ai/captures/t0063-combat/manny_{sword,rifle,staff}_side.png.

Playable Polyart wizard (T-0024, 2026-11-19; game mode pawn BP_ZAS_WizardHero, anim set "Wizard" on the pack's
UE4_Mannequin_Skeleton, Staff stance = Idle01 + BattleWalk 4 ways, casts from the pack's Attack01/03Start/04 clips):
staff 150 -> 125 (25), WizardFireball 150 -> 120 (30, mana 100 -> 80), WizardFrostNova 150 -> 125 (25, mana -> 65),
WizardHeal 40 -> 80 (mana -> 70); networked: client swing hits the server's dummy 150 -> 125, same-team host untouched.

Playable RPG Hero (Polyart) and friendly Rogue NPC (T-0024, 2026-11-19): hero anim set "RPGHero" (idle + in-place walk;
the pack has no jump clip, so no Air state), HeroSword on the skeleton's own "Sword" socket, hit window 0.20-0.45 s of the
0.67 s NormalAttack01: 150 -> 115 (35) local and from a network client, teammate untouched (5/5 with the hero as the game
mode pawn). Rogue: SKM_Rogue_Main is the merged mesh (SK_Rogue_Main is its SKELETON), MM_Idle/MM_Walk_Fwd, team 1, wanders
(radius 8 m). A wanderer's Speed reads 0 during its 1-4 s pauses: sample bones a few times before calling it frozen.
To play another hero: set game_mode.pawn and apply only the game_mode phase.

## Pitfalls (each one cost a test round)
- The first PIE session after new blueprints were created can fire nothing (wizard hero, 2026-11-19: 4 FAILs with no mana
  spent; the next session passed 8/8). ue_combat_check.py now runs a throw-away warm-up session first (`--no-warmup` skips it).
- **Mesh sideways in the capsule.** Unreal humanoid meshes face +Y with the root at the feet; a Character faces +X with its capsule
  centre ~90 cm up. Without the offset the sword sweep never reaches the target (stamina is charged, no damage). Never hand-copy
  -90/-90: it is wrong for a dragon or a wolf. Measure with `ue_mesh_body.py` (facing from toes-vs-ankles or head-vs-pelvis,
  capsule radius from the sideways leg spread, half height from bounds). The generator falls back to the humanoid values and
  prints a NOTE when a character has no measured body.
- **Two packs, one look, different skeletons.** "Wizard for Battle" PBR and Polyart have the same body but separate
  `UE4_Mannequin_Skeleton` assets, not marked compatible. An anim BP / montage / blend space plays only on its own skeleton's
  meshes. Use the mesh the existing anim BP was made for (here `/Game/BattleWizardPBR/Meshes/WizardSM`; `BP_WizardPlayer` uses
  it), or retarget. Check: `animation.read_anim_blueprint` -> `targetSkeleton`, and `asset.get_mesh_info` -> `skeletonPath`.
- **A reference pose can look like an animated pose.** The Polyart wizard's bind pose has the arms down, so in a capture it looks
  "animated" while nothing plays; the PBR wizard's bind pose is a T-pose. And a T-pose seen side-on looks like a normal stance.
  Judge animation from `pie.anim_state` (active state / montage) and from two capture angles, not from one picture.
- **Bridge-built anim BP state machines.** `create_state_machine` / `add_state` never wired the entry; such a machine outputs the
  reference pose. `animation.set_state_machine_entry` fixes it (it reports `unchanged` when the entry was already set: the
  ZAS `ABP_WizardPlayer` Locomotion already had Ground as entry, so its T-pose is something else -- open on T-0024/T-0063).
- **Unwired anim graphs = T-pose.** `set_state_animation` drops a player node into the state graph but connects NOTHING (not the
  pose to "Output Animation Pose", not the blend space X/Y). `unreal_combat.py` anim_sets wires every pin explicitly (Get
  Direction -> X, Get Speed -> Y, player Pose -> Result, state machine -> Slot 'DefaultSlot' -> Output Pose). Read a state back
  with `blueprint.read_graph {graphName: <state>}`: every pose pin must say `connected: true`.
- **Hitscan must not trace Visibility.** The default Pawn capsule IGNORES the Visibility channel: a Visibility trace passes
  through every character (`pie.view_trace` shows `blocksVisibility: false`). Gun/spell traces use the weapon's TraceChannel
  (default Pawn); world geometry blocks Pawn too.
- **The server must refresh bones.** A mesh with AlwaysTickPose refreshes bones only while rendered; a server (or a pawn behind
  the listen-server host's camera) is not rendered, so the blade freezes and melee misses. The character sets
  AlwaysTickPoseAndRefreshBones on the authority; a hit window that got fewer than 3 frames also gets a reach sweep.
- **Testing in the editor: the throttle.** The rig editor throttles to a few fps when its window is not in front
  (bThrottleCPUWhenNotForeground); a 0.24 s hit window can pass in one frame. Measurements that need a frame rate: set it false
  (save:false) for the test; it comes back on the next editor start. Ask the owner not to click the editor during a test.
- **A client pawn's rotation is the client's.** level.move_actor on the server can set a client-controlled pawn's location, but
  its facing comes from the client's control rotation: place targets in front of where the CLIENT faces.
- **Borrowing animations from another skeleton (spec `retarget` + `montages`).** The wizard's casts were retargeted onto Manny
  with an existing UE4->UE5 mannequin retargeter (`RTG_UE4Manny_UE5Manny`, shipped in several Fab demo packs; search
  `asset.search {classFilter: IKRetargeter}`): 20 of 28 chains map, the 8 unmapped are finger metacarpals (fine for casts).
  Pick the release time from the clip, not by eye: `animation.sample_pose` hand_r over the clip; Attack01 reaches furthest
  forward at 0.55-0.6 s of 1.0 s, so Fireball ReleaseDelay 0.55. Measured: AM_Manny_CastA plays on cast (anim_state
  currentMontage), mana 80 -> 60, aimed fireball Shield 50 -> 20. A fireball aimed straight ahead from the over-the-shoulder
  camera misses a dummy straight ahead (the camera sits ~90 cm right): aim from `pie.view_trace` viewLocation in tests.
- **Effects (spec `fx`, `scripts/unreal_niagara_fx.py`).** Recipes projectile / impact / muzzle / area / aura (or raw `layers`)
  copy engine template emitters and override module inputs; colour per element (Fire, Frost, Lightning, Poison, Arcane, Holy,
  Physical, Shadow, or [r, g, b]) in HDR. Names in weapon/spell data resolve, also inside structs (`ImpactFx {"Niagara":
  "NS_Hit"}`). Check with `tools/rig-ue-mcp/ue_fx_check.py --from-calls <calls>` (sim cache: count, colour, spread per emitter),
  not with screenshots: a viewport capture takes seconds and misses every burst, and the PIE view can stop redrawing while
  gameplay (GAS) keeps ticking. Lessons, all measured:
  - LocationBasedRibbon has NO spawn module: 0 points even on a flying fireball until SpawnPerFrame is added.
  - Effects spawned unattached (cast, impact) must END: Fountain loops forever; the aura recipe sets the EmitterState
    Loop Behavior static switch to Once (0 particles 4 s later instead of ~40).
  - A sphere spawn around a point at chest height puts half the area burst under the floor (z -224 for a 400 cm nova): area
    bursts use Non Uniform Scale z 0.2 (a disc).
  - Measured in PIE: Frost Nova (Area, 25 frost, 35 mana) Shield 50 -> 25; Heal (Self, 40, 30 mana) Health 40 -> 80; fireball
    trail on the live projectile: core 2-5, embers 4-9 particles in the first frames.
- **Pickups (spec `items` + `place` entries with `item`).** `AWatooMPickup` (plugin) is placed with level.place_actor and
  its Item / RespawnSeconds set with level.set_actor_property. Server-only overlap; the hidden state replicates. Ammo items
  name their gun (`AmmoFor`), so rounds reach the right slot. Measured in PIE: medkit Health 30 -> 80, mana potion Mana
  10 -> 60, rifle ammo reserve (0,90,0) -> (0,150,0) with the SWORD equipped, pickup hidden after use, back after 30 s; at
  full health and shield the medkit stays on the floor (consumables count only what they restore).
- **Generated Niagara edits must be SAVED.** set_module_input/add_module/set_static_switch leave a system dirty; the fx phase
  ends with asset.save. Unsaved, the six systems sat in the editor's shutdown "Save Content" prompt, which blocks every
  bridge call (dialog mode defer: a person answers it).
- **add_module is not idempotent**: a re-run added SpawnPerFrame001 (two spawners). The generator removes the module by name
  first (remove_module on a missing module returns alreadyRemoved).
- **Stopping the editor**: rig_build_plugin.py now stops at once when stop_editor reports unsaved work or a dialog, instead
  of waiting. If an editor ever has to be ended by process (only when the dialog lists nothing but regenerable packages), the
  next start shows "Restore Packages" (a startup modal; an auto-relaunch shows it again before start_editor's dialogPolicy
  can apply): remove <project>/Saved/Autosaves/PackageRestoreData.json and the listed autosaves first, then re-apply the spec.
  A start_editor dialogPolicy takes response KEYWORDS ("Restore Packages=no"), not button labels.
- **Montage paths are nested.** Hyper montages live in .../Locomotion/<Style>/Attack/ (Sword) or /Melee/ (Staff); search with
  `asset.search {classFilter: AnimMontage}` instead of guessing. Hyper notifies inside them (AN_AnimTrail, AN_MeleeDamage, ...)
  expect Hyper components and log "Accessed None" in PIE: harmless; WatooMCombat uses its own timed hit window.
- **Plugin rebuild cycle.** `tools/rig-ue-mcp/rig_build_plugin.py <plugin> --install --check-class ... --check-prop ...`
  stages, builds standalone, waits until THIS project's editor process is gone, installs, restarts and checks a class default.
  After a restart the editor opens its default map: `level.load` the test map before PIE.
- **Game mode path.** `gameplay.set_world_game_mode` needs the generated class `<path>.<Name>_C`; the asset path fails with
  "GameMode class not found". The generator writes the class path.
- **Placed actors keep old values.** Changing a character Blueprint default (mesh, body) does not update actors already placed
  in a map if they hold an instance value: re-place them (delete + place) after a mesh change.

## Choosing models (weapon <-> animation)
**Default for every combat character (owner, 2026-11-18: "a model with animations that suits all the different types of
combat"):** the UE5 Mannequin (SKM_Manny / SKM_Quinn) from Hyper Combat Framework v4 (`/Game/Hyper/Locomotion/Chars/
Mannequin_UE5`), which carries one animation set per combat style on ONE skeleton: Sword(34) Sword_Light Sword_Dual
Sword_Shield Blade Dagger Spear Hatchet_Dual Melee_Heavy_Dual Fists_Light | Rifle(110) Pistol(100) Shotgun Bow(36) Grenade |
Staff(20) Staff_Magic(4) | Unarmed(100) HeavyHitReact Dodge GetUp Swimming Hover. Magic is thin there: add the Wizard for
Battle casts (UE4 Mannequin skeleton) by IK retargeting to Manny. Any other look (wizard, hero, monster) wears this set through
an IK retargeter instead of needing its own combat animations. Hyper's blueprints are NOT used (GAS runtime is the plugin).

A model is only right for a weapon when its pack has animations for it. Check the pack before writing the spec:
`find /data/ai/assets/fab/<pack>/Content -name "*.uasset" | grep -i anim`.
- Wizard for Battle (PBR/Polyart): staff caster. Ships Staff01-03SM and idle x3, walk 4-dir, run, jump set, Attack01-04
  (02/03 charged start+maintain), defend, get-hit, dizzy, die/recover, potion drink, pick-up, victory. Use for magic + staff
  melee, not swords or guns.
- Swords: a character with sword animations (FREE_Sword_Animation, rpg-hero-squad, fight mocap packs, retargeted).
- Guns: Animated_Tactical_Soldier, M4A1_rifle_with_character_animations, AK_47_with_animations.

## Creatures (roaming, killable; T-0023, measured 2026-11-19)
1. Import each rigged FBX with `tools/rig-ue-mcp/rig_import_fbx_character.py --name N --dest /Game/.../Animated/N
   --mesh <clip>_withSkin.fbx --anim Walk=... --anim Run=... --textures-from <folder> --apply`. It always uses the
   **Interchange** importer: the legacy FBX importer made these rigs' mesh node `Mesh0` the ROOT bone, and every clip then failed
   ("Mesh contains Mesh0 bone as root but animation doesn't contain the root track"). With Interchange the root is `Hips` and
   the clips import with all 24 tracks.
2. `ue_mesh_body.py --out templates/bodies.creatures.zas.json <SK paths>` (measured: all three face +Y, capsule r 38-47, hh 81-85).
3. A spec like `templates/creatures_spec.zas.json`: per creature an anim_set whose only stance has `idle` and `fwd` = the walk
   (a missing direction uses `fwd`, so a turning creature never blends toward idle), and a character with team 3 and
   `Wander.bEnabled` true. `Wander.MinGroundZ` = the sea surface keeps land creatures out of the water.
4. Spots: shore pixels 1-4 m above the sea next to water in the live heights, >= 400 m apart; place 2 m above the ground.
5. Verify in PIE: positions change (~200 cm/s), `pie.anim_state` shows the creature's ABP with Speed > 0, and
   `animation.get_bone_transform` (world pie, space component) on a foot moves between samples (measured: the foot swings
   40-60 cm and lifts up to 30 cm). A PIE screenshot shows only the player's camera, so judge by these numbers.

Statues and props beside creatures: a `place` entry with `static_mesh` (+ rotation, uniform `scale`) becomes a StaticMeshActor.
The owned dinosaur "theme park statue" packs are static FBX (no skeleton, no clips): import with `asset.import_static_mesh`
(it takes no `save`), check `asset.get_mesh_bounds` (the Spinosaurus came in 1.9 m long; x8 = ~15 m, life size), seat it at
ground + half-height*scale on a spot that is flat over the whole footprint, then `ue_stray_check.py --no-foliage`.

`UWatooMWanderComponent` (on every WatooMCombatCharacter, off by default): server-only; picks a random point within Radius of
the start (traced ground, not below MinGroundZ), walks there with AddMovementInput (the AI controller that placed characters get
by default is what lets that move them), waits WaitMin-WaitMax, repeats; a walk blocked for StuckSeconds picks a new point;
the dead stop. Each anim set is its own phase (`anim <Set>`): graph calls are not idempotent, so re-apply only new sets
(`ue_run_phases.py --phase`).
