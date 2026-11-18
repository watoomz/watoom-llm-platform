import base64
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rig_project_plugins as pp  # noqa: E402

UP = {"FileVersion": 3, "Plugins": [{"Name": "MeshPartitionWater", "Enabled": True}, {"Name": "WaterAdvanced", "Enabled": True},
                                    {"Name": "Niagara", "Enabled": True}]}


class Plugins(unittest.TestCase):
    def test_only_named_plugins_change_and_missing_ones_are_added(self):
        want = {"MeshPartitionWater": False, "GameplayAbilities": True, "Niagara": True}
        self.assertEqual(pp.diff(UP, want), [("GameplayAbilities", None, True), ("MeshPartitionWater", True, False)])
        out = pp.patched(UP, want)
        names = {p["Name"]: p["Enabled"] for p in out["Plugins"]}
        self.assertEqual(names, {"MeshPartitionWater": False, "WaterAdvanced": True, "Niagara": True, "GameplayAbilities": True})
        self.assertTrue(UP["Plugins"][0]["Enabled"])          # the input is not modified
        self.assertEqual(pp.diff(out, want), [])

    def test_repo_spec_keeps_the_foliage_crash_plugin_off_with_a_reason(self):
        with open(pp.SPEC) as f:
            spec = json.load(f)
        mpw = [p for p in spec["plugins"] if p["name"] == "MeshPartitionWater"][0]
        self.assertFalse(mpw["enabled"])
        self.assertIn("T-0061", mpw["why"])
        self.assertTrue(all(p.get("why") for p in spec["plugins"]))

    def test_write_refuses_while_the_editor_runs_and_keeps_a_backup(self):
        ps = pp.write_ps('{"a": 1}', "F:/P/Game/Game.uproject")
        self.assertIn("exit 3", ps)
        self.assertLess(ps.index("exit 3"), ps.index("WriteAllText"))
        self.assertIn(".bak", ps)
        b64 = ps.split("FromBase64String('")[1].split("'")[0]
        self.assertEqual(base64.b64decode(b64).decode(), '{"a": 1}')


if __name__ == "__main__":
    unittest.main()
