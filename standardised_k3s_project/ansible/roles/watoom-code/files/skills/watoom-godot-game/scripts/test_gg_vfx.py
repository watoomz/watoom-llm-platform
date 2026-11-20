"""gg_vfx: refusals are pure; `check` needs a real project + the gl_compatibility selftest and is skipped
without godot or a passing selftest (or when GG_SKIP_ENGINE=1)."""
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
import gg_verify
import gg_vfx

ENGINE = gg_godot.find_godot() and not os.environ.get("GG_SKIP_ENGINE")
RENDER_READY = ENGINE and gg_verify.selftest_gate(gg_vfx.RENDERER) is None
EXAMPLE_COMBAT_SPEC = os.path.join(os.path.dirname(HERE), "templates", "combat_spec.example.json")


class Refusals(unittest.TestCase):
    def test_check_refuses_without_project_godot(self):
        d = tempfile.mkdtemp()
        try:
            with self.assertRaisesRegex(gg_godot.Refused, "no project.godot"):
                gg_vfx.check_project(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_check_refuses_without_synced_runtime(self):
        d = tempfile.mkdtemp()
        try:
            open(os.path.join(d, "project.godot"), "w").close()
            with self.assertRaisesRegex(gg_godot.Refused, "sync-runtime"):
                gg_vfx.check_project(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_check_refuses_spec_with_no_fx_entries(self):
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "addons", "gg", "game"))
            open(os.path.join(d, "project.godot"), "w").close()
            open(os.path.join(d, "addons", "gg", "game", "vfx.gd"), "w").close()
            spec = os.path.join(d, "empty.json")
            with open(spec, "w") as f:
                json.dump({"fx": {}}, f)
            self.assertEqual(gg_vfx.main(["check", "--project", d, "--spec", spec]), 2)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_check_refuses_both_spec_and_combat_spec(self):
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "addons", "gg", "game"))
            open(os.path.join(d, "project.godot"), "w").close()
            open(os.path.join(d, "addons", "gg", "game", "vfx.gd"), "w").close()
            spec = os.path.join(d, "fx.json")
            with open(spec, "w") as f:
                json.dump({"fx": {}}, f)
            self.assertEqual(gg_vfx.main(["check", "--project", d, "--spec", spec, "--combat-spec", EXAMPLE_COMBAT_SPEC]), 2)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class FxFromCombatSpec(unittest.TestCase):
    """T-0075: gg_vfx.py can load its recipes straight from a gg_combat weapon/spell spec (fx_from_combat_spec),
    one source of truth instead of hand-duplicating recipes into a separate fx.json -- pure, no engine needed."""

    def test_example_combat_spec_recipes_are_pulled_out(self):
        doc = gg_combat.load_spec(EXAMPLE_COMBAT_SPEC)
        fx = gg_vfx.fx_from_combat_spec(doc)
        self.assertEqual(fx["AssaultRifle_muzzle"], {"recipe": "muzzle", "element": "Physical"})
        self.assertEqual(fx["Fireball_cast"], {"recipe": "projectile", "element": "Fire"})
        self.assertEqual(len(fx), 7)   # 3 weapon recipes (rifle x2, shotgun x2, knife x1) + 2 spell recipes

    def test_clashing_recipe_under_the_same_name_is_refused(self):
        doc = {"weapons": {"W": {"vfx": {"hit": {"recipe": "impact", "element": "Fire"}}}},
               "spells": {"W": {"vfx": {"hit": {"recipe": "impact", "element": "Frost"}}}}}
        with self.assertRaisesRegex(gg_godot.Refused, "vfx name clash"):
            gg_vfx.fx_from_combat_spec(doc)


@unittest.skipUnless(RENDER_READY, "godot/selftest not available for gl_compatibility")
class Engine(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.proj = os.path.join(self.d, "p")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_default_demo_spec_all_recipes_draw_non_flat_pixels(self):
        self.assertEqual(gg_ui.main(["init", "--project", self.proj, "--name", "VFX"]), 0)
        import gg_project
        self.assertEqual(gg_project.main(["sync-runtime", "--project", self.proj]), 0)
        self.assertEqual(gg_vfx.main(["check", "--project", self.proj]), 0)

    def test_combat_spec_recipes_also_draw_non_flat_pixels(self):
        """T-0075: the same render-and-measure check, fed recipes pulled straight from the example weapon/spell spec."""
        self.assertEqual(gg_ui.main(["init", "--project", self.proj, "--name", "VFX"]), 0)
        import gg_project
        self.assertEqual(gg_project.main(["sync-runtime", "--project", self.proj]), 0)
        self.assertEqual(gg_vfx.main(["check", "--project", self.proj, "--combat-spec", EXAMPLE_COMBAT_SPEC]), 0)


if __name__ == "__main__":
    unittest.main()
