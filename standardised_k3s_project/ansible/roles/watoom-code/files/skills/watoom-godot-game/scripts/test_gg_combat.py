"""gg_combat: refusals are pure; `init`/`check` need a real project and are skipped without godot (or when
GG_SKIP_ENGINE=1). The combat math itself (game/combat.gd, game/combat_attributes.gd) is GDScript, exercised
by tests/test_combat.gd (gg_combat.py init writes it) via `gg_ui.py test`, not here."""
import argparse
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gg_combat
import gg_godot
import gg_ui

ENGINE = gg_godot.find_godot() and not os.environ.get("GG_SKIP_ENGINE")


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


if __name__ == "__main__":
    unittest.main()
