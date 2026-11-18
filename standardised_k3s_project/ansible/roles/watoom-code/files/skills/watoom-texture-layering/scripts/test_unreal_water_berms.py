import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unreal_water_berms as wb  # noqa: E402

Z0, RPC, PX = 3677.7, 4.4387, 800.0


def raw_of(z):
    return np.clip(np.round((np.asarray(z, float) - Z0) * RPC), 0, 65535).astype(np.uint16)


def z_of(raw):
    return raw.astype(float) / RPC + Z0


def lake(x=40, y=40, water_z=9000.0, r_px=6):
    return {"label": "L", "x": x * PX, "y": y * PX, "water_z": water_z, "radius_cm": r_px * PX}


class Berm(unittest.TestCase):
    def test_low_ground_beside_a_lake_gets_a_crest_above_the_water(self):
        z = np.full((81, 81), 8000.0)  # all ground 10 m below the lake surface
        new, rep = wb.berm(raw_of(z), {"lakes": [lake()]}, Z0, RPC, PX)
        zn = z_of(new)
        # just past the carved bank (2 px) the crest stands above the water
        self.assertGreater(zn[40, 40 + 6 + 3], 9000.0 + 50)
        self.assertEqual(rep["capped_px"], 0)

    def test_never_raises_inside_the_water_or_lowers_anything(self):
        z = np.full((81, 81), 8000.0)
        z[0:5, :] = 12000.0  # a hill far away stays as it is
        new, _ = wb.berm(raw_of(z), {"lakes": [lake()]}, Z0, RPC, PX)
        zn = z_of(new)
        self.assertTrue((new >= raw_of(z)).all())
        yy, xx = np.mgrid[0:81, 0:81]
        inside = np.hypot(xx - 40, yy - 40) * PX < 6 * PX
        self.assertTrue((new[inside] == raw_of(z)[inside]).all())

    def test_high_ground_needs_no_berm(self):
        z = np.full((81, 81), 9500.0)  # ground already above crest
        new, rep = wb.berm(raw_of(z), {"lakes": [lake()]}, Z0, RPC, PX)
        self.assertEqual(rep["raised_px"], 0)
        self.assertTrue((new == raw_of(z)).all())

    def test_outer_slope_falls_to_natural_ground(self):
        z = np.full((81, 81), 8800.0)  # 2 m below the water
        new, _ = wb.berm(raw_of(z), {"lakes": [lake()]}, Z0, RPC, PX, crest_m=8.0, slope=0.5)
        zn = z_of(new)
        row = zn[40, 40 + 6 + 2:]  # from where the berm begins (past the 2 px carved bank, left as it is)
        self.assertTrue(all(a >= b - 1 for a, b in zip(row, row[1:])), "the berm must step down outwards")
        self.assertAlmostEqual(row[-1], 8800.0, delta=1)

    def test_a_creek_mouth_through_the_lake_rim_stays_open(self):
        z = np.full((81, 81), 8000.0)
        creek = {"label": "C", "points": [[40 * PX, 40 * PX, 9000.0], [78 * PX, 40 * PX, 9000.0]], "widths_cm": [3 * PX, 3 * PX]}
        new, _ = wb.berm(raw_of(z), {"lakes": [lake()], "creeks": [creek]}, Z0, RPC, PX)
        zn = z_of(new)
        # along the creek's centreline, outside the lake, the ground is not raised (it is the channel)
        self.assertAlmostEqual(zn[40, 50], 8000.0, delta=1)
        # beside the creek a rim stands above its water
        self.assertGreater(zn[40 + 4, 60], 9000.0)

    def test_no_rim_where_a_creek_is_at_sea_level(self):
        z = np.full((41, 41), 3000.0)
        creek = {"label": "C", "points": [[5 * PX, 20 * PX, 3677.7], [35 * PX, 20 * PX, 3677.7]], "widths_cm": [2 * PX, 2 * PX]}
        _, rep = wb.berm(raw_of(z), {"sea_z": 3677.7, "creeks": [creek]}, Z0, RPC, PX)
        self.assertEqual(rep["raised_px"], 0)

    def test_never_builds_on_the_sea_floor_at_a_creek_mouth(self):
        # the creek's last stretch is a few cm above the sea, the ground around its mouth is under the sea
        z = np.full((41, 41), 9000.0)
        z[:, 25:] = 4000.0  # the sea, east of x=25
        creek = {"label": "C", "points": [[5 * PX, 20 * PX, 4900.0], [38 * PX, 20 * PX, 4860.0]], "widths_cm": [2 * PX, 2 * PX]}
        new, _ = wb.berm(raw_of(z), {"sea_z": 4849.26, "creeks": [creek]}, Z0, RPC, PX)
        self.assertTrue((new[:, 25:] == raw_of(z)[:, 25:]).all())

    def test_raise_is_capped_and_reported(self):
        z = np.full((81, 81), 3700.0)  # 53 m below the water
        new, rep = wb.berm(raw_of(z), {"lakes": [lake()]}, Z0, RPC, PX, max_raise_m=5.0)
        self.assertGreater(rep["capped_px"], 0)
        self.assertLessEqual((z_of(new) - 3700.0).max(), 500.0 + 1)
        self.assertEqual(rep["capped"][0]["body"], "L")


if __name__ == "__main__":
    unittest.main()
