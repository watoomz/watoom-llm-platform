---
title: Owned animation library
nav: Animation library
summary: Every animation pack owned on Fab, grouped by type (fighting, weapons, locomotion and so on), with rig and format facts and how to apply a pack to a MetaHuman.
---

## What this is

A SQLite catalogue of the animation packs owned on the Fab account, grouped by what the animations are for, plus a tested path for applying a pack to a MetaHuman in Godot. The database is `/data/ai/assets/catalog/animations.db` (a JSON copy sits beside it). Query it with any SQLite client, for example `select type, title, rig_claims, formats from v_packs_by_type` or `select * from v_clips_by_type where type = 'fighting'`. Tables: `packs`, `pack_types`, `clips`, `types`, `recipes`; views `v_packs_by_type` and `v_clips_by_type`.

Built by `tools/fab/animation_catalog.py` (`refresh` re-reads the account; `build` rebuilds from saved inputs). The catalogue lists what is owned; it does not download anything. Any download still needs the owner's per-asset approval through the owned-assets skill.

## Where the list comes from

Fab's API only lists items that have an Unreal-format download, so animation packs that ship only as FBX, glTF or Unity files are invisible to it (the same gap that hid the MetaHuman packs). The My Library > Animations page is the complete list (66 packs); the API shows 44 of them. The rest are resolved one by one through Fab's per-listing endpoints using the titles from that page. The owner-provided page copy is kept at `/data/ai/assets/catalog/sources/` and must be refreshed when new packs are added. One owned title could not be resolved by search and is recorded with its title only.

## Reading the types and rigs

Types are assigned by keywords in the title and description (a title match counts triple) plus Fab's own category, and a pack can belong to several types; the sections below list each pack once, under its primary type; "any match" in the table counts every type a pack touches. Treat the grouping as a first pass to review, not a verdict. `rig_claims` is what the listing says about its skeleton. `skeleton_evidence` is what the files prove, and is only available for packs downloaded to the server; prefer it. Two packs that claim a UE mannequin rig can still be Mixamo-style in the files, so check before relying on a claim.

## Packs by type

| Type | Primary | Any match | What it covers |
|---|---|---|---|
| fighting | 10 | 30 | Hand-to-hand combat: strikes, martial arts, brawling, grapples, blocks, combos |
| weapons_firearms | 10 | 28 | Guns: rifles, pistols, shooting, aiming, reloads, FPS arms animations |
| weapons_melee | 3 | 12 | Held melee weapons: swords, spears, axes, staves |
| locomotion | 11 | 28 | Moving around: idle, walk, run, strafe, sprint, crawl, gait cycles, motion matching sets |
| traversal | 4 | 13 | Getting past things: climbing, ladders, ziplines, gliding, dashes, jumps, swimming, vaulting |
| reactions | 4 | 15 | Taking damage and dying: hits, deaths, falls, injuries, exhaustion, lying/dead poses |
| emotes_social | 7 | 26 | Communication and expression: emotes, gestures, dances, attitudes, talking, sign language, mudras |
| poses_hands | 1 | 8 | Static poses and hand/finger sets |
| daily_life | 6 | 18 | Everyday actions and object interaction: sitting, kneeling, doors, pick-ups, vehicles, tools |
| sport_fitness | 2 | 5 | Exercise and sport: gym, workouts, yoga, qi gong, stretching |
| magic_fantasy | 4 | 13 | Spellcasting and fantasy movement |
| creature_zombie | 0 | 7 | Zombies, creatures and animals (rig-specific) |
| general_variety | 8 | 8 | Mixed or unspecified animation sets |
| tools | 2 | 2 | Animation tools and plugins, not clip sets |
| not_character_animation | 1 | 1 | Motion graphics or non-character animation |
| unusable_format | 5 | 5 | Formats the pipeline cannot read (Sims 4 packages) |

### Fighting

- **Brawler Animations - Free** (SainDeveloper), unity; ~24 clips; free
- **Cutting the throat** (Animation Shopee), fbx; on server; free; also: emotes social, weapons firearms, weapons melee
- **Fight Animation Mocap Pack (10 Animations)** (Mocap.in), fbx; ~10 clips; on server; free
- **Fight Mocap Animation Data** (Mocap.in), fbx; on server; free; also: locomotion, weapons firearms, weapons melee
- **Game-Ready Fight Animation Pack (7 Mocap animation)** (Mocap.in), fbx; ~7 clips; on server; free
- **Martial Art Animations - Sample** (SainDeveloper), unity; ~17 clips; free
- **Motifect Combat Motion Pack** (Motifect), fbx; ~40 clips; on server; free; also: locomotion, reactions, weapons firearms, weapons melee
- **Motifect Martial Arts Motion Pack** (Motifect), fbx; ~40 clips; on server; free; also: weapons firearms
- **RamsterZ Free Anims Volume 1** (RamsterZ), unreal; on server; free; also: emotes social, magic fantasy
- **Realistic Combat Moves – 10 Mocap Pack** (Mocap.in), fbx; ~5 clips; on server; free

### Weapons firearms

- **AK-47 with animations** (A.D), unreal; on server; also: daily life, fighting
- **Animated Tactical Soldier** (ebbelende3D), blender, fbx, usdz, glb; on server; free; also: fighting, traversal, weapons melee
- **First Person Rifle Animation** (xidePunk Studio), unreal; on server; also: fighting, locomotion, poses hands, traversal
- **FPS Animation  Pack_AKS74U** (y0ung001), unreal; ~18 clips; on server; also: fighting, locomotion
- **Free Animation Pack** (Gamma Studio), unreal; on server; free; also: daily life, emotes social, fighting, locomotion, reactions
- **hit by a bullet** (Animation Shopee), fbx; on server; free; also: emotes social, fighting, magic fantasy, reactions, traversal, weapons melee
- **M4A1 rifle with character animations**, unreal; on server; also: daily life
- **Modern Gun Shooting Mocap Pack** (Mocap.in), fbx; on server; free; also: fighting, locomotion
- **Standing with pistol** (Animation Shopee), unknown
- **Weapon Pack 03 (Animated Revolver Handgun)**, unreal; ~3 clips; on server

### Weapons melee

- **FREE Sword + Animation**, unreal; on server; free; also: daily life, emotes social, locomotion
- **Knife FPS Animations**, unreal; on server; also: weapons firearms
- **Mega Spear Animation Pack** (Infectedfury), unreal; ~400 clips; on server; also: fighting, poses hands

### Locomotion

- **8 Way Levitation Locomotion** (MallHockE), unreal; also: magic fantasy
- **ActorCore Sample Motions** (Reallusion Inc), unreal; also: daily life, emotes social, magic fantasy
- **Basic Walk Cycle Animation Pack** (XYZAnimationStudios), unreal; also: creature zombie, fighting, weapons firearms
- **Creative Characters FREE - Animated Low Poly 3D Models**, unreal; ~14 clips; free; also: creature zombie, magic fantasy, traversal
- **Free Crawl Animation** (voxel vision), unreal; free
- **FREE Motion Matching Walk Dance Card** (Quantum Stage - Swiss Mocap Animations), unreal; free; also: emotes social
- **Free Pack - Basic Motions** (PolyOne Studio), unity; ~22 clips; free; also: creature zombie, daily life, fighting, reactions, sport fitness, traversal, weapons firearms
- **MoCap Online Free Animation Pack / UNREAL 3D Character Animations for FAB Market** (MoCap Online), unreal; ~5 clips; free; also: daily life, emotes social, reactions, traversal
- **Motifect Locomotion Motion Pack** (Motifect), fbx; ~45 clips; free; also: traversal, weapons firearms
- **Pistol and Rifle Locomotion Animations 1700** (Kingboars), fbx; free; also: traversal, weapons firearms
- **RIGIPO AI Text to Animation - FREE Animations** (RIGIPO), unreal; ~38 clips; free; also: creature zombie, emotes social, reactions, weapons firearms

### Traversal

- **Dynamic Falling & Rolling Animation Pack - Free Asset** (DZTFIX KATSU), unreal; ~8 clips; free; also: fighting
- **Free Animation Library** (voxel vision), unreal; free; also: daily life, locomotion, weapons melee
- **Free Animation Set - Zipline - Skydiving - Glide - Paraglider - Dash - Falling** (Raul Jaramillo), unreal; free; also: fighting
- **Free Ladder Animation Set** (BPG), unreal; free; also: locomotion

### Reactions

- **Dead Bodies Sitting & Lying Poses – Mocap Pack** (nikoff), unreal; ~30 clips; also: poses hands
- **FREE Dramatic Death – Animation Performances for NPCs & Cinematics** (Darkania Works), unreal; free; also: emotes social, locomotion, magic fantasy
- **Motifect Injured & Exhausted Motion Pack** (Motifect), fbx; ~30 clips; on server; free; also: emotes social, locomotion, weapons firearms
- **Struggle to Ascension – Animation Pack** (Ursa.Animation), unreal; ~19 clips

### Emotes social

- **American Sign Language Animation Pack - Alphabet and Common Words** (The Mighty Cat Games), unreal; ~47 clips
- **Free Anims Mix Pack** (Jane Gintsar), unreal; ~10 clips; free; also: creature zombie, fighting, magic fantasy, reactions, sport fitness, weapons firearms, weapons melee
- **FREE Character Emote Pack** (Klippies), unreal; ~12 clips; free; also: daily life, locomotion
- **Lit Moves Emotes Mocap** (TrashPraxis), unreal; ~14 clips; also: daily life, magic fantasy, sport fitness
- **Motifect Emotes & Social Motion Pack** (Motifect), fbx; ~30 clips; free; also: weapons firearms
- **Mudra Samples** (Rapa Motion), unreal; ~10 clips; also: fighting
- **Various Attitudes animations (Motion Cast - FREE01)** (Motion Cast), unreal; ~16 clips; also: poses hands, reactions

### Poses hands

- **60 Finger Poses / Hand animations / Male & Female** (Attaku), unreal; also: emotes social

### Daily life

- **Character Interaction Add-On Vol.01** (ZzGERTzZ), unreal; also: fighting, magic fantasy
- **Free Interaction Animation** (voxel vision), unreal; free; also: locomotion
- **Motifect Daily Life Motion Pack** (Motifect), fbx; ~40 clips; free; also: emotes social, weapons firearms
- **Motorcycle Interaction Animset FREE** (SpectraMotions), unreal; free; also: fighting, locomotion, poses hands, weapons firearms
- **Simple First-Person Flashlight Animations V1** (Treety), unreal; also: locomotion, traversal
- **Sit, Squat & Kneel - Lifestyle Animation Pack Vol.1** (Archer wei), unreal; also: fighting, locomotion

### Sport fitness

- **Qi Gong animations (Motion Cast - FREE02)** (Motion Cast), unreal; ~22 clips; also: emotes social
- **Sport Gym Fitness Workout DEMO animations** (TricksUp), unreal; on server; also: daily life, reactions

### Magic fantasy

- **External Wing -human fly pose-** (LuckyMachidaJPN), unreal; also: emotes social, poses hands
- **Mage Collection Samples - Free** (Rapa Motion), unreal; free; also: emotes social, fighting, reactions, weapons firearms
- **MC Sample Animation Pack** (MoCap Central), unreal; ~120 clips; also: creature zombie, daily life, emotes social, fighting, locomotion, poses hands, reactions, weapons firearms, weapons melee
- **Motifect Fantasy & Magic Motion Pack** (Motifect), fbx; ~40 clips; free; also: emotes social, fighting, weapons firearms, weapons melee

### General variety

- **10 Variety Game Animations** (Ralentless), unreal
- **[FREE] 2025 Trendy Dance Collection Mocap Pack** (XenoMocap), unreal; free; also: emotes social
- **Free Animations Pack** (SoerGame), unreal; free
- **Free Animations Pack 2** (SoerGame), unreal; free
- **Lyra Animation Sequences Only** (Kingboars), fbx; free
- **Paragon animations retargeted to Manny** (Kingboars), fbx; free
- **UE4 Mannequin: Mobile** (Epic Games), unreal
- **Zombie Animation Pack: Standard** (QuokkaVoid), unreal; ~50 clips; also: creature zombie

### Tools

- **Dynamic Niagara for Animation**, unreal
- **LCAT: Locodrome Character Animation Toolkit**, unreal

### Not character animation

- **Gold Bar animated Background and Logo reveal** (Denis Levin), unreal

### Unusable format

- **QuinSims_SupportPropsForAnimations.package**, package; on server
- **WW_Anarcis.package**, package; on server
- **WW_GreyNaya_Animations.package**, package; on server
- **WW_Quin_Animations.package**, package; on server
- **WW_Quin_BDSM_Animations.package**, package; on server

## On the server

Downloaded packs, with their clips listed in the `clips` table: AK-47 with animations (skeleton not checked); Animated Tactical Soldier (unknown); Cutting the throat (unknown); FPS Animation  Pack_AKS74U (skeleton not checked); FREE Sword + Animation (skeleton not checked); Fight Animation Mocap Pack (10 Animations) (mixamo_style); Fight Mocap Animation Data (mixamo_style); First Person Rifle Animation (skeleton not checked); Free Animation Pack (skeleton not checked); Game-Ready Fight Animation Pack (7 Mocap animation) (mixamo_style); Knife FPS Animations (skeleton not checked); M4A1 rifle with character animations (skeleton not checked); Mega Spear Animation Pack (skeleton not checked); Modern Gun Shooting Mocap Pack (mixamo_style); Motifect Combat Motion Pack (mixamo_style); Motifect Injured & Exhausted Motion Pack (mixamo_style); Motifect Martial Arts Motion Pack (mixamo_style); RamsterZ Free Anims Volume 1 (skeleton not checked); Realistic Combat Moves – 10 Mocap Pack (mixamo_style); Sport Gym Fitness Workout DEMO animations (ue5_mannequin); Weapon Pack 03 (Animated Revolver Handgun) (skeleton not checked); hit by a bullet (unknown).

The Fab library page also marks two Kingboars packs as on disk (Paragon animations retargeted to Manny, 9.91 GB; Pistol and Rifle Locomotion Animations 1700, 2.35 GB). Those copies are on the owner's own machine, not on the server, so they are not in `clips`.

## Applying a pack to a MetaHuman

The converted MetaHuman body uses Unreal mannequin bone names, so most packs reduce to a bone-name mapping. `retarget_animation.gd` (installed with the `watoom-metahuman` skill) converts every clip in an FBX/glTF onto the body skeleton and saves an animation library.

### ue5-direct

- **Applies to:** packs whose skeleton uses UE5 mannequin names (Sport/Gym, Lyra, Manny-retargeted Paragon, most Unreal packs once exported to FBX)
- **Target:** godot (MetaHuman body skeleton) (status: implemented)
- **Steps:** 1) Download the pack (owner approval per asset, watoom-fab-owned-assets). 2) Import its FBX/GLB into the Godot project. 3) Run retarget_animation.gd --source <fbx> --character res://metahuman/<Name>/<Name>.tscn --map identity: it reads each clip, converts bone rotations to character-space deltas and writes them onto the MetaHuman body skeleton as an Animation in an AnimationLibrary. 4) Play it with the character's AnimationPlayer; the head follows because it copies the body pose.
- **Caveats:** Hip translation is scaled by the height ratio; root motion is dropped unless --keep-root is given. Facial animation is not carried (no RigLogic in Godot).

### mixamo-style

- **Applies to:** packs with Mixamo-style bone names (Hips/Spine/Spine1/Spine2/LeftArm..., e.g. Motifect, Mocap.in, many FBX mocap packs)
- **Target:** godot (MetaHuman body skeleton) (status: implemented)
- **Steps:** Same as ue5-direct with --map mixamo. The map pairs Hips->pelvis, Spine/Spine1/Spine2->spine_01/02/03, Neck/Head->neck_01/head, shoulders and limbs by side, fingers by name.
- **Caveats:** Spine-chain counts differ (Mixamo has 3, MetaHuman 5): the extra MetaHuman spine bones keep their rest pose and the rotation is shared across the mapped ones. Check feet for sliding on first use.

### unreal-uasset

- **Applies to:** Unreal-format animation sequences (.uasset)
- **Target:** unreal (MetaHuman) / godot via export (status: documented, not run here)
- **Steps:** In Unreal 5.8: open the pack and the MetaHuman body skeleton, create an IK Retargeter (source: pack IK rig, target: MetaHuman IK rig), batch-retarget the sequences, then play them on the MetaHuman Blueprint or export FBX/glTF for Godot and use ue5-direct.
- **Caveats:** The MetaHuman plugin must be enabled in the project (see watoom-metahuman copy-to-project). Headless export of animation sequences is not wired in the unreal-export pipeline yet.

### unity-only

- **Applies to:** packs whose only format is Unity (.anim/.unitypackage)
- **Target:** none (status: blocked)
- **Steps:** Unity-only animation clips cannot be read by Godot or Unreal. Check the listing for an FBX; otherwise use the pack only inside Unity.
- **Caveats:** Brawler Animations, Martial Art Animations Sample and Free Pack - Basic Motions are Unity-only listings.

### creature-rig

- **Applies to:** zombie/creature/animal packs with their own skeleton
- **Target:** same-rig meshes only (status: documented)
- **Steps:** Apply to the mesh that ships with the pack (or any mesh skinned to the same skeleton). They do not retarget onto a human MetaHuman.
- **Caveats:** Use for zombies/animals already in the game projects.

### sims-package

- **Applies to:** Sims 4 .package animation files in /data/ai/assets/animations
- **Target:** none (status: not usable)
- **Steps:** These are Sims 4 community packages (game-specific binary resources); they cannot be imported to Godot or Unreal by this pipeline.
- **Caveats:** Kept only so the inventory is complete.

### Command

```bash
godot --headless --path <project> --import   # import the FBX first
godot --headless --path <project> -s res://metahuman/MHC_Base_Female/retarget_animation.gd -- \
    --source res://anims/pack/jab_right.fbx --character res://metahuman/MHC_Base_Female/MHC_Base_Female.tscn
# add --inspect (no --character) to print a source's bones and clips; --map identity|mixamo to override detection; --keep-root to keep hip travel
```

The result is written to `<character folder>/animations/<file>.res`. The character script adds every library in that folder to its `IdleAnimation` player automatically: a one-clip library becomes an animation named after the file (`jab_right`), a multi-clip library keeps its clips under `<file>/<clip>`. Play one with `player.play("jab_right")`.

### What was verified

Retargeted onto the Base_Female MetaHuman and rendered on Bazzite: three Motifect combat clips (jab, mid block, hook-uppercut combo) and one Sport/Gym clip (kettlebell windmill) with the delta solver; and from the Mocap.in packs a slow gun-carry walk, a punch guard, a dodge, a crouch, plus the single-file "Cutting the throat" and "hit by a bullet" clips. Stances, guard hands, an extended jab, a raised arm and a full-body fall all read correctly with the character facing the camera. Not verified: foot contact (sliding), long root-motion clips, finger detail, limb roll (elbow/knee bend direction) on the pose solver, and Unreal-format packs.

### Two solvers

Most Mixamo-style mocap files bake their first frame in as the skeleton's "rest" pose, so there is no neutral T-pose to measure motion against. The retargeter checks the source's rest pose and chooses: the **delta** solver (rotation change from a neutral rest, best fidelity) or the **pose** solver (rebuilds each bone from the source joint positions: limbs aim where the source limbs aim, torso twist follows the hip and shoulder lines, hips travel scales by leg length). Force one with `--solver delta|pose`; the log prints `SOLVER` for each run.

### Unreal-format packs

The ten Unreal-format packs (RamsterZ, AK-47, FPS AKS74U, First Person Rifle, Free Animation Pack, M4A1, Weapon Pack 03, Sword + Animation, Knife FPS, Mega Spear) were exported to FBX with the unreal-export pipeline (`export_pack.py --classes AnimSequence --request-extra '{"anim_format":"fbx"}'`, run headless on Bazzite; 587 sequences, none failed) and then retargeted like any other FBX. The originals under `/data/ai/assets/fab` are untouched; the FBX copies are in `/data/ai/artifacts/unreal-export/anims-fbx/`.

### Retargeted libraries

Every FBX pack on the server has been retargeted onto the Base_Female MetaHuman, one animation library per pack (`animation-packs/<pack>.res`; copy one into the character's `animations/` folder to load it, and its clips then play as `<pack>/<clip>`). Weapon and equipment rigs (spear IK, barbell, dumbbell, revolver, AK fire/reload) animate the prop's own skeleton and are skipped on purpose. First-person packs (arms-only rigs) and per-bone helper clips retarget but only move part of the body, so review them before use.

| Pack | Clips retargeted | Files skipped |
|---|---|---|
| Cutting the throat | 1 | 0 |
| Fight Animation Mocap Pack (10 Animations) | 10 | 0 |
| Fight Mocap Animation Data | 10 | 0 |
| First Person Rifle Animation | 16 | 4 |
| FPS Animation  Pack_AKS74U | 14 | 3 |
| Free Animation Pack | 64 | 0 |
| FREE Sword + Animation | 41 | 0 |
| Game-Ready Fight Animation Pack (7 Mocap animation) | 7 | 0 |
| hit by a bullet | 1 | 0 |
| Knife FPS Animations | 15 | 3 |
| M4A1 rifle with character animations | 32 | 2 |
| Mega Spear Animation Pack | 215 | 129 |
| Modern Gun Shooting Mocap Pack | 12 | 0 |
| Motifect Combat Motion Pack | 40 | 0 |
| Motifect Injured & Exhausted Motion Pack | 30 | 0 |
| Motifect Martial Arts Motion Pack | 40 | 0 |
| RamsterZ Free Anims Volume 1 | 44 | 0 |
| Realistic Combat Moves – 10 Mocap Pack | 10 | 0 |
| Sport Gym Fitness Workout DEMO animations | 18 | 24 |

## Limits

- Rotation retargeting only; no facial animation (Godot does not run RigLogic), no retargeting of props or weapons.
- Hip travel is dropped unless `--keep-root` is given, so locomotion clips play in place by default.
- Creature and zombie packs use their own skeletons and do not apply to a human MetaHuman.
- Sims 4 `.package` files in `/data/ai/assets/animations` are listed for completeness only; this pipeline cannot read them.
