"""gg_vfx: refusals are pure; `check` needs a real project + the gl_compatibility selftest and is skipped
without godot or a passing selftest (or when GG_SKIP_ENGINE=1)."""
import argparse
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gg_godot
import gg_ui
import gg_verify
import gg_vfx

ENGINE = gg_godot.find_godot() and not os.environ.get("GG_SKIP_ENGINE")
RENDER_READY = ENGINE and gg_verify.selftest_gate(gg_vfx.RENDERER) is None


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


if __name__ == "__main__":
    unittest.main()
