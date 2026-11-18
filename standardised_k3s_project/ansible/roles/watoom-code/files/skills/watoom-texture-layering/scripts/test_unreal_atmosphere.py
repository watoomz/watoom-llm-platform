import importlib.util
import json
import os
import tempfile
import pathlib
import unittest

spec = importlib.util.spec_from_file_location("ua", pathlib.Path(__file__).with_name("unreal_atmosphere.py"))
ua = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ua)


def phase(calls, name):
    return [p for p in calls["phases"] if p["name"] == name][0]["calls"]


class Atmosphere(unittest.TestCase):
    def test_exposure_is_locked_with_override_flags(self):
        (m, a), = phase(ua.build(exposure=0.5), "exposure")
        self.assertEqual(m, "level.set_post_process_settings")
        self.assertTrue(a["enableOverrides"])  # a post-process value without its bOverride_ flag is ignored
        self.assertEqual(a["settings"]["AutoExposureMinBrightness"], a["settings"]["AutoExposureMaxBrightness"])

    def test_nebula_is_dimmed_on_the_material_never_through_the_dome_actor(self):
        c = ua.build(nebula=3, nebula_power=1.6)
        neb = phase(c, "nebula")
        self.assertTrue(all(x[0] == "material.set_parameter" and x[1]["assetPath"].endswith("MI_Star_Nebula_03") for x in neb))
        self.assertEqual({x[1]["parameterName"] for x in neb}, {"Power", "Power_Extra_Cubemap"})
        # nothing may move the dome or set its blueprint variables: that reruns its construction script and drops the nebula MI
        every = [x for p in c["phases"] for x in p["calls"]]
        self.assertFalse([x for x in every if x[0] in ("level.move_actor", "editor.set_property")])

    def test_dome_override_is_restored_last_before_the_save(self):
        last = ua.build()["phases"][-1]["calls"]
        self.assertEqual(last[0][0], "level.bulk_set_component_property")
        self.assertTrue(last[0][1]["value"][0].endswith("MI_Star_Nebula_02.MI_Star_Nebula_02"))
        self.assertEqual(last[-1][0], "level.save")

    def test_clouds_use_a_project_instance_and_a_low_layer(self):
        cl = phase(ua.build(cloud_coverage=0.2), "clouds")
        ci = cl[0][1]
        self.assertEqual((ci["packagePath"], ci["name"]), ("/Game/ZAS/Sky", "MI_ZAS_Clouds"))
        self.assertTrue(ci["parentPath"].startswith("/Engine/EngineSky/VolumetricClouds/"))
        self.assertEqual(cl[1][1]["value"], 0.2)
        props = {x[1]["propertyName"]: x[1]["value"] for x in cl if x[0] == "level.set_component_property"}
        self.assertLess(props["LayerBottomAltitude"], 5)  # the 5 km default hides behind the 20 km dome
        self.assertTrue(props["bCastCloudShadows"])

    def test_parts_can_be_left_out_and_actors_are_placed_idempotently(self):
        c = ua.build(atmosphere=None, clouds=None, fog=None)
        self.assertEqual([p["name"] for p in c["phases"]], ["exposure", "nebula", "dome_and_save"])
        full = ua.build()
        places = [x[1] for p in full["phases"] for x in p["calls"] if x[0] == "level.place_actor"]
        self.assertEqual(len(places), 3)
        self.assertTrue(all(p["onConflict"] == "skip" for p in places))

    def test_fog_sits_at_the_given_height(self):
        f = phase(ua.build(fog_z=4849.0), "fog")
        self.assertEqual(f[0][1]["location"]["z"], 4849.0)

    def test_a_game_without_the_nebula_dome_gets_no_dome_calls_and_full_haze(self):
        c = ua.build(dome=None)
        self.assertEqual([p["name"] for p in c["phases"]], ["exposure", "atmosphere", "clouds", "fog", "save"])
        every = [x for p in c["phases"] for x in p["calls"]]
        self.assertFalse([x for x in every if "Nebula" in json.dumps(x) or x[1].get("componentName") == "Dome"])
        haze = [x for x in phase(c, "atmosphere") if x[0] == "level.set_component_property"][0][1]["value"]
        self.assertEqual(haze, 1.0)
        self.assertEqual([x for x in phase(ua.build(), "atmosphere") if x[0] == "level.set_component_property"][0][1]["value"], 0.35)

    def test_labels_paths_and_heights_come_from_the_project_profile(self):
        with tempfile.TemporaryDirectory() as d:
            prof, out = os.path.join(d, "p.json"), os.path.join(d, "o.json")
            json.dump({"label_prefix": "Fort_", "content_root": "/Game/Fort", "sea_cm": 120.0, "size_m": 1000,
                       "sky_dome_label": "", "exposure": 0.7}, open(prof, "w"))
            self.assertEqual(ua.main(["--out", out, "--project", prof]), 0)
            c = json.load(open(out))
        every = [x for p in c["phases"] for x in p["calls"]]
        labels = {x[1].get("actorLabel") or x[1].get("label") for x in every} - {None}
        self.assertEqual(labels, {"Fort_PostProcess", "Fort_Atmosphere", "Fort_Clouds", "Fort_Sun", "Fort_HeightFog"})
        self.assertEqual(phase(c, "exposure")[0][1]["settings"]["AutoExposureMinBrightness"], 0.7)
        self.assertEqual(phase(c, "clouds")[0][1]["packagePath"], "/Game/Fort/Sky")
        fog = phase(c, "fog")[0][1]["location"]
        self.assertEqual((fog["x"], fog["y"], fog["z"]), (50000.0, 50000.0, 120.0))
        self.assertNotIn("ZAS", json.dumps(c))


if __name__ == "__main__":
    unittest.main()
