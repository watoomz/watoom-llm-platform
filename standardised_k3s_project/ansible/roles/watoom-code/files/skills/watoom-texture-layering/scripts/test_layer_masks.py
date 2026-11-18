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

spec_ = importlib.util.spec_from_file_location("build_terrain", HERE.parent.parent / "watoom-terrain-map" / "scripts" / "build_terrain.py")
build_terrain = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(build_terrain)

SPEC = {"seed": 7, "sharpness": 4, "layers": [
    {"name": "grass", "fallback": True, "color": [0.2, 0.5, 0.2]},
    {"name": "rock", "slope_deg": [35, 90, 8], "color": [0.5, 0.5, 0.5]},
    {"name": "snow", "height_norm": [0.85, 1.0, 0.05], "slope_deg": [0, 40, 8], "color": [1, 1, 1]},
    {"name": "mud", "curvature": {"kind": "concave", "strength": 2.0}, "slope_deg": [0, 20, 5], "noise": {"scale_m": 60, "amount": 0.3}, "color": [0.4, 0.3, 0.2]},
]}


def mountain(n=128):
    y, x = np.mgrid[0:n, 0:n] / (n - 1.0)
    h = np.exp(-(((x - 0.5) ** 2 + (y - 0.5) ** 2) / 0.05))
    return (h - h.min()) / (h.max() - h.min())


class LayerMasks(unittest.TestCase):
    def run_cli(self, norm, spec, extra=()):
        d = tempfile.mkdtemp()
        hp, sp, out = os.path.join(d, "h.npy"), os.path.join(d, "s.json"), os.path.join(d, "out")
        np.save(hp, norm)
        json.dump(spec, open(sp, "w"))
        rc = lm.main(["--heightmap", hp, "--cell-size", "10", "--height-range", "0", "300", "--spec", sp, "--out", out, *extra])
        return rc, out

    def test_exr_roundtrip_with_the_real_writer(self):
        h = mountain(64).astype(np.float32)
        p = os.path.join(tempfile.mkdtemp(), "h.exr")
        build_terrain.save_exr_r_float(p, h)
        self.assertTrue(np.array_equal(lm.read_exr_r_float(p).astype(np.float32), h))

    def test_weights_sum_to_255_everywhere_and_files_exist(self):
        rc, out = self.run_cli(mountain(), SPEC)
        self.assertEqual(rc, 0)
        s0 = np.asarray(Image.open(os.path.join(out, "splat_0.png")), np.int32)
        self.assertEqual(s0.shape[-1], 4)
        self.assertTrue((s0.sum(axis=-1) == 255).all())
        for f in ("control_hint.png", "layer_preview.png", "layer_report.json"):
            self.assertTrue(os.path.exists(os.path.join(out, f)), f)

    def test_each_rule_lands_where_it_should(self):
        norm = mountain()
        rc, out = self.run_cli(norm, SPEC)
        s = np.asarray(Image.open(os.path.join(out, "splat_0.png")), np.int32)
        grass, rock, snow = s[..., 0], s[..., 1], s[..., 2]
        top = norm > 0.95
        self.assertGreater(snow[top].mean(), 150)            # snow on the summit
        self.assertLess(snow[norm < 0.3].max(), 5)           # none in the valley
        self.assertGreater(grass[norm < 0.05].mean(), 150)   # fallback on flat low ground
        rep = json.load(open(os.path.join(out, "layer_report.json")))
        self.assertTrue(rep["sum_to_255_everywhere"])
        self.assertGreater(rock.max(), 0)                    # steep flanks exist on this cone
        self.assertEqual([l["channel"] for l in rep["layers"]], list("RGBA"))

    def test_deterministic(self):
        _, a = self.run_cli(mountain(), SPEC)
        _, b = self.run_cli(mountain(), SPEC)
        self.assertTrue(np.array_equal(np.asarray(Image.open(os.path.join(a, "splat_0.png"))), np.asarray(Image.open(os.path.join(b, "splat_0.png")))))

    def test_sharpness_one_is_softer_than_eight(self):
        def crisp(k):
            spec = json.loads(json.dumps(SPEC))
            spec["sharpness"] = k
            _, out = self.run_cli(mountain(), spec)
            s = np.asarray(Image.open(os.path.join(out, "splat_0.png")), np.float64)
            return (np.abs(s - 127.5).mean())
        self.assertGreater(crisp(8), crisp(1))

    def test_second_splat_map_for_more_than_four_layers(self):
        spec = json.loads(json.dumps(SPEC))
        spec["layers"] += [{"name": "sand", "height_norm": [0, 0.04, 0.02]}, {"name": "scree", "slope_deg": [28, 40, 4]}]
        rc, out = self.run_cli(mountain(), spec)
        self.assertEqual(rc, 0)
        s0 = np.asarray(Image.open(os.path.join(out, "splat_0.png")), np.int32)
        s1 = np.asarray(Image.open(os.path.join(out, "splat_1.png")), np.int32)
        self.assertTrue(((s0.sum(-1) + s1.sum(-1)) == 255).all())

    def test_control_hint_matches_dominant_layers(self):
        _, out = self.run_cli(mountain(), SPEC)
        hint = np.asarray(Image.open(os.path.join(out, "control_hint.png")))
        s = np.asarray(Image.open(os.path.join(out, "splat_0.png")))
        self.assertTrue(np.array_equal(hint[..., 0], s.argmax(axis=-1)))

    def test_the_shipped_example_spec_works(self):
        example = json.load(open(HERE.parent / "templates" / "layers.example.json"))
        rc, out = self.run_cli(mountain(), example)
        self.assertEqual(rc, 0)
        rep = json.load(open(os.path.join(out, "layer_report.json")))
        self.assertEqual(len(rep["layers"]), 6)
        self.assertTrue(os.path.exists(os.path.join(out, "splat_1.png")))
        self.assertGreater(sum(l["coverage_pct"] for l in rep["layers"]), 99.9)

    def test_errors(self):
        bad = {"layers": [{"name": "a"}, {"name": "b"}]}
        with self.assertRaises(ValueError):
            self.run_cli(mountain(), bad)
        dup = {"layers": [{"name": "a", "fallback": True}, {"name": "a"}]}
        with self.assertRaises(ValueError):
            self.run_cli(mountain(), dup)
        with self.assertRaises(SystemExit):
            lm.main(["--heightmap", "x.npy", "--spec", "s.json", "--out", "o"])


class Smoothing(unittest.TestCase):
    def test_smooth_field_keeps_a_constant_and_a_plane_and_flattens_noise(self):
        flat = np.full((40, 40), 5.0)
        self.assertTrue(np.allclose(lm.smooth_field(flat, 3), 5.0))
        ramp = np.tile(np.arange(40, dtype=float), (40, 1))
        inner = lm.smooth_field(ramp, 2)[:, 8:-8]
        self.assertTrue(np.allclose(inner, ramp[:, 8:-8], atol=1e-9))   # a plane is unchanged away from the edges
        noisy = np.random.default_rng(1).random((64, 64))
        self.assertLess(lm.smooth_field(noisy, 3).std(), noisy.std() / 3)
        self.assertIs(lm.smooth_field(noisy, 0), noisy)

    def test_quantised_ground_stops_flickering_between_layers(self):
        n = 128
        y, x = np.mgrid[0:n, 0:n]
        gentle = np.floor((x * 0.09 + y * 0.05) * 1.0) / 1.0            # 1 m stair steps on a ~5 degree ramp
        norm = (gentle - gentle.min()) / (gentle.max() - gentle.min())
        raw = lm.derive(norm, 0.0, float(gentle.max() - gentle.min()), 8.0)[0]
        soft = lm.derive(norm, 0.0, float(gentle.max() - gentle.min()), 8.0, smooth_m=24.0)[0]
        inner = (slice(12, -12), slice(12, -12))
        self.assertGreater(raw[inner].std(), 3 * soft[inner].std())

    def test_heights_are_not_smoothed_for_height_rules(self):
        norm = np.random.default_rng(2).random((32, 32))
        a = lm.derive(norm, 10.0, 50.0, 8.0)[1]
        b = lm.derive(norm, 10.0, 50.0, 8.0, smooth_m=24.0)[1]
        self.assertTrue(np.array_equal(a, b))


if __name__ == "__main__":
    unittest.main()