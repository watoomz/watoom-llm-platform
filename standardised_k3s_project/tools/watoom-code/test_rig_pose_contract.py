import unittest, copy
from rig_pose_contract import validate


class RigContract(unittest.TestCase):
    def setUp(self):
        self.v = {
            "schema": "watoom.rig_pose.v1",
            "adapter": "shadowheart-mhx-v1",
            "armature": "Shadowheart",
            "targets": {"hand.L": [0.4, -0.2, 1.2]},
        }

    def test_fixed_route(self):
        validate(self.v)

    def test_foreign_adapter_and_commands(self):
        for key, val in [
            ("adapter", "unknown"),
            ("armature", "Other"),
            ("script", "evil.py"),
            ("properties", {"MhaArbitrary": 1}),
        ]:
            v = copy.deepcopy(self.v)
            v[key] = val
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate(v)

    def test_unmapped_controls(self):
        v = copy.deepcopy(self.v)
        v["controls"] = {"arbitrary-bone": {"world_position": [0, 0, 0]}}
        with self.assertRaises(ValueError):
            validate(v)

    def test_conflicting_ik_fk(self):
        v = copy.deepcopy(self.v)
        v["switches"] = {"arm.L": "FK"}
        with self.assertRaises(ValueError):
            validate(v)

    def test_explicit_fk(self):
        v = {
            "schema": "watoom.rig_pose.v1",
            "adapter": "shadowheart-mhx-v1",
            "armature": "Shadowheart",
            "controls": {"upper_arm.fk.L": {"rotation_euler": [0.2, 0, 0]}},
        }
        with self.assertRaises(ValueError):
            validate(v)
        v["switches"] = {"arm.L": "FK"}
        validate(v)

    def test_locked_pole_rotation_and_hand_translation(self):
        for role, edit in [("knee.L", {"rotation_euler": [0, 0, 0]}), ("hand_ik.L", {"world_position": [0, 0, 0]})]:
            v = copy.deepcopy(self.v)
            v["controls"] = {role: edit}
            with self.subTest(role=role), self.assertRaises(ValueError):
                validate(v)

    def test_finite_bounded_target(self):
        for point in [[float("inf"), 0, 0], [True, 0, 0], [0, 0], [-10001, 0, 0]]:
            v = copy.deepcopy(self.v)
            v["targets"]["hand.L"] = point
            with self.subTest(point=point), self.assertRaises(ValueError):
                validate(v)

    def test_ik_handle_mode_conflict(self):
        v = copy.deepcopy(self.v)
        v.pop("targets")
        v["controls"] = {"hand_ik.L": {"rotation_euler": [0, 0.1, 0]}}
        v["switches"] = {"arm.L": "FK"}
        with self.assertRaises(ValueError):
            validate(v)
        v["switches"]["arm.L"] = "IK"
        validate(v)

    def test_hips_and_poles(self):
        v = copy.deepcopy(self.v)
        v["controls"] = {"hips": {"world_position": [0, 0.3, 0.6]}, "knee.L": {"world_position": [0.1, -0.5, 0.4]}}
        validate(v)

    def test_tolerance_budget(self):
        for val in [0, 0.031, float("nan"), True]:
            v = copy.deepcopy(self.v)
            v["tolerance"] = val
            with self.subTest(val=val), self.assertRaises(ValueError):
                validate(v)


if __name__ == "__main__":
    unittest.main()
