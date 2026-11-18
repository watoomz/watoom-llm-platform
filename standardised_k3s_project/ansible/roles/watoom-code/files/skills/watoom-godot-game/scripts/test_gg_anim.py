"""gg_anim: refusals and spec parsing are pure; `check` needs real asset glbs and the engine, so it is
skipped without godot or when GG_SKIP_ENGINE=1. The rogue retarget/state-machine round trip is verified
manually against the real exported packs (see T-0068's ticket note), not reproduced here since it needs
~180MB of asset glbs this test suite does not carry."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gg_anim
import gg_godot


class Parsing(unittest.TestCase):
    def test_parse_states(self):
        self.assertEqual(gg_anim._parse_states("idle=res://a.glb, walk=res://b.glb"),
                          {"idle": "res://a.glb", "walk": "res://b.glb"})

    def test_parse_states_rejects_bad_entry(self):
        with self.assertRaisesRegex(gg_godot.Refused, "not name=res"):
            gg_anim._parse_states("idle")

    def test_default_transitions_only_include_given_states(self):
        edges = gg_anim._parse_transitions(None, {"idle": "x", "walk": "y"})
        self.assertIn(["idle", "walk"], edges)
        self.assertNotIn(["idle", "jump"], edges)
        for a, b in edges:
            self.assertIn(a, ("idle", "walk"))
            self.assertIn(b, ("idle", "walk"))

    def test_custom_transitions_override_default(self):
        self.assertEqual(gg_anim._parse_transitions("idle-run", {"idle": "x", "run": "y"}), [["idle", "run"]])

    def test_custom_transitions_rejects_bad_entry(self):
        with self.assertRaisesRegex(gg_godot.Refused, "not from-to"):
            gg_anim._parse_transitions("idle", {"idle": "x"})


class Refusals(unittest.TestCase):
    def test_check_refuses_without_project_godot(self):
        import shutil
        import tempfile
        d = tempfile.mkdtemp()
        try:
            with self.assertRaisesRegex(gg_godot.Refused, "no project.godot"):
                gg_anim.check_project(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
