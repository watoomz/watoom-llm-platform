import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_mesh_body as mb  # noqa: E402


def P(x, y, z):
    return {"x": x, "y": y, "z": z}


BIPED = {"root": P(0, 0, 0), "pelvis": P(0, 0, 95), "head": P(0, 2, 165), "hand_l": P(-80, 0, 140), "hand_r": P(80, 0, 140),
         "thigh_l": P(-10, 0, 90), "thigh_r": P(10, 0, 90), "foot_l": P(-15, -3, 10), "foot_r": P(15, -3, 10),
         "ball_l": P(-15, 13, 3), "ball_r": P(15, 13, 3)}
BIPED_BOUNDS = {"min": P(-85, -20, 0), "max": P(85, 25, 180)}
# a wolf facing +X (head ahead of the root), long body, tail behind, legs at the four corners
WOLF = {"Root": P(0, 0, 60), "Spine01": P(-10, 0, 62), "Head": P(70, 0, 80), "Tail03": P(-120, 0, 50),
        "FrontLeg_L": P(45, -12, 30), "FrontPaw_L": P(48, -12, 2), "FrontLeg_R": P(45, 12, 30), "FrontPaw_R": P(48, 12, 2),
        "BackLeg_L": P(-45, -14, 30), "BackPaw_L": P(-48, -14, 2), "BackLeg_R": P(-45, 14, 30), "BackPaw_R": P(-48, 14, 2)}
WOLF_BOUNDS = {"min": P(-130, -25, 0), "max": P(90, 25, 100)}


class Body(unittest.TestCase):
    def test_biped_faces_by_its_feet_and_arms_do_not_widen_the_capsule(self):
        b = mb.body(BIPED_BOUNDS, BIPED)
        self.assertEqual((b["facing"], b["yaw"]), ("+Y", -90.0))
        self.assertEqual(b["evidence"]["method"], "feet")
        self.assertEqual(b["CapsuleHalfHeight"], 90.0)
        self.assertLess(b["CapsuleRadius"], 40)          # T-pose hands at +-80 cm are not legs
        self.assertIn("Z=-90.000000", b["Mesh.RelativeLocation"])

    def test_quadruped_faces_by_its_head_and_its_length_does_not_widen_the_capsule(self):
        b = mb.body(WOLF_BOUNDS, WOLF)
        self.assertEqual((b["facing"], b["yaw"]), ("+X", 0.0))
        self.assertEqual(b["evidence"]["method"], "head")
        self.assertAlmostEqual(b["CapsuleRadius"], 18.0)  # 0.18 x 100 cm: sideways leg reach 14 x 1.25 = 17.5 is below the floor
        self.assertLessEqual(b["CapsuleRadius"], b["CapsuleHalfHeight"])

    def test_mesh_offset_centres_the_legs_on_the_capsule_after_rotation(self):
        shifted = {n: P(v["x"], v["y"] + 30, v["z"]) for n, v in BIPED.items()}   # whole rig 30 cm along +Y (its forward)
        x = lambda body: float(body["Mesh.RelativeLocation"].split("X=")[1].split(",")[0])  # noqa: E731
        # yaw -90 turns mesh +Y into +X, so moving the rig 30 cm forward moves the mesh offset 30 cm back along X
        self.assertAlmostEqual(x(mb.body(BIPED_BOUNDS, shifted)) - x(mb.body(BIPED_BOUNDS, BIPED)), -30.0, places=4)

    def test_each_axis_maps_to_the_yaw_that_turns_it_to_plus_x(self):
        for axis, (vx, vy) in {"+X": (1, 0), "-X": (-1, 0), "+Y": (0, 1), "-Y": (0, -1)}.items():
            self.assertEqual(mb.snap(vx, vy), axis)
            rx, ry = mb.rotate(vx, vy, mb.YAW[axis])
            self.assertAlmostEqual(rx, 1.0)
            self.assertAlmostEqual(ry, 0.0, places=6)

    def test_rig_without_feet_or_head_is_a_marked_guess(self):
        b = mb.body({"min": P(-50, -50, 0), "max": P(50, 50, 100)}, {"Bone01": P(0, 0, 10), "Bone02": P(0, 0, 50)})
        self.assertEqual(b["facing"], "+Y")
        self.assertEqual(b["evidence"]["method"], "guessed")


class Write(unittest.TestCase):
    def test_new_measurements_merge_into_an_existing_file(self):
        import json, os, tempfile
        p = os.path.join(tempfile.mkdtemp(), "bodies.json")
        with open(p, "w") as f:
            json.dump({"/Game/A": {"CapsuleRadius": 1}, "/Game/B": {"CapsuleRadius": 2}}, f)
        got = mb.write_bodies(p, {"/Game/B": {"CapsuleRadius": 3}, "/Game/C": {"CapsuleRadius": 4}})
        self.assertEqual({k: v["CapsuleRadius"] for k, v in got.items()}, {"/Game/A": 1, "/Game/B": 3, "/Game/C": 4})


if __name__ == "__main__":
    unittest.main()
