import json, os, sys, tempfile, unittest
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gg_godot, gg_project, gg_terrain


def project(size=(128.0, 128.0), cell=4.0, rng=(-20.0, 60.0), sea=0.0, preset="low-poly"):
    d = tempfile.mkdtemp()
    import argparse

    a = argparse.Namespace(
        project=d,
        name="t",
        dimension="3d",
        view=None,
        style=preset,
        size_m=list(size),
        cell_m=cell,
        seed=3,
        dry_run=False,
        adopt=False,
    )
    prof, _ = gg_project.build_profile(a)
    prof["world"]["height_range_m"] = list(rng)
    prof["world"]["sea_level_m"] = sea
    json.dump(prof, open(os.path.join(d, "gg_project.json"), "w"))
    return d


class T(unittest.TestCase):
    def test_grid_counts_vertices(self):
        d = project((128, 64), 4.0)
        self.assertEqual(gg_terrain.grid(gg_project.load_profile(d))[:2], (33, 17))

    def test_heights_deterministic_and_island_has_sea_and_land(self):
        d = project()
        c, info, w = gg_terrain.heights(d, "island", 40.0, 5)
        a = open(os.path.join(d, "gg_data/world/heights.f32"), "rb").read()
        gg_terrain.heights(d, "island", 40.0, 5)
        self.assertEqual(a, open(os.path.join(d, "gg_data/world/heights.f32"), "rb").read())
        gg_terrain.heights(d, "island", 40.0, 6)
        self.assertNotEqual(a, open(os.path.join(d, "gg_data/world/heights.f32"), "rb").read())
        self.assertTrue(0.1 < info["land_fraction"] < 0.9, info)
        arr = np.fromfile(os.path.join(d, "gg_data/world/heights.f32"), "<f4").reshape(33, 33)
        self.assertLess(arr[0, 0], 0.0)  # corners are sea
        self.assertGreater(arr[16, 16], 5.0)  # centre is land

    def test_png_round_trip_matches_f32(self):
        from PIL import Image

        d = project()
        gg_terrain.heights(d, "hills", 30.0, 1)
        png = np.asarray(Image.open(os.path.join(d, "gg_data/world/heights.png")), dtype=np.float64)
        f32 = np.fromfile(os.path.join(d, "gg_data/world/heights.f32"), "<f4").reshape(33, 33)
        lo, hi = -20.0, 60.0
        self.assertLess(float(np.abs(png / 65535 * (hi - lo) + lo - f32).max()), (hi - lo) / 65535 + 1e-3)

    def test_relief_refused_names_range(self):
        d = project()
        with self.assertRaises(gg_godot.Refused) as c:
            gg_terrain.heights(d, "hills", 500.0)
        self.assertIn("-20.0", str(c.exception))
        self.assertIn("500", str(c.exception))
        with self.assertRaises(gg_godot.Refused):
            gg_terrain.heights(d, "hills", None)

    def test_from_file_size_mismatch_names_both(self):
        d = project()
        p = os.path.join(d, "h.npy")
        np.save(p, np.zeros((10, 12)))
        with self.assertRaises(gg_godot.Refused) as c:
            gg_terrain.heights(d, from_file=p)
        self.assertIn("12x10", str(c.exception))
        self.assertIn("33x33", str(c.exception))

    def test_sea_outside_terrain_warns(self):
        d = project(sea=-10.0)
        c, info, w = gg_terrain.heights(d, "hills", 30.0, 1)
        self.assertTrue(any("sea level" in x for x in w))

    def test_dry_run_writes_nothing(self):
        d = project()
        gg_terrain.heights(d, "hills", 30.0, 1, dry_run=True)
        self.assertFalse(os.path.exists(os.path.join(d, "gg_data", "world")))

    def test_layers_real_masks_sum_255_and_orientation(self):
        d = project((256, 256), 4.0, (-20, 60))
        gg_terrain.heights(d, "island", 40.0, 2)
        code, rep, warns = gg_terrain.layers(d)
        self.assertEqual(code, 0)
        self.assertTrue(rep["sum_to_255_everywhere"])
        from PIL import Image

        s0 = np.asarray(Image.open(os.path.join(d, "gg_data/world/layers/splat_0.png")))
        self.assertEqual(s0.shape[:2], (65, 65))
        self.assertTrue((s0.astype(int).sum(axis=2) == 255).all())  # 4 layers in one splat map
        prev = np.asarray(Image.open(os.path.join(d, "gg_data/world/layers/layer_preview.png")))
        self.assertEqual(prev.shape[:2], (65, 65))

    def test_layers_spec_refusals(self):
        d = project()
        gg_terrain.heights(d, "hills", 30.0, 1)
        for spec, frag in (
            ({"layers": [{"name": "a", "color": [0, 0, 0]}, {"name": "b", "color": [1, 1, 1]}]}, "fallback"),
            ({"layers": [{"name": "a", "fallback": True}, {"name": "b", "color": [1, 1, 1]}]}, "color"),
            (
                {
                    "layers": [
                        {"name": "l%d" % i, "color": [0, 0, 0], **({"fallback": True} if i == 0 else {})}
                        for i in range(9)
                    ]
                },
                "9 layers",
            ),
        ):
            p = os.path.join(d, "s.json")
            json.dump(spec, open(p, "w"))
            with self.assertRaises(gg_godot.Refused) as c:
                gg_terrain.layers(d, p)
            self.assertIn(frag, str(c.exception))

    def test_layers_before_heights_refused(self):
        with self.assertRaises(gg_godot.Refused) as c:
            gg_terrain.layers(project())
        self.assertIn("heights first", str(c.exception))

    def test_coverage_warning(self):
        d = project()
        gg_terrain.heights(d, "flat", 10.0, 1)
        spec = {
            "seed": 1,
            "layers": [
                {"name": "grass", "fallback": True, "color": [0, 1, 0]},
                {"name": "rock", "slope_deg": [40, 90, 5], "color": [0.5, 0.5, 0.5]},
            ],
        }
        p = os.path.join(d, "s.json")
        json.dump(spec, open(p, "w"))
        c, rep, warns = gg_terrain.layers(d, p)
        self.assertTrue(any("rock" in w and "never appears" in w for w in warns), warns)

    def test_build_args_refuses_mismatched_masks(self):
        d = project((128, 128), 4.0)
        gg_terrain.heights(d, "hills", 30.0, 1)
        gg_terrain.layers(d)
        rp = os.path.join(d, "gg_data/world/layers/layer_report.json")
        rep = json.load(open(rp))
        rep["input"]["size_px"] = [10, 10]
        json.dump(rep, open(rp, "w"))
        prof = gg_project.load_profile(d)
        with self.assertRaises(gg_godot.Refused) as c:
            gg_terrain.build_args(d, prof, {"material": {"shading": "flat"}})
        self.assertIn("33x33", str(c.exception))
        self.assertIn("[10, 10]", str(c.exception))
        rep["input"]["size_px"] = [33, 33]
        rep["sum_to_255_everywhere"] = False
        json.dump(rep, open(rp, "w"))
        with self.assertRaises(gg_godot.Refused) as c:
            gg_terrain.build_args(d, prof, {})
        self.assertIn("255", str(c.exception))

    def test_build_needs_applied_style(self):
        d = project()
        gg_terrain.heights(d, "hills", 30.0, 1)
        gg_terrain.layers(d)
        with self.assertRaises(gg_godot.Refused) as c:
            gg_terrain.build(d)
        self.assertIn("apply", str(c.exception))

    def test_rewriting_heights_deletes_stale_layers_and_build_marker(self):
        d = project()
        gg_terrain.heights(d, "hills", 30.0, 1)
        gg_terrain.layers(d)
        open(os.path.join(d, "gg_data/world/build_ok.json"), "w").write("{}")
        gg_terrain.heights(d, "hills", 30.0, 2)
        self.assertFalse(os.path.exists(os.path.join(d, "gg_data/world/layers")))
        self.assertFalse(os.path.exists(os.path.join(d, "gg_data/world/build_ok.json")))
        with self.assertRaises(gg_godot.Refused) as c:
            gg_terrain.build_args(d, gg_project.load_profile(d), {})
        self.assertIn("layers first", str(c.exception))

    def test_layers_from_other_heights_are_refused_by_hash(self):
        d = project()
        gg_terrain.heights(d, "hills", 30.0, 1)
        gg_terrain.layers(d)
        wp = os.path.join(d, "gg_data/world/world.json")
        w = json.load(open(wp))
        w["heights_sha"] = "0" * 64
        json.dump(w, open(wp, "w"))
        with self.assertRaises(gg_godot.Refused) as c:
            gg_terrain.build_args(d, gg_project.load_profile(d), {})
        self.assertIn("current heights", str(c.exception))

    def test_flipped_or_edited_splat_is_refused(self):
        from PIL import Image, ImageOps

        d = project((128, 128), 4.0)
        gg_terrain.heights(d, "ramp", 40.0, 1)
        gg_terrain.layers(
            d,
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..", "templates", "layers.orientation_probe.json"
            ),
        )
        prof = gg_project.load_profile(d)
        gg_terrain.build_args(d, prof, {})  # untouched: fine
        p = os.path.join(d, "gg_data/world/layers/splat_0.png")
        ImageOps.flip(Image.open(p)).save(p)
        with self.assertRaises(gg_godot.Refused) as c:
            gg_terrain.build_args(d, prof, {})
        self.assertIn("does not match the weights derived from heights.png", str(c.exception))

    def test_size_not_multiple_of_cell_refused(self):
        d = project((130.0, 128.0), 4.0)
        with self.assertRaises(gg_godot.Refused) as c:
            gg_terrain.grid(gg_project.load_profile(d))
        self.assertIn("multiple", str(c.exception))

    def test_single_layer_spec_refused(self):
        d = project()
        gg_terrain.heights(d, "hills", 30.0, 1)
        p = os.path.join(d, "s.json")
        json.dump({"layers": [{"name": "a", "fallback": True, "color": [0, 1, 0]}]}, open(p, "w"))
        with self.assertRaises(gg_godot.Refused) as c:
            gg_terrain.layers(d, p)
        self.assertIn("2..8", str(c.exception))

    def test_nan_heights_file_refused(self):
        d = project()
        a = np.zeros((33, 33))
        a[3, 3] = np.nan
        p = os.path.join(d, "h.npy")
        np.save(p, a)
        with self.assertRaises(gg_godot.Refused) as c:
            gg_terrain.heights(d, from_file=p)
        self.assertIn("NaN", str(c.exception))

    def test_layer_masks_exit_becomes_refusal(self):
        d = project()
        gg_terrain.heights(d, "hills", 30.0, 1)

        class Fake:
            @staticmethod
            def main(argv):
                raise SystemExit("bad spec")

        old = gg_terrain._lm
        gg_terrain._lm = lambda: Fake
        try:
            with self.assertRaises(gg_godot.Refused) as c:
                gg_terrain.layers(d)
        finally:
            gg_terrain._lm = old
        self.assertIn("bad spec", str(c.exception))

    def test_every_preset_has_a_layer_template(self):
        for n in ("realistic", "stylised-painterly", "low-poly", "pixel-art"):
            sp = json.load(
                open(
                    os.path.join(
                        os.path.dirname(gg_terrain.HERE) if False else os.path.dirname(os.path.abspath(__file__)),
                        "..",
                        "templates",
                        "layers.%s.json" % n,
                    )
                )
            )
            self.assertEqual(sum(1 for l in sp["layers"] if l.get("fallback")), 1)

    def test_pixel_layer_colours_are_palette_colours(self):
        import gg_style

        pal = {
            tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
            for h in gg_style.load_preset("pixel-art")["material"]["palette"]
        }
        sp = json.load(
            open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates", "layers.pixel-art.json"))
        )
        for l in sp["layers"]:
            self.assertIn(tuple(round(c * 255) for c in l["color"]), pal, l["name"])


class Check(unittest.TestCase):
    def test_agreement_and_mirror_detection(self):
        exp = np.zeros((16, 16), int)
        exp[:, 8:] = 1
        exp[:4, :] = 2
        self.assertEqual(gg_terrain.agreement(exp, exp)[0], 1.0)
        self.assertLess(gg_terrain.agreement(exp[:, ::-1], exp)[0], 0.6)

    def test_mirror_margin_logic(self):
        # symmetric terrain: flips agree as well as the real one -> must be reported as not proving orientation
        exp = np.zeros((16, 16), int)
        exp[:, :8] = 1
        exp[:, 8:] = 2
        obs = exp.copy()
        ag = gg_terrain.agreement(obs, exp)[0]
        fx = gg_terrain.agreement(obs[:, ::-1], exp)[0]
        self.assertLess(fx, ag - 0.08)  # asymmetric: clearly separated
        sym = np.zeros((16, 16), int)
        sym[:, 4:12] = 1
        self.assertGreaterEqual(gg_terrain.agreement(sym[:, ::-1], sym)[0], gg_terrain.agreement(sym, sym)[0] - 0.08)

    def test_measured_refs_survive_hue_shift_and_flag_identical_layers(self):
        exp = np.zeros((16, 16), int)
        exp[:, 8:] = 1
        img = np.zeros((16, 16, 3))
        img[exp == 0] = (200, 100, 50)
        img[exp == 1] = (50, 100, 200)
        refs, sep = gg_terrain.measured_refs(img, exp)
        self.assertGreater(sep, 0.1)
        self.assertTrue((gg_terrain.classify_by_chroma(img, refs) == exp).all())
        img[:] = (120, 120, 120)
        self.assertLess(gg_terrain.measured_refs(img, exp)[1], 0.02)


if __name__ == "__main__":
    unittest.main()
