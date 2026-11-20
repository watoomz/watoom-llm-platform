"""gg_assets: ranking, refusals and copying are pure; `check` runs the real engine (skipped without godot/xvfb or when GG_SKIP_ENGINE=1)."""
import json, os, shutil, struct, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gg_assets, gg_godot, gg_ui

ENGINE = gg_godot.find_godot() and not os.environ.get("GG_SKIP_ENGINE")


def tiny_glb(path, height=2.0):
    """One triangle with a coloured material: the smallest valid glb."""
    js = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
          "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "material": 0}]}],
          "materials": [{"pbrMetallicRoughness": {"baseColorFactor": [0.8, 0.3, 0.2, 1]}}],
          "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3", "min": [0, 0, 0], "max": [1, height, 0]}],
          "bufferViews": [{"buffer": 0, "byteLength": 36}], "buffers": [{"byteLength": 36}]}
    j = json.dumps(js).encode()
    j += b" " * (-len(j) % 4)
    b = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, height, 0)
    total = 12 + 8 + len(j) + 8 + len(b)
    open(path, "wb").write(struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<II", len(j), 0x4E4F534A) + j + struct.pack("<II", len(b), 0x004E4942) + b)


def entry(i, pack, ext="glb", mb=1.0, anims=0, path=None, converted=False):
    g = {"meshes": 1, "skins": 1 if anims else 0, "animations": anims, "animation_names": ["Idle"] * min(anims, 3), "materials": 1, "generator": ""} if ext == "glb" else None
    return {"id": i, "pack": pack, "path": path or "/data/ai/assets/fab/%s/x.%s" % (pack, ext), "ext": ext, "bytes": int(mb * 1048576), "converted": converted, "glb": g}


MODELS = [entry("zombie-a-zombie-7", "zombie-a", anims=11, converted=True), entry("dragon-b-prowler", "dragon-b", anims=5, mb=18),
          entry("dragon-c-huge", "dragon-c", mb=245), entry("skeleton-d-fbx", "skeleton-d", ext="fbx"), entry("skeleton-e", "skeleton-e", anims=0, mb=2)]


class Find(unittest.TestCase):
    def test_all_tokens_must_match_and_big_files_are_hidden(self):
        ids = [m["id"] for m in gg_assets.find(MODELS, "dragon")[0]]
        self.assertEqual(ids, ["dragon-b-prowler"])           # the 245 MB one is over the default limit
        self.assertEqual(len(gg_assets.find(MODELS, "dragon", max_mb=None)[0]), 2)
        self.assertEqual(gg_assets.find(MODELS, "dragon skeleton")[1], 0)

    def test_filters(self):
        self.assertEqual([m["id"] for m in gg_assets.find(MODELS, "", ext="fbx")[0]], ["skeleton-d-fbx"])
        self.assertEqual({m["id"] for m in gg_assets.find(MODELS, "", animated=True)[0]}, {"zombie-a-zombie-7", "dragon-b-prowler"})

    def test_glb_ranks_before_fbx_and_limit_applies(self):
        hits, total = gg_assets.find(MODELS, "skeleton", limit=1)
        self.assertEqual((hits[0]["id"], total), ("skeleton-e", 2))

    def test_describe_is_one_compact_line(self):
        line = gg_assets.describe(MODELS[0])
        self.assertNotIn("\n", line)
        self.assertIn("anims 11", line)
        self.assertIn("fbx: textures not inside", gg_assets.describe(MODELS[3]))


class Use(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.src = os.path.join(self.d, "src.glb")
        tiny_glb(self.src)
        self.models = [dict(entry("hero-pack-hero", "hero-pack", path=self.src), bytes=os.path.getsize(self.src))]
        self.old_roots = gg_assets.ROOTS
        gg_assets.ROOTS = (self.d,)
        self.proj = os.path.join(self.d, "proj"); os.makedirs(self.proj)

    def tearDown(self):
        gg_assets.ROOTS = self.old_roots
        shutil.rmtree(self.d, ignore_errors=True)

    def test_use_copies_records_and_refuses_overwrite(self):
        dest, e, sha = gg_assets.use(self.models, "hero-pack-hero", self.proj, "hero")
        self.assertTrue(os.path.isfile(dest) and dest.endswith("assets/library/hero.glb"))
        with open(os.path.join(self.proj, "assets/library/ASSETS.md")) as f:
            notes = f.read()
        self.assertIn("| hero | hero.glb | hero-pack-hero |", notes)
        with self.assertRaisesRegex(gg_godot.Refused, "already holds"):
            gg_assets.use(self.models, "hero-pack-hero", self.proj, "hero")
        gg_assets.use(self.models, "hero-pack-hero", self.proj, "hero", replace=True)
        with open(os.path.join(self.proj, "assets/library/ASSETS.md")) as f:
            self.assertEqual(f.read().count("| hero |"), 1)

    def test_refusals(self):
        with self.assertRaisesRegex(gg_godot.Refused, "no asset"): gg_assets.use(self.models, "nope", self.proj, "x")
        for bad in ("Hero", "1x", "a/b", "a" * 40, ""):
            with self.assertRaisesRegex(gg_godot.Refused, "slot"): gg_assets.use(self.models, "hero-pack-hero", self.proj, bad)
        big = [dict(self.models[0], bytes=200 * 1048576)]
        with self.assertRaisesRegex(gg_godot.Refused, "--allow-large"): gg_assets.use(big, "hero-pack-hero", self.proj, "hero")
        outside = [dict(self.models[0], path="/etc/passwd")]
        with self.assertRaisesRegex(gg_godot.Refused, "not a regular file under"): gg_assets.use(outside, "hero-pack-hero", self.proj, "hero")

    def test_gltf_with_external_bin_or_textures_is_refused(self):
        gltf = os.path.join(self.d, "src2.gltf")
        json.dump({"asset": {"version": "2.0"}, "buffers": [{"uri": "src2.bin", "byteLength": 36}],
                   "images": [{"uri": "textures/diffuse.png"}]}, open(gltf, "w"))
        models = [dict(entry("ext-pack-ext", "ext-pack", ext="gltf", path=gltf), bytes=os.path.getsize(gltf))]
        with self.assertRaisesRegex(gg_godot.Refused, "external file.*src2.bin.*textures/diffuse.png|src2.bin"):
            gg_assets.use(models, "ext-pack-ext", self.proj, "hero")

    def test_self_contained_gltf_with_embedded_data_uris_is_allowed(self):
        gltf = os.path.join(self.d, "src3.gltf")
        json.dump({"asset": {"version": "2.0"}, "buffers": [{"uri": "data:application/octet-stream;base64,AA==", "byteLength": 1}]}, open(gltf, "w"))
        models = [dict(entry("embed-pack-embed", "embed-pack", ext="gltf", path=gltf), bytes=os.path.getsize(gltf))]
        dest, e, sha = gg_assets.use(models, "embed-pack-embed", self.proj, "hero")
        self.assertTrue(os.path.isfile(dest) and dest.endswith("assets/library/hero.gltf"))

    def test_missing_index_is_a_refusal(self):
        with self.assertRaisesRegex(gg_godot.Refused, "model index"): gg_assets.load_index(os.path.join(self.d, "none.json"))

    def test_check_flags_drop_the_scatter_only_rule(self):
        data = {"meshes": 1, "surfaces": 1, "triangles": 10, "aabb": {"pos": [0, 5, 0], "size": [1, 2, 1]}, "lights": 0, "skeletons": 0, "animation_players": 0,
                "materials": [{"node": "n", "surface": 0, "kind": "StandardMaterial3D", "albedo": [0.8, 0.3, 0.2, 1], "albedo_texture": False, "emission": 0.0, "cull": "back"}]}
        self.assertEqual([f for f in gg_assets.check_flags(data) if f["level"] == "error"], [])


@unittest.skipUnless(ENGINE, "godot not available")
class Engine(unittest.TestCase):
    def test_check_inspects_a_real_glb_and_flags_a_wrong_scale(self):
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "g")
            os.makedirs(os.path.join(p, "assets/library"))
            self.assertEqual(gg_ui.main(["init", "--project", p, "--name", "g"]), 0)
            tiny_glb(os.path.join(p, "assets/library/ok.glb"), 2.0)
            self.assertEqual(gg_assets.main(["check", "--project", p, "--slot", "ok"]), 0)
            tiny_glb(os.path.join(p, "assets/library/small.glb"), 0.02)
            self.assertEqual(gg_assets.main(["check", "--project", p, "--slot", "small"]), 1)
            self.assertEqual(gg_assets.main(["check", "--project", p, "--slot", "missing"]), 2)
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
