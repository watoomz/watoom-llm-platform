import json, os, sys, tempfile, unittest
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unreal_creek_river as cr

Z0, RPC, PX = 3677.7, 4.4387, 800.0


def raw_of(cm):
    return np.round((np.asarray(cm, float) - Z0) * RPC).astype(np.uint16)


class River(unittest.TestCase):
    def setUp(self):
        n = 60
        yy, xx = np.mgrid[0:n, 0:n]
        z = 6000.0 - xx * 20.0 + np.abs(yy - 30) * 80.0  # a valley along row 30 falling to the east
        self.n, self.z = n, z
        self.raw = raw_of(z)
        self.old = [[x * PX, 33 * PX, 0.0] for x in range(5, 55, 5)]  # old path 3 rows off the real valley floor

    def test_path_follows_the_valley_floor_not_the_old_polyline(self):
        pts, bed = cr.build(self.raw, self.old, Z0, RPC, PX, n_points=20)
        rows = [p[1] / PX for p in pts[2:-2]]
        self.assertTrue(all(abs(r - 30) < 1.6 for r in rows), rows)

    def test_water_falls_and_is_never_below_the_bed_downstream(self):
        pts, bed = cr.build(self.raw, self.old, Z0, RPC, PX, n_points=20, over_cm=40.0, fall_cm=3.0)
        w = [p[2] for p in pts]
        self.assertTrue(all(a > b for a, b in zip(w, w[1:])))
        for i in range(len(w)):
            self.assertTrue(w[i] >= max(bed[i:]) + 39.0 - 1e-6 or i == len(w) - 1 or w[i] >= bed[i] + 39.0)

    def test_head_is_capped_at_the_lake_surface(self):
        pts, bed = cr.build(self.raw, self.old, Z0, RPC, PX, n_points=20, start_z=5800.0)
        self.assertAlmostEqual(pts[0][2], 5800.0, delta=0.01)
        self.assertTrue(max(p[2] for p in pts) <= 5800.01)
        w = [p[2] for p in pts]
        self.assertTrue(all(a >= b for a, b in zip(w, w[1:])))  # level at the head at worst, never rising

    def test_spline_text_has_matching_curves(self):
        pts = [[0, 0, 100.0], [10, 0, 90.0], [20, 5, 80.0]]
        t = cr.spline_text(pts)
        self.assertTrue(t.startswith("(Position=(Points=(") and t.count("InVal=") == 3 * 2)  # points 1 and 2 in each of 3 curves
        self.assertEqual(t.count("OutVal=("), 9)
        self.assertIn("Rotation=(Points=", t)
        self.assertIn("Scale=(Points=", t)

    def test_cli_writes_points_and_text(self):
        d = tempfile.mkdtemp()
        Image.fromarray(self.raw).save(os.path.join(d, "h.png"))
        json.dump(self.old, open(os.path.join(d, "o.json"), "w"))
        rc = cr.main(["--heights", os.path.join(d, "h.png"), "--polyline", os.path.join(d, "o.json"), "--z0", str(Z0), "--raw-per-cm", str(RPC),
                      "--size-m", str((self.n - 1) * PX / 100.0), "--points", "12", "--out", os.path.join(d, "p.json"), "--out-text", os.path.join(d, "t.txt")])
        self.assertEqual(rc, 0)
        self.assertEqual(len(json.load(open(os.path.join(d, "p.json")))), 12)
        self.assertTrue(open(os.path.join(d, "t.txt")).read().startswith("(Position="))


if __name__ == "__main__":
    unittest.main()
