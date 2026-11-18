import os, sys, unittest
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_village_build as vb

Z0, RPC, PX = 3677.7, 4.4387, 800.0


class Build(unittest.TestCase):
    def setUp(self):
        self.old = np.full((20, 20), round((6000.0 - Z0) * RPC), np.uint16)
        self.new = np.full((20, 20), round((7000.0 - Z0) * RPC), np.uint16)

    def test_transforms_sit_on_the_ground_minus_the_sink(self):
        t = vb.transforms([{"mesh": "Well", "x": 4000, "y": 4000, "yaw": 30, "sink": 10}, {"mesh": "Well", "x": 5000, "y": 4000, "yaw": 0}], self.new, Z0, RPC, PX)
        self.assertEqual(len(t["Well"]), 2)
        self.assertAlmostEqual(t["Well"][0]["location"]["z"], 6990.0, delta=0.5)
        self.assertEqual(t["Well"][0]["rotation"]["yaw"], 30)

    def test_moved_actor_keeps_its_height_above_the_ground(self):
        m = vb.moves({"A": {"x": 8000, "y": 8000, "yaw": 5}}, {"A": (4000, 4000, 6105.0)}, self.old, self.new, Z0, RPC, PX)
        self.assertAlmostEqual(m["A"]["z"], 7105.0, delta=0.5)


if __name__ == "__main__":
    unittest.main()
