import copy, json, os, sys, tempfile, unittest
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gg_catalog as C, gg_godot


def fam(**kw):
    f = {"category": "tree_upland", "scene": "res://a.tscn", "above_sea_m": [1.0, 40.0], "max_slope": 0.5, "near_water_m": [8, None], "min_spacing_m": 3.0, "wind": 0.2, "scale_range": [0.8, 1.2]}
    f.update(kw)
    return f


def data(h=8.0, w=3.0, base=0.0, mats=None, meshes=1, **kw):
    d = {"meshes": meshes, "aabb": {"pos": [0, base, 0], "size": [w, h, w]}, "materials": mats if mats is not None else [{"node": "M", "surface": 0, "kind": "StandardMaterial3D", "albedo": [0.2, 0.5, 0.2, 1], "albedo_texture": False, "emission": 0.0, "cull": "disabled"}],
         "lights": 0, "skeletons": 0, "animation_players": 0, "triangles": 500}
    d.update(kw)
    return d


class T(unittest.TestCase):
    def test_default_catalog_rules_pass_for_every_default(self):
        for d in C.DEFAULTS:
            f = {k: d[k] for k in ("category", "above_sea_m", "max_slope", "near_water_m", "min_spacing_m", "wind") if k in d}
            f.update(scene="res://assets/gg/%s.tscn" % d["name"], scale_range=[0.8, 1.3])
            if d.get("allow_in_sea"):
                f["allow_in_sea"] = True
            self.assertEqual(C.family_errors(d["name"], f), [], d["name"])

    def test_every_preset_has_colours_for_the_default_assets(self):
        import gg_style
        for n in gg_style.list_presets():
            specs = C.asset_specs(n)
            self.assertEqual(len(specs), len(C.DEFAULTS))
            for s in specs:
                self.assertTrue(all(0 <= c <= 1 for c in s["colors"]["leaf"]), (n, s["name"]))

    def test_rules_by_category(self):
        cases = [(fam(category="wet_margin", above_sea_m=[-0.3, None], near_water_m=[0, None]), "high limit"),
                 (fam(category="wet_margin", above_sea_m=[-0.3, 20.0], near_water_m=[0, 12]), "must not have an upper above_sea_m"),
                 (fam(category="dune_coast", above_sea_m=[0.3, 40.0], near_water_m=[0, 60]), "<= 15"),
                 (fam(near_water_m=[1, None]), ">= 4"),
                 (fam(category="dry_scrub", near_water_m=[2, None]), ">= 10"),
                 (fam(allow_in_sea=True), "allow_in_sea"),
                 (fam(category="rock", wind=0.5, near_water_m=[0, None]), "wind 0"),
                 (fam(category="nope"), "not one of"),
                 (fam(above_sea_m=[10, 5]), "low is above high"),
                 (fam(near_water_m=[-1, 5]), "under 0"),
                 (fam(max_slope=0), "max_slope"),
                 (fam(min_spacing_m=0), "min_spacing_m"),
                 (fam(scale_range=[0.8, 9]), "over 4"),
                 (fam(wind=2), "wind"),
                 (fam(scene="a.tscn"), "res://"),
                 (fam(bogus=1), "unknown key"),
                 (fam(category="aquatic", above_sea_m=[-3.0, None], near_water_m=[0, 30]), "at most 4 m"),
                 (fam(near_water_m=[None, 12]), "low must be a number")]
        for f, frag in cases:
            errs = C.family_errors("x", f)
            self.assertTrue(any(frag in e for e in errs), (frag, errs))

    def test_family_names_and_shapes(self):
        for bad in ("../x", "Pine", "a b", "", "1x", "x" * 40, "a:b"):
            self.assertTrue(C.family_errors(bad, fam()), bad)
        self.assertEqual(C.family_errors("pine_2", fam()), [])
        self.assertIn("must be an object", C.family_errors("x", [1])[0])

    def test_fingerprint_binds_category_scene_import_and_dependencies(self):
        d = tempfile.mkdtemp(); os.makedirs(d + "/a")
        for n in ("s.tscn", "t.png"): open(d + "/a/" + n, "w").write(n)
        f = fam(scene="res://a/s.tscn", verified_deps=["res://a/t.png"])
        base = C.fingerprint(d, f)
        self.assertEqual(base, C.fingerprint(d, dict(f)))
        self.assertNotEqual(base, C.fingerprint(d, dict(f, category="grass")))
        open(d + "/a/t.png", "w").write("changed"); self.assertNotEqual(base, C.fingerprint(d, f)); open(d + "/a/t.png", "w").write("t.png")
        open(d + "/a/s.tscn.import", "w").write("x"); self.assertNotEqual(base, C.fingerprint(d, f))
        os.remove(d + "/a/t.png"); self.assertNotEqual(base, C.fingerprint(d, f))

    def test_inspect_with_fake_engine_stamps_only_on_success_and_keeps_concurrent_edits(self):
        import types
        d = tempfile.mkdtemp(); os.makedirs(d + "/assets")
        open(d + "/assets/a.tscn", "w").write("x")
        C.save_catalog(d, {"schema": 1, "families": {"a": fam(scene="res://assets/a.tscn", verified=None, verified_sha=None), "b": fam(scene="res://assets/a.tscn")}})
        import gg_project, gg_style
        saved = (gg_project.load_profile, gg_style.check_applied)
        self.addCleanup(lambda: (setattr(gg_project, "load_profile", saved[0]), setattr(gg_style, "check_applied", saved[1])))
        gg_project.load_profile = lambda p: {"dimension": "3d"}
        gg_style.check_applied = lambda p, prof: {"renderer": "x", "lighting": {"sun_azimuth_deg": 0}, "render": {}, "capture_frames": 2}
        calls = []
        def fake(project, op, args, **kw):
            calls.append(op)
            cat = C.load_catalog(project); cat["families"]["b"]["max_slope"] = 0.9; C.save_catalog(project, cat)   # an edit made while the engine runs
            return types.SimpleNamespace(code=0, why="", result={"data": data(dependencies=[])})
        orig = C.render_check
        C.render_check = lambda *a, **k: (0, {"sun": {"coverage": .05, "luma_mean": .3, "black_fraction": 0, "white_fraction": 0, "png": "p"}, "shade": {"coverage": .05, "luma_mean": .3, "black_fraction": 0, "white_fraction": 0, "png": "p"}})
        try:
            code, rep = C.inspect(d, "a", run=fake)
            self.assertEqual(code, 0)
            cat = C.load_catalog(d)
            self.assertTrue(cat["families"]["a"]["verified"]); self.assertEqual(cat["families"]["a"]["verified_sha"], C.fingerprint(d, cat["families"]["a"]))
            self.assertEqual(cat["families"]["b"]["max_slope"], 0.9)      # the concurrent edit survived the stamp
            with self.assertRaises(gg_godot.Refused): C.inspect(d, "a", out="/tmp", run=fake)
            C.render_check = lambda *a, **k: (0, {"sun": {"coverage": .05, "luma_mean": .3, "black_fraction": .9, "white_fraction": 0, "png": "p"}, "shade": {"coverage": .05, "luma_mean": .3, "black_fraction": 0, "white_fraction": 0, "png": "p"}})
            code, rep = C.inspect(d, "a", run=fake)
            self.assertEqual(code, 1)
            self.assertIsNone(C.load_catalog(d)["families"]["a"]["verified"])      # a failed inspect un-verifies
        finally:
            C.render_check = orig

    def test_validate_catalog_shape(self):
        self.assertIn("no families", " ".join(C.validate({"schema": 1, "families": {}})))
        self.assertIn("schema", " ".join(C.validate({"families": {"a": fam()}})))
        self.assertEqual(C.validate({"schema": 1, "families": {"a": fam()}}), [])

    def test_flags_each_problem(self):
        def msgs(d, cat="tree_upland"):
            return [(x["level"], x["msg"]) for x in C.asset_flags(d, cat)]
        self.assertTrue(any("no mesh" in m for l, m in msgs({"meshes": 0})))
        self.assertTrue(any(l == "error" and "wrong scale" in m for l, m in msgs(data(h=0.08))))
        self.assertTrue(any(l == "warn" and "usual" in m for l, m in msgs(data(h=2.5))))
        self.assertTrue(any("lying down" in m for l, m in msgs(data(h=1.0, w=12.0))))
        self.assertTrue(any("would float or sink" in m for l, m in msgs(data(base=18.0))))
        black = [{"node": "M", "surface": 0, "kind": "StandardMaterial3D", "albedo": [0, 0, 0, 1], "albedo_texture": False, "emission": 0.0, "cull": "back"}]
        self.assertTrue(any("renders black" in m for l, m in msgs(data(mats=black))))
        self.assertFalse(any("black" in m for l, m in msgs(data(mats=[dict(black[0], albedo_texture=True)]))))  # a texture rescues a black albedo
        self.assertTrue(any("glows" in m for l, m in msgs(data(mats=[dict(black[0], albedo=[.3, .6, .2, 1], emission=3.0)]))))
        self.assertTrue(any("invisible" in m for l, m in msgs(data(mats=[dict(black[0], albedo=[.3, .6, .2, 0.0])]))))
        self.assertTrue(any("no material" in m for l, m in msgs(data(mats=[{"node": "M", "surface": 0, "kind": "none"}]))))
        self.assertTrue(any(l == "warn" and "white" in m for l, m in msgs(data(mats=[dict(black[0], albedo=[1, 1, 1, 1])]))))
        self.assertTrue(any("light" in m for l, m in msgs(data(lights=2))))
        self.assertTrue(any("heavy" in m for l, m in msgs(data(triangles=50000))))

    def test_single_sided_warning_is_one_line_and_skips_shader_materials(self):
        std = [{"node": "Blade%d" % i, "surface": 0, "kind": "StandardMaterial3D", "albedo": [.2, .5, .2, 1], "albedo_texture": False, "emission": 0.0, "cull": "back"} for i in range(5)]
        out = [x for x in C.asset_flags(data(h=0.5, w=0.5, mats=std), "grass") if "single-sided" in x["msg"]]
        self.assertEqual(len(out), 1)
        sh = [dict(m, kind="ShaderMaterial") for m in std]
        self.assertFalse([x for x in C.asset_flags(data(h=0.5, w=0.5, mats=sh), "grass") if "single-sided" in x["msg"]])

    def test_clean_asset_has_no_errors(self):
        self.assertFalse([x for x in C.asset_flags(data(), "tree_upland") if x["level"] == "error"])

    def test_views_look_at_lit_and_shaded_sides(self):
        style = {"lighting": {"sun_azimuth_deg": 135}}
        v = {x["name"]: x for x in C.view_set(None, style, data())}
        sun, shade = v["sun"]["position"], v["shade"]["position"]
        self.assertAlmostEqual(sun[0], -shade[0], 6); self.assertAlmostEqual(sun[2], -shade[2], 6)
        az = np.radians(135)
        self.assertGreater(sun[0] * np.sin(az) + sun[2] * np.cos(az), 0)  # sun camera is on the side the light comes from
        self.assertLessEqual(sun[1], 1.6)

    def test_render_flags(self):
        ok = {"sun": {"coverage": 0.05, "black_fraction": 0.0, "white_fraction": 0.0}, "shade": {"coverage": 0.05, "black_fraction": 0.1, "white_fraction": 0.0}}
        self.assertEqual(C.render_flags(ok), [])
        self.assertIn("not visible", C.render_flags({"sun": {"coverage": 0.0, "black_fraction": 0, "white_fraction": 0}, "shade": {"coverage": 0.001, "black_fraction": 0, "white_fraction": 0}})[0]["msg"])
        bad = copy.deepcopy(ok); bad["shade"]["black_fraction"] = 0.8
        self.assertIn("black in the shade", C.render_flags(bad)[0]["msg"])
        bad = copy.deepcopy(ok); bad["sun"]["white_fraction"] = 0.9
        self.assertIn("white in the sun", C.render_flags(bad)[0]["msg"])

    def test_sha_changes_with_file_and_missing_is_none(self):
        d = tempfile.mkdtemp(); os.makedirs(d + "/assets"); p = d + "/assets/a.tscn"
        open(p, "w").write("x"); a = C.sha_of(d, "res://assets/a.tscn"); open(p, "w").write("y")
        self.assertNotEqual(a, C.sha_of(d, "res://assets/a.tscn")); self.assertIsNone(C.sha_of(d, "res://assets/none.tscn"))

    def test_load_catalog_errors_and_atomic_save(self):
        d = tempfile.mkdtemp()
        with self.assertRaises(gg_godot.Refused) as c: C.load_catalog(d)
        self.assertIn("gg_catalog.py init", str(c.exception))
        open(C.catalog_path(d), "w").write("{bad")
        with self.assertRaises(gg_godot.Refused) as c: C.load_catalog(d)
        self.assertIn("not valid JSON", str(c.exception))
        C.save_catalog(d, {"schema": 1, "families": {"a": fam()}})
        self.assertEqual(C.load_catalog(d)["families"]["a"]["category"], "tree_upland")
        self.assertFalse(os.path.exists(C.catalog_path(d) + ".new"))


if __name__ == "__main__":
    unittest.main()
