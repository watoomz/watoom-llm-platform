import importlib.util
import os
import pathlib
import tempfile
import unittest

import numpy as np
from PIL import Image

spec = importlib.util.spec_from_file_location("uc", pathlib.Path(__file__).with_name("unreal_creeks.py"))
uc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uc)


def valley(n=127):
    """A V-shaped valley draining toward the bottom edge, rising to both sides and to the top."""
    y, x = np.mgrid[0:n, 0:n]
    h = 20000 + (np.abs(x - n // 2) * 120) + ((n - 1 - y) * 60)
    return np.clip(h, 0, 65535).astype(np.uint16)


class Creeks(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        Image.fromarray(valley()).save(os.path.join(self.d, "heightmap16.png"))
        self.out = uc.build(self.d, 1000.0, 3677.7, 4.4387, "/Game/M_Water", keep=200, min_len=20, sea_m=0.1, max_creeks=2)

    def test_a_creek_follows_the_valley_floor(self):
        self.assertGreaterEqual(len(self.out["creeks"]), 1)
        c = self.out["creeks"][0]
        self.assertTrue(abs(c["start_px"][1] - 63) < 8 and abs(c["end_px"][1] - 63) < 8)

    def test_water_steps_down_and_is_carved_below_the_bank(self):
        c = self.out["creeks"][0]
        self.assertLessEqual(c["water_z_end_cm"], c["water_z_start_cm"])
        old = np.asarray(Image.open(os.path.join(self.d, "heightmap16.png"))).astype(int)
        new = np.asarray(Image.open(os.path.join(self.d, "heightmap16_creeks.png"))).astype(int)
        self.assertGreater(self.out["carved_vertices"], 0)
        self.assertTrue((new <= old).all())

    def test_carve_tiles_and_water_actors_are_written(self):
        names = [p["name"] for p in self.out["phases"]]
        self.assertEqual(names, ["carve", "water"])
        self.assertTrue(all(m == "landscape.set_height_region" and "heightsBase64" in a for m, a in self.out["phases"][0]["calls"]))
        w = self.out["phases"][1]["calls"][0]
        self.assertEqual(w[0], "level.place_actor")
        self.assertEqual(w[1]["material"], "/Game/M_Water")

    def test_creek_mask_is_written_for_the_scatter_script(self):
        m = np.fromfile(os.path.join(self.d, "creek_mask.u8"), np.uint8)
        self.assertEqual(m.size, 127 * 127)
        self.assertGreater(int((m == 255).sum()), 0)

class IrregularBanks(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        n = 127
        Image.fromarray(valley(n)).save(os.path.join(self.d, "heightmap16.png"))
        for nm, v in (("grass", 255), ("dry_grass", 0), ("dirt", 0), ("rock", 0), ("mud", 0)):
            np.full(n * n, v, np.uint8).tofile(os.path.join(self.d, nm + ".u8"))
        self.kw = dict(keep=200, min_len=20, sea_m=0.1, max_creeks=1)
        self.plain = uc.build(self.d, 1000.0, 3677.7, 4.4387, "/Game/M", **self.kw)
        self.plain_h = np.asarray(Image.open(os.path.join(self.d, "heightmap16_creeks.png"))).astype(int)
        self.out = uc.build(self.d, 1000.0, 3677.7, 4.4387, "/Game/M", irregular=True, bank_paint=True, depth_cm=450.0,
                            clean_prefix="Creek_", **self.kw)
        self.irr_h = np.asarray(Image.open(os.path.join(self.d, "heightmap16_creeks.png"))).astype(int)

    def test_deeper_and_not_the_same_as_the_uniform_channel(self):
        self.assertLess(self.irr_h.min(), self.plain_h.min())
        self.assertFalse((self.irr_h == self.plain_h).all())

    def test_water_width_varies_along_the_creek(self):
        widths = {round(a["scale"]["y"], 2) for m, a in self.out["phases"][-1]["calls"] if m == "level.place_actor"}
        self.assertGreater(len(widths), 3)

    def test_bank_sections_are_painted_with_normalised_weights(self):
        names = [p["name"] for p in self.out["phases"]]
        self.assertEqual(names, ["carve", "paint", "water"])
        paint = self.out["phases"][1]
        self.assertIn("sand", paint["layers"])
        self.assertIn("stone", paint["layers"])
        self.assertEqual([c[1]["layerName"] for c in paint["calls"] if c[0] == "landscape.add_layer"], ["sand", "stone"])
        w = [np.fromfile(os.path.join(self.d, "with_creeks", nm + ".u8"), np.uint8).astype(int) for nm in paint["layers"]]
        total = np.sum(w, axis=0)
        self.assertTrue((total == 255).all(), "every pixel must sum to exactly 255 (min %d, max %d)" % (total.min(), total.max()))
        self.assertGreater(int((np.max(w, axis=0) < 255).sum()), 0)  # blended bank pixels exist, so the rounding was exercised
        bank = np.fromfile(os.path.join(self.d, "creek_bank.u8"), np.uint8)
        self.assertGreater(int((bank > 0).sum()), 0)

    def test_calls_carry_the_landscape_label_and_no_placeholder(self):
        import json
        out = uc.build(self.d, 1000.0, 3677.7, 4.4387, "/Game/M", irregular=True, bank_paint=True, depth_cm=450.0, landscape="MyLand", **self.kw)
        self.assertNotIn("<landscape label>", json.dumps(out))
        carve, paint = out["phases"][0]["calls"], out["phases"][1]["calls"]
        self.assertTrue(carve and all(c[1]["actorLabel"] == "MyLand" for c in carve))
        self.assertTrue(all(c[1]["landscapeName"] == "MyLand" for c in paint if c[0] == "landscape.add_layer"))
        self.assertTrue(all(c[1]["actorLabel"] == "MyLand" for c in paint if c[0] == "landscape.set_layer_weight_region"))

    def test_cli_requires_the_landscape_and_takes_it_from_the_profile(self):
        import json
        out = os.path.join(self.d, "c.json")
        base = ["--ue-dir", self.d, "--size-m", "1000", "--z0", "3677.7", "--raw-per-cm", "4.4387", "--material", "/Game/M", "--out", out]
        with self.assertRaises(SystemExit):
            uc.main(base)
        prof = os.path.join(self.d, "p.json")
        json.dump({"landscape": "ProfLand", "water_material": "/Game/Water/MI_River"}, open(prof, "w"))
        self.assertEqual(uc.main(base + ["--project", prof]), 0)
        got = json.load(open(out))
        self.assertTrue(all(c[1]["actorLabel"] == "ProfLand" for c in got["phases"][0]["calls"]))
        water = [c for c in got["phases"][-1]["calls"] if c[0] == "level.place_actor"]
        self.assertTrue(water and all(c[1]["material"] == "/Game/M" for c in water))
        with self.assertRaises(SystemExit):   # the profile's Water-plugin river material is not used for the planes
            uc.main([x for x in base if x not in ("--material", "/Game/M")] + ["--project", prof])

    def test_old_water_is_deleted_first(self):
        first = self.out["phases"][-1]["calls"][0]
        self.assertEqual(first, ["level.delete_actors", {"labelPrefix": "Creek_"}])

    def test_baseline_limits_the_carve_to_changed_tiles(self):
        Image.fromarray(self.irr_h.astype(np.uint16)).save(os.path.join(self.d, "current.png"))
        out = uc.build(self.d, 1000.0, 3677.7, 4.4387, "/Game/M", irregular=True, bank_paint=True, depth_cm=450.0,
                       baseline="current.png", **self.kw)
        self.assertEqual(out["phases"][0]["calls"], [])

class Ribbon(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        Image.fromarray(valley()).save(os.path.join(self.d, "heightmap16.png"))
        self.out = uc.build(self.d, 1000.0, 3677.7, 4.4387, "/Game/M", keep=200, min_len=20, sea_m=0.1, max_creeks=1, irregular=True,
                            ribbon_mesh="/Game/ZAS/Meshes/SM_Water", clean_prefix="Creek_", ribbon_section=10)
        self.ribbon = [p for p in self.out["phases"] if p["name"] == "ribbon"][0]["calls"]

    def test_ribbon_replaces_the_separate_planes(self):
        water = [p for p in self.out["phases"] if p["name"] == "water"][0]["calls"]
        self.assertEqual(water, [["level.delete_actors", {"labelPrefix": "Creek_"}]])

    def test_each_section_is_a_spline_plus_a_spline_mesh_with_the_water_mesh(self):
        kinds = [c[0] for c in self.ribbon]
        self.assertEqual(kinds[0], "level.delete_actors")
        pairs = kinds[1:]
        self.assertGreater(len(pairs), 2)
        self.assertEqual(pairs[0::2], ["level.create_spline_actor"] * (len(pairs) // 2))
        self.assertEqual(pairs[1::2], ["level.build_spline_meshes"] * (len(pairs) // 2))
        mesh = [c[1] for c in self.ribbon if c[0] == "level.build_spline_meshes"][0]
        self.assertEqual(mesh["staticMesh"], "/Game/ZAS/Meshes/SM_Water")
        self.assertEqual(mesh["collisionProfile"], "NoCollision")

    def test_spline_points_follow_the_water_surface_downhill(self):
        sp = [c[1]["splinePoints"] for c in self.ribbon if c[0] == "level.create_spline_actor"]
        zs = [p["z"] for s in sp for p in s]
        self.assertGreaterEqual(zs[0], zs[-1])
        self.assertTrue(all(len(s) >= 2 for s in sp))

    def test_without_ribbon_mesh_there_is_no_ribbon_phase(self):
        out = uc.build(self.d, 1000.0, 3677.7, 4.4387, "/Game/M", keep=200, min_len=20, sea_m=0.1, max_creeks=1)
        self.assertNotIn("ribbon", [p["name"] for p in out["phases"]])

    def test_neighbouring_sections_overlap_by_several_points_so_bends_leave_no_gap(self):
        sp = [c[1]["splinePoints"] for c in self.ribbon if c[0] == "level.create_spline_actor"]
        self.assertGreater(len(sp), 2)
        for a, b in zip(sp, sp[1:]):
            shared = {(round(p["x"], 1), round(p["y"], 1)) for p in a} & {(round(p["x"], 1), round(p["y"], 1)) for p in b}
            self.assertGreaterEqual(len(shared), 4)

    def test_section_width_is_at_least_the_channel_width_with_margin(self):
        scales = [c[1]["scale"]["y"] for c in self.ribbon if c[0] == "level.build_spline_meshes"]
        cm = 1000.0 * 100 / 100  # valley() is 101 px for 1000 m
        self.assertTrue(all(y >= 1.3 * 0.5 * 2 * cm * 1.35 / 100.0 - 1e-6 for y in scales))

    def test_creek_width_and_route_vary_a_lot_when_irregular(self):
        a = uc.build(self.d, 1000.0, 3677.7, 4.4387, "/Game/M", keep=200, min_len=20, sea_m=0.1, max_creeks=1, irregular=True, seed=1, meander_px=0.0)
        b = uc.build(self.d, 1000.0, 3677.7, 4.4387, "/Game/M", keep=200, min_len=20, sea_m=0.1, max_creeks=1, irregular=True, seed=1, meander_px=3.0)
        c = lambda o: [p for p in o["phases"] if p["name"] == "carve"][0]["calls"]
        self.assertNotEqual([x[1]["heightsBase64"] for x in c(a)], [x[1]["heightsBase64"] for x in c(b)])


class Lakes(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        n = 129
        yy, xx = np.mgrid[0:n, 0:n]
        h = (30000 + 220 * (n - 1 - yy) + 60 * np.abs(xx - 64)).astype(np.uint16)  # a valley running down to a coast at the bottom
        h[-12:, :] = 1000
        Image.fromarray(h).save(os.path.join(self.d, "heightmap16.png"))
        os.makedirs(os.path.join(self.d, "isl"))
        for nm in uc.BASE_LAYERS + ["sand", "stone"]:
            (np.full((n, n), 255 if nm == "grass" else 0, np.uint8)).tofile(os.path.join(self.d, "isl", nm + ".u8"))
        self.n = n
        self.out = uc.build(self.d, 1000.0, 3677.7, 4.4387, "/Game/M", keep=300, min_len=20, max_creeks=2, irregular=True, rough=True, bank_paint=True,
                            lakes=True, lake_material="/Game/WaterMaterials/Materials/M_Lake", lake_px=(3.0, 5.0), lake_depth_cm=(300.0, 600.0),
                            lake_margin_px=6, sea_cm=3677.7 + 1200 / 4.4387, layers_dir=os.path.join(self.d, "isl"), seed=4)

    def test_a_creek_head_inside_the_map_gets_a_lake_of_random_size_and_depth(self):
        lk = self.out["lakes"]
        self.assertGreaterEqual(len(lk), 1)
        for l in lk:
            self.assertTrue(3.0 <= l["radius_px"] <= 5.0 and 300 <= l["depth_cm"] <= 600)
        w = [p for p in self.out["phases"] if p["name"] == "water"][0]["calls"]
        self.assertTrue(any(c[0] == "level.place_actor" and c[1]["label"].startswith("Lake_") and "Cylinder" in c[1]["staticMesh"] for c in w))
        self.assertTrue(any(c[0] == "level.bulk_set_component_property" and c[1]["labelPrefix"] == "Lake_" for c in w))

    def test_lake_is_carved_below_its_water_level(self):
        l = self.out["lakes"][0]
        h = np.asarray(Image.open(os.path.join(self.d, "heightmap16_creeks.png"))).astype(float) / 4.4387 + 3677.7
        y, x = l["px"]
        self.assertLess(h[y, x], l["water_cm"] - 100)

    def test_paint_reads_the_island_layers_so_sand_and_stone_are_kept(self):
        p = [x for x in self.out["phases"] if x["name"] == "paint"][0]
        self.assertIn("sand", p["layers"])
        self.assertEqual(p["layers"].count("sand"), 1)
        self.assertEqual(len(p["layers"]), 7)

    def test_bank_codes_interleave_with_rough(self):
        b = np.fromfile(os.path.join(self.d, "creek_bank.u8"), np.uint8)
        self.assertGreaterEqual(len(set(b.tolist()) - {0}), 3)


if __name__ == "__main__":
    unittest.main()
