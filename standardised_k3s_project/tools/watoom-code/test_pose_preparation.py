import unittest, tempfile, pathlib, copy
from asset_capture_contract import manifest, sha


class PoseContract(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.t.name)
        p = self.root / "s.blend"
        p.write_bytes(b"fixture")
        self.v = {
            "schema": 1,
            "mode": "pose-prepare",
            "source": str(p),
            "source_sha256": sha(p),
            "preparation": {
                "method": "auto",
                "plan": {
                    "schema": "watoom.human_pose_auto_plan.v1",
                    "armature": "Rig",
                    "targets": {"hand.L": {"point": [1, 0, 1]}},
                },
            },
        }

    def tearDown(self):
        self.t.cleanup()

    def valid(self, v):
        return manifest(v, [self.root])

    def test_inspection_and_auto(self):
        self.valid(self.v)
        v = copy.deepcopy(self.v)
        v.pop("preparation")
        v["mode"] = "pose-inspect"
        self.valid(v)

    def test_no_code_or_mixed_render_fields(self):
        for k, val in [
            ("script", "/tmp/evil.py"),
            ("command", "blender"),
            ("visibility", {"hide": ["clothes"]}),
            ("pose", []),
        ]:
            v = copy.deepcopy(self.v)
            v[k] = val
            with self.subTest(k=k), self.assertRaises(ValueError):
                self.valid(v)

    def test_solver_budgets(self):
        for settings in [
            {"iterations": 181},
            {"full_body_passes": 9},
            {"max_collision_faces_per_mesh": 60001},
            {"max_self_collision_candidates": 100001},
        ]:
            v = copy.deepcopy(self.v)
            v["preparation"]["plan"]["settings"] = settings
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                self.valid(v)

    def test_no_pelvis_or_output_override(self):
        for key, val in [("pelvis_world_position", [0, 0, 1]), ("output", "/tmp/x.blend"), ("script", "evil")]:
            v = copy.deepcopy(self.v)
            v["preparation"]["plan"][key] = val
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.valid(v)

    def test_finite_goals(self):
        v = copy.deepcopy(self.v)
        v["preparation"]["plan"]["targets"]["hand.L"]["point"] = [float("nan"), 0, 0]
        with self.assertRaises(ValueError):
            self.valid(v)

    def test_recipe_review_and_channels(self):
        v = copy.deepcopy(self.v)
        v["preparation"] = {
            "method": "recipe",
            "plan": {
                "schema": "watoom.human_pose_recipe.v1",
                "armature": "Rig",
                "calibration_verified": True,
                "human_reviewed": True,
                "poses": {"Bone": {"rotation_quaternion": [1, 0, 0, 0]}},
            },
        }
        self.valid(v)
        for key, val in [
            ("human_reviewed", False),
            ("calibration_verified", False),
            ("poses", {"Bone": {"allow_constrained": True}}),
        ]:
            bad = copy.deepcopy(v)
            bad["preparation"]["plan"][key] = val
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.valid(bad)

    def test_capture_cannot_smuggle_preparation(self):
        v = copy.deepcopy(self.v)
        v["mode"] = "still"
        with self.assertRaises(ValueError):
            self.valid(v)


if __name__ == "__main__":
    unittest.main()
