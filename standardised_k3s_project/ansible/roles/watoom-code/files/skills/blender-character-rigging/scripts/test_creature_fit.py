"""creature_fit on a synthetic theropod (no Blender needed): python3 -m unittest test_creature_fit"""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import creature_fit as cf  # noqa: E402

RNG = np.random.default_rng(3)


def blob(c, r, n):
    """Points on an axis-aligned ellipsoid surface around c with radii r."""
    d = RNG.normal(size=(n, 3))
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    return np.asarray(c) + d * np.asarray(r)


def rod(a, b, r, n):
    a, b = np.asarray(a, float), np.asarray(b, float)
    t = RNG.random(n)[:, None]
    return a + t * (b - a) + RNG.normal(scale=r, size=(n, 3)) * [1, 1, 0.3]


def theropod(facing_deg=0.0, sail=False, hand_on_ground=False, stagger=0.0):
    """+X forward before the turn: body at x 0..3, head at x 4.5, tail to x -5, hips at x 0, feet on z=0 at y +-0.5."""
    parts = [blob((0.8, 0, 2.6), (2.2, 0.8, 0.8), 6000),          # body
             blob((4.6, 0, 3.2), (0.7, 0.35, 0.4), 1500),         # head (higher than the tail tip)
             rod((2.6, 0, 2.8), (4.0, 0, 3.2), 0.2, 800),          # neck
             rod((-1.0, 0, 2.6), (-5.0, 0, 1.6), 0.15, 2000)]      # tail
    for y, dx in ((0.5, stagger), (-0.5, -stagger)):
        parts += [rod((0, y, 2.2), (0.4 + dx, y, 1.2), 0.18, 900),  # thigh (knee forward)
                  rod((0.4 + dx, y, 1.2), (-0.1 + dx, y, 0.3), 0.12, 900),
                  rod((-0.1 + dx, y, 0.3), (0.5 + dx, y, 0.02), 0.08, 600)]
    if sail:
        parts.append(np.c_[RNG.uniform(-0.5, 2.0, 4000), RNG.normal(scale=0.02, size=4000), RNG.uniform(3.4, 5.5, 4000)])
    if hand_on_ground:
        parts.append(rod((2.5, 0.3, 2.0), (2.9, 0.3, 0.02), 0.05, 400))
    p = np.vstack(parts)
    p[:, 2] -= p[:, 2].min()
    a = math.radians(facing_deg)
    rot = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
    return p @ rot.T, rot @ np.array([1.0, 0, 0])


class Fit(unittest.TestCase):
    def check(self, f, fwd):
        j = {k: (np.array(a), np.array(b)) for k, (a, b) in f["joints"].items()}
        self.assertGreater(np.dot(f["frame"]["forward"], fwd), 0.97, "facing")
        self.assertGreater((j["head"][1] - j["pelvis"][0]) @ fwd, 3.0, "head in front of the hips")
        self.assertLess((j["tail_06"][1] - j["pelvis"][0]) @ fwd, -4.0, "tail behind the hips")
        for s in "lr":
            hip, knee, ankle = j["thigh_" + s][0], j["calf_" + s][0], j["foot_" + s][0]
            self.assertTrue(hip[2] > knee[2] > ankle[2] > 0, "leg %s ordered top to bottom" % s)
            self.assertLess(j["ball_" + s][0][2], 0.3, "ball %s on the ground" % s)
        side = [np.dot(j["thigh_l"][0], f["frame"]["left"]), np.dot(j["thigh_r"][0], f["frame"]["left"])]
        self.assertGreater(side[0], side[1], "left hip is on the left")
        return j

    def test_any_facing(self):
        for deg in (0, 90, 200, -35):
            p, fwd = theropod(deg)
            self.check(cf.fit(p), fwd)

    def test_staggered_statue_legs_are_traced_separately(self):
        p, fwd = theropod(stagger=0.7)
        j = self.check(cf.fit(p), fwd)
        # each knee stays with its own foot: the front leg's knee is forward of the rear leg's
        self.assertGreater((j["calf_l"][0] - j["calf_r"][0]) @ fwd, 0.6)

    def test_a_sail_does_not_lift_the_spine(self):
        p, fwd = theropod(sail=True)
        j = self.check(cf.fit(p), fwd)
        self.assertLess(max(j["spine_%02d" % i][0][2] for i in (1, 2, 3)), 3.4, "spine stays in the body, below the sail")

    def test_a_hand_on_the_ground_is_not_a_foot(self):
        p, fwd = theropod(hand_on_ground=True)
        j = self.check(cf.fit(p), fwd)
        for s in "lr":
            self.assertLess((j["ball_" + s][1] - j["thigh_" + s][0]) @ fwd, 1.5, "toe %s stays near its foot" % s)

    def test_one_leg_is_refused(self):
        p, _ = theropod()
        with self.assertRaises(ValueError):
            cf.fit(p[~((p[:, 1] < -0.2) & (p[:, 2] < 2.0))])  # right leg removed: the fit needs two feet


if __name__ == "__main__":
    unittest.main()
