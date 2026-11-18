import json
import os
import pathlib
import subprocess
import tempfile
import unittest

BLENDER = os.environ.get("BLENDER", "/data/ai/toolchains/blender/5.2.3/blender-5.2.3-linux-x64/blender")
HERE = pathlib.Path(__file__).resolve().parent


@unittest.skipUnless(os.path.exists(BLENDER), "pinned Blender not installed here")
class LayeredMaterial(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        work = tempfile.mkdtemp()
        p = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", str(HERE / "test_blender_layered_material_inner.py"), "--", work],
                           capture_output=True, text=True, timeout=600)
        line = next((l for l in p.stdout.splitlines() if l.startswith("@@RESULT@@")), None)
        if line is None:
            raise AssertionError("Blender produced no result:\n" + p.stdout[-1500:] + p.stderr[-1500:])
        cls.r = json.loads(line[len("@@RESULT@@"):])

    def test_layers_land_where_the_masks_say(self):
        g, rock, snow = self.r["ground"], self.r["ball_front_mid"], self.r["ball_top"]
        self.assertGreater(g[1], g[0] * 1.8)                       # grass: green dominates on flat low ground (albedo ratio 5:1)
        self.assertLess(rock[1], rock[0] * 1.12)                   # rock is not tinted green by the grass layer
        self.assertGreaterEqual(snow[2], snow[0])                  # snow albedo is slightly blue-white
        self.assertLess(abs(rock[0] - rock[2]), 0.08 * max(rock))  # rock: neutral grey on the steep flank
        self.assertGreater(rock[1], 0)
        self.assertGreater(min(snow), 0.45)                        # snow: bright in every channel on the flat summit
        self.assertGreater(sum(snow), sum(rock) * 1.2)

    def test_every_mask_type_builds_and_reaches_the_bsdf(self):
        self.assertEqual(len(self.r["masks"]), 7)
        self.assertTrue(all(m.endswith(":True") for m in self.r["masks"]), self.r["masks"])
        self.assertTrue(self.r["vcol_ok"])
        self.assertTrue(self.r["bad_mask_rejected"])

    def test_texture_colour_spaces_and_normal_chain(self):
        s = self.r["tex_spaces"]
        self.assertEqual(s["rock_basecolor"], "sRGB")
        for k in ("rock_normal", "rock_roughness", "rock_ao"):
            self.assertEqual(s[k], "Non-Color", k)
        self.assertTrue(self.r["tex_normal_node"])
        self.assertEqual(self.r["tex_warnings"], [])

    def test_the_shipped_material_example_builds(self):
        e = self.r["example"]
        self.assertTrue(e["ok"])
        self.assertEqual(e["layers"], ["base", "moss", "snow", "wear"])
        self.assertEqual(e["assigned"], ["Ball"])

    def test_box_projection_skips_tangent_normals_with_a_warning(self):
        self.assertTrue(any("box projection" in w for w in self.r["box_warnings"]))
        self.assertTrue(self.r["missing_basecolor_rejected"])


if __name__ == "__main__":
    unittest.main()
