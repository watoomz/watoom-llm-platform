import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location("us", pathlib.Path(__file__).with_name("unreal_sky.py"))
us = importlib.util.module_from_spec(spec)
spec.loader.exec_module(us)


class Sky(unittest.TestCase):
    def test_atmosphere_is_removed_before_the_dome_is_placed(self):
        c = us.build()
        self.assertEqual(c[0], ["level.delete_actor", {"actorLabel": "SkyAtmosphere"}])
        self.assertEqual(c[1][0], "level.place_actor")
        self.assertTrue(c[1][1]["actorClass"].endswith("BP_Star_Dome.BP_Star_Dome_C"))

    def test_dome_is_scaled_into_the_far_clip_and_given_a_nebula_instance(self):
        c = us.build(nebula=3)
        self.assertEqual(c[2][1]["scale"]["x"], 0.00004)
        ov = [x for x in c if x[0] == "level.bulk_set_component_property"][0][1]
        self.assertEqual(ov["componentName"], "Dome")
        self.assertTrue(ov["value"][0].endswith("MI_Star_Nebula_03.MI_Star_Nebula_03"))

    def test_captured_source_is_movable_and_recaptured_for_an_is_sky_material(self):
        c = us.build(sky_source="captured")
        sl = [x for x in c if x[0] == "level.set_light_properties"][0][1]
        self.assertEqual(sl["mobility"], "Movable")
        self.assertTrue(sl["recaptureSky"])
        self.assertAlmostEqual(sl["intensity"], 1.2)
        self.assertFalse([x for x in c if x[0] in ("level.set_component_property", "editor.set_property")])

    def test_default_is_a_specified_cubemap_because_the_star_dome_is_not_is_sky(self):
        c = us.build()
        sl = [x for x in c if x[0] == "level.set_light_properties"][0][1]
        self.assertEqual(sl["mobility"], "Movable")
        self.assertNotIn("recaptureSky", sl)
        props = {x[1]["propertyName"]: x[1] for x in c if x[0] == "level.set_component_property"}
        self.assertEqual(props["SourceType"]["value"], "SLS_SpecifiedCubemap")
        self.assertEqual(props["Cubemap"]["value"], "/Engine/MapTemplates/Sky/DaylightAmbientCubemap.DaylightAmbientCubemap")
        self.assertIs(props["bRealTimeCapture"]["value"], False)
        self.assertTrue(all(p["actorLabel"] == "SkyLight" and p["componentName"] == "SkyLightComponent0" for p in props.values()))
        self.assertEqual(c[-1][0], "level.save")

    def test_component_path_uses_the_verified_editor_set_property_form(self):
        c = us.build(sky_component_path="/Game/Maps/L.L:PersistentLevel.SkyLight_0.SkyLightComponent0")
        sets = [x[1] for x in c if x[0] == "editor.set_property"]
        self.assertEqual([s["propertyName"] for s in sets], ["SourceType", "Cubemap", "bRealTimeCapture"])
        self.assertTrue(all(s["objectPath"].endswith("SkyLightComponent0") for s in sets))
        self.assertFalse([x for x in c if x[0] == "level.set_component_property"])

    def test_cli_flag_selects_the_source_and_unknown_source_is_refused(self):
        import json, os, tempfile
        out = os.path.join(tempfile.mkdtemp(), "s.json")
        self.assertEqual(us.main(["--sky-source", "captured", "--out", out]), 0)
        calls = json.load(open(out))["phases"][0]["calls"]
        self.assertTrue(any(c[0] == "level.set_light_properties" and c[1].get("recaptureSky") for c in calls))
        with self.assertRaises(ValueError):
            us.build(sky_source="static")

    def test_keeping_the_atmosphere_and_bad_nebula(self):
        self.assertEqual(us.build(atmosphere=None)[0][0], "level.place_actor")
        with self.assertRaises(ValueError):
            us.build(nebula=9)


if __name__ == "__main__":
    unittest.main()
