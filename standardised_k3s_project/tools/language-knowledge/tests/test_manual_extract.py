"""Tests for extract/manual_extract.py: the generic "add a different tool/manual" extractor."""
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("manual_extract", HERE.parent / "extract" / "manual_extract.py")
manual_extract = importlib.util.module_from_spec(SPEC)
sys.modules["manual_extract"] = manual_extract
SPEC.loader.exec_module(manual_extract)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class ManualExtractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.product_dir = self.root / "manuals" / "widget"
        write(self.product_dir / "sources" / "guide.md", "The widget_init() call takes a size in bytes.\nCall widget_free() when done.")
        write(self.product_dir / "source.json", json.dumps({
            "product": "widget", "version": "9.1", "language": "c", "license": "MIT", "trust_tier": "vendor_doc",
            "pages": [{"uri": "https://example.invalid/guide", "file": "guide.md"}],
        }))

    def tearDown(self):
        self.tmp.cleanup()

    def _run_cli(self, out_dir):
        import subprocess
        import sys as _sys
        p = subprocess.run([_sys.executable, str(HERE.parent / "extract" / "manual_extract.py"),
                            "--manuals-root", str(self.root / "manuals"), "--product", "widget", "--out", str(out_dir)],
                           capture_output=True, text=True)
        return p

    def test_valid_entry_produces_a_schema_complete_card(self):
        entry = {"symbol": "widget_init", "kind": "api_method", "signature": "widget_init(size)",
                  "summary": "Initialise a widget.", "source_file": "guide.md",
                  "source_span": "The widget_init() call takes a size in bytes."}
        write(self.product_dir / "entries.jsonl", json.dumps(entry))
        p = self._run_cli(self.root / "out1")
        self.assertEqual(0, p.returncode, p.stderr)
        cards = [json.loads(l) for l in (self.root / "out1" / "cards.jsonl").read_text().splitlines()]
        self.assertEqual(1, len(cards))
        card = cards[0]
        for key in ("id", "product", "version", "kind", "symbol", "signature", "source", "trust_tier", "status"):
            self.assertIn(key, card)
        self.assertEqual("widget.widget_init@9.1", card["id"])
        self.assertEqual("source_checked", card["status"])
        self.assertEqual("vendor_doc", card["trust_tier"])
        self.assertIn("sha256:", card["source"]["revision"])

    def test_source_span_not_in_source_file_fails_the_whole_run(self):
        write(self.product_dir / "entries.jsonl", json.dumps({
            "symbol": "fabricated", "kind": "api_method", "signature": "fabricated()",
            "summary": "made up", "source_file": "guide.md", "source_span": "this sentence is not in the guide",
        }))
        p = self._run_cli(self.root / "out2")
        self.assertNotEqual(0, p.returncode)
        self.assertIn("source_span not found", p.stderr)
        self.assertFalse((self.root / "out2" / "cards.jsonl").exists() and
                         (self.root / "out2" / "cards.jsonl").read_text().strip())

    def test_whitespace_differences_between_entry_and_source_are_tolerated(self):
        write(self.product_dir / "entries.jsonl", json.dumps({
            "symbol": "widget_free", "kind": "api_method", "signature": "widget_free()",
            "summary": "Free a widget.", "source_file": "guide.md",
            "source_span": "Call   widget_free()\nwhen   done.",
        }))
        p = self._run_cli(self.root / "out3")
        self.assertEqual(0, p.returncode, p.stderr)

    def test_source_file_not_listed_in_source_json_pages_fails(self):
        write(self.product_dir / "entries.jsonl", json.dumps({
            "symbol": "x", "kind": "api_method", "signature": "x()", "summary": "x",
            "source_file": "unlisted.md", "source_span": "x",
        }))
        p = self._run_cli(self.root / "out4")
        self.assertNotEqual(0, p.returncode)
        self.assertIn("not listed in source.json pages", p.stderr)

    def test_missing_required_key_fails(self):
        write(self.product_dir / "entries.jsonl", json.dumps({"symbol": "x", "kind": "api_method"}))
        p = self._run_cli(self.root / "out5")
        self.assertNotEqual(0, p.returncode)
        self.assertIn("missing required key", p.stderr)

    def test_duplicate_symbol_fails(self):
        entry = {"symbol": "widget_init", "kind": "api_method", "signature": "widget_init(size)",
                  "summary": "Initialise.", "source_file": "guide.md",
                  "source_span": "The widget_init() call takes a size in bytes."}
        write(self.product_dir / "entries.jsonl", "\n".join([json.dumps(entry), json.dumps(entry)]))
        p = self._run_cli(self.root / "out6")
        self.assertNotEqual(0, p.returncode)
        self.assertIn("duplicate card id", p.stderr)

    def test_manifest_counts_match(self):
        entries = [
            {"symbol": "widget_init", "kind": "api_method", "signature": "widget_init(size)",
             "summary": "Initialise.", "source_file": "guide.md", "source_span": "The widget_init() call takes a size in bytes."},
            {"symbol": "nope", "kind": "api_method", "signature": "nope()", "summary": "x",
             "source_file": "guide.md", "source_span": "not present anywhere"},
        ]
        write(self.product_dir / "entries.jsonl", "\n".join(json.dumps(e) for e in entries))
        p = self._run_cli(self.root / "out7")
        self.assertEqual(1, p.returncode)
        manifest = json.loads((self.root / "out7" / "manifest.json").read_text())
        self.assertEqual(2, manifest["entries_total"])
        self.assertEqual(1, manifest["cards_written"])
        self.assertEqual(1, manifest["failures"])

    def test_esp32_div_fixture_entries_all_verify(self):
        """The real ESP32-DIV v2 seed content under manuals/esp32-div must still verify (regression guard)."""
        repo_manuals = HERE.parent / "manuals"
        p = __import__("subprocess").run(
            [sys.executable, str(HERE.parent / "extract" / "manual_extract.py"),
             "--manuals-root", str(repo_manuals), "--product", "esp32-div", "--out", str(self.root / "esp32out")],
            capture_output=True, text=True)
        self.assertEqual(0, p.returncode, p.stderr)
        manifest = json.loads((self.root / "esp32out" / "manifest.json").read_text())
        self.assertEqual(0, manifest["failures"])
        self.assertGreater(manifest["cards_written"], 15)


    def test_esp32_div_v2_engineering_entries_all_verify(self):
        """The first-party ESP32-DIV v2 engineering guide must keep every entry's span in its source (regression guard)."""
        repo_manuals = HERE.parent / "manuals"
        p = __import__("subprocess").run(
            [sys.executable, str(HERE.parent / "extract" / "manual_extract.py"),
             "--manuals-root", str(repo_manuals), "--product", "esp32-div-v2-engineering", "--out", str(self.root / "esp32eng")],
            capture_output=True, text=True)
        self.assertEqual(0, p.returncode, p.stderr)
        manifest = json.loads((self.root / "esp32eng" / "manifest.json").read_text())
        self.assertEqual(0, manifest["failures"])
        self.assertGreaterEqual(manifest["cards_written"], 50)


if __name__ == "__main__":
    unittest.main()
