import os, sys, unittest
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unreal_ocean_depth as od

Z0, RPC, SEA = 3677.7, 4.4387, 4849.0


def raw_of(cm):
    return np.round((np.asarray(cm, float) - Z0) * RPC).astype(np.uint16)


def zc(raw):
    return raw.astype(float) / RPC + Z0


class OceanDepth(unittest.TestCase):
    def setUp(self):
        n = 60
        z = np.full((n, n), SEA + 4.0)  # flat sea plateau just above sea level
        z[:, 40:] = SEA + 900.0  # land on the right
        z[5:9, 5:9] = SEA - 200.0  # a lake-like bowl inside the sea is still sea (edge connected via the plateau)
        z[30:34, 44:48] = SEA - 300.0  # inland bowl, not connected to the sea
        self.n, self.z = n, z
        self.raw = raw_of(z)

    def test_floor_ramps_down_with_distance_and_land_is_untouched(self):
        new, sea, deep = od.deepen(self.raw, SEA, Z0, RPC, ramp_px=10.0, deep_cm=1000.0)
        z = zc(new)
        row = z[20]
        self.assertAlmostEqual(deep, 1000.0)
        self.assertTrue(row[39] > SEA - 40)  # next to the land: shallow
        self.assertTrue(row[29] < SEA - 450)  # 10 px out: at full depth
        self.assertTrue(row[10] < SEA - 990)  # far: deep and flat
        self.assertTrue((new[:, 40:] == self.raw[:, 40:]).all())  # land never changed
        self.assertTrue((new <= self.raw).all())  # nothing raised

    def test_inland_bowl_is_not_sea_and_stays_as_it_was(self):
        new, sea, _ = od.deepen(self.raw, SEA, Z0, RPC, ramp_px=10.0)
        self.assertFalse(sea[31, 45])
        self.assertTrue((new[30:34, 44:48] == self.raw[30:34, 44:48]).all())

    def test_depth_is_capped_by_the_lowest_height_the_landscape_can_hold(self):
        new, _, deep = od.deepen(self.raw, SEA, Z0, RPC, ramp_px=5.0, deep_cm=99999.0, floor_margin_cm=60.0)
        self.assertAlmostEqual(deep, SEA - Z0 - 60.0)
        self.assertTrue(zc(new).min() >= Z0 + 59.0)

    def test_deeper_existing_floor_is_kept(self):
        z = self.z.copy()
        z[10:14, 2:6] = SEA - 1500.0
        raw = raw_of(z)
        new, _, _ = od.deepen(raw, SEA, Z0, RPC, ramp_px=10.0, deep_cm=1000.0)
        self.assertTrue((new[10:14, 2:6] == raw[10:14, 2:6]).all())

    def test_calls_cover_only_changed_tiles(self):
        new, _, _ = od.deepen(self.raw, SEA, Z0, RPC, ramp_px=10.0)
        ph = od.calls_for(self.raw, new)[0]
        self.assertEqual(ph["name"], "heights")
        self.assertTrue(len(ph["calls"]) >= 1)
        m, args = ph["calls"][0]
        self.assertEqual(m, "landscape.set_height_region")
        self.assertIn("heightsBase64", args)


if __name__ == "__main__":
    unittest.main()
