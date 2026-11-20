import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_roam_check as rc  # noqa: E402


class Roam(unittest.TestCase):
    def test_only_placed_wanderers_are_checked(self):
        calls = {"phases": [
            {"name": "characters", "calls": [
                ["blueprint.set_class_default", {"assetPath": "/Game/C/BP_Rex", "propertyName": "Wander.bEnabled", "value": True}],
                ["blueprint.set_class_default", {"assetPath": "/Game/C/BP_Dummy", "propertyName": "TeamId", "value": 2}]]},
            {"name": "place", "calls": [
                ["level.place_actor", {"actorClass": "/Game/C/BP_Rex.BP_Rex_C", "label": "Rex_1"}],
                ["level.place_actor", {"actorClass": "/Game/C/BP_Dummy.BP_Dummy_C", "label": "Dummy_1"}],
                ["level.place_actor", {"actorClass": "StaticMeshActor", "label": "Statue"}],
                ["level.save", {}]]}]}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(calls, f)
        self.assertEqual(rc.wanderers(f.name), ["Rex_1"])

    def test_a_sliding_frozen_mesh_fails_and_a_walker_passes(self):
        roots = [(0, 0, 0), (150, 0, 0), (300, 0, 0)]
        self.assertEqual(rc.judge(roots, [(10, 0, 0)] * 3)[:2], (True, False))      # moves, foot still: T-pose slide
        self.assertEqual(rc.judge(roots, [(10, 0, 0), (30, 0, 5), (10, 0, 0)])[:2], (True, True))
        self.assertEqual(rc.judge([(0, 0, 0)] * 3, [(10, 0, 0), (30, 0, 5)])[:2], (False, True))  # animates in place
        self.assertEqual(rc.judge([], [])[:2], (False, False))


if __name__ == "__main__":
    unittest.main()
