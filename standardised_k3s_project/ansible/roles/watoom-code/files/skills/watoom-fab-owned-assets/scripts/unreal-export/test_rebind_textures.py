"""rebind_textures.py: pure refusal paths only (no engine). Actually rebinding a glb's materials needs
Blender, verified manually against the AK-47 and rogue packs for T-0067 -- see gg_assets.py check output in
the ticket note, not reproduced here since a Blender round-trip is too slow/heavy for a unit test."""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rebind_textures


class Refusals(unittest.TestCase):
    def test_refuses_missing_glb(self):
        d = tempfile.mkdtemp()
        try:
            self.assertEqual(rebind_textures.main(["--glb", os.path.join(d, "no.glb"), "--textures-dir", d,
                                                     "--bind", "{}", "--out", os.path.join(d, "out.glb")]), 2)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_refuses_missing_textures_dir(self):
        d = tempfile.mkdtemp()
        try:
            glb = os.path.join(d, "in.glb")
            open(glb, "w").close()
            self.assertEqual(rebind_textures.main(["--glb", glb, "--textures-dir", os.path.join(d, "nope"),
                                                     "--bind", "{}", "--out", os.path.join(d, "out.glb")]), 2)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_refuses_bind_group_with_no_albedo_match(self):
        d = tempfile.mkdtemp()
        try:
            glb = os.path.join(d, "in.glb")
            open(glb, "w").close()
            tex = os.path.join(d, "tex")
            os.makedirs(tex)
            bind = json.dumps({"Material_0": "Nonexistent"})
            self.assertEqual(rebind_textures.main(["--glb", glb, "--textures-dir", tex, "--bind", bind,
                                                     "--out", os.path.join(d, "out.glb")]), 2)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_finds_albedo_by_suffix_variants(self):
        d = tempfile.mkdtemp()
        try:
            open(os.path.join(d, "T_Exterior_D.tga"), "w").close()
            found = rebind_textures.find_group_textures(d, "Exterior")
            self.assertEqual(found["albedo"], os.path.join(d, "T_Exterior_D.tga"))
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
