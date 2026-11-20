import importlib.util
import json
import os
import pathlib
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("uc", HERE / "unreal_combat.py")
uc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uc)
with open(HERE.parent / "templates" / "combat_spec.zas.json") as _f:
    ZAS = json.load(_f)


def phase(calls, name):
    """Calls of one phase; "anim" gathers every "anim <set>" phase."""
    if name == "anim":
        return [c for p in calls["phases"] if p["name"].startswith("anim ") for c in p["calls"]]
    return [p for p in calls["phases"] if p["name"] == name][0]["calls"]


def defaults(calls, bp_name):
    return {a["propertyName"]: a["value"] for m, a in phase(calls, "characters")
            if m == "blueprint.set_class_default" and a["assetPath"].endswith("/" + bp_name)}


class Combat(unittest.TestCase):
    def setUp(self):
        self.c = uc.build(ZAS, "/unused")

    def test_phase_order_puts_tags_and_data_before_what_references_them(self):
        self.assertEqual([p["name"] for p in self.c["phases"] if not p["name"].startswith("fx ")],
                         ["tags", "input", "anim Manny", "anim MannyBow", "anim MannyGuns", "anim RPGHero", "anim Rogue", "anim Wizard", "retarget", "montages", "data", "items", "characters", "game_mode", "place"])

    def test_spell_cooldown_tag_is_registered_and_set(self):
        self.assertIn(["reflection.create_tag", {"tag": "Cooldown.Spell.Fireball", "comment": "WatooMCombat (unreal_combat.py)"}],
                      phase(self.c, "tags"))
        (m, a), = [x for x in phase(self.c, "data") if x[1]["items"][0]["className"] == "WatooMSpellData"]
        self.assertEqual(a["items"][0]["properties"]["CooldownTag"], "Cooldown.Spell.Fireball")

    def test_data_assets_are_upserted_with_properties_as_given(self):
        calls = phase(self.c, "data")
        self.assertTrue(all(m == "asset.bulk_upsert_data_assets" and a["onConflict"] == "update" for m, a in calls))
        w = {i["name"]: i for i in calls[0][1]["items"]}
        self.assertEqual(sorted(w), ["DA_Weapon_Bow", "DA_Weapon_HeroSword", "DA_Weapon_Pistol", "DA_Weapon_Rifle", "DA_Weapon_Shotgun", "DA_Weapon_Staff", "DA_Weapon_Sword", "DA_Weapon_WizardStaff"])
        self.assertEqual(w["DA_Weapon_Rifle"]["packagePath"], "/Game/ZAS/Combat/Weapons")
        self.assertEqual(w["DA_Weapon_Rifle"]["properties"]["FireMode"], "Auto")

    def test_items_resolve_weapon_names_to_the_data_asset(self):
        (m, a), = phase(self.c, "items")
        pick = [i for i in a["items"] if i["name"] == "DA_Item_RiflePickup"][0]
        self.assertEqual(pick["properties"]["Weapon"], "/Game/ZAS/Combat/Weapons/DA_Weapon_Rifle")

    def test_base_mapping_context_is_copied_never_edited(self):
        calls = phase(self.c, "input")
        self.assertEqual(calls[0], ["asset.duplicate", {"sourcePath": "/Game/ZAS/Player/Input/IMC_Wizard",
                                                        "destinationPath": "/Game/ZAS/Combat/Input/IMC_ZAS_Combat", "onConflict": "skip"}])
        maps = [a for m, a in calls if m == "gameplay.add_imc_mapping"]
        self.assertTrue(all(a["imcPath"].endswith("IMC_ZAS_Combat") for a in maps))
        self.assertEqual({(a["inputActionPath"].rsplit("/", 1)[1], a["key"]) for a in maps},
                         {("IA_Reload", "R"), ("IA_NextWeapon", "Q"), ("IA_Spell1", "One"), ("IA_Spell2", "Two"), ("IA_Spell3", "Three"), ("IA_Spell4", "Four")})

    def test_player_character_gets_weapons_spells_and_input(self):
        d = defaults(self.c, "BP_ZAS_CombatWizard")
        self.assertEqual(d["StartingWeapons"], ["/Game/ZAS/Combat/Weapons/DA_Weapon_" + n for n in ("Sword", "Rifle", "Staff")])
        self.assertEqual(d["Mesh.AnimClass"], "/Game/ZAS/Combat/Anim/Manny/ABP_Manny_Combat")
        self.assertEqual(d["StartingSpells"], ["/Game/ZAS/Combat/Spells/DA_Spell_" + n for n in ("Fireball", "FrostNova", "Heal")])
        self.assertEqual(d["PrimaryAction"], "/Game/ZAS/Player/Input/IA_Attack")
        self.assertEqual(d["ReloadAction"], "/Game/ZAS/Combat/Input/IA_Reload")
        self.assertEqual(d["SpellActions"], ["/Game/ZAS/Combat/Input/IA_Spell%d" % i for i in (1, 2, 3)])
        self.assertEqual(d["DefaultMappingContext"], "/Game/ZAS/Combat/Input/IMC_ZAS_Combat")
        dummy = defaults(self.c, "BP_ZAS_TargetDummy")
        self.assertNotIn("DefaultMappingContext", dummy)
        self.assertEqual(dummy["TeamId"], 2)
        creates = [a for m, a in phase(self.c, "characters") if m == "blueprint.create"]
        self.assertTrue(all(a["parentClass"] == uc.PARENT for a in creates))

    def test_humanoid_mesh_offset_is_the_default_and_a_spec_can_override_it(self):
        d = defaults(self.c, "BP_ZAS_CombatWizard")
        self.assertEqual(d["Mesh.RelativeRotation"], "(Pitch=0.000000,Yaw=-90.000000,Roll=0.000000)")
        self.assertEqual(d["Mesh.RelativeLocation"], "(X=0.000000,Y=0.000000,Z=-90.000000)")
        c = uc.build({"characters": {"BP_Q": {"defaults": {"Mesh.RelativeRotation": "(Pitch=0,Yaw=0,Roll=0)"}}}}, "/Game/G/Combat")
        self.assertEqual(defaults(c, "BP_Q")["Mesh.RelativeRotation"], "(Pitch=0,Yaw=0,Roll=0)")

    def test_a_measured_body_sets_capsule_and_mesh_for_any_creature(self):
        dragon = {"facing": "+Y", "yaw": -90.0, "CapsuleHalfHeight": 437.5, "CapsuleRadius": 328.1,
                  "Mesh.RelativeLocation": "(X=207.8,Y=9.7,Z=-433.2)", "Mesh.RelativeRotation": "(Pitch=0,Yaw=-90,Roll=0)", "evidence": {}}
        mesh = "/Game/Dragons/SK_Dragon"
        notes = []
        c = uc.build({"bodies": {mesh: dragon}, "characters": {"BP_Dragon": {"defaults": {"Mesh.SkeletalMeshAsset": mesh}}}},
                     "/Game/G/Combat", notes)
        d = defaults(c, "BP_Dragon")
        self.assertEqual(d["CapsuleComponent.CapsuleRadius"], 328.1)
        self.assertEqual(d["CapsuleComponent.CapsuleHalfHeight"], 437.5)
        self.assertEqual(d["Mesh.RelativeLocation"], "(X=207.8,Y=9.7,Z=-433.2)")
        self.assertNotIn("evidence", d)
        self.assertEqual(notes, [])

    def test_unmeasured_mesh_gets_the_fallback_and_a_note(self):
        notes = []
        uc.build({"characters": {"BP_X": {"defaults": {"Mesh.SkeletalMeshAsset": "/Game/M/SK_X"}}}}, "/Game/G/Combat", notes)
        self.assertEqual(len(notes), 1)
        self.assertIn("ue_mesh_body.py", notes[0])

    ANIM = {"anim_sets": {"Manny": {"skeleton": "/Game/H/SK_Mannequin", "speed": 400, "default_stance": "Unarmed",
                                    "air": "/Game/H/MM_Fall_Loop",
                                    "stances": {"Unarmed": {"idle": "/Game/H/U_Idle", "fwd": "/Game/H/U_Fwd", "bwd": "/Game/H/U_Bwd",
                                                            "left": "/Game/H/U_L", "right": "/Game/H/U_R"},
                                                "Sword": {"idle": "/Game/H/S_Idle", "fwd": "/Game/H/S_Fwd"}}}},
            "characters": {"BP_M": {"anim_set": "Manny"}}}

    def test_anim_set_builds_wired_blend_spaces_and_state_machine(self):
        c = uc.build(self.ANIM, "/Game/G/Combat")
        calls = phase(c, "anim")
        bs = [a for m, a in calls if m == "animation.populate_blendspace"]
        self.assertEqual([b["assetPath"].rsplit("/", 1)[1] for b in bs], ["BS_Manny_Sword", "BS_Manny_Unarmed"])
        unarmed = [s for s in bs[1]["samples"]]
        self.assertEqual(len(unarmed), 3 + 5)                     # idle row + fwd/right/left/bwd(+-180)
        self.assertEqual(len(bs[0]["samples"]), 3 + 5)            # idle + fwd only: fwd fills every direction
        wires = [(a["graphName"], a["sourceNode"], a["targetNode"]) for m, a in calls if m == "blueprint.connect_pins"]
        # every state's player is wired to its output and fed by Direction/Speed: the T-pose trap of 2026-11-18
        self.assertIn(("Unarmed", "BS_Manny_Unarmed\nBlendspace Player", "Output Animation Pose"), wires)
        self.assertIn(("Sword", "Get Speed", "BS_Manny_Sword\nBlendspace Player"), wires)
        self.assertIn(("Air", "MM_Fall_Loop\nSequence Player", "Output Animation Pose"), wires)
        self.assertIn(("AnimGraph", uc.SLOT, "Output Pose\nAnimGraph"), wires)
        entry = [a for m, a in calls if m == "animation.set_state_machine_entry"]
        self.assertEqual(entry[0]["stateName"], "Unarmed")
        conds = {(a["fromState"], a["toState"]): (a["variableName"], a.get("negate", False))
                 for m, a in calls if m == "animation.set_transition_condition"}
        self.assertEqual(conds[("Unarmed", "Sword")], ("bStance_Sword", False))
        self.assertEqual(conds[("Air", "Unarmed")], ("bInAir", True))
        abp = [a for m, a in calls if m == "animation.create_anim_blueprint"][0]
        self.assertEqual(abp["parentClass"], "/Script/WatooMCombat.WatooMCombatAnimInstance")
        self.assertEqual(defaults(c, "BP_M")["Mesh.AnimClass"], "/Game/G/Combat/Anim/Manny/ABP_Manny_Combat")
        names = [p["name"] for p in c["phases"]]
        self.assertLess(names.index("anim Manny"), names.index("characters"))

    def test_bad_anim_sets_are_refused(self):
        for bad in ({"anim_sets": {"M": {"skeleton": "s", "stances": {"Sword": {"idle": "a"}}}}},           # default Unarmed missing
                    {"anim_sets": {"M": {"skeleton": "s", "stances": {"Unarmed": {"fwd": "a"}}}}},          # no idle
                    {"anim_sets": {"M": {"skeleton": "s", "stances": {"Unarmed": {"idle": "a"}, "Two Hand": {"idle": "b"}}}}},
                    {"characters": {"BP_X": {"anim_set": "Nope"}}}):
            with self.assertRaises(ValueError, msg=bad):
                uc.build(bad, "/Game/G/Combat")

    def test_montages_are_authored_first_and_named_ones_resolve(self):
        c = uc.build({"montages": {"AM_CastA": {"anim": "/Game/R/Cast01"}},
                      "spells": {"Fireball": {"CastMontage": "AM_CastA", "ReleaseDelay": 0.55}}}, "/Game/G/Combat")
        (m, a), = phase(c, "montages")
        self.assertEqual(a["items"][0]["packagePath"], "/Game/G/Combat/Anim/Montages")
        self.assertEqual(a["items"][0]["slotName"], "DefaultSlot")
        spell = phase(c, "data")[0][1]["items"][0]["properties"]
        self.assertEqual(spell["CastMontage"], "/Game/G/Combat/Anim/Montages/AM_CastA")
        names = [p["name"] for p in c["phases"]]
        self.assertLess(names.index("montages"), names.index("data"))

    def test_fx_systems_are_built_before_data_and_names_resolve_in_structs(self):
        c = uc.build({"fx": {"NS_Hit": {"recipe": "impact", "element": "Physical"}, "NS_Ball": {"recipe": "projectile"}},
                      "weapons": {"Sword": {"Kind": "Melee", "ImpactFx": {"Niagara": "NS_Hit", "Scale": 1}}},
                      "spells": {"Ball": {"ProjectileFx": "NS_Ball"}}}, "/Game/G/Combat")
        names = [p["name"] for p in c["phases"]]
        self.assertLess(names.index("fx NS_Hit"), names.index("data"))
        w, s = [a["items"][0]["properties"] for m, a in phase(c, "data")]
        self.assertEqual(w["ImpactFx"], {"Niagara": "/Game/G/Combat/FX/NS_Hit", "Scale": 1})
        self.assertEqual(s["ProjectileFx"], "/Game/G/Combat/FX/NS_Ball")

    def test_items_are_placed_as_pickups_with_their_data(self):
        c = uc.build({"items": {"Medkit": {"Kind": "Consumable", "RestoreHealth": 50}},
                      "place": [{"item": "Medkit", "label": "P_Med", "location": [1, 2, 3], "respawn": 20}]}, "/Game/G/Combat")
        calls = phase(c, "place")
        self.assertEqual(calls[0][1]["actorClass"], uc.PICKUP)
        props = {a["propertyName"]: a["value"] for m, a in calls if m == "level.set_actor_property"}
        self.assertEqual(props, {"Item": "/Game/G/Combat/Items/DA_Item_Medkit", "RespawnSeconds": 20.0})
        with self.assertRaises(ValueError):
            uc.build({"place": [{"item": "Nope", "label": "X"}]}, "/Game/G/Combat")

    def test_a_walk_only_creature_uses_the_walk_for_every_direction(self):
        spec = {"anim_sets": {"Croc": {"skeleton": "/Game/C/SK", "speed": 150, "default_stance": "Walk",
                                       "stances": {"Walk": {"idle": "/Game/C/Walk", "fwd": "/Game/C/Walk"}}}}}
        (m, a), = [x for x in phase(uc.build(spec, "/Game/G/Combat"), "anim") if x[0] == "animation.populate_blendspace"]
        moving = [smp for smp in a["samples"] if smp["y"] > 0]
        self.assertEqual(len(moving), 5)
        self.assertTrue(all(smp["animation"] == "/Game/C/Walk" for smp in moving))

    def test_a_static_mesh_can_be_placed_with_scale(self):
        c = uc.build({"place": [{"static_mesh": "/Game/S/SM_Statue", "label": "Statue_1", "location": [1, 2, 3],
                                 "rotation": [0, -79, 0], "scale": 8}]}, "/Game/G/Combat")
        (m, a), = [x for x in phase(c, "place") if x[0] == "level.place_actor"]
        self.assertEqual((a["actorClass"], a["staticMesh"], a["scale"]["z"], a["rotation"]["yaw"]),
                         ("StaticMeshActor", "/Game/S/SM_Statue", 8.0, -79))

    def test_spell_keys_are_slots_per_player_not_spells_per_spec(self):
        chars = {"A": {"player": True, "spells": ["S1", "S2"]}, "B": {"player": True, "spells": ["S3", "S4"]}}
        spec = {"input": {"spell_keys": ["One", "Two"]}, "spells": {n: {} for n in ("S1", "S2", "S3", "S4")}, "characters": chars}
        acts = [a["name"] for m, a in phase(uc.build(spec, "/Game/G/Combat"), "input") if m == "gameplay.create_input_action"]
        self.assertEqual(acts, ["IA_Spell1", "IA_Spell2"])
        chars["B"]["spells"].append("S1")
        with self.assertRaises(ValueError):
            uc.build(spec, "/Game/G/Combat")

    def test_map_is_opened_before_placing_and_actors_skip_on_rerun(self):
        calls = phase(self.c, "place")
        self.assertEqual([m for m, _ in calls[:3]], ["level.create", "level.load", "gameplay.set_world_game_mode"])
        places = [a for m, a in calls if m == "level.place_actor"]
        self.assertEqual(places[0]["actorClass"], "/Game/ZAS/Combat/Characters/BP_ZAS_TargetDummy.BP_ZAS_TargetDummy_C")
        self.assertTrue(all(a["onConflict"] == "skip" for a in places))
        self.assertEqual(calls[2][1]["gameModePath"], "/Game/ZAS/Combat/BP_ZAS_CombatGameMode.BP_ZAS_CombatGameMode_C")
        self.assertEqual(calls[-1][0], "level.save")
        gm = phase(self.c, "game_mode")
        self.assertEqual(gm[1][1]["value"], "/Game/ZAS/Combat/Characters/BP_ZAS_WizardHero.BP_ZAS_WizardHero_C")

    def test_a_map_can_take_another_specs_hero_and_retire_an_old_pawn(self):
        spec = {"game_mode": {"name": "BP_Main", "pawn": "/Game/ZAS/Combat/Characters/BP_ZAS_WizardHero"},
                "map": {"path": "/Game/ZAS/Maps/L_Main"}, "remove": ["ZAS_Player"],
                "place": [{"player_start": True, "label": "PS", "location": [1, 2, 3], "rotation": [0, 140, 0]}]}
        c = uc.build(spec, "/Game/ZAS/Combat")
        self.assertEqual(phase(c, "game_mode")[1][1]["value"],
                         "/Game/ZAS/Combat/Characters/BP_ZAS_WizardHero.BP_ZAS_WizardHero_C")
        calls = phase(c, "place")
        self.assertEqual([m for m, _ in calls], ["level.create", "level.load", "level.delete_actor",
                                                 "gameplay.set_world_game_mode", "level.place_actor", "level.save"])
        self.assertEqual((calls[4][1]["actorClass"], calls[4][1]["rotation"]["yaw"]), ("PlayerStart", 140))
        self.assertNotIn("templateLevel", calls[0][1])
        with self.assertRaises(ValueError):
            uc.build({"game_mode": {"name": "G", "pawn": "BP_Nobody"}}, "/Game/ZAS/Combat")

    def test_any_blueprint_actor_can_be_placed_with_properties(self):
        spec = {"map": {"path": "/Game/M"}, "place": [{"actor": "/Game/Fish/BP_FishWander", "label": "F1", "location": [1, 2, 3],
                                                       "properties": {"WanderRadius": 800, "HeightRange": 200}}]}
        calls = phase(uc.build(spec, "/Game/G/Combat"), "place")
        self.assertEqual(calls[2][1]["actorClass"], "/Game/Fish/BP_FishWander.BP_FishWander_C")
        self.assertEqual([(a["propertyName"], a["value"]) for m, a in calls if m == "level.set_actor_property"],
                         [("HeightRange", 200), ("WanderRadius", 800)])
        with self.assertRaises(ValueError):
            uc.build({"place": [{"actor": "BP_FishWander", "label": "F"}]}, "/Game/G/Combat")

    def test_bad_specs_are_refused(self):
        for bad in ({"weapons": {"my sword": {}}},
                    {"weapons": {}, "characters": {"BP_X": {"weapons": ["Axe"]}}},
                    {"characters": {"BP_X": {"player": True}}},
                    {"spells": {"A": {}, "B": {}}, "input": {"spell_keys": ["One"]}},
                    {"characters": {"BP_X": {}}, "place": [{"character": "BP_Y", "label": "y"}]}):
            with self.assertRaises(ValueError, msg=bad):
                uc.build(bad, "/Game/G/Combat")

    def test_minimal_spec_and_profile_root(self):
        with tempfile.TemporaryDirectory() as d:
            sp, prof, out = (os.path.join(d, n) for n in ("s.json", "p.json", "o.json"))
            json.dump({"weapons": {"Axe": {"Kind": "Melee", "Damage": 50}}}, open(sp, "w"))
            json.dump({"content_root": "/Game/Fort"}, open(prof, "w"))
            self.assertEqual(uc.main(["--spec", sp, "--out", out, "--project", prof]), 0)
            with open(out) as f:
                c = json.load(f)
        self.assertEqual([p["name"] for p in c["phases"]], ["data"])
        self.assertEqual(c["phases"][0]["calls"][0][1]["items"][0]["packagePath"], "/Game/Fort/Combat/Weapons")


if __name__ == "__main__":
    unittest.main()
