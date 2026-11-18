import os, sys, unittest
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_foliage_census as fc

Z0, RPC, PX, SEA = 3677.7, 4.4387, 800.0, 4849.26


def heights(z_cm, n=20):
    return np.full((n, n), np.round((z_cm - Z0) * RPC), np.uint16)


class Census(unittest.TestCase):
    def test_variants_group_into_one_family(self):
        self.assertEqual(fc.family("FT_SM_Tree_03.FT_SM_Tree_03"), "SM_Tree")
        self.assertEqual(fc.family("FT_SM_GrassPatch_Var02"), "SM_GrassPatch")
        self.assertEqual(fc.family("FT_banana_01_04"), "banana")
        self.assertEqual(fc.family("FT_SM_MT_PM_V60_Cyperus_eragrostis_01_06"), "SM_MT_PM_V60_Cyperus_eragrostis")

    def test_summary_reports_height_above_sea_and_in_sea_count(self):
        raw = heights(SEA + 300.0)   # ground 3 m above the sea
        out = fc.summarise({"A": {"types": 2, "points": [(4000, 4000, 0), (8000, 8000, 0)]}}, raw, Z0, RPC, PX, SEA)
        self.assertEqual(out["A"]["instances"], 2)
        self.assertAlmostEqual(out["A"]["above_sea_m"]["p50"], 3.0, delta=0.05)
        self.assertEqual(out["A"]["in_sea"], 0)
        low = fc.summarise({"A": {"types": 1, "points": [(4000, 4000, 0)]}}, heights(SEA - 100.0), Z0, RPC, PX, SEA)
        self.assertEqual(low["A"]["in_sea"], 1)

    def test_slope_of_a_ramp(self):
        raw = np.tile(np.round((np.arange(20) * PX * 0.25 + 3000.0 - Z0) * RPC), (20, 1)).astype(np.uint16)  # rises 0.25 per px along x
        self.assertAlmostEqual(fc.slope(raw, RPC, PX, 5 * PX, 5 * PX), 0.25, delta=0.01)

    def test_audit_flags_unclassified_and_contradicting_families(self):
        census = {"Tree": {"instances": 10, "in_sea": 0, "above_sea_m": {"p5": 1.0, "p50": 5.0, "p95": 40.0}, "slope_p95": 0.1},
                  "Reed": {"instances": 5, "in_sea": 3, "above_sea_m": {"p5": -0.4, "p50": 0.2, "p95": 0.5}, "slope_p95": 0.05},
                  "New": {"instances": 1, "in_sea": 0, "above_sea_m": {"p5": 1.0, "p50": 1.0, "p95": 1.0}, "slope_p95": 0.0}}
        catalog = {"Tree": {"above_sea_m": [0.5, 30.0]}, "Reed": {"above_sea_m": [-0.5, 2.0], "allow_in_sea": True}}
        missing, wrong = fc.audit(census, catalog)
        self.assertEqual(missing, ["New"])
        self.assertEqual([w[0] for w in wrong], ["Tree"])   # 40 m is above its limit; the reed may stand in the sea

    def test_water_distance_counts_sea_and_mask_pixels(self):
        raw = heights(SEA + 500.0, 12)
        mask = np.zeros((12, 12), np.uint8)
        mask[5, 5] = 1
        d = fc.water_distance(raw, Z0, RPC, SEA, mask)
        self.assertEqual(d[5, 5], 0)
        self.assertAlmostEqual(d[5, 8], 3.0, delta=0.01)       # three pixels straight
        self.assertAlmostEqual(d[8, 8], 4.0, delta=0.01)       # chamfer approximation of 4.24
        sea = fc.water_distance(heights(SEA - 50.0, 6), Z0, RPC, SEA)
        self.assertEqual(float(sea.max()), 0.0)                # everything is sea
        self.assertTrue(np.isinf(fc.water_distance(raw, Z0, RPC, SEA)).all())  # no water anywhere
        with self.assertRaises(ValueError):
            fc.water_distance(raw, Z0, RPC, SEA, np.zeros((5, 5), np.uint8))

    def test_summary_and_audit_use_distance_to_water(self):
        raw = heights(SEA + 500.0, 12)
        dist = fc.water_distance(raw, Z0, RPC, SEA, np.pad(np.ones((1, 1), np.uint8), ((5, 6), (5, 6))))
        out = fc.summarise({"Marsh": {"types": 1, "points": [(5 * PX, 9 * PX, 0)]}}, raw, Z0, RPC, PX, SEA, dist)
        self.assertAlmostEqual(out["Marsh"]["near_water_m"]["p50"], 4 * PX / 100.0, delta=1.0)   # four pixels, about 32 m
        missing, wrong = fc.audit(out, {"Marsh": {"near_water_m": [0, 20]}})
        self.assertEqual([w[0] for w in wrong], ["Marsh"])


class ExampleCatalog(unittest.TestCase):
    """templates/asset_catalog.example.json: water-bound families are held to the water by distance, not by height above the sea."""

    def setUp(self):
        import json
        path = os.path.join(fc.SKILL, "..", "templates", "asset_catalog.example.json")
        self.families = json.load(open(path))["families"]

    def test_water_bound_families_have_a_water_distance_limit_and_no_height_ceiling(self):
        wet = {k: v for k, v in self.families.items() if v["category"] in ("wet_margin", "aquatic", "tree_riparian")}
        self.assertIn("SM_Plant", wet)
        self.assertIn("SM_MT_PM_V60_Cyperus_eragrostis", wet)
        for name, c in wet.items():
            self.assertIsNotNone(c["near_water_m"][1], name)
            self.assertIsNone(c["above_sea_m"][1], name)

    def test_the_measured_census_is_flagged_for_distance_to_water_not_for_height(self):
        # census 2026-11-16: Cyperus median 36 m above the sea and about 30 m from water; a bank plant 23 m up beside a lake is fine
        stats = lambda p50_above, p50_near: {"instances": 100, "in_sea": 0, "slope_p95": 0.1,
                                             "above_sea_m": {"p5": p50_above - 5, "p50": p50_above, "p95": p50_above + 5},
                                             "near_water_m": {"p5": 0.0, "p50": p50_near, "p95": p50_near + 10}}
        _, wrong = fc.audit({"SM_MT_PM_V60_Cyperus_eragrostis": stats(36.0, 30.0), "SM_Plant": stats(23.0, 8.0)}, self.families)
        self.assertEqual([f for f, _ in wrong], ["SM_MT_PM_V60_Cyperus_eragrostis"])
        self.assertIn("distance to water", wrong[0][1])


if __name__ == "__main__":
    unittest.main()
