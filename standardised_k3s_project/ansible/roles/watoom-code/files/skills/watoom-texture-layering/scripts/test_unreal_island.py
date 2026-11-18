import importlib.util
import os
import pathlib
import tempfile
import unittest

import numpy as np
from PIL import Image

spec = importlib.util.spec_from_file_location("ui", pathlib.Path(__file__).with_name("unreal_island.py"))
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)

N, SIZE, Z0, RPC = 129, 1000.0, 1000.0, 4.0


def flat(z_cm=3000.0):
    return np.full((N, N), (z_cm - Z0) * RPC, np.uint16)


class Island(unittest.TestCase):
    def setUp(self):
        self.res = ui.build(flat(), SIZE, Z0, RPC, seed=3, mountain_cm=2000.0, mountain_px=20.0, beach_px=6, cliff_px=2, cliff_cm=400, floor_cm=300)
        self.z = self.res["z"]

    def test_edge_is_sea_and_centre_is_land_so_it_is_an_island(self):
        self.assertTrue((self.z[:3, :] < self.res["sea_cm"]).all() and (self.z[:, :3] < self.res["sea_cm"]).all())
        self.assertGreater(self.z[N // 2, N // 2], self.res["sea_cm"] + 500)

    def test_mountain_is_the_highest_ground_near_the_middle(self):
        my, mx = np.unravel_index(self.z.argmax(), self.z.shape)
        self.assertLess(abs(my - N / 2), N * 0.15)
        self.assertLess(abs(mx - N / 2), N * 0.15)
        self.assertGreater(self.z.max(), 3000 + 1200)

    def test_outline_is_not_a_circle(self):
        land = ~self.res["masks"]["under"]
        yy, xx = np.nonzero(land)
        r = np.hypot(yy - N / 2, xx - N / 2)
        edge = [r[(np.arctan2(yy - N / 2, xx - N / 2) > a) & (np.arctan2(yy - N / 2, xx - N / 2) < a + 0.2)].max() for a in np.linspace(-3, 2.8, 20)]
        self.assertGreater(max(edge) - min(edge), 4.0)

    def test_there_are_beaches_and_cliffs_and_seabed_is_sand(self):
        m = self.res["masks"]
        self.assertGreater(m["beach"].sum(), 20)
        self.assertGreater(m["cliff"].sum(), 5)
        self.assertGreater(self.res["layers"]["sand"][m["under"]].mean(), 0.9)
        self.assertGreater(self.res["layers"]["sand"][m["beach"]].mean(), 0.2)
        self.assertGreater((self.res["layers"]["rock"] + self.res["layers"]["stone"])[m["cliff"]].mean(), 0.5)

    def test_layer_weights_sum_to_one_and_heights_stay_in_range(self):
        tot = sum(self.res["layers"].values())
        self.assertLess(abs(tot - 1).max(), 1e-6)
        self.assertEqual(self.res["heights"].dtype, np.uint16)

    def test_same_seed_is_repeatable_and_other_seed_differs(self):
        a = ui.build(flat(), SIZE, Z0, RPC, seed=3, mountain_cm=2000.0, mountain_px=20.0)["heights"]
        b = ui.build(flat(), SIZE, Z0, RPC, seed=4, mountain_cm=2000.0, mountain_px=20.0)["heights"]
        self.assertTrue((a == ui.build(flat(), SIZE, Z0, RPC, seed=3, mountain_cm=2000.0, mountain_px=20.0)["heights"]).all())
        self.assertFalse((a == b).all())


class Main(unittest.TestCase):
    def test_cli_writes_masks_as_0_or_255_because_the_scatter_reads_them_that_way(self):
        d = tempfile.mkdtemp()
        Image.fromarray(flat()).save(os.path.join(d, "heightmap16.png"))
        self.assertEqual(ui.main(["--ue-dir", d, "--size-m", "1000", "--z0", "1000", "--raw-per-cm", "4", "--seed", "3", "--landscape", "MyLand", "--out", os.path.join(d, "o.json")]), 0)
        import json
        text = open(os.path.join(d, "o.json")).read()
        self.assertNotIn("<landscape label>", text)
        ph = {p["name"]: p["calls"] for p in json.loads(text)["phases"]}
        self.assertTrue(ph["carve"] and all(c[1]["actorLabel"] == "MyLand" for c in ph["carve"]))
        self.assertTrue(all(c[1].get("landscapeName", c[1].get("actorLabel")) == "MyLand" for c in ph["paint"]))
        with self.assertRaises(SystemExit):   # no silent placeholder: the label is required without a profile
            ui.main(["--ue-dir", d, "--size-m", "1000", "--z0", "1000", "--raw-per-cm", "4", "--out", os.path.join(d, "o2.json")])
        for nm in ("under", "beach", "cliff"):
            a = np.fromfile(os.path.join(d, "island_%s.u8" % nm), np.uint8)
            self.assertTrue(set(np.unique(a).tolist()) <= {0, 255}, nm)
        self.assertGreater(int((np.fromfile(os.path.join(d, "island_under.u8"), np.uint8) == 255).sum()), 100)


class Calls(unittest.TestCase):
    def test_phases_carve_only_changed_tiles_and_paint_writes_all_seven_layers(self):
        res = ui.build(flat(), SIZE, Z0, RPC, seed=3)
        d = tempfile.mkdtemp()
        ph = ui.calls_for(res, res["heights"], d, N, ocean_material="/Game/WaterMaterials/Materials/M_Ocean")
        self.assertEqual(ph[0]["calls"], [])  # baseline identical
        ph = ui.calls_for(res, flat(), d, N, ocean_material="/Game/WaterMaterials/Materials/M_Ocean")
        self.assertGreater(len(ph[0]["calls"]), 0)
        names = {c[1]["layerName"] for c in ph[1]["calls"] if c[0] == "landscape.set_layer_weight_region"}
        self.assertEqual(names, set(ui.ISLAND_LAYERS))
        self.assertEqual([c[0] for c in ph[2]["calls"]], ["level.place_actor", "level.set_actor_material"])
        self.assertGreaterEqual(ph[2]["calls"][0][1]["scale"]["x"] * 100 / 100000.0, 20.0)  # km: reaches the horizon, not just the map edge
        args = ph[2]["calls"][0][1]
        self.assertIn("staticMesh", args)  # level.place_actor rejects "mesh": the ocean plane was never placed
        self.assertNotIn("mesh", args)
        tot = sum(np.fromfile(os.path.join(d, "island_layers", nm + ".u8"), np.uint8).astype(int) for nm in ui.ISLAND_LAYERS)
        self.assertTrue((tot == 255).all())


if __name__ == "__main__":
    unittest.main()
