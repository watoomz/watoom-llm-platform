import os
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_look_probe as lp  # noqa: E402


class Probe(unittest.TestCase):
    def test_metrics_split_ground_and_sky(self):
        a = np.zeros((100, 10, 3), np.uint8)
        a[:25] = 255          # sky quarter fully clipped
        a[55:] = 100          # ground
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.png")
            Image.fromarray(a).save(p)
            m = lp.metrics(p)
        self.assertAlmostEqual(m["ground"], 100.0, places=0)
        self.assertEqual(m["sky_clip_pct"], 100.0)

    def test_summary_and_closest(self):
        self.assertEqual(lp.summary({"a": {"ground": 100.0}, "b": {"ground": 120.0}}), (110.0, 20.0))
        self.assertEqual(lp.closest({0.3: (135.0, 60), 0.45: (104.0, 50), 0.6: (86.0, 44)}, 105), 0.45)

    def test_probe_set_uses_owner_view_unmoved_then_each_yaw_and_survives_a_failed_view(self):
        shots = []

        def shoot(path, cam):
            shots.append(cam)
            if cam and cam[4] == 90:
                raise SystemExit("capture failed")
            Image.fromarray(np.full((40, 10, 3), 80, np.uint8)).save(path)
        with tempfile.TemporaryDirectory() as d:
            per = lp.probe_set(shoot, d, "t", (1.0, 2.0, 3.0), [0, 90], -8)
        self.assertIsNone(shots[0])  # the owner's view is captured where it is
        self.assertEqual(shots[1], (1.0, 2.0, 3.0, -8, 0))
        self.assertEqual(sorted(per), ["owner", "y0"])


if __name__ == "__main__":
    unittest.main()
