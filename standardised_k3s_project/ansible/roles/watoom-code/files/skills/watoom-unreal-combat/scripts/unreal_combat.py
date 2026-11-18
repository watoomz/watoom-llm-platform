#!/usr/bin/env python3
"""Combat content for any Unreal game on the WatooMCombat plugin: one spec JSON -> a phases calls file for ue_run_phases.py.

  unreal_combat.py --spec combat.json --out calls.json [--project unreal_project.json]

The C++ (attributes, damage, abilities, character) lives in the plugin (plugin/WatooMCombat, built and installed per
tools/rig-ue-mcp/README.md "Building a C++ code plugin"). Everything a game adds is DATA, written by this script:

  {"content_root": "/Game/<Game>/Combat",            default: <profile content_root>/Combat
   "tags": ["Damage.Type.Poison"],                    extra gameplay tags to register (spell cooldown tags are added automatically)
   "input": {"base_imc": "/Game/.../IMC_Player",      optional: copied (never edited) to <root>/Input/<imc>, keeps its keys/modifiers
             "imc": "IMC_Combat",
             "actions": {"Move": "/Game/.../IA_Move", "Look": "...", "Jump": "...", "Primary": "..."},   existing InputActions
             "new_actions": {"Reload": "R", "NextWeapon": "Q"},                                        made here: IA_<name> + key
             "spell_keys": ["One", "Two", "Three"]},                                                   IA_Spell<i> per spell slot
   "retarget": [{"retargeter": "/Game/.../RTG_UE4Manny_UE5Manny", "source_mesh": "/Game/.../SK_Src", "target_mesh":
                 "/Game/.../SKM_Manny", "anims": ["/Game/.../Attack01Anim"], "output": "Manny/FromWizard", "prefix": "MM_Wizard_"}],
                                                      -> <root>/Anim/<output>/<prefix><anim>_Retargeted (animation.batch_retarget_animations)
   "montages": {"AM_CastA": {"anim": "/Game/.../Cast_Seq", "slot": "DefaultSlot", "blendIn": 0.1, "blendOut": 0.2}},
                                                      -> <root>/Anim/Montages/AM_CastA; a weapon/spell property naming one resolves to it
   "fx": {"NS_Fireball_Trail": {"recipe": "projectile", "element": "Fire"}}   -> <root>/FX/... (unreal_niagara_fx.py recipes);
                                                      ProjectileFx "NS_Fireball_Trail" or ImpactFx {"Niagara": "NS_..."} resolve
   "weapons": {"Sword": {"Kind": "Melee", "StaticMesh": "/Game/...", "Damage": 35, ...}},   -> <root>/Weapons/DA_Weapon_Sword
   "spells":  {"Fireball": {"Delivery": "Projectile", "ManaCost": 20, ...}},                 -> <root>/Spells/DA_Spell_Fireball
   "items":   {"Medkit": {"Kind": "Consumable", "RestoreHealth": 50}, "RiflePickup": {"Kind": "Weapon", "Weapon": "Rifle"}},
   "anim_sets": {"Manny": {"skeleton": "/Game/.../SK_Mannequin", "speed": 400, "default_stance": "Unarmed",
                           "stances": {"Unarmed": {"idle": A, "fwd": A, "bwd": A, "left": A, "right": A}, "Sword": {...}},
                           "air": "/Game/.../Fall_Loop"}},   -> <root>/Anim/<set>/ABP_<set>_Combat + BS_<set>_<stance>
   "bodies_file": "bodies.json",                      ue_mesh_body.py output (mesh path -> body); relative to the spec file
   "characters": {"BP_Hero": {"anim_set": "Manny" (sets Mesh.AnimClass to the generated anim BP),
                              "body": {...} (optional; else looked up in bodies_file by Mesh.SkeletalMeshAsset), "defaults": {"Mesh.SkeletalMeshAsset": "/Game/...", "Mesh.AnimClass": "/Game/.../ABP_X", "TeamId": 1},
                              "weapons": ["Sword", "Rifle"], "spells": ["Fireball"], "player": true}},
   "game_mode": {"name": "BP_CombatGameMode", "pawn": "BP_Hero"},       a GameMode BP whose DefaultPawnClass is that character
                                                                         (pawn may be a /Game/ path: a hero another spec made)
   "map": {"path": "/Game/<Game>/Combat/Maps/L_Arena", "template": "/Engine/Maps/Templates/Template_Default"},
   "remove": ["OldPlayer"],                                             actor labels deleted from the map before placing
                                                                         (e.g. a hand-placed pawn the game mode's hero replaces)
   "place": [{"character": "BP_Dummy", "label": "Dummy_1", "location": [x, y, z], "rotation": [0, 180, 0]},
             {"item": "Medkit", "label": "Pickup_Medkit_1", "location": [x, y, z], "respawn": 30},   -> AWatooMPickup
             {"static_mesh": "/Game/.../SM_Statue", "label": "Statue_1", "location": [x, y, z], "rotation": [...], "scale": 8}]}
                                                                         -> a StaticMeshActor (statues, props next to creatures)

"anim_sets" (any skeleton): one 2D blend space per stance (X = Direction -180..180, Y = Speed 0..speed; idle on the speed-0
row, fwd/right/left/bwd jogs at 0/90/-90/+-180) and one anim BP whose parent is UWatooMCombatAnimInstance, with variables
Speed, Direction, bInAir, bIsDead and bStance_<Name>, a Locomotion state machine (a state per stance + Air), the blend space
player wired to the state output and fed by Get Direction / Get Speed, transitions stance->stance on bStance_<to>, stance->Air
on bInAir, Air->default stance on NOT bInAir, the entry set explicitly, and Locomotion -> Slot 'DefaultSlot' -> Output Pose.
Every wire is explicit: set_state_animation and create_state_machine do NOT wire anything (an unwired state outputs the
reference pose = T-pose, T-0063 2026-11-18). A weapon chooses its stance with "Stance" (missing stance -> default stance).
Re-running the anim section on an existing anim BP is not supported (state machines are not idempotent): delete the anim BP
(asset.delete) first, or use a new set name.

"map" is opened (created from the template the first time) before anything is placed; the game mode is set as that level's
override. Without "map", place/game_mode act on the level open in the editor.

Property names inside weapons/spells/items/defaults are the plugin's UPROPERTY names as they are (see references/combat.md):
enums by value name ("Gun", "Auto"), gameplay tags by plain name ("Damage.Type.Fire"), assets by path. In items, "Weapon", "AmmoFor" and
"Spell" may name a weapon/spell of this spec. A spell without "CooldownTag" gets Cooldown.Spell.<Name>, registered here.
"player": true wires the input actions and mapping context into the character (Move/Look/Jump/Primary/Reload/NextWeapon/Spells).
Characters are Blueprints of /Script/WatooMCombat.WatooMCombatCharacter (or "parent"). Re-running is safe: data assets are
upserted, Blueprints/actions/tags are idempotent, placed actors use onConflict skip.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "watoom-texture-layering", "scripts"))
import ue_project  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unreal_niagara_fx  # noqa: E402

PARENT = "/Script/WatooMCombat.WatooMCombatCharacter"
CLASSES = {"weapons": ("WatooMWeaponData", "Weapons", "DA_Weapon_"),
           "spells": ("WatooMSpellData", "Spells", "DA_Spell_"),
           "items": ("WatooMItemData", "Items", "DA_Item_")}
# FALLBACK only, for a character with no measured body: the humanoid import convention (mesh faces +Y, root at the feet, ~180 cm).
# Measure every model instead (tools/rig-ue-mcp/ue_mesh_body.py: biped, quadruped, dragon, ...) and pass it as "body" or
# "bodies_file". Without a body the mesh stands sideways in the capsule and melee sweeps/muzzles point the wrong way (T-0063,
# 2026-11-18: the first sword test charged stamina but never hit). A spec's own "defaults" always win.
MESH_DEFAULTS = {"Mesh.RelativeLocation": "(X=0.000000,Y=0.000000,Z=-90.000000)",
                 "Mesh.RelativeRotation": "(Pitch=0.000000,Yaw=-90.000000,Roll=0.000000)"}
BODY_KEYS = {"CapsuleHalfHeight": "CapsuleComponent.CapsuleHalfHeight", "CapsuleRadius": "CapsuleComponent.CapsuleRadius",
             "Mesh.RelativeLocation": "Mesh.RelativeLocation", "Mesh.RelativeRotation": "Mesh.RelativeRotation"}
INPUT_SLOTS = {"Move": "MoveAction", "Look": "LookAction", "Jump": "JumpAction", "Primary": "PrimaryAction",
               "Reload": "ReloadAction", "NextWeapon": "NextWeaponAction"}


def asset_path(root, kind, name):
    cls, folder, prefix = CLASSES[kind]
    return "%s/%s/%s%s" % (root, folder, prefix, name)


def cooldown_tag(name, props):
    return props.get("CooldownTag") or "Cooldown.Spell." + name


def montage_calls(root, spec):
    items = []
    for name, m in sorted(spec.get("montages", {}).items()):
        if not name.replace("_", "").isalnum() or "anim" not in m:
            raise ValueError("montages.%s: needs a plain asset name and an 'anim'" % name)
        items.append({"name": name, "packagePath": root + "/Anim/Montages", "animSequencePath": m["anim"],
                      "slotName": m.get("slot", "DefaultSlot"), "blendIn": m.get("blendIn", 0.1), "blendOut": m.get("blendOut", 0.2)})
    return [["animation.author_montages_batch", {"items": items}]] if items else []


PICKUP = "/Script/WatooMCombat.WatooMPickup"


def upsert(root, spec, kind, resolve=None):
    cls, folder, prefix = CLASSES[kind]
    items = []
    for name, props in sorted(spec.get(kind, {}).items()):
        p = dict(props)
        if kind == "spells":
            p["CooldownTag"] = cooldown_tag(name, props)
        if resolve:
            p = resolve(p)
        items.append({"name": prefix + name, "className": cls, "packagePath": "%s/%s" % (root, folder), "properties": p})
    return ["asset.bulk_upsert_data_assets", {"items": items, "onConflict": "update", "save": True}] if items else None


SLOT = "Slot 'DefaultSlot'\nGroup 'DefaultGroup'"
DIRS = (("fwd", 0.0), ("right", 90.0), ("left", -90.0), ("bwd", 180.0), ("bwd", -180.0))


def anim_set_calls(root, name, a):
    """Blend spaces + generated combat anim BP for one skeleton (see module docstring)."""
    pkg = "%s/Anim/%s" % (root, name)
    abp = "%s/ABP_%s_Combat" % (pkg, name)
    speed = float(a.get("speed", 400))
    stances = a["stances"]
    default = a.get("default_stance", "Unarmed")
    if default not in stances:
        raise ValueError("anim_sets.%s: default_stance %s is not one of its stances %s" % (name, default, sorted(stances)))
    for st in stances:
        if not st.isalnum():
            raise ValueError("anim_sets.%s: stance %r must be letters/digits (it becomes bStance_%s)" % (name, st, st))
    calls = []
    for st, anims in sorted(stances.items()):
        if "idle" not in anims:
            raise ValueError("anim_sets.%s.%s needs at least an idle" % (name, st))
        bs = "BS_%s_%s" % (name, st)
        samples = [{"animation": anims["idle"], "x": x, "y": 0.0} for x in (-180.0, 0.0, 180.0)]
        # a direction without its own clip uses the forward one (creatures and NPCs often ship only a walk; they turn to face
        # where they go, so Direction stays near 0 anyway, and the blend never falls back to the idle mid-stride)
        samples += [{"animation": anims.get(k) or anims["fwd"], "x": x, "y": speed} for k, x in DIRS if anims.get(k) or anims.get("fwd")]
        calls.append(["animation.create_blendspace", {"name": bs, "skeletonPath": a["skeleton"], "packagePath": pkg,
                                                      "axisHorizontal": "Direction", "horizontalMin": -180, "horizontalMax": 180,
                                                      "axisVertical": "Speed", "verticalMin": 0, "verticalMax": speed, "onConflict": "skip"}])
        calls.append(["animation.populate_blendspace", {"assetPath": "%s/%s" % (pkg, bs), "clearExisting": True, "samples": samples}])
    calls.append(["animation.create_anim_blueprint", {"name": "ABP_%s_Combat" % name, "skeletonPath": a["skeleton"], "packagePath": pkg,
                                                      "parentClass": "/Script/WatooMCombat.WatooMCombatAnimInstance", "onConflict": "skip"}])
    variables = [("Speed", "float"), ("Direction", "float"), ("bInAir", "bool"), ("bIsDead", "bool")]
    variables += [("bStance_" + st, "bool") for st in sorted(stances)]
    for v, t in variables:
        calls.append(["blueprint.add_variable", {"assetPath": abp, "name": v, "varType": t, "onConflict": "skip"}])
    sm = "Locomotion"
    calls.append(["animation.create_state_machine", {"assetPath": abp, "name": sm}])
    states = sorted(stances) + (["Air"] if a.get("air") else [])
    for st in states:
        calls.append(["animation.add_state", {"assetPath": abp, "stateMachineName": sm, "stateName": st, "onConflict": "skip"}])
    wire = lambda graph, sn, sp, tn, tp: ["blueprint.connect_pins", {"assetPath": abp, "graphName": graph, "sourceNode": sn,  # noqa: E731
                                                                    "sourcePin": sp, "targetNode": tn, "targetPin": tp, "deferCompile": True}]
    for st in sorted(stances):
        bs = "BS_%s_%s" % (name, st)
        player = "%s\nBlendspace Player" % bs
        calls.append(["animation.set_state_animation", {"assetPath": abp, "stateMachineName": sm, "stateName": st, "animAssetPath": "%s/%s" % (pkg, bs)}])
        calls.append(wire(st, player, "Pose", "Output Animation Pose", "Result"))
        for v in ("Direction", "Speed"):
            calls.append(["blueprint.add_node", {"assetPath": abp, "graphName": st, "nodeClass": "K2Node_VariableGet",
                                                 "nodeParams": {"variableName": v}, "deferCompile": True}])
        calls.append(wire(st, "Get Direction", "Direction", player, "X"))
        calls.append(wire(st, "Get Speed", "Speed", player, "Y"))
    if a.get("air"):
        air = a["air"].rsplit("/", 1)[1].split(".")[0]
        calls.append(["animation.set_state_animation", {"assetPath": abp, "stateMachineName": sm, "stateName": "Air", "animAssetPath": a["air"]}])
        calls.append(wire("Air", "%s\nSequence Player" % air, "Pose", "Output Animation Pose", "Result"))
    for st in sorted(stances):
        for to in sorted(stances):
            if to != st:
                calls.append(["animation.add_transition", {"assetPath": abp, "stateMachineName": sm, "fromState": st, "toState": to, "blendDuration": 0.2}])
                calls.append(["animation.set_transition_condition", {"assetPath": abp, "stateMachineName": sm, "fromState": st, "toState": to,
                                                                     "variableName": "bStance_" + to}])
        if a.get("air"):
            calls.append(["animation.add_transition", {"assetPath": abp, "stateMachineName": sm, "fromState": st, "toState": "Air", "blendDuration": 0.15}])
            calls.append(["animation.set_transition_condition", {"assetPath": abp, "stateMachineName": sm, "fromState": st, "toState": "Air",
                                                                 "variableName": "bInAir"}])
    if a.get("air"):
        calls.append(["animation.add_transition", {"assetPath": abp, "stateMachineName": sm, "fromState": "Air", "toState": default, "blendDuration": 0.15}])
        calls.append(["animation.set_transition_condition", {"assetPath": abp, "stateMachineName": sm, "fromState": "Air", "toState": default,
                                                             "variableName": "bInAir", "negate": True}])
    calls.append(["animation.set_state_machine_entry", {"assetPath": abp, "stateMachineName": sm, "stateName": default}])
    calls.append(["blueprint.add_node", {"assetPath": abp, "graphName": "AnimGraph", "nodeClass": "AnimGraphNode_Slot", "deferCompile": True}])
    calls.append(wire("AnimGraph", "%s\nState Machine" % sm, "Pose", SLOT, "Source"))
    calls.append(wire("AnimGraph", SLOT, "Pose", "Output Pose\nAnimGraph", "Result"))
    calls.append(["blueprint.set_class_default", {"assetPath": abp, "propertyName": "DefaultStance", "value": default}])
    calls.append(["blueprint.compile_all", {"assetPaths": [abp], "save": True}])
    return abp, calls


def body_defaults(name, c, bodies, notes):
    """Capsule + mesh transform for one character from its measured body (any creature), else the humanoid fallback."""
    mesh = c.get("defaults", {}).get("Mesh.SkeletalMeshAsset")
    b = c.get("body") or (bodies or {}).get(mesh)
    if not b:
        if mesh:
            notes.append("%s: no measured body for %s; using the humanoid fallback. Run tools/rig-ue-mcp/ue_mesh_body.py %s"
                         % (name, mesh, mesh))
        return dict(MESH_DEFAULTS)
    return {BODY_KEYS[k]: v for k, v in b.items() if k in BODY_KEYS}


def build(spec, root, notes=None):
    notes = [] if notes is None else notes
    spec = dict(spec)
    root = spec.get("content_root", root).rstrip("/")
    weapons, spells = spec.get("weapons", {}), spec.get("spells", {})
    for kind in ("weapons", "spells", "items"):
        for name in spec.get(kind, {}):
            if not name.replace("_", "").isalnum():
                raise ValueError("%s name %r: letters, digits and _ only (it becomes an asset name)" % (kind, name))
    phases = []

    anim_bps = {}
    anim_phases = []
    for set_name, a in sorted(spec.get("anim_sets", {}).items()):
        anim_bps[set_name], cs = anim_set_calls(root, set_name, a)
        # one phase per set: the graph calls (add_node, connect_pins) are NOT idempotent, so a set that already exists on the rig
        # must be left out when re-applying (ue_run_phases.py --only / a filtered calls file); its phase name says which it is
        anim_phases.append({"name": "anim " + set_name, "calls": cs})

    tags = list(dict.fromkeys(list(spec.get("tags", [])) + [cooldown_tag(n, p) for n, p in sorted(spells.items())]))
    if tags:
        phases.append({"name": "tags", "calls": [["reflection.create_tag", {"tag": t, "comment": "WatooMCombat (unreal_combat.py)"}]
                                                 for t in tags]})

    inp = spec.get("input")
    action_paths, imc_path, spell_actions = {}, None, []
    if inp:
        calls = []
        ipkg = root + "/Input"
        action_paths.update(inp.get("actions", {}))
        imc_path = "%s/%s" % (ipkg, inp.get("imc", "IMC_Combat"))
        if inp.get("base_imc"):
            calls.append(["asset.duplicate", {"sourcePath": inp["base_imc"], "destinationPath": imc_path, "onConflict": "skip"}])
        else:
            calls.append(["gameplay.create_input_mapping", {"name": imc_path.rsplit("/", 1)[1], "packagePath": ipkg, "onConflict": "skip"}])
        keyed = list(inp.get("new_actions", {}).items())
        keys = inp.get("spell_keys", [])
        # keys are SLOTS (spell 1, 2, 3 of whichever character is played), so the count is the most spells one player carries,
        # not the spec's spell count (a second hero with its own three spells needs no extra keys)
        slots = max([len(c.get("spells", [])) for c in spec.get("characters", {}).values() if c.get("player")] or [len(spells)])
        if len(keys) < slots:
            raise ValueError("input.spell_keys has %d key(s) for %d spell slot(s)" % (len(keys), slots))
        for i in range(slots):
            keyed.append(("Spell%d" % (i + 1), keys[i]))
        for name, key in keyed:
            path = "%s/IA_%s" % (ipkg, name)
            calls.append(["gameplay.create_input_action", {"name": "IA_" + name, "packagePath": ipkg, "valueType": "Boolean",
                                                          "onConflict": "skip"}])
            calls.append(["gameplay.add_imc_mapping", {"imcPath": imc_path, "inputActionPath": path, "key": key, "save": True}])
            if name.startswith("Spell") and name[5:].isdigit():
                spell_actions.append(path)
            else:
                action_paths[name] = path
        phases.append({"name": "input", "calls": calls})

    phases.extend(anim_phases)

    rcalls = []
    for r in spec.get("retarget", []):
        rcalls.append(["animation.batch_retarget_animations", {
            "retargeterPath": r["retargeter"], "sourceMesh": r["source_mesh"], "targetMesh": r["target_mesh"], "animPaths": r["anims"],
            "outputPath": "%s/Anim/%s" % (root, r["output"]), "prefix": r.get("prefix", ""), "overwrite": False}])
    if rcalls:
        phases.append({"name": "retarget", "calls": rcalls})

    montages = {n: "%s/Anim/Montages/%s" % (root, n) for n in spec.get("montages", {})}
    mcalls = montage_calls(root, spec)
    if mcalls:
        phases.append({"name": "montages", "calls": mcalls})

    fx_phases, fx_paths = unreal_niagara_fx.fx_calls(root, spec.get("fx", {}))
    phases.extend(fx_phases)
    names = dict(montages, **fx_paths)

    def resolve(p):
        """Montage / fx names -> asset paths, also inside structs such as ImpactFx {"Niagara": "NS_Hit"}."""
        if isinstance(p, dict):
            return {k: resolve(v) for k, v in p.items()}
        return names.get(p, p) if isinstance(p, str) else p
    data = [c for c in (upsert(root, spec, "weapons", resolve), upsert(root, spec, "spells", resolve)) if c]
    if data:
        phases.append({"name": "data", "calls": data})

    def resolve_item(p):
        p = dict(p)
        for k in ("Weapon", "AmmoFor"):
            if p.get(k) in weapons:
                p[k] = asset_path(root, "weapons", p[k])
        if p.get("Spell") in spells:
            p["Spell"] = asset_path(root, "spells", p["Spell"])
        return p
    items = upsert(root, spec, "items", resolve_item)
    if items:
        phases.append({"name": "items", "calls": [items]})

    chars = spec.get("characters", {})
    bp_paths = {}
    if chars:
        calls = []
        for name, c in sorted(chars.items()):
            bp = "%s/Characters/%s" % (root, name)
            bp_paths[name] = bp
            calls.append(["blueprint.create", {"assetPath": bp, "parentClass": c.get("parent", PARENT), "onConflict": "skip"}])
            d = dict(body_defaults(name, c, spec.get("bodies"), notes), **c.get("defaults", {}))
            if c.get("anim_set"):
                if c["anim_set"] not in anim_bps:
                    raise ValueError("character %s: anim_set %s is not in this spec's anim_sets" % (name, c["anim_set"]))
                d.setdefault("Mesh.AnimClass", anim_bps[c["anim_set"]])
            unknown = [w for w in c.get("weapons", []) if w not in weapons] + [s for s in c.get("spells", []) if s not in spells]
            if unknown:
                raise ValueError("character %s names %s, not in this spec's weapons/spells" % (name, unknown))
            if "weapons" in c:
                d["StartingWeapons"] = [asset_path(root, "weapons", w) for w in c["weapons"]]
            if "spells" in c:
                d["StartingSpells"] = [asset_path(root, "spells", s) for s in c["spells"]]
            if c.get("player"):
                if not inp:
                    raise ValueError("character %s is a player but the spec has no input section" % name)
                d["DefaultMappingContext"] = imc_path
                for slot, prop in INPUT_SLOTS.items():
                    if slot in action_paths:
                        d[prop] = action_paths[slot]
                d["SpellActions"] = spell_actions[:len(c.get("spells", []))]
            for prop, value in d.items():
                calls.append(["blueprint.set_class_default", {"assetPath": bp, "propertyName": prop, "value": value}])
        calls.append(["blueprint.compile_all", {"assetPaths": [bp_paths[n] for n in sorted(bp_paths)], "save": True}])
        phases.append({"name": "characters", "calls": calls})

    gm = spec.get("game_mode")
    if gm:
        if gm["pawn"] not in bp_paths and not gm["pawn"].startswith("/Game/"):
            raise ValueError("game_mode.pawn %s is not a character of this spec (or a /Game/ Blueprint path)" % gm["pawn"])
        gpath = "%s/%s" % (root, gm["name"])
        pawn = bp_paths.get(gm["pawn"], gm["pawn"])  # a path: a character another spec made (one hero, several maps)
        phases.append({"name": "game_mode", "calls": [
            ["gameplay.create_game_mode", {"name": gm["name"], "packagePath": root, "parentClass": gm.get("parent", "GameModeBase")}],
            ["blueprint.set_class_default", {"assetPath": gpath, "propertyName": "DefaultPawnClass",
                                             "value": "%s.%s_C" % (pawn, pawn.rsplit("/", 1)[1])}],
            ["blueprint.compile_all", {"assetPaths": [gpath], "save": True}]]})

    place = spec.get("place", [])
    lvl = spec.get("map")
    remove = spec.get("remove", [])
    if place or remove or (gm and lvl):
        calls = []
        if lvl:
            calls.append(["level.create", dict({"levelPath": lvl["path"], "onConflict": "skip"}, **({"templateLevel": lvl["template"]} if lvl.get("template") else {}))])
            calls.append(["level.load", {"levelPath": lvl["path"], "saveFirst": True}])
        for label in remove:
            calls.append(["level.delete_actor", {"actorLabel": label}])
        if gm:
            # needs the generated class (<path>.<name>_C); the bare asset path is "GameMode class not found"
            calls.append(["gameplay.set_world_game_mode", {"gameModePath": "%s/%s.%s_C" % (root, gm["name"], gm["name"])}])
        for p in place:
            x, y, z = p.get("location", [0, 0, 0])
            if "item" in p:
                if p["item"] not in spec.get("items", {}):
                    raise ValueError("place: %s is not an item of this spec" % p["item"])
                a = {"actorClass": PICKUP, "label": p["label"], "onConflict": "skip", "location": {"x": x, "y": y, "z": z}}
                calls.append(["level.place_actor", a])
                calls.append(["level.set_actor_property", {"actorLabel": p["label"], "propertyName": "Item",
                                                           "value": "%s/Items/DA_Item_%s" % (root, p["item"])}])
                if p.get("respawn"):
                    calls.append(["level.set_actor_property", {"actorLabel": p["label"], "propertyName": "RespawnSeconds",
                                                               "value": float(p["respawn"])}])
                continue
            if "static_mesh" in p:
                a = {"actorClass": "StaticMeshActor", "label": p["label"], "onConflict": "skip", "staticMesh": p["static_mesh"],
                     "location": {"x": x, "y": y, "z": z}}
                if "rotation" in p:
                    pi, ya, ro = p["rotation"]
                    a["rotation"] = {"pitch": pi, "yaw": ya, "roll": ro}
                if "scale" in p:
                    sc = float(p["scale"])
                    a["scale"] = {"x": sc, "y": sc, "z": sc}
                calls.append(["level.place_actor", a])
                continue
            if p.get("character") not in bp_paths:
                raise ValueError("place: %s is not a character of this spec" % p.get("character"))
            bp = bp_paths[p["character"]]
            a = {"actorClass": "%s.%s_C" % (bp, bp.rsplit("/", 1)[1]), "label": p["label"], "onConflict": "skip",
                 "location": {"x": x, "y": y, "z": z}}
            if "rotation" in p:
                pi, ya, ro = p["rotation"]
                a["rotation"] = {"pitch": pi, "yaw": ya, "roll": ro}
            calls.append(["level.place_actor", a])
        calls.append(["level.save", {}])
        phases.append({"name": "place", "calls": calls})
    return {"phases": phases}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    root = ue_project.get("content_root", "/Game/Game") + "/Combat"
    with open(a.spec) as f:
        spec = json.load(f)
    if spec.get("bodies_file"):
        with open(os.path.join(os.path.dirname(os.path.abspath(a.spec)), spec["bodies_file"])) as f:
            spec["bodies"] = json.load(f)
    notes = []
    calls = build(spec, root, notes)
    for n in notes:
        print("NOTE " + n)
    with open(a.out, "w") as f:
        json.dump(calls, f, indent=1)
    print("%s: %s" % (a.out, ", ".join("%s %d" % (p["name"], len(p["calls"])) for p in calls["phases"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
