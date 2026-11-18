import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_water_fetch as wf  # noqa: E402


def reply(d):
    return "[x] " + json.dumps(d)


def pt(x, y, z):
    return {"worldLocation": {"x": x, "y": y, "z": z}}


class Fetch(unittest.TestCase):
    def call(self, cat, meth, args, what, timeout=120):
        if meth == "get_water_state":
            return reply({"success": True, "bodies": [
                {"actorLabel": "Sea", "actorPath": "/L:P.Ocean_1", "componentClass": "WaterBodyOceanComponent"},
                {"actorLabel": "Creek", "actorPath": "/L:P.River_0", "componentClass": "WaterBodyRiverComponent"},
                {"actorLabel": "Lake", "actorPath": "/L:P.Lake_0", "componentClass": "WaterBodyLakeComponent"}]})
        if meth == "get_actor_details":
            return reply({"success": True, "location": {"x": 0, "y": 0, "z": 4849.26}})
        if meth == "get_spline_info" and args["actorLabel"] == "Creek":
            return reply({"success": True, "points": [pt(0, 0, 9000), pt(1000, 0, 8900), pt(2000, 0, 8800)]})
        if meth == "get_spline_info":
            return reply({"success": True, "points": [pt(1100, 1000, 7000), pt(1000, 1100, 7000), pt(900, 1000, 7000), pt(1000, 900, 7000)]})
        if meth == "get_property":
            self.assertEqual(args["objectPath"], "/L:P.River_0.WaterSplineMetadata")
            return reply({"success": True, "value": {"Points": [{"InVal": 0, "OutVal": 4800}, {"InVal": 2, "OutVal": 3000}]}})
        raise AssertionError(meth)

    def test_fetch_collects_sea_creeks_and_lakes(self):
        w = wf.fetch(self.call)
        self.assertEqual(w["sea_z"], 4849.26)
        self.assertEqual(w["creeks"], [{"label": "Creek", "points": [[0, 0, 9000], [1000, 0, 8900], [2000, 0, 8800]],
                                         "widths_cm": [4800.0, 4800.0, 3000.0]}])
        self.assertEqual(w["lakes"], [{"label": "Lake", "x": 1000.0, "y": 1000.0, "water_z": 7000, "radius_cm": 100.0}])

    def test_an_empty_width_curve_gives_none(self):
        self.assertIsNone(wf.widths({}, 3))


if __name__ == "__main__":
    unittest.main()
