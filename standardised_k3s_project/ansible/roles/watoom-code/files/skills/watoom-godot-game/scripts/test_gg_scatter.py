import json, os, sys, tempfile, unittest
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gg_catalog as C, gg_census, gg_godot, gg_scatter as S


class W:
    """A small fake World: a slope rising along +x, sea at 0, a water strip at x < 20 m."""
    def __init__(self, n=65, cell=4.0, sea=0.0):
        self.cell, self.sea = cell, sea
        x = np.arange(n) * cell
        self.h = np.tile(-2.0 + x * 0.1, (n, 1))               # -2 .. 10.6 m, slope 0.1
        self.dist = np.maximum(0.0, np.tile(x - 20.0, (n, 1)))   # water where x <= 20
        gy, gx = np.gradient(self.h, cell)
        self.slope = np.hypot(gx, gy)
        self._l = None
        self.wd = {"size_m": [(n - 1) * cell] * 2}

    def layer_weights(self):
        n = self.h.shape[1]
        a = np.zeros(self.h.shape); a[:, n // 2:] = 1.0
        return {"low": 1 - a, "high": a}


def fam(**kw):
    f = {"category": "shrub", "scene": "res://a.tscn", "above_sea_m": [0.5, 20.0], "max_slope": 0.5, "near_water_m": [3, None], "min_spacing_m": 2.0, "scale_range": [0.8, 1.2], "wind": 0.0}
    f.update(kw)
    return f


class T(unittest.TestCase):
    def test_ground_y_matches_the_mesh_triangles(self):
        h = np.array([[0.0, 10.0], [20.0, 0.0]])  # a(0,0)=0 b(1,0)=10 c(0,1)=20 d(1,1)=0 ; mesh diagonal is b-c
        self.assertAlmostEqual(S.ground_y(h, 0.0, 0.0, 1.0), 0.0, 3)
        self.assertAlmostEqual(S.ground_y(h, 0.999999, 0.0, 1.0), 10.0, 3)
        self.assertAlmostEqual(S.ground_y(h, 0.0, 0.999999, 1.0), 20.0, 3)
        self.assertAlmostEqual(S.ground_y(h, 0.5, 0.5, 1.0), 15.0, 3)   # on the diagonal: mean of b and c (bilinear would say 7.5)
        self.assertAlmostEqual(S.ground_y(h, 0.25, 0.25, 1.0), 0.0 + 0.25 * 10 + 0.25 * 20, 3)

    def test_cell_mask_applies_every_rule_and_counts(self):
        w = W()
        m, why = S.cell_mask(w, fam(), {})
        ys, xs = np.nonzero(m)
        x = xs * w.cell
        self.assertTrue((w.h[m] - w.sea >= 0.5).all()); self.assertTrue((w.dist[m] >= 3).all()); self.assertTrue((w.h[m] > 0).all())
        self.assertGreater(why["above_sea_m"], 0)
        _, why_w = S.cell_mask(w, fam(near_water_m=[30, None]), {})
        self.assertGreater(why_w["near_water_m"], 0)  # the height rule runs first and already removed the cells nearest the water above
        m2, why2 = S.cell_mask(w, fam(max_slope=0.05), {})
        self.assertFalse(m2.any()); self.assertGreater(why2["max_slope"], 0)
        m3, _ = S.cell_mask(w, fam(above_sea_m=[-5.0, 20.0], allow_in_sea=True, near_water_m=[0, None]), {})
        self.assertTrue(m3[:, 0].all())  # in the sea allowed
        m4, _ = S.cell_mask(w, fam(), {"on_layers": ["high"], "min_weight": 0.5})
        self.assertFalse(m4[:, :32].any())
        m5, _ = S.cell_mask(w, fam(), {}, exclude=np.ones(w.h.shape, bool))
        self.assertFalse(m5.any())

    def test_place_respects_rules_spacing_and_seed(self):
        w = W(); f = fam(min_spacing_m=3.0)
        inst, why, cells = S.place(w, f, {}, 60, np.random.default_rng(1))
        self.assertGreater(len(inst), 30)
        for x, y, z, yaw, s in inst:
            self.assertGreaterEqual(S.bilinear(w.dist, x, z, w.cell), 3 - 1e-6)
            self.assertGreater(y, 0.5 - 1e-6 + w.sea)
            self.assertTrue(0.8 <= s <= 1.2)
            self.assertAlmostEqual(y, S.ground_y(w.h, x, z, w.cell), 2)
        pts = np.array([[i[0], i[2]] for i in inst])
        d = np.hypot(pts[:, None, 0] - pts[None, :, 0], pts[:, None, 1] - pts[None, :, 1]) + np.eye(len(pts)) * 99
        self.assertGreaterEqual(float(d.min()), 3.0 - 1e-6)
        again, _, _ = S.place(w, f, {}, 60, np.random.default_rng(1))
        self.assertEqual(inst, again)
        other, _, _ = S.place(w, f, {}, 60, np.random.default_rng(2))
        self.assertNotEqual(inst, other)

    def test_place_nothing_when_habitat_empty_and_never_in_sea(self):
        w = W()
        inst, why, cells = S.place(w, fam(above_sea_m=[500.0, 600.0]), {}, 10, np.random.default_rng(1))
        self.assertEqual((inst, cells), ([], 0))
        inst, _, _ = S.place(w, fam(above_sea_m=[-5.0, 30.0], near_water_m=[0, None]), {}, 200, np.random.default_rng(1))
        self.assertTrue(all(S.ground_y(w.h, x, z, w.cell) > w.sea for x, y, z, _, _ in inst))

    def test_wet_family_stays_within_its_distance_band(self):
        w = W(); f = fam(category="wet_margin", above_sea_m=[-3.0, None], near_water_m=[0, 12], allow_in_sea=False, max_slope=0.5)
        inst, _, _ = S.place(w, f, {}, 100, np.random.default_rng(1))
        self.assertGreater(len(inst), 5)
        self.assertTrue(all(S.bilinear(w.dist, x, z, w.cell) <= 12 + 1e-6 for x, y, z, _, _ in inst))

    def test_check_plan_refusals(self):
        d = tempfile.mkdtemp(); os.makedirs(d + "/assets"); open(d + "/assets/a.tscn", "w").write("x")
        ok = fam(scene="res://assets/a.tscn", verified="2026-11-17")
        ok["verified_sha"] = C.fingerprint(d, ok)
        cat = {"families": {"ok": ok, "unver": dict(ok, verified=None), "stale": dict(ok, verified_sha="0" * 64), "prop": dict(ok, category="prop", near_water_m=[0, None])}}
        w = W()
        def errs(entries): return " | ".join(S.check_plan(d, {"entries": entries}, cat, w))
        self.assertEqual(errs([{"family": "ok", "count": 5}]), "")
        self.assertIn("not in the catalog", errs([{"family": "zzz", "count": 5}]))
        self.assertIn("UNVERIFIED", errs([{"family": "unver", "count": 5}]))
        self.assertIn("changed", errs([{"family": "stale", "count": 5}]))
        cat["families"]["recat"] = dict(ok, category="grass")      # category edited after verification
        self.assertIn("changed", errs([{"family": "recat", "count": 5}]))
        open(d + "/assets/a.tscn.import", "w").write("scale 100")   # import settings changed after verification
        self.assertIn("changed", errs([{"family": "ok", "count": 5}]))
        self.assertIn("prop", errs([{"family": "prop", "count": 5}]))
        self.assertIn("count must be", errs([{"family": "ok", "count": 0}]))
        self.assertIn("count must be", errs([{"family": "ok", "count": 10 ** 7}]))
        self.assertIn("not a terrain layer", errs([{"family": "ok", "count": 5, "on_layers": ["bogus"]}]))

    def test_exclude_mask_size_mismatch_names_both(self):
        from PIL import Image
        d = tempfile.mkdtemp(); p = d + "/m.png"; Image.fromarray(np.zeros((10, 12), np.uint8)).save(p)
        with self.assertRaises(gg_godot.Refused) as c: S.load_exclude(d, p, W())
        self.assertIn("12x10", str(c.exception)); self.assertIn("65x65", str(c.exception))

    def test_load_plan_errors(self):
        d = tempfile.mkdtemp()
        with self.assertRaises(gg_godot.Refused) as c: S.load_plan(d)
        self.assertIn("scatter.py plan" if False else "gg_scatter.py plan", str(c.exception))
        open(S.plan_path(d), "w").write(json.dumps({"schema": 1, "entries": []}))
        with self.assertRaises(gg_godot.Refused): S.load_plan(d)

    def test_audit_clean_for_placed_and_flags_misplaced(self):
        w = W(); f = fam(category="wet_margin", above_sea_m=[-3.0, None], near_water_m=[0, 12], max_slope=0.5)
        inst, _, _ = S.place(w, f, {}, 80, np.random.default_rng(3))
        pos = [[x, y, z] for x, y, z, _, _ in inst]
        st = gg_census.analyse_family(w, f, pos, S.ground_y, S.bilinear)
        self.assertEqual(st["bad_rules"], []); self.assertFalse(st["off_ground_bad"])
        far = [[200.0, S.ground_y(w.h, 200.0, 100.0, 4.0), 100.0]] * 20   # 180 m from the water
        st = gg_census.analyse_family(w, f, far, S.ground_y, S.bilinear)
        self.assertIn("too_far_from_water", st["bad_rules"])
        sea = [[4.0, 3.0, 100.0]] * 10                                    # in the sea AND 3 m up from the ground
        st = gg_census.analyse_family(w, fam(), sea, S.ground_y, S.bilinear)
        self.assertIn("in_sea", st["bad_rules"]); self.assertTrue(st["off_ground_bad"])
        float_ = [[100.0, S.ground_y(w.h, 100.0, 100.0, 4.0) + 5.0, 100.0]] * 10
        self.assertTrue(gg_census.analyse_family(w, fam(), float_, S.ground_y, S.bilinear)["off_ground_bad"])

    def test_one_instance_in_the_sea_is_never_tolerated(self):
        w = W(); f = fam()
        inst, _, _ = S.place(w, f, {}, 200, np.random.default_rng(4))
        pos = [[x, y, z] for x, y, z, _, _ in inst]
        pos[0] = [4.0, S.ground_y(w.h, 4.0, 100.0, 4.0), 100.0]
        self.assertIn("in_sea", gg_census.analyse_family(w, f, pos, S.ground_y, S.bilinear)["bad_rules"])

    def test_many_small_shares_add_up(self):
        w = W(); f = fam(near_water_m=[3, None], max_slope=0.5)
        inst, _, _ = S.place(w, f, {}, 200, np.random.default_rng(5))
        pos = [[x, y, z] for x, y, z, _, _ in inst]
        # 2.5% of the instances stand 2.8 m from the water (limit 3 m)
        near = [22.8, 0, 100.0]; near[1] = S.ground_y(w.h, near[0], near[2], 4.0)
        for i in range(5):
            pos[i] = list(near)
        self.assertEqual(S.bilinear(w.dist, near[0], near[2], 4.0) < 3, True)
        st = gg_census.analyse_family(w, f, pos, S.ground_y, S.bilinear)
        self.assertIn("too_close_to_water", st["bad_rules"])

    def test_standing_in_a_creek_is_refused_for_dry_families_in_placement_and_audit(self):
        w = W(); w.h[:, 20:24] = 5.0; w.dist[:, 20:24] = 0.0         # a creek channel high above the sea
        f = fam(near_water_m=[0, None], above_sea_m=[0.5, 20.0])
        self.assertTrue(C.stands_on_dry_land(f))
        m, why = S.cell_mask(w, f, {})
        self.assertFalse(m[:, 20:24].any()); self.assertGreater(why["not_in_water"], 0)
        st = gg_census.analyse_family(w, f, [[84.0, 5.0, 100.0]] * 3, S.ground_y, S.bilinear)
        self.assertIn("in_water", st["bad_rules"])
        reed = fam(category="wet_margin", above_sea_m=[-3.0, None], near_water_m=[0, 12])
        self.assertFalse(C.stands_on_dry_land(reed))
        self.assertNotIn("in_water", gg_census.analyse_family(w, reed, [[84.0, 5.0, 100.0]] * 3, S.ground_y, S.bilinear)["bad_rules"])

    def test_stamp_valid_only_while_every_input_is_unchanged(self):
        d = tempfile.mkdtemp(); wd = os.path.join(d, "gg_data", "world"); os.makedirs(wd); os.makedirs(d + "/levels/main"); os.makedirs(wd + "/layers")
        open(d + "/levels/main/scatter.tscn", "w").write("s"); open(d + "/gg_catalog.json", "w").write("c"); open(wd + "/water_dist.f32", "w").write("w"); open(wd + "/layers/layer_report.json", "w").write("l")
        S.atomic_json(wd + "/scatter_ok.json", {"heights_sha": "H", "hashes": S.stamp_hashes(d, "main")})
        self.assertTrue(S.stamp_valid(d, "main", "H"))
        self.assertFalse(S.stamp_valid(d, "main", "other"))
        for rel, new in (("/levels/main/scatter.tscn", "edited"), ("/gg_catalog.json", "tightened"), ("/gg_data/world/water_dist.f32", "again"), ("/gg_data/world/layers/layer_report.json", "relayered")):
            old = open(d + rel).read(); open(d + rel, "w").write(new)
            self.assertFalse(S.stamp_valid(d, "main", "H"), rel)
            open(d + rel, "w").write(old)
        self.assertTrue(S.stamp_valid(d, "main", "H"))

    def test_terrain_mesh_diagonal_matches_ground_y(self):
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "runtime", "ops", "build_terrain.gd")).read()
        self.assertIn("idx.append_array([a, b, c, b, d, c])", src)   # ground_y interpolates exactly these two triangles


if __name__ == "__main__":
    unittest.main()
