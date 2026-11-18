import json, os, sys, tempfile, unittest
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unreal_creek_extend as ce

PX = 800.0


class Extend(unittest.TestCase):
    def setUp(self):
        n = 60
        yy, xx = np.mgrid[0:n, 0:n]
        self.z = 7000.0 - xx * 30.0 + np.abs(yy - 30) * 60.0  # valley along row 30 falling east; sea only from x=50
        self.z[:, 50:] = 4000.0  # sea in the east (below sea_z)
        self.pts = [[x * PX, 30 * PX, 6400.0 - x * 8.0] for x in range(5, 30, 3)]

    def test_sea_mask_is_edge_connected_only(self):
        z = self.z.copy()
        z[10:13, 10:13] = 4000.0  # inland pit
        s = ce.sea_mask(z, 4849.0)
        self.assertTrue(s[30, 55])
        self.assertFalse(s[11, 11])

    def test_extend_to_sea_ends_at_the_coast_and_water_never_rises(self):
        out = ce.extend(self.pts, self.z, PX, sea_z=4849.0)
        self.assertGreater(len(out), len(self.pts))
        self.assertGreaterEqual(out[-1][0], 49 * PX)
        w = [p[2] for p in out]
        self.assertTrue(all(a >= b - 1e-6 for a, b in zip(w, w[1:])))
        self.assertAlmostEqual(w[-1], 4859.0, delta=0.5)

    def test_join_ends_on_the_other_creek_without_rising(self):
        other = [[x * PX, 40 * PX, 5000.0] for x in range(0, 50, 5)]
        out = ce.extend(self.pts, self.z, PX, join=other)
        self.assertAlmostEqual(out[-1][1], 40 * PX, delta=1)
        self.assertTrue(out[-1][2] <= self.pts[-1][2] + 1e-6)

    def test_trim_drops_points_below_the_level(self):
        pts = [[0, 0, 5000.0], [1, 0, 4900.0], [2, 0, 4700.0], [3, 0, 4600.0]]
        self.assertEqual(len(ce.trim_below(pts, 4850.0)), 2)

    def test_approach_cuts_a_parallel_creek_and_joins_straight(self):
        other = [[x * PX, 40 * PX, 5000.0] for x in range(0, 50, 5)]
        run = [[x * PX, 44 * PX, 6000.0 - x * 5.0] for x in range(5, 45, 3)]  # runs alongside the target, 4 px away, for its whole length
        out = ce.extend(run, self.z, PX, join=other, approach_cm=5 * PX)
        self.assertLess(out[-1][0], 12 * PX)  # cut near where it first came within 5 px, not at the far end
        self.assertAlmostEqual(out[-1][1], 40 * PX, delta=1)

    def test_into_sea_carries_the_channel_on_past_the_coast_at_sea_level(self):
        base = ce.extend(self.pts, self.z, PX, sea_z=4849.0)
        out = ce.extend(self.pts, self.z, PX, sea_z=4849.0, into_sea_cm=9 * PX)
        self.assertGreater(len(out), len(base))
        self.assertGreater(out[-1][0], base[-1][0] + 6 * PX)  # further east, into the sea
        self.assertAlmostEqual(out[-1][2], 4849.5, delta=0.01)
        w = [p[2] for p in out]
        self.assertTrue(all(a >= b - 1e-6 for a, b in zip(w, w[1:])))


if __name__ == "__main__":
    unittest.main()
