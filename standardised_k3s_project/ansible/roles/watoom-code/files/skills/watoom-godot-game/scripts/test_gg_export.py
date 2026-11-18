import os, sys, tempfile, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gg_export as E, gg_godot


class Pure(unittest.TestCase):
    def test_main_scene_replaced(self):
        t = '[application]\n\nconfig/name="x"\nrun/main_scene="res://levels/_boot/boot.tscn"\n\n[rendering]\na=1\n'
        o = E.set_main_scene(t, "res://levels/main/level.tscn")
        self.assertIn('run/main_scene="res://levels/main/level.tscn"', o)
        self.assertNotIn("_boot", o)
        self.assertIn("[rendering]", o)

    def test_main_scene_added_to_existing_or_missing_section(self):
        self.assertIn('run/main_scene="res://a.tscn"', E.set_main_scene('[application]\n\nconfig/name="x"\n', "res://a.tscn"))
        o = E.set_main_scene("[rendering]\na=1\n", "res://a.tscn")
        self.assertIn("[application]", o)
        self.assertIn('run/main_scene="res://a.tscn"', o)

    def test_preset_cfg(self):
        c = E.preset_cfg("windows", "/o/game.exe")
        self.assertIn('platform="Windows Desktop"', c)
        self.assertIn('export_path="/o/game.exe"', c)
        self.assertIn("gg_data/*", c)

    def test_stage_skips_data_and_rewrites_main_scene(self):
        with tempfile.TemporaryDirectory() as d:
            p, s = os.path.join(d, "p"), os.path.join(d, "stage")
            os.makedirs(os.path.join(p, "gg_data"))
            os.makedirs(os.path.join(p, ".godot"))
            os.makedirs(os.path.join(p, "levels"))
            open(os.path.join(p, "gg_data", "big.bin"), "w").write("x")
            open(os.path.join(p, "levels", "a.tscn"), "w").write("x")
            open(os.path.join(p, "project.godot"), "w").write('[application]\n\nrun/main_scene="res://boot.tscn"\n')
            E.stage(p, s, "res://levels/main/level.tscn")
            self.assertEqual(sorted(os.listdir(s)), ["levels", "project.godot"])
            self.assertIn("levels/main/level.tscn", open(os.path.join(s, "project.godot")).read())
            self.assertIn("boot.tscn", open(os.path.join(p, "project.godot")).read())  # the project is untouched


class Frames(unittest.TestCase):
    def test_blank_and_flat_fail(self):
        import numpy as np
        self.assertFalse(E.frame_verdict(np.zeros((20, 20, 3)))[0])
        self.assertFalse(E.frame_verdict(np.full((20, 20, 3), 0.5))[0])

    def test_matching_and_mismatching_start(self):
        import numpy as np
        rng = np.random.default_rng(1)
        a = rng.random((64, 64, 3))
        self.assertTrue(E.frame_verdict(a, a)[0])
        self.assertTrue(E.frame_verdict(a, np.clip(a + 0.01, 0, 1))[0])
        ok, ev, why = E.frame_verdict(a, 1 - a)
        self.assertFalse(ok)
        self.assertIn("not showing the level", why)


class Refusals(unittest.TestCase):
    def _prof(self, presets):
        return {"export": {"presets": presets}}

    def test_refuses_without_valid_smoke(self):
        with mock.patch.object(E.gg_terrain, "load_world", return_value={"heights_sha": "h"}), \
             mock.patch.object(E.gg_player, "stamp_state", return_value=(False, ["runtime_lock"])):
            with self.assertRaisesRegex(gg_godot.Refused, "no valid smoke test.*runtime_lock"):
                E.check_allowed("/p", self._prof(["pck"]), "pck", "godot")

    def test_refuses_preset_not_listed(self):
        with mock.patch.object(E.gg_terrain, "load_world", return_value={"heights_sha": "h"}), \
             mock.patch.object(E.gg_player, "stamp_state", return_value=(True, [])):
            with self.assertRaisesRegex(gg_godot.Refused, "not in gg_project.json"):
                E.check_allowed("/p", self._prof(["pck"]), "linux", "godot")

    def test_refuses_missing_templates_but_pck_needs_none(self):
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(E.gg_terrain, "load_world", return_value={"heights_sha": "h"}), \
             mock.patch.object(E.gg_player, "stamp_state", return_value=(True, [])), \
             mock.patch.object(E, "engine_version", return_value="4.7.2.stable"), \
             mock.patch.object(E, "templates_dir", return_value=os.path.join(d, "4.7.2.stable")):
            E.check_allowed("/p", self._prof(["pck", "linux"]), "pck", "godot")
            with self.assertRaisesRegex(gg_godot.Refused, "no export templates"):
                E.check_allowed("/p", self._prof(["pck", "linux"]), "linux", "godot")
            os.makedirs(os.path.join(d, "4.7.2.stable"))
            open(os.path.join(d, "4.7.2.stable", "linux_release.x86_64"), "w").write("x")
            E.check_allowed("/p", self._prof(["pck", "linux"]), "linux", "godot")


if __name__ == "__main__":
    unittest.main()
