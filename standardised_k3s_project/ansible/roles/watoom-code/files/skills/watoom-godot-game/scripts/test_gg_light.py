import copy, json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gg_godot, gg_light, gg_project, gg_style
import test_gg_terrain as tt


def metrics(p50, p95=0.8, p5=0.1, sat=0.3):
    return {"luma_p50": p50, "luma_p95": p95, "luma_p5": p5, "sat_mean": sat, "clip_black": 0.0, "clip_white": 0.0, "luma_std": 0.2}


class Fake:
    """Pretend renderer: p50 = k * exposure * sun_energy (so the hints really have an effect), optionally ignoring exposure."""
    def __init__(self, k=0.4, ignore=False):
        self.k, self.ignore, self.calls = k, ignore, 0
    def __call__(self, project, style, prof, out, run=None):
        self.calls += 1
        e = style["post"]["exposure"] if not self.ignore else 1.0
        p50 = min(1.0, self.k * e * style["lighting"]["sun_energy"] / 1.2)
        return 0, {"views": [{"name": "overview", "metrics": metrics(p50, p95=min(1.0, p50 + 0.2), p5=0.6 * p50 + 0.1, sat=0.2)}], "why": "ok"}


class T(unittest.TestCase):
    def setUp(self):
        self.d = tt.project(preset="realistic")
        os.makedirs(os.path.join(self.d, "gg_data"), exist_ok=True)
        prof = gg_project.load_profile(self.d)
        gg_style.write_resolved(self.d, prof)
        self.orig = gg_light.shoot_style

    def tearDown(self):
        gg_light.shoot_style = self.orig

    def test_parse_hint_takes_first_tunable_key(self):
        self.assertEqual(gg_light.parse_hint("too dark: raise post.exposure by 0.05 or lighting.sun_energy by 0.1, then"), (1, "post.exposure", 0.05))
        self.assertEqual(gg_light.parse_hint("lower lighting.sun_energy by 0.1"), (-1, "lighting.sun_energy", 0.1))
        self.assertEqual(gg_light.parse_hint("raise post.exposure by 0.05 or lighting.sun_energy by 0.1, then", dead={"post.exposure"}), (1, "lighting.sun_energy", 0.1))
        self.assertIsNone(gg_light.parse_hint("raise post.exposure by 0.05", dead={"post.exposure"}))
        self.assertIsNone(gg_light.parse_hint("raise material.roughness by 0.1"))
        self.assertIsNone(gg_light.parse_hint(None))

    def test_every_preset_hint_for_a_tunable_metric_parses(self):
        for n in gg_style.list_presets():
            h = gg_style.load_preset(n)["fix_hints"]
            for m in ("luma_p50", "luma_p95", "luma_p5"):
                for d in ("low", "high"):
                    self.assertIsNotNone(gg_light.parse_hint(h[m][d]), "%s %s %s: %s" % (n, m, d, h[m][d]))

    def test_level_targets_span_all_terrains(self):
        t = gg_light.level_targets([metrics(0.4), metrics(0.6)])
        self.assertAlmostEqual(t["luma_p50"][0], 0.4 - 0.08, 3); self.assertAlmostEqual(t["luma_p50"][1], 0.6 + 0.08, 3)
        self.assertEqual(t["clip_black"], [None, 0.02])

    def test_tune_recovers_dark_scene_and_does_not_write(self):
        prof = gg_project.load_profile(self.d)
        prof["style"]["overrides"] = {"post": {"exposure": 0.3}}
        json.dump(prof, open(os.path.join(self.d, "gg_project.json"), "w"))
        gg_style.write_resolved(self.d, prof)
        st = gg_style.resolve(prof); lo, hi = st["targets"]["luma_p50"]
        fake = Fake(k=0.4 * 1.2 / 1.2 * 1.0)
        gg_light.shoot_style = fake
        before = open(os.path.join(self.d, "gg_project.json")).read()
        code, rep = gg_light.tune(self.d, max_steps=8, write=False)
        self.assertEqual(code, 0, rep["why"])
        self.assertGreater(len(rep["steps"]), 0)
        self.assertEqual(before, open(os.path.join(self.d, "gg_project.json")).read())
        self.assertGreaterEqual(rep["final"]["luma_p50"], lo - 0.01); self.assertLessEqual(rep["final"]["luma_p50"], hi + 0.01)
        self.assertTrue(all("post.exposure" in s["change"] or "lighting" in s["change"] for s in rep["steps"]))

    def test_tune_flags_dead_value_reverts_it_and_uses_the_next_lever(self):
        prof = gg_project.load_profile(self.d)
        prof["style"]["overrides"] = {"lighting": {"sun_energy": 0.4}}
        json.dump(prof, open(os.path.join(self.d, "gg_project.json"), "w")); gg_style.write_resolved(self.d, prof)
        gg_light.shoot_style = Fake(ignore=True)  # exposure does nothing; sun_energy does
        code, rep = gg_light.tune(self.d, max_steps=8)
        self.assertTrue(any("not using it again" in s.get("warning", "") for s in rep["steps"]), rep)
        self.assertNotIn("exposure", json.dumps(rep["overrides"]))  # the dead change was undone
        self.assertEqual(code, 0, rep["why"])

    def test_already_good_scene_passes_with_zero_changes(self):
        st = gg_style.resolve(gg_project.load_profile(self.d)); lo, hi = st["targets"]["luma_p50"]
        gg_light.shoot_style = lambda *a, **k: (0, {"views": [{"name": "overview", "metrics": metrics((lo + hi) / 2, p95=(st["targets"]["luma_p95"][0] + st["targets"]["luma_p95"][1]) / 2,
                                                                p5=(st["targets"]["luma_p5"][0] + st["targets"]["luma_p5"][1]) / 2, sat=(st["targets"]["sat_mean"][0] + st["targets"]["sat_mean"][1]) / 2)}], "why": "ok"})
        code, rep = gg_light.tune(self.d)
        self.assertEqual((code, rep["steps"]), (0, []))

    def test_engine_failure_propagates_its_code(self):
        gg_light.shoot_style = lambda *a, **k: (3, {"views": [], "why": "fatal shader error"})
        code, rep = gg_light.tune(self.d)
        self.assertEqual(code, 3); self.assertIn("shader", rep["why"])

    def test_2d_refused_and_missing_level_refused(self):
        with self.assertRaises(gg_godot.Refused) as c: gg_light.refuse_2d({"dimension": "2d"})
        self.assertIn("3D only", str(c.exception))
        prof = gg_project.load_profile(self.d); st = gg_style.resolve(prof)
        with self.assertRaises(gg_godot.Refused) as c: gg_light.shoot_style(self.d, st, prof, self.d)
        self.assertIn("gg_terrain.py build", str(c.exception))

    def test_unverified_build_refused(self):
        os.makedirs(os.path.join(self.d, "levels", "main"), exist_ok=True); open(os.path.join(self.d, "levels/main/terrain.tscn"), "w").write("x")
        import gg_terrain
        gg_terrain.heights(self.d, "hills", 30.0, 1)
        prof = gg_project.load_profile(self.d); st = gg_style.resolve(prof)
        with self.assertRaises(gg_godot.Refused) as c: gg_light.shoot_style(self.d, st, prof, self.d)
        self.assertIn("build_ok", str(c.exception))

    def test_hard_failure_keeps_metrics_and_is_reported_by_view(self):
        import gg_verify
        os.makedirs(os.path.join(self.d, "levels", "main"), exist_ok=True); open(os.path.join(self.d, "levels/main/terrain.tscn"), "w").write("x")
        import gg_terrain
        gg_terrain.heights(self.d, "hills", 30.0, 1)
        json.dump({"heights_sha": json.load(open(os.path.join(self.d, "gg_data/world/world.json")))["heights_sha"]}, open(os.path.join(self.d, "gg_data/world/build_ok.json"), "w"))
        old = gg_verify.shot
        gg_verify.shot = lambda *a, **k: (1, {"views": [{"name": "overview", "metrics": metrics(0.01), "failures": [{"hint": "clip_black 0.9 > 0.5"}]}, {"name": "ground", "metrics": metrics(0.4), "failures": []}], "why": "x"})
        try:
            prof = gg_project.load_profile(self.d); st = gg_style.resolve(prof)
            code, rep = gg_light.shoot_style(self.d, st, prof, self.d)
        finally:
            gg_verify.shot = old
        self.assertEqual(code, 0); self.assertEqual(len(rep["views"]), 2); self.assertIn("overview", rep["hard"][0])

    def test_write_failure_is_not_success(self):
        prof = gg_project.load_profile(self.d); prof["style"]["overrides"] = {"post": {"exposure": 0.3}}
        json.dump(prof, open(os.path.join(self.d, "gg_project.json"), "w")); gg_style.write_resolved(self.d, prof)
        gg_light.shoot_style = Fake(k=0.4)
        old = gg_light.write_overrides; gg_light.write_overrides = lambda *a, **k: 3
        try:
            code, rep = gg_light.tune(self.d, max_steps=8, write=True)
        finally:
            gg_light.write_overrides = old
        self.assertEqual(code, 3); self.assertIn("apply failed", rep["why"])

    def test_non_lighting_failures_are_reported_as_unfixable(self):
        st = gg_style.resolve(gg_project.load_profile(self.d))
        m = metrics(0.4); m["sat_mean"] = 0.3
        gg_light.shoot_style = lambda *a, **k: (0, {"views": [{"name": "overview", "metrics": dict(m, luma_p50=0.4, luma_p95=0.8, luma_p5=0.1, sat_mean=0.01, flat_fraction=0.99, unique_colors=5, local_contrast=0.0)}], "why": "ok"})
        code, rep = gg_light.tune(self.d, max_steps=1)
        self.assertEqual(code, 1)

    def test_every_preset_has_level_targets_with_hints(self):
        for n in gg_style.list_presets():
            p = gg_style.load_preset(n)
            self.assertIn("luma_p50", p["targets"], n)


if __name__ == "__main__":
    unittest.main()
