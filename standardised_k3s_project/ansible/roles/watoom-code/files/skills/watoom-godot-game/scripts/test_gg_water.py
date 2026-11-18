import json, os, sys, tempfile, unittest
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gg_godot, gg_project, gg_terrain, gg_water, gg_style
import test_gg_terrain as tt


def level(shape="island", size=(256.0, 256.0), cell=4.0, relief=40.0, seed=2, sea=0.0, preset="low-poly"):
    d = tt.project(size, cell, (-20.0, 60.0), sea, preset)
    gg_style.write_resolved(d, gg_project.load_profile(d))
    gg_terrain.heights(d, shape, relief, seed)
    return d


class T(unittest.TestCase):
    def test_edt_exact_against_brute_force(self):
        m = np.zeros((23, 31), bool); m[5, 7] = m[18, 25] = m[0, 30] = True
        j, i = np.mgrid[0:23, 0:31]
        ref = np.minimum.reduce([np.hypot(j - a, i - b) for a, b in ((5, 7), (18, 25), (0, 30))]) * 3.0
        self.assertLess(float(np.abs(gg_water.edt(m, 3.0) - ref).max()), 1e-9)
        self.assertTrue(np.isinf(gg_water.edt(np.zeros((4, 4), bool), 1.0)).all())

    def test_creek_bed_never_rises_and_banks_hold(self):
        d = level()
        code, info, w = gg_water.creek(d, auto=True, width=8.0, depth=1.5)
        self.assertEqual(code, 0, (info, w))
        c = json.load(open(os.path.join(d, "gg_data/world/creeks.json")))["creeks"][0]
        bed = np.array(c["bed"])
        self.assertTrue((np.diff(bed) <= 1e-9).all())
        self.assertEqual(info["bank_clearance"], 1.0)
        self.assertLess(info["max_water_depth_m"], 2.5)
        self.assertLess(c["points"][-1][1], 3.0)  # ends at the sea

    def test_creek_invalidates_layers_and_build_marker(self):
        d = level(); gg_terrain.layers(d)
        open(os.path.join(d, "gg_data/world/build_ok.json"), "w").write("{}")
        gg_water.creek(d, auto=True, width=8.0)
        self.assertFalse(os.path.exists(os.path.join(d, "gg_data/world/layers")))
        self.assertFalse(os.path.exists(os.path.join(d, "gg_data/world/build_ok.json")))

    def test_dry_run_writes_nothing(self):
        d = level(); before = open(os.path.join(d, "gg_data/world/heights.f32"), "rb").read()
        gg_water.creek(d, auto=True, width=8.0, dry_run=True)
        self.assertEqual(before, open(os.path.join(d, "gg_data/world/heights.f32"), "rb").read())
        self.assertFalse(os.path.exists(os.path.join(d, "gg_data/world/creeks.json")))

    def test_refusals(self):
        d = level()
        for kw, frag in (({"auto": False, "waypoints": None}, "exactly one"), ({"auto": True, "waypoints": "1,1 2,2"}, "exactly one"),
                         ({"waypoints": "abc"}, "x,z"), ({"waypoints": "500,10 20,20"}, "outside"), ({"waypoints": "128,128"}, "two waypoints"),
                         ({"waypoints": "128,128 130,130"}, "on land"), ({"auto": True, "width": 3.0}, "two cells"), ({"auto": True, "width": 100.0}, "1..40")):
            with self.assertRaises(gg_godot.Refused) as c: gg_water.creek(d, **{"width": 8.0, **kw})
            self.assertIn(frag, str(c.exception), kw)

    def test_second_creek_refused_and_heights_reset_removes_creek(self):
        d = level(); gg_water.creek(d, auto=True, width=8.0)
        with self.assertRaises(gg_godot.Refused): gg_water.creek(d, auto=True, width=8.0)
        gg_terrain.heights(d, "island", 40.0, 2)
        self.assertFalse(os.path.exists(os.path.join(d, "gg_data/world/creeks.json")))

    def test_no_sea_refused_for_auto(self):
        d = level("hills", relief=30.0, sea=-10.0)  # everything is land
        with self.assertRaises(gg_godot.Refused) as c: gg_water.creek(d, auto=True, width=8.0)
        self.assertIn("land and sea", str(c.exception))

    def test_analyse_outputs_and_distance_map(self):
        d = level(); gg_water.creek(d, auto=True, width=8.0)
        code, info, warns = gg_water.analyse(d)
        self.assertEqual(code, 0)
        w = gg_terrain.world_dir(d)
        dist = np.fromfile(os.path.join(w, "water_dist.f32"), "<f4").reshape(65, 65)
        h = np.fromfile(os.path.join(w, "heights.f32"), "<f4").reshape(65, 65)
        self.assertTrue((dist[h < 0] == 0).all())
        self.assertGreater(float(dist.max()), 20.0)
        self.assertEqual(info["creek_registered"], 1.0)
        self.assertGreater(info["water_fraction"], 0.3)

    def test_tampered_creek_is_rejected_by_registration(self):
        d = level(); gg_water.creek(d, auto=True, width=8.0)
        p = os.path.join(gg_terrain.world_dir(d), "creeks.json"); c = json.load(open(p))
        for pt in c["creeks"][0]["points"]: pt[0] += 12.0
        json.dump(c, open(p, "w"))
        code, info, warns = gg_water.analyse(d)
        self.assertEqual(code, 1); self.assertTrue(any("carved trench" in x for x in warns))

    def test_creek_file_from_older_heights_refused(self):
        d = level(); gg_water.creek(d, auto=True, width=8.0)
        p = os.path.join(gg_terrain.world_dir(d), "creeks.json"); c = json.load(open(p)); c["heights_sha"] = "0" * 64; json.dump(c, open(p, "w"))
        with self.assertRaises(gg_godot.Refused) as e: gg_water.analyse(d)
        self.assertIn("older heights", str(e.exception))

    def test_no_water_warns(self):
        d = level("hills", relief=30.0, sea=-10.0)
        code, info, warns = gg_water.analyse(d)
        self.assertTrue(any("no sea" in x for x in warns))

    def test_build_needs_verified_terrain(self):
        d = level()
        with self.assertRaises(gg_godot.Refused) as c: gg_water.build(d)
        self.assertIn("gg_terrain.py layers and build", str(c.exception))

    def test_bank_clearance_detects_spill(self):
        d = level(); h, wd = gg_water.load_heights(d)
        # a fake creek along a cross-slope with no berm: banks lower than the water on one side
        pts = [[100.0 + k * 4, 15.0, 130.0] for k in range(10)]
        cr = {"points": pts, "width_m": 8.0, "depth_m": 1.5}
        flat = np.zeros_like(h); flat[:, :] = 0.0; flat[:, :] += np.linspace(0, 20, h.shape[0])[:, None]  # slopes up along +z
        self.assertLess(gg_water.bank_clearance(flat, wd, cr), 0.9)

    def test_shore_band_selects_boundary(self):
        e = np.zeros((20, 20), int); e[:, 10:] = 1
        b = gg_water.shore_band(e, 2)
        self.assertTrue(b[:, 8:12].all()); self.assertFalse(b[:, :7].any())


if __name__ == "__main__":
    unittest.main()
