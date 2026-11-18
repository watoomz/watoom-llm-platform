import os, sys, unittest
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unreal_ground_paint as gp

PX = 800.0


def base(n=40):
    w = {"grass": np.full((n, n), 20, np.uint8), "dry_grass": np.full((n, n), 120, np.uint8), "dirt": np.full((n, n), 60, np.uint8), "mud": np.zeros((n, n), np.uint8)}
    z = np.full((n, n), 6000.0)
    return w, z


class Paint(unittest.TestCase):
    def total(self, w):
        return sum(w[k].astype(int) for k in gp.LAYERS)

    def test_total_per_pixel_is_preserved_and_grass_grows_on_gentle_land(self):
        w, z = base()
        new = gp.plan(w, z, PX, np.full(z.shape, np.inf), 4849.0)
        self.assertTrue((self.total(new) == self.total(w)).all())
        self.assertGreater(new["grass"].mean(), w["grass"].mean() + 100)
        self.assertLess(new["dry_grass"].mean(), 30)

    def test_steep_ground_and_sea_level_ground_are_left_alone(self):
        w, z = base()
        z[:, 20:] += np.arange(20)[None, :] * 1000.0  # slope 1.25
        z[:5, :] = 4900.0  # barely above the sea
        new = gp.plan(w, z, PX, np.full(z.shape, np.inf), 4849.0)
        self.assertTrue((new["dry_grass"][10:, 30:] == w["dry_grass"][10:, 30:]).all())
        self.assertTrue((new["dry_grass"][:4, :10] == w["dry_grass"][:4, :10]).all())

    def test_mud_is_strongest_at_the_creek_and_fades_out(self):
        w, z = base()
        dist = np.abs(np.arange(40) - 5)[None, :].repeat(40, 0) * PX  # creek along column 5
        new = gp.plan(w, z, PX, dist, 4849.0, swamp_cm=6000.0, half_cm=2400.0)
        self.assertTrue(new["mud"][10, 5] > 150)  # in the channel
        self.assertTrue(new["mud"][10, 5] > new["mud"][10, 9] > new["mud"][10, 12])
        self.assertEqual(int(new["mud"][10, 30]), 0)  # far away: none
        self.assertTrue((self.total(new) == self.total(w)).all())

    def test_calls_cover_changed_tiles_and_layers_only(self):
        w, z = base()
        new = gp.plan(w, z, PX, np.full(z.shape, np.inf), 4849.0)
        ph = gp.calls_for(w, new)[0]
        self.assertEqual(ph["name"], "paint")
        self.assertEqual({c[1]["layerName"] for c in ph["calls"]}, {"grass", "dry_grass", "dirt"})  # mud untouched here
        self.assertEqual(ph["calls"][0][0], "landscape.set_layer_weight_region")


class SlopePass(unittest.TestCase):
    def setup(self, n=60):
        w = {"grass": np.full((n, n), 100, np.uint8), "dry_grass": np.full((n, n), 20, np.uint8), "dirt": np.full((n, n), 10, np.uint8),
             "mud": np.full((n, n), 60, np.uint8), "rock": np.zeros((n, n), np.uint8), "sand": np.full((n, n), 30, np.uint8)}
        z = np.full((n, n), 6000.0)
        z += np.maximum(np.arange(n) - 30, 0)[None, :] * 900.0  # flat for 30 columns, then a steep ramp (slope ~1.1)
        return w, z

    def test_total_preserved_sand_untouched_and_steep_side_gets_rock(self):
        w, z = self.setup()
        new = gp.slope_pass(w, z, PX, 4849.0)
        tot = lambda d: sum(d[k].astype(int) for k in d)
        self.assertTrue((tot(new) == tot(w)).all())
        self.assertTrue((new["sand"] == w["sand"]).all())
        self.assertEqual(int(new["rock"][:, :20].sum()), 0)  # flat side: no rock
        self.assertGreater(new["rock"][:, 45:].mean(), 60)  # steep side: rock
        self.assertLess(new["grass"][:, 45:].mean(), w["grass"][:, 45:].mean() / 2)

    def test_edge_is_broken_up_by_noise_not_a_straight_contour(self):
        w, z = self.setup()
        new = gp.slope_pass(w, z, PX, 4849.0, dirt_slope=(0.05, 0.2), rock_slope=(0.4, 1.4))
        mid = new["rock"][:, 31:40].astype(int)
        self.assertGreater(mid.std(), 3)  # varies along the edge rows, so patchy

    def test_underwater_ground_is_left_alone_and_rock_layer_is_required(self):
        w, z = self.setup()
        new = gp.slope_pass(w, z, PX, 1e9)  # the whole map is under the sea
        self.assertEqual(int(new["rock"].sum()), 0)
        del w["rock"]
        with self.assertRaises(ValueError):
            gp.slope_pass(w, z, PX, 4849.0)

    def test_noise_is_deterministic_per_seed(self):
        self.assertTrue((gp.fbm((30, 30), 3) == gp.fbm((30, 30), 3)).all())
        self.assertFalse((gp.fbm((30, 30), 3) == gp.fbm((30, 30), 4)).all())


if __name__ == "__main__":
    unittest.main()
