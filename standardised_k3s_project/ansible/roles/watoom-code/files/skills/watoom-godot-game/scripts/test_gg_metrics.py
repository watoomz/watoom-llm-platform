import os, sys, tempfile, unittest
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gg_metrics as gm


def grey(v, w=32, h=32):
    return np.full((h, w, 3), v, np.uint8)


class T(unittest.TestCase):
    def test_solid_grey(self):
        m = gm.measure(grey(128))
        self.assertAlmostEqual(m["luma_p50"], 128 / 255, places=3)
        self.assertEqual(m["sat_mean"], 0.0)
        self.assertEqual(m["unique_colors"], 1)
        self.assertEqual(m["flat_fraction"], 1.0)

    def test_pure_red_saturation_one(self):
        a = np.zeros((8, 8, 3), np.uint8); a[..., 0] = 255
        self.assertAlmostEqual(gm.measure(a)["sat_mean"], 1.0)

    def test_half_black_half_white(self):
        a = np.zeros((10, 10, 3), np.uint8); a[:, 5:] = 255
        m = gm.measure(a)
        self.assertAlmostEqual(m["clip_black"], 0.5); self.assertAlmostEqual(m["clip_white"], 0.5)
        self.assertAlmostEqual(sum(m["hist16"]), 1.0)

    def test_grid_integrity_pixel_art(self):
        small = np.random.RandomState(1).randint(0, 255, (8, 8, 3), np.uint8)
        big = np.kron(small, np.ones((4, 4, 1), np.uint8))
        self.assertEqual(gm.measure(big, 4)["grid_integrity"], 1.0)
        shifted = np.roll(big, 1, axis=1)
        self.assertLess(gm.measure(shifted, 4)["grid_integrity"], 1.0)
        self.assertIsNone(gm.measure(big)["grid_integrity"])

    def test_refuses_16bit_and_transparent(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.png"); Image.fromarray(np.zeros((4, 4), np.uint16)).save(p)
            with self.assertRaises(gm.Refused): gm.load_rgb(p)
            q = os.path.join(d, "b.png"); a = np.zeros((4, 4, 4), np.uint8); a[0, 0, 3] = 10; Image.fromarray(a, "RGBA").save(q)
            with self.assertRaises(gm.Refused): gm.load_rgb(q)
            r = os.path.join(d, "c.png"); a[..., 3] = 255; Image.fromarray(a, "RGBA").save(r)
            self.assertEqual(gm.load_rgb(r).shape, (4, 4, 3))

    def test_targets_and_hints(self):
        m = gm.measure(grey(128))
        self.assertEqual(gm.compare_targets(m, {"luma_p50": [0.4, 0.6]}), [])
        f = gm.compare_targets(m, {"luma_p50": [0.6, None]}, fix_hints={"luma_p50": {"low": "raise exposure"}})
        self.assertEqual((f[0]["direction"], f[0]["hint"]), ("low", "raise exposure"))
        self.assertEqual(gm.compare_targets(m, {"luma_p50": [0.51, None]}, tol=0.02), [])
        self.assertEqual(gm.compare_targets(m, {"luma_p50": [0.51, None]}), [])  # default tol 0.01 matches shot
        self.assertEqual(gm.compare_targets(m, {"clip_black": [None, 0.01]}), [])
        with self.assertRaises(gm.Refused): gm.compare_targets(m, {"nope": [0, 1]})
        for bad in ({"luma_p50": 0.4}, {"luma_p50": [0.9, 0.1]}, {"luma_p50": [0.1]}, {"luma_p50": {"min": 1}}):
            with self.assertRaises(gm.Refused): gm.compare_targets(m, bad)

    def test_unmeasured_grid_is_skipped(self):
        self.assertEqual(gm.compare_targets(gm.measure(grey(1)), {"grid_integrity": [0.98, None]}), [])

    def test_hard_failures(self):
        self.assertEqual(gm.hard_failures(gm.measure(grey(128)))[0]["metric"], "luma_std")  # blank frame
        h = gm.hard_failures(gm.measure(grey(0)), expect_size=(64, 64))
        self.assertTrue({"luma_std", "clip_black", "size"} <= {x["metric"] for x in h})
        self.assertIn("32x32", [x for x in h if x["metric"] == "size"][0]["hint"])

    def _pair(self, f):
        a = np.random.RandomState(2).randint(60, 120, (32, 32, 3), np.uint8)
        b = f(a.copy())
        ma, mb = gm.measure(a), gm.measure(b); ma["_rgb"], mb["_rgb"] = a, b
        return ma, mb

    def test_compare_directions(self):
        ma, mb = self._pair(lambda x: np.clip(x.astype(int) + 60, 0, 255).astype(np.uint8))
        self.assertTrue(gm.compare_images(ma, mb, "brighter")[0]); self.assertFalse(gm.compare_images(ma, mb, "darker")[0])
        ma, mb = self._pair(lambda x: np.concatenate([np.clip(x[..., :1].astype(int) + 80, 0, 255).astype(np.uint8), x[..., 1:]], axis=2))
        self.assertTrue(gm.compare_images(ma, mb, "tint-r", 0.05)[0]); self.assertFalse(gm.compare_images(ma, mb, "tint-b", 0.05)[0])
        ma, mb = self._pair(lambda x: x)
        self.assertTrue(gm.compare_images(ma, mb, "same")[0]); self.assertFalse(gm.compare_images(ma, mb, "different")[0])
        with self.assertRaises(gm.Refused): gm.compare_images(ma, mb, "bluer")

    def test_small_change_is_reported_not_ignored(self):
        a = np.random.RandomState(2).randint(60, 120, (40, 40, 3), np.uint8)
        b = a.copy(); b[:6, :6] = 255  # a small object changed: 2.25% of pixels
        ma, mb = gm.measure(a), gm.measure(b); ma["_rgb"], mb["_rgb"] = a, b
        self.assertTrue(gm.compare_images(ma, mb, "different")[0]); self.assertFalse(gm.compare_images(ma, mb, "same")[0])
        self.assertIn("changed", gm.compare_images(ma, mb, "brighter")[1])
        with self.assertRaises(gm.Refused) as c:
            m2 = gm.measure(a[:20]); m2["_rgb"] = a[:20]; gm.compare_images(ma, m2, "different")
        self.assertIn("40x40", str(c.exception)); self.assertIn("40x20", str(c.exception))

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "g.png"); Image.fromarray(grey(128)).save(p)
            self.assertEqual(gm.main([p, "--json"]), 1)  # flat grey = blank frame
            self.assertEqual(gm.main([os.path.join(d, "none.png")]), 2)


if __name__ == "__main__":
    unittest.main()
