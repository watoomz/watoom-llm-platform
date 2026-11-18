import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_look_check as lc  # noqa: E402

LP = "/Game/Maps/L.L:PersistentLevel"


def reply(d):
    return "[x] " + json.dumps(d)


class Look(unittest.TestCase):
    def setUp(self):
        self.props = {"BP_Star_Dome_C_0.Dome OverrideMaterials": ["/Game/P/MI_Star_Nebula_02.MI_Star_Nebula_02"],
                      "PostProcessVolume_0 Settings.ColorContrast": {"X": 1.25, "Y": 1.25, "Z": 1.25, "W": 1},
                      "PostProcessVolume_0 Settings.bOverride_ColorContrast": True,
                      "SkyLight_0.SkyLightComponent0 SourceType": "SLS_SpecifiedCubemap"}
        self.scalars = [{"name": "Contrast", "value": 2.8}, {"name": "SS Power", "value": 0.03}]
        self.material_reads = 0

    def call(self, cat, meth, args, what, timeout=120):
        if meth == "get_property":
            self.assertTrue(args["objectPath"].startswith(LP + "."))
            key = args["objectPath"][len(LP) + 1:] + " " + args["propertyName"]
            return reply({"success": True, "value": self.props[key]})
        if meth == "read_instance":
            self.material_reads += 1
            return reply({"success": True, "scalarParameters": self.scalars})
        raise AssertionError(meth)

    CHECKS = [{"object": "BP_Star_Dome_C_0.Dome", "property": "OverrideMaterials", "contains": "MI_Star_Nebula_"},
              {"object": "PostProcessVolume_0", "property": "Settings.ColorContrast", "approx": 1.25, "tol": 0.01},
              {"object": "PostProcessVolume_0", "property": "Settings.bOverride_ColorContrast", "equals": True},
              {"object": "SkyLight_0.SkyLightComponent0", "property": "SourceType", "equals": "SLS_SpecifiedCubemap"},
              {"material": "/Game/W/MI_A", "scalar": "Contrast", "approx": 2.8, "tol": 0.005},
              {"material": "/Game/W/MI_A", "scalar": "SS Power", "approx": 0.03, "tol": 0.005}]

    def test_recipe_in_place_has_no_drift(self):
        res = lc.run(self.call, self.CHECKS, LP)
        self.assertTrue(all(ok for _, ok, _ in res))
        self.assertEqual(self.material_reads, 1)  # one read_instance per material, not per parameter

    def test_black_dome_is_drift(self):
        # the 2026-11-18 state: the dome fell back to a dynamic instance of its black base material
        self.props["BP_Star_Dome_C_0.Dome OverrideMaterials"] = ["/Game/L.L:PersistentLevel.BP_Star_Dome_C_0.Dome.MID_M_Star_Nebula_0"]
        bad = [c for c, ok, _ in lc.run(self.call, self.CHECKS, LP) if not ok]
        self.assertEqual([c["property"] for c in bad], ["OverrideMaterials"])

    def test_value_without_override_flag_is_drift(self):
        self.props["PostProcessVolume_0 Settings.bOverride_ColorContrast"] = False
        bad = [c for c, ok, _ in lc.run(self.call, self.CHECKS, LP) if not ok]
        self.assertEqual([c["property"] for c in bad], ["Settings.bOverride_ColorContrast"])

    def test_missing_scalar_and_wrong_number_are_drift(self):
        self.scalars = [{"name": "Contrast", "value": 1.0}]
        bad = [c.get("scalar") for c, ok, _ in lc.run(self.call, self.CHECKS, LP) if not ok]
        self.assertEqual(bad, ["Contrast", "SS Power"])

    def test_default_checks_cover_dome_lights_post_process_and_all_six_leaf_materials(self):
        objs = {c.get("object") for c in lc.DEFAULT_CHECKS}
        self.assertTrue({"BP_Star_Dome_C_0.Dome", "DirectionalLight_0.LightComponent0", "SkyLight_0.SkyLightComponent0",
                         "PostProcessVolume_0"} <= objs)
        self.assertEqual(len({c["material"] for c in lc.DEFAULT_CHECKS if "material" in c and "Leaves" in c["material"]}), 6)

    def test_default_checks_cover_the_atmosphere_setup(self):
        objs = {c.get("object") for c in lc.DEFAULT_CHECKS}
        self.assertTrue({"SkyAtmosphere_0.SkyAtmosphereComponent", "VolumetricCloud_0.VolumetricCloudComponent",
                         "ExponentialHeightFog_0.HeightFogComponent0"} <= objs)
        props = {c.get("property") for c in lc.DEFAULT_CHECKS if c.get("object") == "PostProcessVolume_0"}
        self.assertTrue({"Settings.AutoExposureMinBrightness", "Settings.bOverride_AutoExposureMinBrightness"} <= props)


class FromCalls(unittest.TestCase):
    CALLS = {"phases": [
        {"name": "exposure", "calls": [["level.set_post_process_settings", {"actorLabel": "G_PP", "enableOverrides": True,
                                                                            "settings": {"AutoExposureMinBrightness": 0.7}}]]},
        {"name": "x", "calls": [
            ["level.place_actor", {"actorClass": "/Script/Engine.VolumetricCloud", "label": "G_Clouds"}],
            ["level.set_component_property", {"actorLabel": "G_Clouds", "componentName": "VolumetricCloudComponent",
                                              "propertyName": "Material", "value": "/Game/G/Sky/MI_G_Clouds.MI_G_Clouds"}],
            ["level.set_component_property", {"actorLabel": "G_Sun", "componentName": "LightComponent0", "propertyName": "bCastCloudShadows",
                                              "value": True}],
            ["material.set_parameter", {"assetPath": "/Game/G/Sky/MI_G_Clouds", "parameterName": "Cloud_GlobalCoverage", "value": 0.35}],
            ["level.save", {}]]}]}

    def test_every_value_set_becomes_a_check_and_nothing_else(self):
        cs = lc.checks_from_calls(self.CALLS)
        got = sorted((c.get("label") or c.get("material"), c.get("property") or c.get("scalar")) for c in cs)
        self.assertEqual(got, [("/Game/G/Sky/MI_G_Clouds", "Cloud_GlobalCoverage"), ("G_Clouds", "Material"),
                               ("G_PP", "Settings.AutoExposureMinBrightness"), ("G_PP", "Settings.bOverride_AutoExposureMinBrightness"),
                               ("G_Sun", "bCastCloudShadows")])
        mat = [c for c in cs if c.get("property") == "Material"][0]
        self.assertEqual(mat["contains"], "MI_G_Clouds")

    def test_labels_are_resolved_to_object_paths_once(self):
        seen = []

        def call(cat, meth, args, what, timeout=120):
            seen.append((meth, args.get("actorLabel") or args.get("objectPath")))
            if meth == "get_actor_details":
                return reply({"success": True, "path": "/Game/M.M:PersistentLevel." + args["actorLabel"] + "_0"})
            if meth == "get_property":
                return reply({"success": True, "value": {"Settings.AutoExposureMinBrightness": 0.7}.get(args["propertyName"], True)})
            return reply({"success": True, "scalarParameters": [{"name": "Cloud_GlobalCoverage", "value": 0.35}]})
        cs = [c for c in lc.checks_from_calls(self.CALLS) if c.get("property") != "Material"]
        res = lc.run(call, cs, "/unused")
        self.assertTrue(all(ok for _, ok, _ in res))
        self.assertEqual(sum(1 for m, _ in seen if m == "get_actor_details"), 2)  # G_PP and G_Sun, each once
        self.assertIn(("get_property", "/Game/M.M:PersistentLevel.G_Sun_0.LightComponent0"), seen)


if __name__ == "__main__":
    unittest.main()
