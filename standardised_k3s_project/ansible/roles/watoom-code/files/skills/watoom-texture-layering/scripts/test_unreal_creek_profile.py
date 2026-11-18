import os, sys, unittest
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unreal_creek_profile as cp

Z0, RPC, PX = 3677.7, 4.4387, 800.0


def raw_of(cm):
    return np.round((np.asarray(cm, float) - Z0) * RPC).astype(np.uint16)


def zc(raw):
    return raw.astype(float) / RPC + Z0


class CreekProfile(unittest.TestCase):
    def setUp(self):
        n = 60
        self.z = np.full((n, n), 6000.0)  # flat ground
        self.raw = raw_of(self.z)
        # straight creek along x at row 30 (world y = 30 * PX), water level 5900 falling to 5800
        self.pts = [[x * PX, 30 * PX, 5900.0 - x * 2.0] for x in range(5, 56, 5)]
        self.samples = cp.hermite(self.pts)

    def test_hermite_passes_through_points_and_is_dense(self):
        self.assertAlmostEqual(self.samples[0][0], self.pts[0][0])
        self.assertAlmostEqual(self.samples[-1][2], self.pts[-1][2])
        gaps = np.hypot(*np.diff(self.samples[:, :2], axis=0).T)
        self.assertTrue(gaps.max() < 250)

    def test_middle_is_deepest_and_sides_are_shallower(self):
        new, s = cp.carve(self.raw, self.samples, Z0, RPC, PX, half_cm=2400.0, deep_cm=700.0)
        z = zc(new)
        col = z[:, 30]
        wz = 5900.0 - 30 * 2.0
        self.assertAlmostEqual(col[30], wz - 700.0, delta=3)  # centre: full depth below the water
        self.assertTrue(col[30] < col[31] < col[32] < col[33])  # shallower and shallower going out
        self.assertTrue(col[32] < wz)  # still under the water at 2 px (1600 cm of 2400)
        self.assertAlmostEqual(col[33], 6000.0, delta=1)  # 3 px = the edge: the original bank, not carved

    def test_ground_far_from_the_creek_is_untouched(self):
        new, s = cp.carve(self.raw, self.samples, Z0, RPC, PX, half_cm=2400.0, deep_cm=700.0)
        self.assertTrue((new[:20, :] == self.raw[:20, :]).all())
        self.assertTrue((new[40:, :] == self.raw[40:, :]).all())

    def test_low_ground_beside_the_channel_gets_a_rim_above_the_water(self):
        z = self.z.copy()
        z[26:35, :] = 5850.0  # a low flat plain: below the water level 5840 + nothing
        raw = raw_of(z)
        new, s = cp.carve(raw, self.samples, Z0, RPC, PX, half_cm=2400.0, deep_cm=700.0, berm_cm=40.0, berm_px=2.0)
        zn = zc(new)
        wz = 5900.0 - 30 * 2.0
        self.assertTrue(zn[34, 30] >= wz + 20)  # rim just outside the channel is above the water

    def test_channel_never_raises_ground_that_is_already_deeper(self):
        z = self.z.copy()
        z[30, 25] = 5000.0  # an existing deep hole in the channel
        raw = raw_of(z)
        new, s = cp.carve(raw, self.samples, Z0, RPC, PX, half_cm=2400.0, deep_cm=700.0)
        self.assertTrue(new[30, 25] <= raw[30, 25])

    def test_calls_cover_changed_tiles_only(self):
        new, s = cp.carve(self.raw, self.samples, Z0, RPC, PX, half_cm=2400.0, deep_cm=700.0)
        ph = cp.calls_for(self.raw, new)[0]
        self.assertEqual(ph["name"], "heights")
        self.assertEqual(len(ph["calls"]), 1)  # the whole creek sits inside the first 127 px tile
        self.assertEqual(ph["calls"][0][0], "landscape.set_height_region")


class Junction(unittest.TestCase):
    def test_second_creek_rim_does_not_block_first_creek_channel_and_no_rim_at_sea(self):
        n = 60
        z = np.full((n, n), 6000.0)
        raw = raw_of(z)
        a = [[x * PX, 30 * PX, 5900.0] for x in range(5, 40, 5)]            # creek A along row 30
        b = [[30 * PX, y * PX, 5900.0] for y in range(5, 31, 5)]            # creek B comes down column 30 and ends on A
        new = raw
        for pts in (a, b):
            new, _ = cp.carve(new, cp.hermite(pts), Z0, RPC, PX, 2400.0, 700.0)
        for pts in (a, b):
            new, _ = cp.carve(new, cp.hermite(pts), Z0, RPC, PX, 2400.0, 700.0, rim=False)
        zz = zc(new)
        self.assertTrue(zz[30, 29] < 5900.0)  # junction channel is below the water
        sea = [[x * PX, 30 * PX, 4849.5] for x in range(5, 40, 5)]
        low = raw_of(np.full((n, n), 4800.0))
        out, _ = cp.carve(low, cp.hermite(sea), Z0, RPC, PX, 2400.0, 200.0, berm_min_z=4854.0)
        self.assertTrue(zc(out).max() < 4849.0)  # sea floor not lifted above the sea


class Lake(unittest.TestCase):
    def test_lake_bowl_is_deepest_in_the_middle_with_a_rim_and_the_cli_runs(self):
        import json, tempfile
        from PIL import Image
        n = 60
        z = np.full((n, n), 6000.0)
        z[:, 40:] = 6600.0  # higher ground on the right
        raw = raw_of(z)
        d = tempfile.mkdtemp()
        Image.fromarray(raw).save(os.path.join(d, "h.png"))
        size_m = (n - 1) * PX / 100.0
        rc = cp.main(["--landscape", "Landscape", "--heights", os.path.join(d, "h.png"), "--lake", "%f,%f,5900,24,1000" % (25 * PX, 25 * PX), "--z0", str(Z0), "--raw-per-cm", str(RPC),
                      "--size-m", str(size_m), "--out", os.path.join(d, "c.json"), "--out-heights", os.path.join(d, "o.png")])
        self.assertEqual(rc, 0)
        new = np.asarray(Image.open(os.path.join(d, "o.png")))
        zc2 = zc(new)
        self.assertAlmostEqual(zc2[25, 25], 4900.0, delta=3)  # 1000 cm under the 5900 surface at the centre
        self.assertTrue(zc2[25, 25] < zc2[25, 27] < zc2[25, 29])  # shallower towards the shore
        self.assertTrue(zc2[25, 25 - 3] > 5880)  # the shore ring holds the water in (rim above the surface)
        self.assertTrue((new[:, 50:] == raw[:, 50:]).all())  # far ground untouched
        self.assertTrue(len(json.load(open(os.path.join(d, "c.json")))["phases"][0]["calls"]) >= 1)


    def test_creek_starting_inside_a_lake_leaves_no_ring_in_the_water_and_the_outlet_stays_open(self):
        import json, tempfile
        from PIL import Image
        n = 80
        z = np.full((n, n), 6000.0)
        raw = raw_of(z)
        d = tempfile.mkdtemp()
        Image.fromarray(raw).save(os.path.join(d, "h.png"))
        # lake centre (30,40) radius 10 px at surface 5900; the creek starts at the centre and runs east, water 5900 falling to 5700
        pts = [[(30 + 4 * k) * PX, 40 * PX, 5900.0 - 20 * k] for k in range(0, 12)]
        json.dump(pts, open(os.path.join(d, "p.json"), "w"))
        rc = cp.main(["--landscape", "Landscape", "--heights", os.path.join(d, "h.png"), "--lake", "%f,%f,5900,%f,800" % (30 * PX, 40 * PX, 10 * PX / 100.0), "--spline", os.path.join(d, "p.json"),
                      "--half-width-m", str(2.5 * PX / 100.0), "--deep-cm", "400", "--z0", str(Z0), "--raw-per-cm", str(RPC), "--size-m", str((n - 1) * PX / 100.0),
                      "--out", os.path.join(d, "c.json"), "--out-heights", os.path.join(d, "o.png")])
        self.assertEqual(rc, 0)
        zn = zc(np.asarray(Image.open(os.path.join(d, "o.png"))))
        inside = zn[34:47, 25:36]  # inside 85% of the lake radius (7.8 px of 8.5)
        self.assertTrue(inside.max() < 5900.0)  # nothing stands above the lake surface inside it
        self.assertTrue(zn[40, 44] < 5900.0)  # the outlet channel east of the lake is below its water, not blocked by the lake's rim


if __name__ == "__main__":
    unittest.main()
