"""gg_combat: refusals are pure; `init`/`check` need a real project and are skipped without godot (or when
GG_SKIP_ENGINE=1). The combat math itself (game/combat.gd, game/combat_attributes.gd) is GDScript, exercised
by tests/test_combat.gd (gg_combat.py init writes it) via `gg_ui.py test`, not here."""
import argparse
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gg_combat
import gg_godot
import gg_ui

ENGINE = gg_godot.find_godot() and not os.environ.get("GG_SKIP_ENGINE")
EXAMPLE_SPEC = os.path.join(os.path.dirname(HERE), "templates", "combat_spec.example.json")
PACK_SPECS = os.path.join(os.path.dirname(HERE), "templates", "combat_specs")


class Refusals(unittest.TestCase):
    def test_init_refuses_without_project(self):
        with self.assertRaisesRegex(gg_godot.Refused, "no project.godot"):
            gg_combat.init(argparse.Namespace(project="/no/such/dir", force=False, dry_run=False))

    def test_check_project_refuses_without_project_godot(self):
        d = tempfile.mkdtemp()
        try:
            with self.assertRaisesRegex(gg_godot.Refused, "no project.godot"):
                gg_combat.check_project(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_check_project_refuses_without_synced_runtime(self):
        d = tempfile.mkdtemp()
        try:
            open(os.path.join(d, "project.godot"), "w").close()
            with self.assertRaisesRegex(gg_godot.Refused, "sync-runtime"):
                gg_combat.check_project(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)


CONVERTED_RIFLE = "/data/ai/assets/fab/low-poly-weapons-set-0794c54e/glb/converted/SM_AssaultRifle_01.glb"
WF_PACK = "weapons-free-low-poly-3d-models-pack-e4d37345"
WF_CONVERTED = "/data/ai/assets/fab/%s/glb/converted/SM_rifle_001.glb" % WF_PACK


class Spec(unittest.TestCase):
    """T-0075: the declarative weapon/spell spec loader/validator/resolver -- pure, no project or engine needed."""

    def test_example_template_is_valid(self):
        doc = gg_combat.load_spec(EXAMPLE_SPEC)
        self.assertEqual(gg_combat.spec_errors(doc), [])
        self.assertIn("AssaultRifle", doc["weapons"])
        self.assertIn("Fireball", doc["spells"])

    def test_every_pack_spec_is_valid(self):
        names = sorted(n for n in os.listdir(PACK_SPECS) if n.endswith(".json"))
        self.assertTrue(names)
        for name in names:
            doc = gg_combat.load_spec(os.path.join(PACK_SPECS, name))
            self.assertEqual(gg_combat.spec_errors(doc), [], name)

    def test_load_spec_refuses_missing_file(self):
        with self.assertRaisesRegex(gg_godot.Refused, "no such spec file"):
            gg_combat.load_spec("/no/such/combat_spec.json")

    def test_resolve_ability_returns_the_named_entry(self):
        doc = gg_combat.load_spec(EXAMPLE_SPEC)
        rifle = gg_combat.resolve_ability(doc, "weapons", "AssaultRifle")
        self.assertEqual(rifle["delivery"], "raycast")
        self.assertEqual(rifle["effect"]["damage_type"], "physical")

    def test_resolve_ability_refuses_unknown_name(self):
        doc = gg_combat.load_spec(EXAMPLE_SPEC)
        with self.assertRaisesRegex(gg_godot.Refused, "not found in spec"):
            gg_combat.resolve_ability(doc, "weapons", "NoSuchGun")

    def test_spec_errors_rejects_unknown_delivery(self):
        doc = {"schema": 1, "weapons": {"Bad": {"delivery": "teleport", "range_m": 1.0, "cooldown_s": 1.0, "effect": {"kind": "damage", "amount": 1.0}}}}
        errs = gg_combat.spec_errors(doc)
        self.assertTrue(any("delivery" in e for e in errs), errs)

    def test_spec_errors_rejects_unknown_effect_kind(self):
        doc = {"schema": 1, "weapons": {"Bad": {"delivery": "melee", "range_m": 1.0, "cooldown_s": 1.0, "effect": {"kind": "frobnicate", "amount": 1.0}}}}
        errs = gg_combat.spec_errors(doc)
        self.assertTrue(any("kind" in e for e in errs), errs)

    def test_spec_parts_must_be_a_list_of_paths(self):
        doc = gg_combat.load_spec(EXAMPLE_SPEC)
        self.assertEqual(doc["weapons"]["AssaultRifle"]["parts"][0], "res://assets/library/ar_mag.glb")
        doc["weapons"]["AssaultRifle"]["parts"] = "res://assets/library/ar_mag.glb"
        self.assertTrue(any("parts" in e for e in gg_combat.spec_errors(doc)))

    def test_spec_errors_requires_at_least_one_ability(self):
        errs = gg_combat.spec_errors({"schema": 1})
        self.assertTrue(any("neither 'weapons' nor 'spells'" in e for e in errs), errs)

    def test_load_spec_refuses_invalid_doc(self):
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "bad.json")
            with open(p, "w") as f:
                json.dump({"schema": 2}, f)
            with self.assertRaisesRegex(gg_godot.Refused, "invalid"):
                gg_combat.load_spec(p)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_main_spec_refuses_without_weapon_or_spell(self):
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "addons", "gg", "game"))
            open(os.path.join(d, "project.godot"), "w").close()
            open(os.path.join(d, "addons", "gg", "game", "combat.gd"), "w").close()
            self.assertEqual(gg_combat.main(["spec", "--project", d, "--spec", EXAMPLE_SPEC]), 2)
            self.assertEqual(gg_combat.main(["spec", "--project", d, "--spec", EXAMPLE_SPEC, "--weapon", "AssaultRifle", "--spell", "Fireball"]), 2)
        finally:
            shutil.rmtree(d, ignore_errors=True)


@unittest.skipUnless(ENGINE, "godot not available")
class Engine(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.proj = os.path.join(self.d, "p")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_init_writes_test_and_check_passes_live(self):
        self.assertEqual(gg_ui.main(["init", "--project", self.proj, "--name", "Combat"]), 0)
        import gg_project
        self.assertEqual(gg_project.main(["sync-runtime", "--project", self.proj]), 0)
        self.assertEqual(gg_combat.main(["init", "--project", self.proj]), 0)
        self.assertTrue(os.path.isfile(os.path.join(self.proj, "tests", "test_combat.gd")))
        self.assertEqual(gg_combat.main(["init", "--project", self.proj]), 2)  # already exists, no --force
        self.assertEqual(gg_combat.main(["check", "--project", self.proj]), 0)
        self.assertEqual(gg_combat.main(["slice", "--project", self.proj]), 0)
        self.assertEqual(gg_combat.main(["pickups", "--project", self.proj]), 0)
        self.assertEqual(gg_combat.main(["mp", "--project", self.proj, "--timeout", "20"]), 0)

    def test_spec_weapon_and_spell_fire_live(self):
        """T-0075: the example spec's AssaultRifle (raycast) and Fireball (instant, with a mana cost) both
        fire for real against the engine -- cooldown gates, vfx recipes build -- via the data-driven `spec`
        op, exercising the same CombatComponent `slice` already proves, but spec-loaded instead of hardcoded."""
        self.assertEqual(gg_ui.main(["init", "--project", self.proj, "--name", "Combat"]), 0)
        import gg_project
        self.assertEqual(gg_project.main(["sync-runtime", "--project", self.proj]), 0)
        # the models are checked in test_spec_models_from_the_converted_pack: this project has no assets
        doc = gg_combat.load_spec(EXAMPLE_SPEC)
        for w in doc["weapons"].values():
            w.pop("mesh", None)
            w.pop("parts", None)
        spec = os.path.join(self.proj, "spec_no_models.json")
        with open(spec, "w") as f:
            json.dump(doc, f)
        self.assertEqual(gg_combat.main(["spec", "--project", self.proj, "--spec", spec, "--weapon", "AssaultRifle"]), 0)
        self.assertEqual(gg_combat.main(["spec", "--project", self.proj, "--spec", EXAMPLE_SPEC, "--spell", "Fireball"]), 0)

    @unittest.skipUnless(os.path.isfile(CONVERTED_RIFLE), "converted low-poly-weapons-set glbs not on this host")
    def test_spec_models_from_the_converted_pack(self):
        """T-0075 pilot: the bridge-exported, glb-converted rifle/shotgun (body + parts) brought in with gg_assets.py
        use load at a hand-held size and every part sits on its body."""
        import gg_assets
        import gg_project
        self.assertEqual(gg_ui.main(["init", "--project", self.proj, "--name", "Combat"]), 0)
        self.assertEqual(gg_project.main(["sync-runtime", "--project", self.proj]), 0)
        for asset, slot in (("sm-assaultrifle-01", "ar_body"), ("sm-assaultrifle-magazine-01", "ar_mag"),
                            ("sm-assaultrifle-trigger-01", "ar_trigger"), ("sm-pumpshotgun-01", "sg_body"),
                            ("sm-pumpshotgun-trigger-01", "sg_trigger")):
            self.assertEqual(gg_assets.main(["use", "--asset", "low-poly-weapons-set-0794c54e-" + asset, "--project", self.proj, "--slot", slot]), 0)
        for name in ("AssaultRifle", "PumpShotgun"):
            self.assertEqual(gg_combat.main(["spec", "--project", self.proj, "--spec", EXAMPLE_SPEC, "--weapon", name]), 0, name)

    @unittest.skipUnless(os.path.isfile(WF_CONVERTED), "converted weapons-free-low-poly glbs not on this host")
    def test_weapons_free_pack_spec_live(self):
        """T-0075 follow-on: every weapon of templates/combat_specs/weapons-free-low-poly.json with its models."""
        import gg_assets
        import gg_project
        self.assertEqual(gg_ui.main(["init", "--project", self.proj, "--name", "Combat"]), 0)
        self.assertEqual(gg_project.main(["sync-runtime", "--project", self.proj]), 0)
        for asset, slot in (("pistol-001", "wf_pistol"), ("pistol-drum-001", "wf_pistol_drum"), ("rifle-001", "wf_rifle"),
                            ("rifle-magazine-001", "wf_rifle_mag"), ("shotgun-001", "wf_shotgun"),
                            ("shotgun-handguard-001", "wf_shotgun_handguard"), ("sniper-rifle-001", "wf_sniper"),
                            ("sight-001", "wf_sight"), ("knife-001", "wf_knife"), ("axe-001", "wf_axe"),
                            ("baseball-bat-001", "wf_bat"), ("hockey-stick-001", "wf_hockey_stick")):
            self.assertEqual(gg_assets.main(["use", "--asset", "%s-sm-%s" % (WF_PACK, asset), "--project", self.proj, "--slot", slot]), 0)
        spec = os.path.join(PACK_SPECS, "weapons-free-low-poly.json")
        for name in gg_combat.load_spec(spec)["weapons"]:
            self.assertEqual(gg_combat.main(["spec", "--project", self.proj, "--spec", spec, "--weapon", name]), 0, name)


if __name__ == "__main__":
    unittest.main()
