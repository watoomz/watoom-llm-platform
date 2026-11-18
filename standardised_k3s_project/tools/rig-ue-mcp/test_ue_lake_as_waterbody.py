import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_lake_as_waterbody as lw


class Imports(unittest.TestCase):
    def test_reuses_circle_spline_text_and_carve_lake_bank_from_the_river_script(self):
        # no reimplementation: this module must share the exact same circle/carve math as ue_lake_as_river.py
        import ue_lake_as_river as lr
        self.assertIs(lw.circle_spline_text, lr.circle_spline_text)
        self.assertIs(lw.carve_lake_bank, lr.carve_lake_bank)

    def test_has_no_width_curve_helper(self):
        # a lake has no RiverWidth-equivalent -- this module should not define/import a width-curve builder
        self.assertFalse(hasattr(lw, "width_curve"))


class AffectsLandscapeDisabled(unittest.TestCase):
    def test_baffectslandscape_is_set_false_not_true(self):
        # bAffectsLandscape=true fires the Water plugin's OWN automatic landscape brush on rebuild_water_zone (T-0049,
        # 2026-11-18), which fights this script's manual carve_lake_bank() and produced a sea-level-flat lake bed on a live
        # test. Must be False, same as ue_lake_as_river.py's WaterBodyRiver.
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ue_lake_as_waterbody.py")) as f:
            src = f.read()
        self.assertIn('("bAffectsLandscape", False)', src)
        self.assertNotIn('("bAffectsLandscape", True)', src)


class FakeTransport:
    """Stands in for ue_route.SshTransport: records every call, answers with a flat landscape and a configurable set of actors."""
    actors = set()
    log = []

    def __init__(self, cmd):
        self.is_error = False

    def call(self, cat, meth, args=None, timeout=60):
        args = args or {}
        FakeTransport.log.append((meth, args))
        if meth == "get_actor_details":
            label = args["actorLabel"]
            if label in FakeTransport.actors or label == "ZAS_Landscape":
                return json.dumps({"success": True, "actorPath": "/Game/M.M:PersistentLevel.%s" % label, "class": "WaterBodyLake"})
            return json.dumps({"success": False, "error": "no actor"})
        if meth == "place_actor":
            FakeTransport.actors.add(args["label"])
        if meth == "delete_actor":
            FakeTransport.actors.discard(args["actorLabel"])
        if meth == "get_height_region":
            reg = args["region"]
            w, h = reg["maxX"] - reg["minX"] + 1, reg["maxY"] - reg["minY"] + 1
            heights = [32768] * (w * h) if args.get("editLayer") == "Water" else [20000] * (w * h)
            return json.dumps({"region": dict(reg, width=w, height=h), "heights": heights, "rawUnitsPerWorldCm": 4.438741894094393,
                               "height": {"meanZ": 3678.0 + 20000 / 4.438741894094393, "meanRaw": 20000}})
        return json.dumps({"success": True})

    def close(self):
        pass


class Modes(unittest.TestCase):
    ARGS = ["--label", "ZAS_LakeBody_9", "--center-x", "50000", "--center-y", "50000", "--water-z", "8000",
            "--radius-cm", "2000", "--material", "/Game/M"]

    def run_main(self, extra, actors=()):
        FakeTransport.actors = set(actors)
        FakeTransport.log = []
        with mock.patch.object(lw.ue_route, "SshTransport", FakeTransport), mock.patch("sys.stdout"):
            lw.main(self.ARGS + extra)
        return [m for m, _ in FakeTransport.log], FakeTransport.log

    def test_carve_only_never_touches_the_water_body(self):
        methods, _ = self.run_main(["--carve-only"], actors={"ZAS_LakeBody_9"})
        for untouched in ("set_component_property", "set_water_body_property", "move_actor", "place_actor", "delete_actor"):
            self.assertNotIn(untouched, methods)
        self.assertIn("set_height_region", methods)
        self.assertIn("save", methods)

    def test_carve_only_refuses_a_missing_lake(self):
        with self.assertRaises(SystemExit):
            self.run_main(["--carve-only"])

    def test_recreate_deletes_then_places_a_fresh_actor(self):
        methods, _ = self.run_main(["--recreate"], actors={"ZAS_LakeBody_9"})
        self.assertLess(methods.index("delete_actor"), methods.index("place_actor"))
        self.assertIn("move_actor", methods)

    def test_a_plain_rerun_reuses_the_existing_actor(self):
        methods, _ = self.run_main([], actors={"ZAS_LakeBody_9"})
        self.assertNotIn("place_actor", methods)
        self.assertNotIn("delete_actor", methods)

    def test_clear_water_first_writes_neutral_before_the_carve(self):
        _, log = self.run_main(["--carve-only", "--clear-water-first"], actors={"ZAS_LakeBody_9"})
        writes = [a for m, a in log if m == "set_height_region"]
        self.assertEqual(len(writes), 2)
        self.assertTrue(all(v == 32768 for v in writes[0]["heights"]))
        self.assertEqual(writes[0]["region"], writes[1]["region"], "the clear must cover exactly the rectangle the carve writes")

    def test_depth_is_one_scalar_written_as_fixed_water_depth(self):
        _, log = self.run_main(["--depth-cm", "450"])
        depth = [a for m, a in log if m == "set_water_body_property" and a["propertyName"] == "FixedWaterDepth"]
        self.assertEqual([d["value"] for d in depth], [450.0])

    def test_old_label_is_hidden_on_every_run(self):
        # a level.load can un-hide it (T-0049), so every run re-hides it
        FakeTransport.actors = {"Lake_9"}
        _, log = self.run_main(["--carve-only", "--old-label", "Lake_9"], actors={"ZAS_LakeBody_9", "Lake_9"})
        hide = [a for m, a in log if m == "set_editor_visibility"]
        self.assertEqual(hide, [{"hidden": True, "actorLabels": ["Lake_9"]}])

    def test_materials_only_sets_materials_without_spline_move_or_carve(self):
        methods, log = self.run_main(["--materials-only"], actors={"ZAS_LakeBody_9"})
        for untouched in ("set_component_property", "move_actor", "set_height_region", "place_actor", "delete_actor"):
            self.assertNotIn(untouched, methods)
        mats = [a["value"] for m, a in log if m == "set_water_body_property" and a["propertyName"] == "WaterMaterial"]
        self.assertEqual(mats, ["/Game/M"])
        self.assertIn("save", methods)

    def test_materials_only_can_delete_the_old_disc(self):
        _, log = self.run_main(["--materials-only", "--old-label", "Lake_9", "--delete-old"], actors={"ZAS_LakeBody_9", "Lake_9"})
        self.assertIn(("delete_actor", {"actorLabel": "Lake_9"}), log)

    def test_materials_only_refuses_a_missing_lake(self):
        with self.assertRaises(SystemExit):
            self.run_main(["--materials-only"])

    def test_carve_only_and_recreate_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            self.run_main(["--carve-only", "--recreate"], actors={"ZAS_LakeBody_9"})


if __name__ == "__main__":
    unittest.main()
