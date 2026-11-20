import unittest, tempfile, pathlib, json
from asset_catalog import Catalog, atomic, checksum


class SelectedCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name) / "assets"
        self.root.mkdir()
        self.path = self.root / "pack/mesh.uasset"
        self.path.parent.mkdir()
        self.path.write_bytes(b"original")
        self.catalog = Catalog(self.root, pathlib.Path(self.tmp.name) / "state/catalog.json")

    def test_selected_replay_preserves_existing_annotations_and_cursor(self):
        result = self.catalog.index_selected(["pack/mesh.uasset"])
        key = result["ids"][0]
        data = self.catalog.load()
        data["cursor"] = "another/pending"
        data["records"][key]["dungeon_adapter"] = {"status": "VERIFIED"}
        atomic(self.catalog.state, data)
        replay = self.catalog.index_selected(["pack/mesh.uasset"])
        self.assertEqual(replay["hashed_bytes"], 0)
        self.assertEqual(self.catalog.load()["cursor"], "another/pending")
        self.assertEqual(self.catalog.load()["records"][key]["dungeon_adapter"], {"status": "VERIFIED"})

    def test_changed_source_invalidates_verification(self):
        key = self.catalog.index_selected(["pack/mesh.uasset"])["ids"][0]
        data = self.catalog.load()
        data["records"][key]["dungeon_adapter"] = {"status": "VERIFIED"}
        atomic(self.catalog.state, data)
        self.path.write_bytes(b"changed file")
        self.catalog.index_selected(["pack/mesh.uasset"])
        row = self.catalog.load()["records"][key]
        self.assertNotIn("dungeon_adapter", row)
        self.assertEqual(row["sha256"], checksum(self.path))

    def test_budget_failure_keeps_catalog_atomic(self):
        self.catalog.index_selected(["pack/mesh.uasset"])
        before = self.catalog.state.read_bytes()
        other = self.root / "pack/other.ubulk"
        other.write_bytes(b"x" * 32)
        with self.assertRaises(ValueError):
            self.catalog.index_selected(["pack/other.ubulk"], hash_budget=8)
        self.assertEqual(before, self.catalog.state.read_bytes())
        self.assertEqual(other.read_bytes(), b"x" * 32)

    def test_selected_source_cannot_escape_library(self):
        (self.root / "bad.uasset").symlink_to(pathlib.Path(self.tmp.name) / "outside")
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.catalog.index_selected(["bad.uasset"])


if __name__ == "__main__":
    unittest.main()
