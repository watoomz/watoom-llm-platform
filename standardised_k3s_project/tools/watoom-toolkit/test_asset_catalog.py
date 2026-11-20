import json, pathlib, tempfile, unittest
from asset_catalog import Catalog, checksum


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name) / "assets"
        self.root.mkdir()
        self.catalog = Catalog(self.root, pathlib.Path(self.tmp.name) / "state/catalog.json")

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, name, value=b"asset"):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(value)
        return p

    def finish(self):
        for _ in range(20):
            result = self.catalog.index(limit=1)
            if result["scan_complete"]:
                return result
        self.fail("scan did not finish")

    def test_incremental_search_source_hash_and_existing_asset(self):
        source = self.put("fab/forest/rock.glb")
        before = checksum(source)
        self.put("fab/forest/tree.fbx")
        result = self.finish()
        self.assertEqual(result["indexed"], 2)
        rock = self.catalog.search("rock", category="rocks", format="glb")[0]
        path, record = self.catalog.resolve(rock["id"])
        self.assertEqual(record["sha256"], before)
        self.assertEqual(path, source)
        self.assertEqual(checksum(source), before)

    def test_future_pack_and_changes_reindex_without_rebuild(self):
        self.put("fab/pack/a.obj")
        self.finish()
        self.put("humble_assets/new/terrain.obj")
        self.finish()
        item = self.catalog.search("terrain")[0]
        self.assertEqual(item["categories"], ["terrain"])
        self.put("humble_assets/new/terrain.obj", b"changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.catalog.resolve(item["id"])
        self.finish()
        self.assertEqual(self.catalog.resolve(item["id"])[1]["sha256"], checksum(self.root / item["path"]))

    def test_excludes_engine_build_tree_and_escape_symlink(self):
        self.put("unreal-engine/Engine/mesh.obj")
        self.put("fab/pack/Intermediate/mesh.obj")
        outside = pathlib.Path(self.tmp.name) / "outside.obj"
        outside.write_bytes(b"private")
        (self.root / "escape.obj").symlink_to(outside)
        result = self.finish()
        self.assertEqual(result["indexed"], 0)
        self.assertTrue(result["errors"])

    def test_unknown_license_and_engine_are_not_invented(self):
        self.put("fab/paid/model.uasset")
        self.finish()
        entry = self.catalog.search("model")[0]
        self.assertEqual(entry["license"]["status"], "UNVERIFIED")
        self.assertEqual(entry["engine_compatibility"]["unreal"], "UNVERIFIED")

    def test_metadata_survives_new_catalog_instance_and_previous_snapshot(self):
        self.put("fab/pack/idle.fbx")
        self.finish()
        other = Catalog(self.root, self.catalog.state)
        self.assertEqual(len(other.search("idle", category="animations")), 1)
        self.finish()
        self.assertTrue(self.catalog.state.with_suffix(".previous.json").exists())

    def test_existing_manifest_enables_rig_animation_and_preview_search(self):
        source = self.put("generated/opaque-job/asset.glb")
        manifest = self.put(
            "generated/opaque-job/manifest.json",
            json.dumps(
                {
                    "generator_id": "asset-assistant.quadruped",
                    "animations": ["Idle", "Walk"],
                    "skin_count": 1,
                    "input_manifest": {"style": "wombat"},
                }
            ).encode(),
        )
        self.put("generated/opaque-job/perspective.png")
        self.finish()
        item = self.catalog.search("wombat", category="wildlife", format="glb")[0]
        self.assertIn("skeletons", item["categories"])
        self.assertIn("animations", item["categories"])
        self.assertEqual(item["preview"], "generated/opaque-job/perspective.png")
        self.assertEqual(item["engine_compatibility"]["godot"], "UNVERIFIED")
        expected = item["sha256"]
        manifest.write_text(json.dumps({"generator_id": "watoom.rock", "animations": [], "skin_count": 0}))
        self.catalog.index(limit=1024, hash_budget=0)
        updated = self.catalog.search("rock", format="glb")[0]
        self.assertNotIn("skeletons", updated["categories"])
        self.assertEqual(updated["sha256"], expected)
        self.assertEqual(checksum(source), expected)


if __name__ == "__main__":
    unittest.main()
