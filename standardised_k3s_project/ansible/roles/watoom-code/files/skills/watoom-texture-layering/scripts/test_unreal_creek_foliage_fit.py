import os, sys, unittest
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unreal_creek_foliage_fit as ff

Z0, RPC, PX = 3677.7, 4.4387, 800.0


def raw_of(cm):
    return np.round((np.asarray(cm, float) - Z0) * RPC).astype(np.uint16)


class Fit(unittest.TestCase):
    def setUp(self):
        n = 40
        z = np.full((n, n), 6000.0)
        z[20, :] = 5400.0  # deep middle row
        z[19, :] = z[21, :] = 5800.0  # shallow sides (water is at 5900)
        self.raw = raw_of(z)
        self.samples = np.array([[x * PX, 20 * PX, 5900.0] for x in range(0, 40)], float)

    def inst(self, x_px, y_px, z, idx=0):
        return {"type": "/Game/T", "index": idx, "x": x_px * PX, "y": y_px * PX, "z": z, "rotation": {"pitch": 0, "yaw": 10, "roll": 0}, "scale": {"x": 1, "y": 1, "z": 1}}

    def test_deep_middle_is_removed(self):
        r = ff.plan([self.inst(10, 20, 6000.0)], self.raw, Z0, RPC, PX, self.samples, 6000.0)
        self.assertEqual(r["remove"], [{"type": "/Game/T", "index": 0}])
        self.assertEqual(r["add"], [])

    def test_shallow_edge_is_kept_standing_in_the_water_at_the_new_ground(self):
        r = ff.plan([self.inst(10, 21, 6000.0, 7)], self.raw, Z0, RPC, PX, self.samples, 6000.0)
        self.assertEqual(r["remove"], [{"type": "/Game/T", "index": 7}])
        self.assertEqual(len(r["add"]), 1)
        self.assertAlmostEqual(r["add"][0]["location"]["z"], 5800.0, delta=3)
        self.assertEqual(r["add"][0]["rotation"]["yaw"], 10)

    def test_untouched_and_far_instances_are_kept(self):
        r = ff.plan([self.inst(10, 30, 6000.0), self.inst(10, 25, 6000.0)], self.raw, Z0, RPC, PX, self.samples, 4000.0)
        self.assertEqual((r["remove"], r["add"], r["kept"]), ([], [], 2))

    def test_instance_already_on_the_new_ground_is_kept(self):
        r = ff.plan([self.inst(10, 21, 5800.0)], self.raw, Z0, RPC, PX, self.samples, 6000.0)
        self.assertEqual((r["remove"], r["add"], r["kept"]), ([], [], 1))


if __name__ == "__main__":
    unittest.main()
