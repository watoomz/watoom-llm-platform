"""gg_ui: pure analysis tests always run; the real-engine tests are skipped when godot/xvfb-run or the selftest report is missing (or GG_SKIP_ENGINE=1)."""
import os, shutil, sys, tempfile, unittest
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gg_godot, gg_ui, gg_verify

ENGINE = gg_godot.find_godot() and shutil.which("xvfb-run") and not os.environ.get("GG_SKIP_ENGINE") and gg_verify.selftest_gate("gl_compatibility") is None


def rgba(h, w, fill=(0, 0, 0, 0)):
    a = np.zeros((h, w, 4), dtype=np.uint8)
    a[:, :] = fill
    return a


class Analysis(unittest.TestCase):
    def test_empty_image_is_not_drawn(self):
        _, rows = gg_ui.shot_checks(rgba(240, 1920), {})
        self.assertFalse(dict((n, o) for n, o, _ in rows)["drawn"])

    def test_alpha_bbox_and_coverage(self):
        a = np.zeros((100, 200), dtype=np.uint8)
        a[60:, :] = 255
        m = gg_ui.analyse_alpha(a)
        self.assertEqual(m["bbox"], [0, 60, 199, 99])
        self.assertAlmostEqual(m["coverage"], 0.4)
        self.assertEqual(m["bottom_row_drawn"], 1.0)

    def test_faint_alpha_below_threshold_is_not_drawn(self):
        a = np.full((10, 10), gg_ui.ALPHA_ON - 1, dtype=np.uint8)
        self.assertEqual(gg_ui.analyse_alpha(a)["coverage"], 0.0)

    def test_dock_bottom_checks_width_height_and_edge(self):
        img = rgba(240, 1920, (30, 30, 40, 255))
        ok = dict((n, o) for n, o, _ in gg_ui.shot_checks(img, {}, dock="bottom", screen=(1920, 1080))[1])
        self.assertTrue(ok["strip width"] and ok["strip height"] and ok["bottom edge drawn"])
        narrow = dict((n, o) for n, o, _ in gg_ui.shot_checks(rgba(240, 1000, (30, 30, 40, 255)), {}, dock="bottom", screen=(1920, 1080))[1])
        self.assertFalse(narrow["strip width"])
        tall = dict((n, o) for n, o, _ in gg_ui.shot_checks(rgba(700, 1920, (30, 30, 40, 255)), {}, dock="bottom", screen=(1920, 1080))[1])
        self.assertFalse(tall["strip height"])

    def test_see_through_is_opt_in(self):
        img = rgba(240, 1920, (30, 30, 40, 255))
        names = [n for n, _, _ in gg_ui.shot_checks(img, {}, dock="bottom")[1]]
        self.assertNotIn("see-through", names)
        rows = dict((n, o) for n, o, _ in gg_ui.shot_checks(img, {}, dock="bottom", see_through=True)[1])
        self.assertFalse(rows["see-through"])
        img[:, :400] = 0
        rows = dict((n, o) for n, o, _ in gg_ui.shot_checks(img, {}, dock="bottom", see_through=True)[1])
        self.assertTrue(rows["see-through"])

    def test_clipped_small_and_tiny_text_are_named(self):
        census = {"clipped": [{"name": "Wide"}], "small_buttons": [{"name": "Tiny"}], "labels": [{"name": "Lbl", "font_size": 8}]}
        rows = dict((n, (o, d)) for n, o, d in gg_ui.shot_checks(rgba(50, 50, (9, 9, 9, 255)), census)[1])
        for k, word in (("nothing clipped", "Wide"), ("buttons big enough", "Tiny"), ("text size", "Lbl")):
            self.assertFalse(rows[k][0])
            self.assertIn(word, rows[k][1])

    def test_flat_model_view_fails_and_a_drawn_one_passes(self):
        flat = rgba(100, 100, (20, 20, 20, 255))
        busy = flat.copy()
        busy[30:70, 30:70] = (200, 60, 40, 255)
        census = {"model_views": [{"name": "V", "rect": [10, 10, 80, 80]}]}
        self.assertFalse(dict((n, o) for n, o, _ in gg_ui.shot_checks(flat, census)[1])["model view V"])
        self.assertTrue(dict((n, o) for n, o, _ in gg_ui.shot_checks(busy, census)[1])["model view V"])

    def test_min_model_views_counts_the_containers(self):
        rows = dict((n, o) for n, o, _ in gg_ui.shot_checks(rgba(50, 50, (9, 9, 9, 255)), {"model_views": []}, min_views=2)[1])
        self.assertFalse(rows["model views"])

    def test_overlay_checks(self):
        probe = {"flags": {"borderless": True, "always_on_top": True, "transparent": True, "mouse_passthrough": False}, "window": {"position": [0, 840], "size": [1920, 240]},
                 "screen": {"size": [1920, 1080], "usable": [0, 0, 1920, 1040 + 40]}, "passthrough_points": 4, "viewport_transparent_bg": True,
                 "project": {"per_pixel_transparency": True, "size_transparent": False, "borderless": False, "always_on_top": False, "transparent_background": False}}
        self.assertTrue(all(o for _, o, _ in gg_ui.overlay_checks(probe, require_passthrough=True)))
        bad = dict(probe, window={"position": [0, 0], "size": [1000, 900]})
        rows = dict((n, o) for n, o, _ in gg_ui.overlay_checks(bad))
        self.assertFalse(rows["full width"] or rows["strip height"] or rows["docked at the bottom"])
        nothing = dict(probe, flags={"borderless": False, "always_on_top": False, "transparent": False, "mouse_passthrough": False})
        rows = dict((n, o) for n, o, _ in gg_ui.overlay_checks(nothing))
        self.assertFalse(rows["borderless"] or rows["always on top"] or rows["transparent"])

    def test_parse_size_and_scene_refusals(self):
        self.assertEqual(gg_ui.parse_size("1920x240"), (1920, 240))
        for bad in ("1920", "axb", "10x10", "99999x100"):
            with self.assertRaises(gg_godot.Refused):
                gg_ui.parse_size(bad)
        with tempfile.TemporaryDirectory() as d:
            for scene in ("scenes/main.tscn", "res://../x.tscn", "res://a b.tscn", "res://missing.tscn"):
                with self.assertRaises(gg_godot.Refused):
                    gg_ui.check_scene(d, scene)


class Init(unittest.TestCase):
    def test_init_writes_the_overlay_project_and_refuses_a_non_empty_folder(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "g")
            self.assertEqual(gg_ui.main(["init", "--project", p, "--name", "strip_game", "--height", "200"]), 0)
            text = open(os.path.join(p, "project.godot")).read()
            for want in ("window/size/borderless=true", "window/per_pixel_transparency/allowed=true", "viewport/transparent_background=true", 'rendering_method="gl_compatibility"', "viewport_height=200"):
                self.assertIn(want, text)
            self.assertTrue(os.path.isfile(os.path.join(p, "addons/gg/game/overlay_window.gd")))
            self.assertTrue(os.path.isfile(os.path.join(p, "tests/test_overlay.gd")))
            self.assertEqual(gg_ui.main(["init", "--project", p, "--name", "again"]), 2)
            q = os.path.join(d, "pre"); os.makedirs(os.path.join(q, "assets"))
            open(os.path.join(q, "BRIEF.md"), "w").write("x"); open(os.path.join(q, "assets", "hero.glb"), "w").write("x")
            self.assertEqual(gg_ui.main(["init", "--project", q, "--name", "pre"]), 0)
            self.assertTrue(os.path.isfile(os.path.join(q, "assets", "hero.glb")))
            self.assertEqual(gg_ui.main(["init", "--project", os.path.join(d, "x"), "--name", "9bad"]), 2)

    def test_test_with_no_tests_is_a_refusal_not_a_pass(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "g")
            gg_ui.main(["init", "--project", p, "--name", "g"])
            os.remove(os.path.join(p, "tests/test_overlay.gd"))
            self.assertEqual(gg_ui.main(["test", "--project", p]), 2)


@unittest.skipUnless(ENGINE, "godot/xvfb-run/selftest not available")
class Engine(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.p = os.path.join(self.d, "g")
        self.assertEqual(gg_ui.main(["init", "--project", self.p, "--name", "g"]), 0)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def write(self, rel, text):
        open(os.path.join(self.p, rel), "w").write(text)

    def test_sample_test_passes_a_wrong_assertion_fails_a_silent_test_fails(self):
        self.assertEqual(gg_ui.main(["test", "--project", self.p]), 0)
        self.write("tests/test_bad.gd", 'extends "res://addons/gg/lib/gg_test.gd"\nfunc test_wrong() -> void:\n\teq(2 + 2, 5)\nfunc test_silent() -> void:\n\tpass\n')
        self.assertEqual(gg_ui.main(["test", "--project", self.p]), 1)

    def test_a_syntax_error_in_a_test_is_exit_3_not_a_pass(self):
        self.write("tests/test_syntax.gd", 'extends "res://addons/gg/lib/gg_test.gd"\nfunc test_x() -> void:\n\tvar a := \n')
        self.assertEqual(gg_ui.main(["test", "--project", self.p]), 3)

    def test_the_stub_docks_and_a_scene_that_never_docks_fails_the_overlay_check(self):
        self.assertEqual(gg_ui.main(["overlay-check", "--project", self.p]), 0)
        self.write("scripts/main.gd", "extends Control\nfunc _ready() -> void:\n\tpass\n")
        self.assertEqual(gg_ui.main(["overlay-check", "--project", self.p]), 1)

    def test_shot_measures_a_drawn_strip_and_a_blank_scene_fails(self):
        self.write("scripts/main.gd", 'extends Control\nfunc _ready() -> void:\n\tvar p := ColorRect.new()\n\tp.color = Color(0.2, 0.2, 0.3, 1)\n\tp.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)\n\tadd_child(p)\n')
        args = ["shot", "--project", self.p, "--scene", "res://scenes/main.tscn", "--size", "1920x240", "--dock", "bottom", "--name", "s"]
        self.assertEqual(gg_ui.main(args), 0)
        self.assertTrue(os.path.isfile(os.path.join(self.p, "gg_data/ui_shot/s.png")))
        self.write("scripts/main.gd", "extends Control\nfunc _ready() -> void:\n\tpass\n")
        self.assertEqual(gg_ui.main(args), 1)

    def test_a_script_error_in_the_scene_is_not_a_pass(self):
        self.write("scripts/main.gd", "extends Control\nfunc _ready() -> void:\n\tvar x := \n")
        code = gg_ui.main(["shot", "--project", self.p, "--scene", "res://scenes/main.tscn", "--name", "e"])
        self.assertIn(code, (3, 4, 5))


if __name__ == "__main__":
    unittest.main()
