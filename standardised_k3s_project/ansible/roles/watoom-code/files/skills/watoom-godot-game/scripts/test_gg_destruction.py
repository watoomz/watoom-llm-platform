"""gg_destruction.py without an engine: refusals, the test-wall fixture's layout, init. The engine check itself is
`gg_destruction.py check` (ops/destruction_check.gd), run on a real project."""
import json
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gg_destruction as gd  # noqa: E402


def glb_nodes(path):
    with open(path, "rb") as f:
        data = f.read()
    n = struct.unpack_from("<I", data, 12)[0]
    return [x.get("name", "") for x in json.loads(data[20:20 + n])["nodes"]]


class Destruction(unittest.TestCase):
    def test_fixture_is_an_intact_mesh_and_24_pieces(self):
        names = glb_nodes(gd.FIXTURE)
        self.assertIn("Intact", names)
        self.assertEqual(len([n for n in names if n.startswith("Piece_")]), 24)

    def test_refuses_a_folder_that_is_not_a_project(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(gd.main(["init", "--project", d]), 2)
            self.assertEqual(gd.main(["check", "--project", d]), 2)

    def test_refuses_a_project_without_the_runtime(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "project.godot"), "w").close()
            self.assertEqual(gd.main(["init", "--project", d]), 2)   # names sync-runtime

    def test_init_copies_the_wall_once(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "project.godot"), "w").close()
            os.makedirs(os.path.join(d, "addons", "gg", "game"))
            open(os.path.join(d, "addons", "gg", "game", "destructible.gd"), "w").close()
            self.assertEqual(gd.main(["init", "--project", d]), 0)
            self.assertTrue(os.path.isfile(os.path.join(d, "assets", "destruction", "test_wall.glb")))
            self.assertEqual(gd.main(["init", "--project", d]), 2)                # no silent overwrite
            self.assertEqual(gd.main(["init", "--project", d, "--force"]), 0)

    def test_fracture_refuses_bad_paths_before_starting_blender(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(gd.main(["fracture", "--source", os.path.join(d, "nope.fbx"), "--out", os.path.join(d, "a.glb")]), 2)
            src = os.path.join(d, "w.fbx")
            open(src, "w").close()
            self.assertEqual(gd.main(["fracture", "--source", src, "--out", os.path.join(d, "a.fbx")]), 2)

    def test_fps_and_range_refuse_without_a_project(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(gd.main(["fps", "--project", d]), 2)
            self.assertEqual(gd.main(["range", "--project", d]), 2)

    def test_runtime_and_fracture_script_are_where_the_stage_expects(self):
        rt = os.path.join(os.path.dirname(gd.HERE), "runtime")
        self.assertTrue(os.path.isfile(os.path.join(rt, "game", "destructible.gd")))
        self.assertTrue(os.path.isfile(os.path.join(rt, "ops", "destruction_check.gd")))
        self.assertTrue(os.path.isfile(os.path.join(rt, "game", "fps_weapon.gd")))
        self.assertTrue(os.path.isfile(os.path.join(rt, "ops", "fps_check.gd")))
        self.assertTrue(os.path.isfile(os.path.join(rt, "ops", "build_fps_range.gd")))
        self.assertTrue(os.path.isfile(gd.FRACTURE))


if __name__ == "__main__":
    unittest.main()
