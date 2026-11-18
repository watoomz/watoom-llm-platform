import os, sys, unittest
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_place_assets as pa


class Place(unittest.TestCase):
    def test_ground_z_is_bilinear_and_clamped(self):
        raw = np.zeros((5, 5)); raw[:, 2:] = 44387.0  # right half 10000 cm above z0
        z = pa.ground_z(raw, 1.5 * 800, 800, 0.0, 4.4387, 800.0)
        self.assertAlmostEqual(z, 5000.0, delta=1)  # half way across the step
        self.assertAlmostEqual(pa.ground_z(raw, 9e9, 9e9, 100.0, 4.4387, 800.0), 100.0 + 44387 / 4.4387, delta=1)

    def test_actor_z_puts_the_lowest_point_below_the_ground(self):
        # actor at 1000, bounds centre 1200 extent 300 -> bottom 900; want bottom at ground 500 - sink 20 = 480
        self.assertAlmostEqual(pa.actor_z_for_bottom(1000.0, 1200.0, 300.0, 500.0, 20.0), 580.0)


if __name__ == "__main__":
    unittest.main()
