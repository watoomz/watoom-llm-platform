import importlib.util
import os
import pathlib
import tempfile
import unittest

import numpy as np
from PIL import Image

spec = importlib.util.spec_from_file_location("uss", pathlib.Path(__file__).with_name("unreal_scene_scatter.py"))
uss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uss)

RECIPE = {"package": "/Game/T/Foliage", "seed": 3, "grass_spacing_px": 10, "forest_count": 6, "rock_count": 4,
          "grass": ["/Game/P/SM_Grass_A"], "trees": ["/Game/P/SM_Tree_A", "/Game/P/SM_Tree_B"], "bushes": ["/Game/P/SM_Bush"],
          "flowers": ["/Game/P/SM_Flower"], "rocks": ["/Game/P/SM_Rock"],
          "village": {"houses": ["/Game/P/BP_House.BP_House_C"], "props": ["/Game/P/BP_Well.BP_Well_C"]}}


def make(n=253, creek=False):
    d = tempfile.mkdtemp()
    y, x = np.mgrid[0:n, 0:n]
    Image.fromarray((20000 + x * 20 + y * 10).astype(np.uint16)).save(os.path.join(d, "heightmap16.png"))
    np.full(n * n, 255, np.uint8).tofile(os.path.join(d, "grass.u8"))
    r = np.zeros((n, n), np.uint8)
    r[30:60, 30:60] = 255
    r.tofile(os.path.join(d, "rock.u8"))
    if creek:
        m = np.zeros((n, n), np.uint8)
        m[:, 100:140] = 255
        m.tofile(os.path.join(d, "creek_mask.u8"))
    return d


class Scatter(unittest.TestCase):
    def test_phase_order_puts_forest_and_rocks_before_grass(self):
        out = uss.build(make(), 2000.0, 3000.0, 15000.0, RECIPE)
        self.assertEqual([p["name"] for p in out["phases"]],
                         ["create_types", "type_settings", "add_types_to_level", "forest", "rocks", "village", "creek_trees", "creek_rocks", "creek_biomes", "coast_rocks", "bank_pebbles", "flowers", "grass"])
        self.assertTrue(all(len(p["calls"]) > 0 for p in out["phases"] if not p["name"].startswith(("creek_", "coast_", "bank_"))))

    def test_trees_are_upright_and_grass_is_culled_and_scaled(self):
        out = uss.build(make(), 2000.0, 3000.0, 15000.0, RECIPE)
        st = {a["foliageTypePath"].rsplit("/", 1)[-1]: a["settings"] for _, a in out["phases"][1]["calls"]}
        self.assertEqual(st["FT_SM_Tree_A"]["AlignToNormal"], "False")
        self.assertIn("ZOffset", st["FT_SM_Tree_A"])
        self.assertIn("CullDistance", st["FT_SM_Grass_A"])
        self.assertEqual(st["FT_SM_Grass_A"]["AlignToNormal"], "True")

    def test_scenery_avoids_the_creek_mask(self):
        n = 253
        out = uss.build(make(n, creek=True), 2000.0, 3000.0, 15000.0, RECIPE)
        cm = out["pixel_cm"]
        grass_x = [a["center"]["x"] / cm for p in out["phases"] if p["name"] == "grass" for _, a in p["calls"]]
        self.assertTrue(grass_x)
        self.assertFalse(any(100 <= x < 140 for x in grass_x))

    def test_village_calls_use_blueprint_classes_with_ground_z(self):
        out = uss.build(make(), 2000.0, 3000.0, 15000.0, RECIPE)
        v = [a for p in out["phases"] if p["name"] == "village" for _, a in p["calls"]]
        self.assertEqual(len(v), 2)
        self.assertTrue(all(a["actorClass"].endswith("_C") and 3000.0 <= a["location"]["z"] <= 15000.0 for a in v))

class MaskSize(unittest.TestCase):
    def test_a_mask_of_the_wrong_size_is_refused_naming_both_sizes(self):
        d = make(253, creek=True)
        np.zeros(505 * 505, np.uint8).tofile(os.path.join(d, "creek_mask.u8"))  # a mask made for another landscape size
        with self.assertRaises(ValueError) as e:
            uss.build(d, 4000.0, 3000.0, 15000.0, RECIPE)
        msg = str(e.exception)
        self.assertIn("creek_mask.u8", msg)
        self.assertIn(str(505 * 505), msg)
        self.assertIn("253 x 253", msg)


class CreekBanks(unittest.TestCase):
    def setUp(self):
        self.n = 253
        self.d = make(self.n, creek=True)
        b = np.zeros((self.n, self.n), np.uint8)
        b[:, 94:104] = 2   # pebble bank code 1 + 1: lies inside the creek mask (100:140) as in the real layout
        b[:, 136:146] = 5  # stone bank code 4 + 1
        b.tofile(os.path.join(self.d, "creek_bank.u8"))
        self.out = uss.build(self.d, 2000.0, 3000.0, 15000.0, dict(RECIPE, creek_tree_count=40, creek_rock_count=20))
        self.cm = 2000.0 * 100 / (self.n - 1)

    def calls(self, name):
        return [p for p in self.out["phases"] if p["name"] == name][0]["calls"]

    def test_trees_line_the_creek_but_not_in_it(self):
        trees = self.calls("creek_trees")
        self.assertGreater(len(trees), 10)
        for m, a in trees:
            px = a["center"]["x"] / self.cm
            self.assertTrue(px < 100 or px >= 140, "tree site inside the channel: %.1f" % px)
            self.assertTrue(80 < px < 160, "tree site too far from the creek: %.1f" % px)

    def test_rocks_sit_on_pebble_and_stone_banks(self):
        rocks = self.calls("creek_rocks")
        self.assertGreater(len(rocks), 0)
        for m, a in rocks:
            px = a["center"]["x"] / self.cm
            self.assertTrue(93 < px < 105 or 135 < px < 147, px)

    def test_no_creek_means_no_creek_phases_content(self):
        out = uss.build(make(), 2000.0, 3000.0, 15000.0, RECIPE)
        self.assertEqual([len(p["calls"]) for p in out["phases"] if p["name"].startswith("creek_")], [0, 0, 0])

    def test_clear_first_removes_every_recipe_type_before_anything_is_placed(self):
        d = make()
        out = uss.build(d, 4000.0, 3000.0, 15000.0, dict(RECIPE, clear_first=True))
        self.assertEqual(out["phases"][0]["name"], "clear")
        calls = out["phases"][0]["calls"]
        self.assertTrue(all(c[0] == "foliage.remove_type_from_level" and c[1]["force"] for c in calls))
        self.assertEqual(len(calls), len(out["phases"][1]["calls"]))  # one per created type
        self.assertEqual(uss.build(d, 4000.0, 3000.0, 15000.0, RECIPE)["phases"][0]["name"], "create_types")


class IslandScatter(unittest.TestCase):
    def island(self, n=253):
        d = make(n, creek=True)
        sea = np.zeros((n, n), np.uint8)
        sea[:, :60] = 255  # the west is sea
        sea.tofile(os.path.join(d, "island_under.u8"))
        beach = np.zeros((n, n), np.uint8)
        beach[:, 60:72] = 255
        beach.tofile(os.path.join(d, "island_beach.u8"))
        cliff = np.zeros((n, n), np.uint8)
        cliff[20:60, 225:240] = 255
        cliff.tofile(os.path.join(d, "island_cliff.u8"))
        bank = np.zeros((n, n), np.uint8)
        bank[:, 98:102] = 2
        bank.tofile(os.path.join(d, "creek_bank.u8"))
        return d

    def sites(self, out, phase):
        c = [x for x in out["phases"] if x["name"] == phase][0]["calls"]
        return [(k[1]["center"]["x"], k[1]["center"]["y"]) for k in c]

    def test_trees_and_grass_keep_off_the_sea_and_the_beach(self):
        d = self.island()
        rec = dict(RECIPE, forest_count=40, forest_sep_px=4)
        out = uss.build(d, 4000.0, 3000.0, 15000.0, rec)
        cm = out["pixel_cm"]
        for ph in ("forest", "grass"):
            xs = [x / cm for x, _ in self.sites(out, ph)]
            self.assertTrue(xs and min(xs) > 56, ph)  # grass sites are jittered by a few pixels at most; the sea and beach start at 0..72

    def test_coast_rocks_sit_on_beach_cliff_or_water_edge_only(self):
        d = self.island()
        out = uss.build(d, 4000.0, 3000.0, 15000.0, dict(RECIPE, coast_rock_count=30))
        cm = out["pixel_cm"]
        pts = [(x / cm, y / cm) for x, y in self.sites(out, "coast_rocks")]
        self.assertGreater(len(pts), 5)
        for x, y in pts:
            on_beach = 60 <= x <= 73
            on_cliff = 224 <= x <= 240 and 19 <= y <= 60
            on_shore = 58 <= x <= 64
            self.assertTrue(on_beach or on_cliff or on_shore, (x, y))

    def test_bank_pebbles_follow_the_painted_bank(self):
        d = self.island()
        out = uss.build(d, 4000.0, 3000.0, 15000.0, dict(RECIPE, pebbles=["/Game/P/SM_Pebble"], bank_pebble_count=30))
        cm = out["pixel_cm"]
        pts = [x / cm for x, _ in self.sites(out, "bank_pebbles")]
        self.assertGreater(len(pts), 5)
        self.assertTrue(all(97 <= x <= 142 for x in pts))  # the painted bank or the ring around the creek mask
        types = [c[1]["foliageTypePath"] for c in [p for p in out["phases"] if p["name"] == "bank_pebbles"][0]["calls"]]
        self.assertTrue(all(t.endswith("FT_SM_Pebble") for t in types))

    def test_reads_other_heightmap_and_layer_directory(self):
        d = self.island()
        Image.fromarray(np.full((253, 253), 30000, np.uint16)).save(os.path.join(d, "heightmap16_creeks.png"))
        ld = os.path.join(d, "with_creeks")
        os.makedirs(ld)
        np.zeros(253 * 253, np.uint8).tofile(os.path.join(ld, "grass.u8"))  # no grass anywhere in the final weights
        out = uss.build(d, 4000.0, 3000.0, 15000.0, RECIPE, heights="heightmap16_creeks.png", layers_dir=ld)
        self.assertEqual([p for p in out["phases"] if p["name"] == "grass"][0]["calls"], [])


if __name__ == "__main__":
    unittest.main()


BIOMES = {"section_m": 300, "band_px": 8, "gap_px": 1, "count": 120, "sep_px": 2, "radius_cm": 600, "mix": 0.0,
          "biomes": [{"name": "palm_fern", "meshes": ["/Game/P/SM_Fern_A", "/Game/P/SM_Fern_B"], "scale": [0.6, 1.1], "per_site": 4},
                     {"name": "reedy", "meshes": ["/Game/P/SM_Reed"], "scale": [0.8, 1.4], "per_site": 7},
                     {"name": "bamboo", "meshes": ["/Game/P/SM_Bamboo"], "scale": [0.5, 0.9], "per_site": 3}]}


class CreekBiomes(unittest.TestCase):
    def setUp(self):
        self.n = 253
        self.cm = 2000.0 * 100 / (self.n - 1)
        self.d = make(self.n, creek=True)
        self.out = uss.build(self.d, 2000.0, 3000.0, 15000.0, dict(RECIPE, creek_biomes=BIOMES))

    def phase(self, name):
        return [p for p in self.out["phases"] if p["name"] == name][0]["calls"]

    def test_every_biome_mesh_gets_a_type_upright_with_its_own_scale(self):
        created = {a["meshPath"] for m, a in self.phase("create_types")}
        for b in BIOMES["biomes"]:
            for mesh in b["meshes"]:
                self.assertIn(mesh, created)
        settings = {a["foliageTypePath"]: a["settings"] for m, a in self.phase("type_settings")}
        reed = settings["/Game/T/Foliage/FT_SM_Reed"]
        self.assertEqual(reed["AlignToNormal"], "False")
        self.assertEqual(reed["ScaleX"], "(Min=0.80,Max=1.40)")
        self.assertEqual(reed["RandomPitchAngle"], "0.0")

    def test_sites_line_the_creek_and_stay_out_of_the_channel(self):
        calls = self.phase("creek_biomes")
        self.assertGreater(len(calls), 20)
        for m, a in calls:
            px = a["center"]["x"] / self.cm
            self.assertTrue(px < 100 or px >= 140, "biome site inside the channel: %.1f" % px)
            self.assertTrue(85 < px < 155, "biome site too far from the creek: %.1f" % px)

    def test_each_section_is_one_biome_when_mix_is_zero(self):
        cell = int(BIOMES["section_m"] * 100.0 / self.cm)
        seen = {}
        for m, a in self.phase("creek_biomes"):
            key = (round(a["center"]["y"] / self.cm) // cell, round(a["center"]["x"] / self.cm) // cell)
            biome = next(b["name"] for b in BIOMES["biomes"] if any(a["foliageTypePath"].endswith("FT_" + x.rsplit("/", 1)[-1]) for x in b["meshes"]))
            seen.setdefault(key, set()).add(biome)
        self.assertTrue(all(len(v) == 1 for v in seen.values()), seen)
        self.assertGreater(len({next(iter(v)) for v in seen.values()}), 1, "all sections got the same biome")

    def test_mix_lets_other_biomes_into_a_section(self):
        out = uss.build(self.d, 2000.0, 3000.0, 15000.0, dict(RECIPE, creek_biomes=dict(BIOMES, mix=1.0, section_m=100000)))
        calls = [p for p in out["phases"] if p["name"] == "creek_biomes"][0]["calls"]
        self.assertGreater(len({a["foliageTypePath"] for m, a in calls}), 2)

    def test_per_site_counts_come_from_the_biome(self):
        for m, a in self.phase("creek_biomes"):
            expected = 7 if a["foliageTypePath"].endswith("FT_SM_Reed") else 3 if a["foliageTypePath"].endswith("FT_SM_Bamboo") else 4
            self.assertEqual(a["count"], expected)

    def test_without_the_recipe_key_nothing_changes(self):
        out = uss.build(self.d, 2000.0, 3000.0, 15000.0, RECIPE)
        self.assertEqual([p for p in out["phases"] if p["name"] == "creek_biomes"][0]["calls"], [])


class BiomeTemplate(unittest.TestCase):
    def test_example_recipe_builds_and_every_mesh_is_a_game_path(self):
        import json
        tpl = json.load(open(os.path.join(os.path.dirname(__file__), "..", "templates", "creek_biomes.example.json")))
        biomes = tpl["creek_biomes"]["biomes"]
        self.assertGreaterEqual(len(biomes), 5)
        for b in biomes:
            self.assertTrue(b["meshes"] and all(m.startswith("/Game/") for m in b["meshes"]), b["name"])
            self.assertEqual(len(b["meshes"]), len(set(b["meshes"])), b["name"])
        out = uss.build(make(253, creek=True), 2000.0, 3000.0, 15000.0, dict(RECIPE, creek_biomes=tpl["creek_biomes"]))
        calls = [p for p in out["phases"] if p["name"] == "creek_biomes"][0]["calls"]
        self.assertGreater(len(calls), 20)
