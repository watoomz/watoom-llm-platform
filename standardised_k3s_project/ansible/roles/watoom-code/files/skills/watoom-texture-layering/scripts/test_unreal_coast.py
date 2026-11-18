import os, sys, tempfile, unittest
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unreal_coast as uc

Z0, RPC, SEA = 3677.7, 4.4387, 4849.0


def raw_of(cm):
    return np.round((np.asarray(cm, float) - Z0) * RPC).astype(np.uint16)


class Coast(unittest.TestCase):
    def setUp(self):
        n = 40
        self.n = n
        self.sea = np.zeros((n, n), bool)
        self.sea[:, :8] = True  # sea on the left, land elsewhere
        z = np.full((n, n), SEA + 800.0)
        z[:, :8] = SEA - 300.0
        z[20:24, 20:24] = SEA - 120.0  # inland hollow below the sea level
        self.raw = raw_of(z)

    def test_inland_hollow_is_lifted_above_the_sea_but_the_sea_floor_is_untouched(self):
        new = uc.raise_land(self.raw, self.sea, SEA, Z0, RPC, 150.0)
        zc = new.astype(float) / RPC + Z0
        self.assertTrue((zc[~self.sea] >= SEA + 140).all())
        self.assertTrue((new[self.sea] == self.raw[self.sea]).all())
        self.assertTrue((new[~self.sea] >= self.raw[~self.sea]).all())  # land is never lowered

    def test_distance_is_zero_on_the_sea_and_grows_inland(self):
        d = uc.dist_to(self.sea)
        self.assertEqual(d[5, 3], 0)
        self.assertAlmostEqual(d[5, 10], 3.0, places=3)
        self.assertGreater(d[5, 30], d[5, 15])

    def test_beach_is_sand_near_the_water_not_on_cliffs_and_weights_still_sum_to_255(self):
        cliff = np.zeros((self.n, self.n), np.uint8)
        cliff[30:, :] = 255
        w = uc.beach_weight(self.sea, cliff, 10.0)
        self.assertGreater(w[5, 8], 0.9)
        self.assertLess(w[5, 30], 0.01)
        self.assertEqual(w[35, 9], 0.0)  # cliff
        layers = {k: np.zeros((self.n, self.n)) for k in uc.LAYERS}
        layers["grass"][:] = 0.7
        layers["dirt"][:] = 0.3
        out = uc.repaint(layers, w)
        self.assertTrue((sum(v.astype(int) for v in out.values()) == 255).all())
        self.assertGreater(out["sand"][5, 8], 200)
        self.assertEqual(out["sand"][5, 35], 0)
        self.assertAlmostEqual(int(out["grass"][5, 35]), 0.7 * 255, delta=1)

    def test_calls_only_cover_changed_tiles_and_write_every_layer(self):
        cliff = np.zeros((self.n, self.n), np.uint8)
        layers = {k: np.zeros((self.n, self.n), np.uint8) for k in uc.LAYERS}
        layers["grass"][:] = 255
        new_raw = uc.raise_land(self.raw, self.sea, SEA, Z0, RPC)
        new = uc.repaint({k: v / 255.0 for k, v in layers.items()}, uc.beach_weight(self.sea, cliff))
        ph = uc.calls_for(self.raw, new_raw, layers, new)
        self.assertEqual(len(ph[0]["calls"]), 1)
        self.assertEqual(len(ph[1]["calls"]), len(uc.LAYERS))
        self.assertEqual({c[1]["layerName"] for c in ph[1]["calls"]}, set(uc.LAYERS))
        named = uc.calls_for(self.raw, new_raw, layers, new, "MyLand")
        self.assertTrue(all(c[1]["actorLabel"] == "MyLand" for p in named for c in p["calls"]))  # height tiles name the landscape too


if __name__ == "__main__":
    unittest.main()
