import copy, json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gg_godot, gg_style, gg_schema


class T(unittest.TestCase):
    def test_four_presets_valid(self):
        names = gg_style.list_presets()
        self.assertEqual(names, ["low-poly", "pixel-art", "realistic", "stylised-painterly"])
        for n in names:
            self.assertEqual(gg_style.preset_errors(gg_style.load_preset(n)), [], n)

    def test_presets_differ_in_data(self):
        p = {n: gg_style.load_preset(n) for n in gg_style.list_presets()}
        self.assertEqual({p[n]["material"]["shading"] for n in p}, {"pbr", "toon", "flat", "unshaded"})
        self.assertEqual(p["pixel-art"]["render"]["internal"], [320, 180])
        self.assertEqual(p["pixel-art"]["render"]["window"][0] % 320, 0)
        self.assertLessEqual(len(p["pixel-art"]["material"]["palette"]), 32)
        self.assertEqual(p["low-poly"]["renderer"], "gl_compatibility")

    def test_target_ranges_not_identical_between_presets(self):
        p = {n: gg_style.load_preset(n)["targets"] for n in gg_style.list_presets()}
        names = list(p)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                self.assertNotEqual(p[a], p[b])

    def test_validation_names_field(self):
        p = gg_style.load_preset("realistic")
        p["lighting"]["sun_energy"] = 99
        p["post"]["tonemap"] = "gamma"
        p["targets"]["luma_p50"] = [0.9, 0.1]
        p["targets"]["nope"] = [0, 1]
        text = "\n".join(gg_style.preset_errors(p))
        for frag in ("$.lighting.sun_energy", "99", "$.post.tonemap", "gamma", "luma_p50", "lo 0.9 > hi 0.1", "unknown metric"):
            self.assertIn(frag, text)

    def test_unknown_and_missing_keys(self):
        p = gg_style.load_preset("low-poly"); p["bogus"] = 1; del p["water"]
        text = "\n".join(gg_style.preset_errors(p))
        self.assertIn("unknown key 'bogus'", text); self.assertIn("missing required 'water'", text)

    def test_palette_rules(self):
        p = gg_style.load_preset("pixel-art"); p["material"]["palette"] = None
        self.assertTrue(any("palette_quantize" in e for e in gg_style.preset_errors(p)))

    def prof(self, **kw):
        d = {"dimension": "3d", "style": {"preset": "low-poly", "overrides": {}}, "title": "T"}
        d.update(kw)
        return d

    def test_overrides_merge_and_refuse_unknown(self):
        r = gg_style.resolve(self.prof(style={"preset": "low-poly", "overrides": {"post": {"exposure": 1.4}}}))
        self.assertEqual(r["post"]["exposure"], 1.4); self.assertEqual(r["post"]["tonemap"], "linear")
        with self.assertRaises(gg_godot.Refused) as c:
            gg_style.resolve(self.prof(style={"preset": "low-poly", "overrides": {"post": {"exposur": 1.4}}}))
        self.assertIn("exposur", str(c.exception))
        with self.assertRaises(gg_godot.Refused): gg_style.resolve(self.prof(style={"preset": "low-poly", "overrides": {"post": {"exposure": 40}}}))

    def test_dimension_refused_names_both(self):
        with self.assertRaises(gg_godot.Refused) as c: gg_style.resolve(self.prof(dimension="2d"))
        self.assertIn("2d", str(c.exception)); self.assertIn("3d", str(c.exception))
        self.assertEqual(gg_style.resolve(self.prof(dimension="2d", style={"preset": "pixel-art"}))["name"], "pixel-art")

    def test_unknown_preset_lists_choices(self):
        with self.assertRaises(gg_godot.Refused) as c: gg_style.load_preset("photoreal")
        self.assertIn("low-poly", str(c.exception))

    def test_settings_typed(self):
        pix = gg_style.load_preset("pixel-art")
        s, actions = gg_style.settings_for({"title": "T"}, pix)
        d = {x["key"]: x for x in s}
        self.assertEqual(d["display/window/size/viewport_width"]["value"], 320)
        self.assertEqual(d["display/window/size/window_width_override"]["value"], 1280)
        self.assertEqual(d["display/window/stretch/mode"]["value"], "viewport")
        self.assertEqual(d["rendering/textures/canvas_textures/default_texture_filter"]["value"], 0)
        self.assertTrue(d["rendering/2d/snap/snap_2d_transforms_to_pixel"]["value"])
        real = gg_style.settings_for({"title": "T"}, gg_style.load_preset("realistic"))[0]
        rd = {x["key"]: x for x in real}
        self.assertEqual(rd["display/window/size/viewport_width"]["value"], 1280)
        self.assertEqual(rd["rendering/anti_aliasing/quality/msaa_3d"]["value"], 1)
        self.assertEqual(rd["display/window/stretch/mode"]["value"], "disabled")
        self.assertIn("move_forward", actions)

    def test_matrix_verdict(self):
        ok, pr = gg_style.matrix_verdict({"a": {"a": [], "b": [{"metric": "x"}]}, "b": {"a": [{"metric": "x"}], "b": []}}, ["a", "b"])
        self.assertTrue(ok)
        ok, pr = gg_style.matrix_verdict({"a": {"a": [], "b": []}, "b": {"a": [{"metric": "x"}], "b": [{"metric": "y"}]}}, ["a", "b"])
        self.assertFalse(ok)
        self.assertTrue(any("a image passes b" in x for x in pr)); self.assertTrue(any("b fails its own" in x for x in pr))

    def test_check_applied_refuses_stale_and_missing(self):
        with tempfile.TemporaryDirectory() as d:
            prof = self.prof()
            with self.assertRaises(gg_godot.Refused) as c: gg_style.check_applied(d, prof)
            self.assertIn("apply", str(c.exception))
            gg_style.write_resolved(d, prof)
            self.assertEqual(gg_style.check_applied(d, prof)["name"], "low-poly")
            prof["style"]["preset"] = "realistic"  # edited the profile, did not apply
            with self.assertRaises(gg_godot.Refused) as c: gg_style.check_applied(d, prof)
            self.assertIn("changed since the last apply", str(c.exception))

    def test_overrides_limit_probe_to_structural_targets(self):
        seen = {}
        class R:
            def __call__(s, project, op, args=None, **kw):
                seen.update(args); raise gg_godot.Refused("stop")
        st = gg_style.load_preset("low-poly")
        with self.assertRaises(gg_godot.Refused):
            gg_style.probe_shot("P", st, "3d", tempfile.mkdtemp(), run=R(), scene="res://x.tscn", overrides=True, require_selftest=False)

    def test_sky_ambient_mismatch_and_gradient_refused(self):
        p = gg_style.load_preset("low-poly"); p["lighting"]["ambient_source"] = "sky"
        self.assertIn("ambient_source", "\n".join(gg_style.preset_errors(p)))
        p = gg_style.load_preset("realistic"); p["lighting"]["sky"]["kind"] = "gradient"
        self.assertIn("gradient", "\n".join(gg_style.preset_errors(p)))

    def test_calibrated_targets_shape(self):
        m = {"luma_p5": .2, "luma_p50": .5, "luma_p95": .8, "sat_mean": .4, "flat_fraction": .9, "unique_colors": 11, "luma_std": .2, "grid_integrity": 1.0}
        t = gg_style.calibrated_targets(m, grid_block=True)
        self.assertEqual(t["unique_colors"][0], 5); self.assertGreaterEqual(t["luma_std"][0], 0.02)
        self.assertEqual(t["grid_integrity"], [0.98, None])
        flat = {"luma_p5": .58, "luma_p50": .58, "luma_p95": .58, "sat_mean": .67, "flat_fraction": 1.0, "unique_colors": 1, "luma_std": 0.0}
        self.assertGreaterEqual(gg_style.calibrated_targets(flat)["luma_std"][0], 0.02)  # a uniform image can never pass

    def test_cli_validate_and_list(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.json"); bad = gg_style.load_preset("realistic"); bad["renderer"] = "dx12"; json.dump(bad, open(p, "w"))
            self.assertEqual(gg_style.main(["validate", p]), 1)
            self.assertEqual(gg_style.main(["list"]), 0)
            self.assertEqual(gg_style.main(["show", "nope"]), 2)


if __name__ == "__main__":
    unittest.main()
