import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location("ulm", pathlib.Path(__file__).with_name("unreal_landscape_material.py"))
ulm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ulm)


class Build(unittest.TestCase):
    def setUp(self):
        self.out = ulm.build(["grass", "dirt", "rock"], {"grass": "/Game/T_g", "dirt": "/Game/T_d", "rock": "/Game/T_r"}, "/Game/ZAS/M_T", 2.5, 0.9)
        self.nodes = self.out["calls"][1][1]["nodes"]

    def test_layer_names_are_set_through_properties(self):
        samples = [n for n in self.nodes if n["class"] == "MaterialExpressionLandscapeLayerSample"]
        self.assertEqual([s["properties"]["ParameterName"] for s in samples], ["grass", "dirt", "rock"])
        self.assertTrue(all("parameterName" not in s for s in samples))

    def test_blend_is_a_sum_of_all_layers(self):
        adds = [n for n in self.nodes if n["class"] == "MaterialExpressionAdd"]
        self.assertEqual(len(adds), 2)
        self.assertEqual(self.out["calls"][1][1]["propertyConnections"][0]["from"], "add_1")

    def test_material_path_is_split_and_missing_texture_refused(self):
        self.assertEqual(self.out["calls"][0][1], {"name": "M_T", "packagePath": "/Game/ZAS"})
        with self.assertRaises(SystemExit):
            ulm.build(["grass", "dirt"], {"grass": "/Game/T_g"}, "/Game/M", 1, 0.5)


class NormalsAndDetail(unittest.TestCase):
    def setUp(self):
        self.out = ulm.build(["grass", "rock"], {"grass": "/Game/T_g", "rock": "/Game/T_r"}, "/Game/ZAS/M_T", 2.5, 0.9,
                             {"grass": "/Game/T_gn", "rock": "/Game/T_rn"}, 0.11)
        self.args = self.out["calls"][1][1]

    def test_detail_adds_a_second_tiling_pass_per_layer(self):
        uv2 = [n for n in self.args["nodes"] if n["name"] == "uv2"][0]
        self.assertAlmostEqual(uv2["properties"]["UTiling"], 0.275)
        self.assertEqual(len([n for n in self.args["nodes"] if n["name"].startswith("tex2_")]), 2)

    def test_normal_maps_drive_the_normal_property_weighted_by_layer(self):
        props = {p["property"]: p["from"] for p in self.args["propertyConnections"]}
        self.assertIn("Normal", props)
        self.assertEqual(props["Normal"], "nadd_rock")
        ws = [c for c in self.args["connections"] if c["to"] == "nm_grass" and c["toInput"] == "B"]
        self.assertEqual(ws[0]["from"], "w_grass")

    def test_without_options_the_graph_is_unchanged(self):
        out = ulm.build(["grass"], {"grass": "/Game/T_g"}, "/Game/ZAS/M_T", 2.5, 0.9)
        names = [n["name"] for n in out["calls"][1][1]["nodes"]]
        self.assertNotIn("uv2", names)
        self.assertEqual([p["property"] for p in out["calls"][1][1]["propertyConnections"]], ["BaseColor", "Roughness"])

class Macro(unittest.TestCase):
    def setUp(self):
        out = ulm.build(["grass", "dirt"], {"grass": "/Game/T_g", "dirt": "/Game/T_d"}, "/Game/ZAS/M_T", 2.5, 0.9, macro=0.006)
        self.args = out["calls"][1][1]

    def test_macro_samples_at_a_very_large_scale(self):
        uvm = [n for n in self.args["nodes"] if n["name"] == "uvm"][0]
        # one UV unit per quad: repeats across a 505 vertex map = 0.006 * 2.5 * 504 = about 7.6
        self.assertAlmostEqual(uvm["properties"]["UTiling"], 0.015)
        self.assertAlmostEqual(uvm["properties"]["UTiling"] * 504, 7.56)

    def test_macro_defaults_to_the_last_layer_texture_and_multiplies_basecolor(self):
        tm = [n for n in self.args["nodes"] if n["name"] == "tex_macro"][0]
        self.assertEqual(tm["texturePath"], "/Game/T_d")
        props = {p["property"]: p["from"] for p in self.args["propertyConnections"]}
        self.assertEqual(props["BaseColor"], "macro_out")
        feed = [c for c in self.args["connections"] if c["to"] == "macro_out" and c["toInput"] == "A"]
        self.assertEqual(feed[0]["from"], "add_0")

    def test_macro_only_changes_brightness_so_it_is_desaturated(self):
        names = [n["name"] for n in self.args["nodes"]]
        self.assertIn("desat", names)
        feed = [c for c in self.args["connections"] if c["to"] == "macro_k" and c["toInput"] == "A"]
        self.assertEqual(feed[0]["from"], "desat")
        src = [c for c in self.args["connections"] if c["to"] == "desat" and c["toInput"] == "Input"]
        self.assertEqual(src[0]["from"], "tex_macro")

    def test_macro_texture_can_be_chosen(self):
        out = ulm.build(["grass"], {"grass": "/Game/T_g"}, "/Game/ZAS/M_T", 2.5, 0.9, macro=0.006, macro_texture="/Game/T_noise")
        tm = [n for n in out["calls"][1][1]["nodes"] if n["name"] == "tex_macro"][0]
        self.assertEqual(tm["texturePath"], "/Game/T_noise")


class Cli(unittest.TestCase):
    def test_tiling_defaults_to_quad_scale_and_the_checks_use_the_viewport_tool(self):
        import json, os, tempfile
        d = tempfile.mkdtemp()
        json.dump({"layers": [{"name": "grass"}]}, open(os.path.join(d, "layer_report.json"), "w"))
        out = os.path.join(d, "m.json")
        self.assertEqual(ulm.main(["--layers", d, "--textures", "grass=/Game/T_g", "--material", "/Game/M", "--landscape", "Land", "--out", out]), 0)
        got = json.load(open(out))
        uv = [n for n in got["calls"][1][1]["nodes"] if n["name"] == "uv"][0]
        self.assertEqual(uv["properties"]["UTiling"], 2.5)
        self.assertEqual(got["calls"][2][1]["landscapeName"], "Land")
        text = " ".join(got["verify"])
        self.assertIn("ue_viewport_shot.py", text)
        self.assertNotIn("inline: 1600", text)


if __name__ == "__main__":
    unittest.main()
