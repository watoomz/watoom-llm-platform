import math, os, sys, unittest
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unreal_village as uv

Z0, RPC, PX = 3677.7, 4.4387, 800.0


class Village(unittest.TestCase):
    def test_layout_is_deterministic_and_inside_the_radius(self):
        ex, a = uv.layout(50000.0, 60000.0)
        ex2, b = uv.layout(50000.0, 60000.0)
        self.assertEqual(a, b)
        self.assertTrue(all(math.hypot(i["x"] - 50000.0, i["y"] - 60000.0) < 9000.0 for i in a))
        self.assertEqual(len(ex), 13)
        self.assertGreater(len(a), 150)

    def test_houses_do_not_overlap_and_keep_lanes_clear(self):
        _, a = uv.layout(0.0, 0.0)
        houses = [(i["x"], i["y"]) for i in a if i["mesh"].startswith("House_Var")]
        self.assertGreater(len(houses), 15)
        for k, p in enumerate(houses):
            for q in houses[k + 1:]:
                self.assertGreater(math.hypot(p[0] - q[0], p[1] - q[1]), 1200.0)
            self.assertFalse(uv.near_lane(math.degrees(math.atan2(p[1], p[0])) % 360.0, 8.0))

    def test_houses_face_the_plaza(self):
        _, a = uv.layout(0.0, 0.0)
        h = next(i for i in a if i["mesh"] == "House_Var01")
        to_center = math.degrees(math.atan2(-h["y"], -h["x"]))
        self.assertAlmostEqual((h["yaw"] - to_center + 180.0) % 360.0 - 180.0, 0.0, delta=0.2)

    def test_pad_is_flat_inside_and_untouched_outside(self):
        n = 80
        yy, xx = np.mgrid[0:n, 0:n]
        z = 6000.0 + np.sin(xx / 5.0) * 200.0 + yy * 10.0
        raw = np.round((z - Z0) * RPC).astype(np.uint16)
        new, level = uv.pad(raw, Z0, RPC, PX, 40 * PX, 40 * PX, 6 * PX, 4 * PX)
        zn = new.astype(float) / RPC + Z0
        self.assertTrue(np.ptp(zn[37:44, 37:44]) < 1.0)
        self.assertTrue((new[:, :20] == raw[:, :20]).all())
        n2, l2 = uv.pad(raw, Z0, RPC, PX, 40 * PX, 40 * PX, 6 * PX, 4 * PX, sea_z=6500.0)
        self.assertGreaterEqual(l2, 6750.0)


if __name__ == "__main__":
    unittest.main()
