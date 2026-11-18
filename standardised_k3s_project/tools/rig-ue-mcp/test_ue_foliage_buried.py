import os, sys, unittest
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_foliage_buried as fb

Z0, RPC, PX = 3677.7, 4.4387, 800.0


class Buried(unittest.TestCase):
    def setUp(self):
        self.raw = np.full((20, 20), np.round((6000.0 - Z0) * RPC), np.uint16)

    def test_ground_z_bilinear(self):
        self.assertAlmostEqual(fb.ground_z(self.raw, Z0, RPC, PX, 5 * PX + 100, 7 * PX), 6000.0, delta=0.5)

    def test_only_instances_far_below_the_ground_are_buried(self):
        ins = [{"index": 0, "x": 4000, "y": 4000, "z": 6000.0}, {"index": 1, "x": 4000, "y": 4000, "z": 5950.0},
               {"index": 2, "x": 4000, "y": 4000, "z": 5900.0}, {"index": 3, "x": 8000, "y": 8000, "z": 5000.0}, {"index": 4, "x": 4000, "y": 4000, "z": 6100.0}]
        self.assertEqual(fb.find_buried(ins, self.raw, Z0, RPC, PX, 80.0), [2, 3])

    def test_in_sea_selects_instances_on_ground_below_the_sea_surface(self):
        low = np.full((20, 20), np.round((4800.0 - Z0) * RPC), np.uint16)   # ground at 4800, sea at 4849
        ins = [{"index": 0, "x": 4000, "y": 4000, "z": 4800.0}, {"index": 1, "x": 8000, "y": 8000, "z": 4810.0}]
        self.assertEqual(fb.find_in_sea(ins, low, Z0, RPC, PX, 4849.26), [0, 1])
        self.assertEqual(fb.find_in_sea(ins, low, Z0, RPC, PX, 4849.26, margin_cm=100.0), [])
        self.assertEqual(fb.find_in_sea(ins, self.raw, Z0, RPC, PX, 4849.26), [])   # ground at 6000, dry land


    def test_edge_connected_sea_leaves_an_inland_bowl_alone(self):
        z = np.full((20, 20), 6000.0)
        z[:, :4] = 4700.0        # the sea, touching the map edge
        z[9:12, 9:12] = 4700.0   # an inland bowl below sea level, surrounded by land
        raw = np.round((z - Z0) * RPC).astype(np.uint16)
        ins = [{"index": 0, "x": 1 * PX, "y": 10 * PX, "z": 4700.0}, {"index": 1, "x": 10 * PX, "y": 10 * PX, "z": 4700.0},
               {"index": 2, "x": 15 * PX, "y": 15 * PX, "z": 6000.0}]
        self.assertEqual(fb.find_in_sea(ins, raw, Z0, RPC, PX, 4849.26), [0, 1])           # plain --in-sea: any ground below sea level
        mask = fb.sea_mask(raw, Z0, RPC, 4849.26)
        self.assertTrue(mask[10, 1] and not mask[10, 10])
        self.assertEqual(fb.find_in_sea(ins, raw, Z0, RPC, PX, 4849.26, mask=mask), [0])   # --edge-connected-sea: the bowl is kept


if __name__ == "__main__":
    unittest.main()
