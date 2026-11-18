import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_combat_check as cc  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "..", "..", "ansible", "roles", "watoom-code", "files", "skills", "watoom-unreal-combat")


def zas_calls():
    sys.path.insert(0, os.path.join(SKILL, "scripts"))
    import unreal_combat as uc
    with open(os.path.join(SKILL, "templates", "combat_spec.zas.json")) as f:
        spec = json.load(f)
    c = uc.build(spec, spec["content_root"])
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(c, f)
    f.close()
    return f.name


class Plan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = cc.plan(zas_calls())

    def test_player_weapons_and_spells_come_from_the_generated_defaults(self):
        p = self.p
        self.assertEqual(p["player"], "BP_ZAS_WizardHero")              # the game mode's pawn
        self.assertEqual(p["player_label"], "BP_ZAS_WizardHero0")
        self.assertEqual(p["weapons"][0]["Kind"], "Melee")
        self.assertEqual([s["path"].rsplit("_", 1)[-1] for s in p["spells"]], ["WizardFireball", "WizardFrostNova", "WizardHeal"])
        self.assertTrue(p["spells"][1]["action"].endswith("IA_Spell2"))
        self.assertEqual(p["map"], "/Game/ZAS/Combat/Maps/L_CombatArena")

    def test_dummies_and_pickups_are_told_apart(self):
        self.assertEqual([d["label"] for d in self.p["dummies"]], ["ZAS_Dummy_1", "ZAS_Dummy_2"])
        kinds = {pk["label"]: pk["item"].get("Kind") for pk in self.p["pickups"]}
        self.assertEqual(kinds["ZAS_Pickup_Medkit"], "Consumable")
        self.assertEqual(kinds["ZAS_Pickup_RifleAmmo"], "Ammo")
        self.assertTrue(self.p["next_weapon"].endswith("IA_NextWeapon"))


class Maths(unittest.TestCase):
    def test_aim_points_the_camera_at_the_target(self):
        r = cc.aim((0, 0, 100), (100, 100, 100))
        self.assertAlmostEqual(r["yaw"], 45, places=2)
        self.assertAlmostEqual(r["pitch"], 0, places=2)
        self.assertLess(cc.aim((0, 0, 200), (500, 0, 100))["pitch"], 0)

    def test_damage_never_exceeds_what_is_left(self):
        self.assertEqual(cc.expected_damage(35, 150, 0), 35)
        self.assertEqual(cc.expected_damage(35, 20, 0), 20)


if __name__ == "__main__":
    unittest.main()
