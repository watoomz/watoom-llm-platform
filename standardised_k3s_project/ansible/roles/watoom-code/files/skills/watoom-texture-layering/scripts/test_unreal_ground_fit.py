import importlib.util
import pathlib
import unittest

import numpy as np

spec = importlib.util.spec_from_file_location("ugf", pathlib.Path(__file__).with_name("unreal_ground_fit.py"))
ugf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ugf)

SIZE_M, Z0, RPC = 1000.0, 1000.0, 4.0
N = 101
CM = SIZE_M * 100 / (N - 1)  # 1000 cm per pixel


def slope(per_px_cm=60.0):
    """Ground rising 60 cm per pixel along x (a steep hillside)."""
    x = np.tile(np.arange(N), (N, 1))
    return ((x * per_px_cm) * RPC).astype(np.uint16)  # raw = (z - Z0) * RPC with z = Z0 + x*60


def comp(name, cx_px, cy_px, half_px, bottom_cm, height=200.0):
    return {"name": name, "o": {"x": cx_px * CM, "y": cy_px * CM, "z": bottom_cm + height / 2},
            "e": {"x": half_px * CM, "y": half_px * CM, "z": height / 2}}


class GroundFit(unittest.TestCase):
    def setUp(self):
        self.h = slope()
        # ground under pixel x=50 is Z0 + 3000; a house body floating 120 cm above the mean ground of its footprint
        self.mean_ground = float(self.h[:, 48:53].mean()) / RPC + Z0
        self.comps = {"House": [comp("SM_BLD_body_01", 50, 50, 2, self.mean_ground + 120),
                                comp("SM_PROP_barrel", 50, 50, 0.3, self.mean_ground + 400, 80),
                                comp("SM_BLD_door_01", 50, 49, 0.3, self.mean_ground + 150)]}
        self.out = ugf.fit(self.comps, self.h, SIZE_M, Z0, RPC)

    def test_base_is_the_body_mesh_not_the_lowest_prop_or_door(self):
        r = self.out["report"][0]
        self.assertAlmostEqual(r["bottom_cm"], self.mean_ground + 120, delta=1)

    def test_floating_house_is_moved_down_onto_the_mean_ground_minus_sink(self):
        mv = self.out["phases"][1]["calls"][0]
        self.assertEqual(mv[0], "level.batch_translate")
        self.assertEqual(mv[1]["actorLabels"], ["House"])
        self.assertAlmostEqual(mv[1]["offset"]["z"], -(120 + 2), delta=8)

    def test_slope_under_the_footprint_is_flattened_and_far_ground_is_untouched(self):
        pad = self.out["phases"][0]["calls"]
        self.assertGreater(len(pad), 0)
        new = self.out["heights"].astype(float) / RPC + Z0
        foot = new[48:53, 47:54]
        self.assertLess(float(foot.max() - foot.min()), 12.0)
        self.assertTrue((self.out["heights"][:, :20] == self.h[:, :20]).all())
        self.assertTrue((self.out["heights"][:, 80:] == self.h[:, 80:]).all())

    def test_flat_ground_gets_a_move_but_no_pad(self):
        flat = np.full((N, N), 4000, np.uint16)
        comps = {"Shed": [comp("SM_BLD_body_02", 30, 30, 1, 1000 + 1000 + 50)]}
        out = ugf.fit(comps, flat, SIZE_M, Z0, RPC)
        self.assertEqual(out["phases"][0]["calls"], [])
        self.assertAlmostEqual(out["phases"][1]["calls"][0][1]["offset"]["z"], -52, delta=1)

    def test_actor_already_on_the_ground_is_not_moved(self):
        flat = np.full((N, N), 4000, np.uint16)
        comps = {"Well": [comp("SM_BLD_body_03", 30, 30, 1, 2000 - 2)]}
        out = ugf.fit(comps, flat, SIZE_M, Z0, RPC)
        self.assertEqual(out["phases"][1]["calls"], [])

    def test_actor_without_meshes_is_reported_not_crashed(self):
        out = ugf.fit({"Empty": []}, self.h, SIZE_M, Z0, RPC)
        self.assertIn("skipped", out["report"][0])


if __name__ == "__main__":
    unittest.main()
