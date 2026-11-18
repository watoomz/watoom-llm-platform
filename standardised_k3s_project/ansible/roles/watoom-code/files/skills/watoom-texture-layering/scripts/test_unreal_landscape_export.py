import base64
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import layer_masks as lm  # noqa: E402
import unreal_landscape_export as ue  # noqa: E402
from test_layer_masks import SPEC, mountain  # noqa: E402

bt = importlib.util.spec_from_file_location("build_terrain", HERE.parent.parent / "watoom-terrain-map" / "scripts" / "build_terrain.py")
build_terrain = importlib.util.module_from_spec(bt)
bt.loader.exec_module(build_terrain)


def make_terrain(n=96):
    d = tempfile.mkdtemp()
    h = mountain(n).astype(np.float32)
    build_terrain.save_exr_r_float(os.path.join(d, "heightmap.exr"), h)
    json.dump({"min_elev_m": 100.0, "max_elev_m": 400.0, "size_m": 2000.0, "meters_per_sample": 2000.0 / (n - 1)}, open(os.path.join(d, "meta.json"), "w"))
    json.dump(SPEC, open(os.path.join(d, "spec.json"), "w"))
    lm.main(["--heightmap", os.path.join(d, "heightmap.exr"), "--meta", os.path.join(d, "meta.json"), "--spec", os.path.join(d, "spec.json"), "--out", os.path.join(d, "layers")])
    return d, h


class Export(unittest.TestCase):
    def test_legal_vertex_counts(self):
        legal = ue.legal_vertex_counts()
        for n in ue.STANDARD:
            self.assertIn(n, legal)
        self.assertIn(1024, legal)       # 33 components x 31 quads + 1: legal by the formula, just unusual
        for n in (1000, 2048, 999):
            self.assertNotIn(n, legal)

    def test_illegal_vertex_count_is_refused_with_neighbours(self):
        d, _ = make_terrain()
        with self.assertRaises(SystemExit) as cm:
            ue.main(["heightmap", "--heightmap", os.path.join(d, "heightmap.exr"), "--meta", os.path.join(d, "meta.json"), "--vertices", "1000", "--out", os.path.join(d, "o")])
        self.assertIn("1009", str(cm.exception))
        self.assertIn("Standard sizes", str(cm.exception))

    def test_resample_keeps_corners_and_is_exact_when_the_size_matches(self):
        a = np.random.default_rng(3).random((33, 33))
        r = ue.resample(a, 65)
        for (y, x) in ((0, 0), (0, 64), (64, 0), (64, 64)):
            self.assertAlmostEqual(r[y, x], a[(y // 64) * 32, (x // 64) * 32])
        self.assertTrue(np.allclose(ue.resample(a, 33), a))

    def test_heightmap_is_a_16_bit_png_over_the_full_range(self):
        d, h = make_terrain()
        out = os.path.join(d, "ue")
        self.assertEqual(ue.main(["heightmap", "--heightmap", os.path.join(d, "heightmap.exr"), "--meta", os.path.join(d, "meta.json"), "--vertices", "127", "--out", out]), 0)
        im = Image.open(os.path.join(out, "heightmap16.png"))
        self.assertEqual(im.mode, "I;16")
        self.assertEqual(im.size, (127, 127))
        arr = np.asarray(im)
        self.assertEqual(int(arr.max()), 65535)
        self.assertEqual(int(arr.min()), 0)
        self.assertEqual(int(arr[63, 63]), int(round(ue.resample(h.astype(np.float64), 127)[63, 63] * 65535)))
        plan = json.load(open(os.path.join(out, "unreal_plan.json")))
        a = plan["plan_real_world_args"]
        self.assertEqual((a["minElevationMeters"], a["maxElevationMeters"], a["elevationEncoding"]), (100.0, 400.0, "full"))
        self.assertEqual(a["realWorldSizeMeters"], {"x": 2000.0, "y": 2000.0})
        self.assertAlmostEqual(plan["metres_per_quad"], 2000.0 / 126)

    def test_flip_y_mirrors_the_heights(self):
        d, _ = make_terrain()
        res = {}
        for flag, name in (([], "a"), (["--flip-y"], "b")):
            out = os.path.join(d, name)
            ue.main(["heightmap", "--heightmap", os.path.join(d, "heightmap.exr"), "--meta", os.path.join(d, "meta.json"), "--vertices", "127", "--out", out, *flag])
            res[name] = np.asarray(Image.open(os.path.join(out, "heightmap16.png")))
        self.assertTrue(np.array_equal(res["a"][::-1], res["b"]))

    def test_weights_sum_to_255_at_every_vertex_and_tiles_reassemble(self):
        d, _ = make_terrain()
        out = os.path.join(d, "w")
        self.assertEqual(ue.main(["weights", "--layers", os.path.join(d, "layers"), "--vertices", "127", "--tile", "64", "--out", out]), 0)
        idx = json.load(open(os.path.join(out, "index.json")))
        self.assertTrue(idx["sum_is_255_everywhere"])
        total = np.zeros((127, 127), np.int32)
        for name, info in idx["layers"].items():
            raw = np.frombuffer(open(os.path.join(out, info["raw"]), "rb").read(), np.uint8).reshape(127, 127)
            total += raw
            rebuilt = np.zeros((127, 127), np.uint8)
            for t in info["tiles"]:
                blk = np.frombuffer(base64.b64decode(open(os.path.join(out, t["file"])).read()), np.uint8).reshape(t["height"], t["width"])
                rebuilt[t["y0"]:t["y0"] + t["height"], t["x0"]:t["x0"] + t["width"]] = blk
            self.assertTrue(np.array_equal(rebuilt, raw), name)
        self.assertTrue((total == 255).all())

    def test_weights_keep_the_layer_pattern_after_resampling(self):
        d, _ = make_terrain()
        out = os.path.join(d, "w")
        ue.main(["weights", "--layers", os.path.join(d, "layers"), "--vertices", "127", "--out", out])
        snow = np.frombuffer(open(os.path.join(out, "snow.u8"), "rb").read(), np.uint8).reshape(127, 127)
        self.assertGreater(snow[55:72, 55:72].mean(), 100)   # summit
        self.assertLess(snow[:10, :10].mean(), 5)            # corner


if __name__ == "__main__":
    unittest.main()
