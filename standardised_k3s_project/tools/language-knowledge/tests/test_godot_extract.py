"""Offline extractor contract tests; fixtures are deliberately small and synthetic."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "extract" / "godot_extract.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "godot"
SPEC = importlib.util.spec_from_file_location("godot_extract", SCRIPT)
extractor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extractor)


class GodotExtractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.out = self.base / "out"
        self.manifest = extractor.extract(FIXTURES, "4.7.2", self.out)
        self.cards = [json.loads(line) for line in
                      (self.out / "cards.jsonl").read_text().splitlines()]
        self.by_symbol = {card["symbol"]: card for card in self.cards}

    def test_counts_and_schema(self):
        self.assertEqual(self.manifest["counts"], {
            "api_class": 2, "api_method": 5, "api_property": 2,
            "api_signal": 1, "api_constant": 6, "api_enum": 2})
        self.assertEqual(self.manifest["total_cards"], 18)
        self.assertEqual(self.manifest["input_files"], 2)
        self.assertEqual(self.manifest["tool_version"], "4.7.2")
        self.assertEqual(self.manifest["generator_version"], extractor.GENERATOR_VERSION)
        ids = [c["id"] for c in self.cards]
        self.assertEqual(ids, sorted(set(ids)))
        for card in self.cards:
            extractor.validate(card)
            self.assertEqual(card["id"], "godot." + card["symbol"] + "@4.7.2")
            self.assertEqual(card["source"]["revision"],
                             "4.7.2+sha256:" + self.manifest["input_sha256"])
            self.assertEqual(card["license"], "MIT")

    def test_exact_signatures(self):
        expected = {
            "Node": "class Node extends Object",
            "HTTPThing": "class HTTPThing",
            "Node.add_child": "Node.add_child(node: Node, force_readable_name: bool = false, internal: InternalMode = 0) -> void",
            "Node._ready": "Node._ready() -> void virtual const",
            "Node.make_node": 'Node.make_node(label: String = &"Hello  world", offset: Vector2 = Vector2(1, 2), mode: Other.Mode) -> Node static',
            "Node.call_many": "Node.call_many(flags: BitField[Flags] = 3, ...) -> InternalMode vararg const",
            "Node.display_name": 'Node.display_name: String = ""',
            "Node.owner": "Node.owner: Node",
            "Node.child_added": "Node.child_added(child: Node)",
            "Node.SPECIAL": "Node.SPECIAL = 0xFF",
            "Node.InternalMode": "enum Node.InternalMode { INTERNAL_MODE_DISABLED = 0, INTERNAL_MODE_FRONT = 1 }",
            "Node.Flags": "enum Node.Flags { FLAG_FIRST = 1, FLAG_SECOND = 2 }",
        }
        for symbol, signature in expected.items():
            with self.subTest(symbol=symbol):
                self.assertEqual(self.by_symbol[symbol]["signature"], signature)

    def test_params_returns_and_spans(self):
        method = self.by_symbol["Node.add_child"]
        self.assertEqual(method["params"], [
            {"name": "node", "type": "Node", "default": None, "doc": ""},
            {"name": "force_readable_name", "type": "bool", "default": "false", "doc": ""},
            {"name": "internal", "type": "InternalMode", "default": "0", "doc": ""}])
        self.assertEqual(method["returns"], "void")
        self.assertIsNone(self.by_symbol["Node.child_added"]["returns"])
        spans = {"Node": "class", "Node.add_child": "method[@name='add_child']",
                 "Node.owner": "member[@name='owner']",
                 "Node.child_added": "signal[@name='child_added']",
                 "Node.SPECIAL": "constant[@name='SPECIAL']",
                 "Node.Flags": "constants/constant[@enum='Flags']"}
        for symbol, span in spans.items():
            self.assertEqual(self.by_symbol[symbol]["source"]["span"], "Node.xml#" + span)

    def test_summaries_and_aliases(self):
        self.assertEqual(self.by_symbol["Node"]["summary"], "A scene node.")
        self.assertEqual(self.by_symbol["HTTPThing"]["summary"],
                         "Fallback description with x < y and [literal].")
        self.assertEqual(self.by_symbol["Node.add_child"]["summary"],
                         "Add a Node with add_child. See details.")
        self.assertEqual(self.by_symbol["Node.display_name"]["summary"], "A label.")
        self.assertEqual(self.by_symbol["Node._ready"]["summary"], "")
        self.assertEqual(self.by_symbol["Node.add_child"]["aliases"],
                         ["Node.AddChild", "node.add_child"])
        self.assertIn("http_thing.get_http_value",
                      self.by_symbol["HTTPThing.get_HTTP_value"]["aliases"])
        element = extractor.ET.fromstring("<method><description>" + "x" * 400 +
                                         "</description></method>")
        self.assertEqual(extractor.summary(element), "x" * 300)

    def test_deprecated_and_experimental(self):
        expected = {"Node._ready": ["experimental: API may change"],
                    "Node.make_node": ["deprecated: Use add_child."],
                    "Node.display_name": ["deprecated"],
                    "Node.child_added": ["experimental"],
                    "Node.SPECIAL": ["experimental: Unstable value"],
                    "HTTPThing": ["deprecated: Replaced", "experimental: Preview class"],
                    "Node.InternalMode": ["deprecated: Old mode"]}
        for symbol, constraints in expected.items():
            self.assertTrue(self.by_symbol[symbol]["deprecated"])
            self.assertEqual(self.by_symbol[symbol]["constraints"], constraints)
        self.assertFalse(self.by_symbol["Node.add_child"]["deprecated"])
        self.assertEqual(self.by_symbol["Node.Flags"]["constraints"], ["bitfield"])

    def test_deterministic_relocated_input_and_hash(self):
        moved = self.base / "classes"
        moved.mkdir()
        for source in reversed(sorted(FIXTURES.glob("*.xml"))):
            shutil.copyfile(source, moved / source.name)
        other = self.base / "other"
        extractor.extract(moved, "4.7.2", other)
        for filename in ("cards.jsonl", "manifest.json"):
            self.assertEqual((self.out / filename).read_bytes(),
                             (other / filename).read_bytes())
        digest = hashlib.sha256()
        for path in sorted(FIXTURES.glob("*.xml")):
            for part in (path.name.encode(), path.read_bytes()):
                digest.update(len(part).to_bytes(8, "big"))
                digest.update(part)
        self.assertEqual(self.manifest["input_sha256"], digest.hexdigest())
        with (moved / "Node.xml").open("a") as stream:
            stream.write("\n")
        changed = extractor.extract(moved, "4.7.2", other)
        self.assertNotEqual(changed["input_sha256"], digest.hexdigest())

    def test_cli_and_failures(self):
        command = [sys.executable, "-B", str(SCRIPT), "--classes", str(FIXTURES),
                   "--version", "4.7.2", "--out", str(self.base / "cli")]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), self.manifest)
        bad = self.base / "bad"
        bad.mkdir()
        for xml in ("<broken", '<class name="Node"><methods><method name="oops"/></methods></class>',
                    '<class name="Node"><members><member name="x"/></members></class>'):
            (bad / "bad.xml").write_text(xml)
            failed = subprocess.run(command[:4] + [str(bad)] + command[5:],
                                    capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("godot_extract:", failed.stderr)
        with self.assertRaises(ValueError):
            extractor.extract(FIXTURES, "4.7", self.out)
        with self.assertRaises(ValueError):
            extractor.extract(self.base / "missing", "4.7.2", self.out)
        empty = self.base / "empty"
        empty.mkdir()
        with self.assertRaises(ValueError):
            extractor.extract(empty, "4.7.2", self.out)
        shutil.copyfile(FIXTURES / "Node.xml", bad / "bad.xml")
        shutil.copyfile(FIXTURES / "Node.xml", bad / "duplicate.xml")
        with self.assertRaisesRegex(ValueError, "duplicate card id"):
            extractor.extract(bad, "4.7.2", self.out)

    def test_schema_rejects_invalid_cards(self):
        for key, value in (("summary", "x" * 301), ("kind", "unknown"),
                           ("params", [{}]), ("source", {}), ("returns", 1),
                           ("aliases", [1]), ("deprecated", "true")):
            card = copy.deepcopy(self.cards[0])
            card[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                extractor.validate(card)


if __name__ == "__main__":
    unittest.main()
