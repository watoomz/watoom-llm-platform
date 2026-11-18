import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rig_import_fbx_character as ic  # noqa: E402


def tree():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "biped"))
    for p in ("biped/Animation_Walking_withSkin.fbx", "biped/Animation_Running_withSkin.fbx", "biped/skin.png", "Model.png"):
        open(os.path.join(d, p), "w").close()
    return d


class Import(unittest.TestCase):
    def test_mesh_then_clips_on_the_mesh_skeleton_with_textures_copied(self):
        d = tree()
        walk, run = os.path.join(d, "biped/Animation_Walking_withSkin.fbx"), os.path.join(d, "biped/Animation_Running_withSkin.fbx")
        files, rdir, rp, calls = ic.plan("SwampMonster", "/Game/ZAS/Creatures/SwampMonster", walk, [("Walk", walk), ("Run", run)])
        self.assertEqual(sorted(os.path.basename(f) for f in files),
                         ["Animation_Running_withSkin.fbx", "Animation_Walking_withSkin.fbx", "skin.png"])
        (m0, a0), (m1, a1), (m2, a2), _save = calls["phases"][0]["calls"]
        self.assertEqual((m0, a0["name"]), ("asset.import_skeletal_mesh", "SK_SwampMonster"))
        self.assertTrue(a0["filePath"].startswith(rdir + "/"))
        self.assertEqual(a0["importer"], "interchange")     # legacy made the mesh node the root bone; clips then failed
        self.assertEqual(a1["skeletonPath"], "/Game/ZAS/Creatures/SwampMonster/SK_SwampMonster_Skeleton")
        self.assertEqual([a1["name"], a2["name"]], ["A_SwampMonster_Walk", "A_SwampMonster_Run"])

    def test_textures_from_a_folder_come_along_once(self):
        d = tree()
        walk = os.path.join(d, "biped/Animation_Walking_withSkin.fbx")
        files = ic.plan("S", "/Game/X", walk, [("Walk", walk)], textures_from=d)[0]
        names = [os.path.basename(f) for f in files]
        self.assertEqual(sorted(names), ["Animation_Walking_withSkin.fbx", "Model.png", "skin.png"])

    def test_clips_are_saved_and_a_static_mesh_too(self):
        d = tree()
        walk = os.path.join(d, "biped/Animation_Walking_withSkin.fbx")
        calls = ic.plan("S", "/Game/X", walk, [("Walk", walk)])[3]["phases"][0]["calls"]
        self.assertEqual(calls[-1], ["asset.save", {"assetPaths": ["/Game/X/A_S_Walk"]}])
        st = ic.plan("Spino", "/Game/X", walk, [], static=True)[3]["phases"][0]["calls"]
        self.assertEqual([m for m, _ in st], ["asset.import_static_mesh", "asset.save"])
        self.assertEqual(st[1][1]["assetPaths"], ["/Game/X/SM_Spino"])

    def test_import_replies_name_what_to_save(self):
        r = '{"success": true, "importedAssets": ["/Game/X/texture_0.texture_0", "/Game/X/SM_S.SM_S"], "animations": [{"path": "/Game/X/A.A"}]}'
        self.assertEqual(sorted(ic.imported_paths(r)), ["/Game/X/A.A", "/Game/X/SM_S.SM_S", "/Game/X/texture_0.texture_0"])
        self.assertEqual(ic.imported_paths("Error: no"), [])

    def test_only_dirty_packages_under_the_destination_are_saved(self):
        r = '{"success": true, "content": [{"package": "/Game/X/Material_001"}, {"package": "/Game/Other/Y"}], "maps": []}'
        self.assertEqual(ic.in_folder(r, "/Game/X"), ["/Game/X/Material_001"])
        self.assertEqual(ic.in_folder(r, "/Game/X/Material"), [])

    def test_bad_names_are_refused(self):
        d = tree()
        f = os.path.join(d, "biped/Animation_Walking_withSkin.fbx")
        with self.assertRaises(ValueError):
            ic.plan("Swamp Monster", "/Game/X", f, [])
        with self.assertRaises(ValueError):
            ic.plan("S", "/Game/X", f, [("Walk fast", f)])


if __name__ == "__main__":
    unittest.main()
