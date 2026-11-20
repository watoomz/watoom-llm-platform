import json, os, struct, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_model_index as B


def glb(path, anims=("Idle", "Run")):
    js = json.dumps(
        {
            "asset": {"version": "2.0", "generator": "t"},
            "meshes": [{}, {}],
            "skins": [{}],
            "materials": [{}],
            "animations": [{"name": n} for n in anims],
        }
    ).encode()
    js += b" " * (-len(js) % 4)
    open(path, "wb").write(
        struct.pack("<4sII", b"glTF", 2, 20 + len(js)) + struct.pack("<II", len(js), 0x4E4F534A) + js
    )


class T(unittest.TestCase):
    def test_facts_index_and_skips(self):
        with tempfile.TemporaryDirectory() as d:
            fab, hum = os.path.join(d, "fab"), os.path.join(d, "hum")
            os.makedirs(os.path.join(fab, "Pack-1", "glb", "converted"))
            os.makedirs(os.path.join(fab, "Pack-1", "__MACOSX"))
            os.makedirs(os.path.join(fab, "zips"))
            os.makedirs(hum)
            glb(os.path.join(fab, "Pack-1", "glb", "converted", "orc.glb"))
            open(os.path.join(fab, "Pack-1", "a.fbx"), "w").write("x")
            open(os.path.join(fab, "Pack-1", "__MACOSX", "junk.fbx"), "w").write("x")
            open(os.path.join(fab, "Pack-1", "tex.png"), "w").write("x")
            open(os.path.join(fab, "zips", "big.fbx"), "w").write("x")
            open(os.path.join(fab, "Pack-1", "bad.glb"), "w").write("not a glb")
            glb(os.path.join(hum, "Hero.glb"), anims=())
            ms = {m["id"]: m for m in B.build(fab, hum)}
            self.assertEqual(sorted(ms), ["humble-assets-hero", "pack-1-a", "pack-1-bad", "pack-1-orc"])
            o = ms["pack-1-orc"]
            self.assertTrue(o["converted"])
            self.assertEqual((o["glb"]["meshes"], o["glb"]["skins"], o["glb"]["animations"]), (2, 1, 2))
            self.assertEqual(o["glb"]["animation_names"], ["Idle", "Run"])
            self.assertIsNone(ms["pack-1-bad"]["glb"])
            self.assertEqual(ms["pack-1-a"]["ext"], "fbx")
            self.assertEqual(ms["humble-assets-hero"]["glb"]["animations"], 0)

    def test_duplicate_names_get_unique_ids_and_main_writes_the_file(self):
        with tempfile.TemporaryDirectory() as d:
            fab = os.path.join(d, "fab")
            os.makedirs(os.path.join(fab, "P", "a"))
            os.makedirs(os.path.join(fab, "P", "b"))
            open(os.path.join(fab, "P", "a", "x.fbx"), "w").write("1")
            open(os.path.join(fab, "P", "b", "x.fbx"), "w").write("2")
            out = os.path.join(d, "idx.json")
            self.assertEqual(B.main(["--fab", fab, "--humble", os.path.join(d, "none"), "--out", out]), 0)
            doc = json.load(open(out))
            self.assertEqual((doc["schema"], doc["count"]), (1, 2))
            self.assertEqual(len({m["id"] for m in doc["models"]}), 2)

    def test_colliding_ids_are_keyed_by_the_file_s_own_relative_path_not_walk_order(self):
        # A colliding id must depend only on (pack, relative path): adding or removing an unrelated
        # third file earlier in walk order must never reassign an id a project's ASSETS.md already cites.
        with tempfile.TemporaryDirectory() as d:
            fab = os.path.join(d, "fab")
            os.makedirs(os.path.join(fab, "P", "a"))
            os.makedirs(os.path.join(fab, "P", "b"))
            open(os.path.join(fab, "P", "a", "x.fbx"), "w").write("1")
            open(os.path.join(fab, "P", "b", "x.fbx"), "w").write("2")
            before = {m["path"]: m["id"] for m in B.build(fab, os.path.join(d, "none"))}
            os.makedirs(os.path.join(fab, "P", "0-earlier"))
            open(os.path.join(fab, "P", "0-earlier", "x.fbx"), "w").write("3")  # sorts before a/x.fbx and b/x.fbx
            after = {m["path"]: m["id"] for m in B.build(fab, os.path.join(d, "none"))}
            for path, old_id in before.items():
                self.assertEqual(after[path], old_id)
            self.assertEqual(len(set(after.values())), 3)


if __name__ == "__main__":
    unittest.main()
