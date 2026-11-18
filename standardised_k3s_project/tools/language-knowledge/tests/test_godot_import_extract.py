"""Offline, stdlib-only tests for the Godot import-option extractor (real .import files from the engine, trimmed; fake binaries holding hint strings)."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

TESTS = Path(__file__).resolve().parent
SCRIPT = TESTS.parent / "extract" / "godot_import_extract.py"
FIXTURES = TESTS / "fixtures" / "import"
SPEC = importlib.util.spec_from_file_location("godot_import_extract", SCRIPT)
extractor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extractor)


class ImportExtractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="import-test-", dir=TESTS)
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)

    def run_extract(self, binary="fake-godot.bin", name="out"):
        out = self.out / name
        manifest = extractor.extract(FIXTURES / binary, "4.7.2", out, FIXTURES)
        cards = [json.loads(line) for line in (out / "cards.jsonl").read_text().splitlines()]
        return manifest, cards, out

    def card(self, cards, symbol):
        return next(c for c in cards if c["symbol"] == symbol)

    def test_fbx_embedded_image_option_has_exact_default_and_engine_labels(self):
        manifest, cards, _ = self.run_extract()
        card = self.card(cards, "scene:fbx/embedded_image_handling")
        self.assertEqual("import_option", card["kind"])
        self.assertEqual("fbx/embedded_image_handling=1", card["signature"])
        self.assertIn("Default: 1 = Extract Textures", card["summary"])
        self.assertIn("2 Embed as Basis Universal", card["summary"])
        self.assertIn("Values: 0 = Discard All Textures; 1 = Extract Textures; 2 = Embed as Basis Universal; 3 = Embed as Uncompressed.", card["constraints"])
        self.assertIn("embedded_image_handling", card["aliases"])
        self.assertEqual("godot.scene:fbx/embedded_image_handling@4.7.2", card["id"])
        self.assertEqual(manifest["total_cards"], len(cards))
        self.assertEqual([], manifest["labels_dropped"])

    def test_options_shared_by_file_types_become_one_card_listing_them(self):
        _, cards, _ = self.run_extract()
        shared = self.card(cards, "scene:meshes/generate_lods")
        self.assertIn(".fbx", shared["constraints"][1])
        self.assertIn(".gltf", shared["constraints"][1])
        self.assertEqual("meshes/generate_lods=true", shared["signature"])
        self.assertEqual("godot.scene:meshes/generate_lods@4.7.2", shared["id"])

    def test_importers_stay_separate(self):
        _, cards, _ = self.run_extract()
        self.assertEqual({"scene", "texture", "wav"}, {c["symbol"].split(":")[0] for c in cards})

    def test_label_missing_from_the_binary_is_dropped_not_invented(self):
        manifest, cards, _ = self.run_extract("fake-godot-no-embedded.bin")
        self.assertIn("scene:fbx/embedded_image_handling", manifest["labels_dropped"])
        card = self.card(cards, "scene:fbx/embedded_image_handling")
        self.assertNotIn("Extract Textures", json.dumps(card))
        self.assertTrue(card["summary"].endswith("Default: 1."))
        self.assertEqual(manifest["labels_verified"] + len(manifest["labels_dropped"]), len(extractor.HINTS))

    def test_output_is_deterministic(self):
        _, _, first = self.run_extract(name="a")
        _, _, second = self.run_extract(name="b")
        self.assertEqual((first / "cards.jsonl").read_bytes(), (second / "cards.jsonl").read_bytes())
        self.assertEqual((first / "manifest.json").read_bytes(), (second / "manifest.json").read_bytes())

    def test_every_card_passes_the_shared_schema(self):
        _, cards, _ = self.run_extract()
        for card in cards:
            extractor.validate(card)
            self.assertLessEqual(len(card["summary"]), 300)
            self.assertEqual({"uri", "revision", "span"}, set(card["source"]))

    def test_bad_input_is_rejected(self):
        with self.assertRaises(ValueError):
            extractor.extract(FIXTURES / "fake-godot.bin", "4.7", self.out / "x", FIXTURES)
        empty = self.out / "empty"
        empty.mkdir()
        with self.assertRaises(ValueError):
            extractor.extract(FIXTURES / "fake-godot.bin", "4.7.2", self.out / "y", empty)

    def test_value_types(self):
        self.assertEqual("bool", extractor.value_type("true"))
        self.assertEqual("int", extractor.value_type("12"))
        self.assertEqual("float", extractor.value_type("0.2"))
        self.assertEqual("String", extractor.value_type('"x"'))
        self.assertEqual("null", extractor.value_type("null"))


if __name__ == "__main__":
    unittest.main()
