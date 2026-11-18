"""Offline, stdlib-only CLI extraction tests using small synthetic help fixtures."""

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
from unittest import mock


TESTS = Path(__file__).resolve().parent
SCRIPT = TESTS.parent / "extract" / "cli_extract.py"
FIXTURES = TESTS / "fixtures" / "cli"
SPEC = importlib.util.spec_from_file_location("cli_extract", SCRIPT)
extractor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extractor)


class CliExtractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cli-test-", dir=TESTS)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def cards(self, product):
        raw = (FIXTURES / (product + ".txt")).read_bytes()
        cards, manifest = extractor.convert(raw, product, "4.7.2" if product == "godot" else "5.2.3")
        return {c["symbol"].split(" ", 1)[1]: c for c in cards}, manifest

    def test_schema_counts_and_provenance(self):
        for product, total in (("godot", 8), ("blender", 15)):
            with self.subTest(product=product):
                cards, manifest = self.cards(product)
                self.assertEqual(manifest["counts"], {"cli_flag": total})
                self.assertEqual(manifest["total_cards"], total)
                self.assertEqual(manifest["generator_version"], extractor.GENERATOR_VERSION)
                digest = hashlib.sha256((FIXTURES / (product + ".txt")).read_bytes()).hexdigest()
                self.assertEqual(manifest["input_sha256"], digest)
                ids = [c["id"] for c in cards.values()]
                self.assertEqual(ids, sorted(set(ids)))
                for flag, card in cards.items():
                    extractor.validate(card)
                    self.assertEqual(card["kind"], "cli_flag")
                    self.assertEqual(card["language"], "cli")
                    self.assertEqual(card["id"], product + "." + card["symbol"] + "@" + card["version"])
                    self.assertEqual(card["source"]["span"], "--help " + flag)
                    self.assertEqual(card["source"]["revision"], card["version"] + "+sha256:" + digest)
                    self.assertEqual(card["license"], "MIT" if product == "godot" else "GPL-2.0-or-later")
                    self.assertEqual(card["params"], [])
                    self.assertIsNone(card["returns"])

    def test_godot_exact_declarations_and_aliases(self):
        cards, _ = self.cards("godot")
        expected = {"--help": "-h, --help", "--headless": "--headless",
                    "--export-release": "--export-release <preset> <path>",
                    "--convert-3to4": "--convert-3to4 [max_file_kb] [max_line_size]",
                    "--": "--, ++", "--bare": "--bare"}
        for flag, signature in expected.items():
            self.assertEqual(cards[flag]["signature"], signature)
        self.assertEqual(cards["--help"]["aliases"], ["--help", "-h"])
        self.assertEqual(cards["--"]["aliases"], ["++", "--"])
        self.assertEqual(cards["--bare"]["summary"], "")
        self.assertEqual(cards["--headless"]["summary"],
                         "Enable headless mode (--display-driver headless --audio-driver Dummy).")
        self.assertNotIn("--display-driver", cards)
        self.assertIn("Converts project", cards["--convert-3to4"]["summary"])

    def test_godot_constraints_and_continuations(self):
        cards, _ = self.cards("godot")
        self.assertIn("Only available in editor builds.", cards["--convert-3to4"]["constraints"])
        self.assertIn("The target directory must exist.", " ".join(cards["--export-release"]["constraints"]))
        self.assertIn("only with --editor", " ".join(cards["--editor-only"]["constraints"]))
        self.assertIn("use with --script", " ".join(cards["--check-only"]["constraints"]))
        self.assertNotIn("--script", cards)

    def test_ansi_and_whitespace_only_normalization(self):
        raw = (FIXTURES / "godot.txt").read_bytes()
        colored = raw.replace(b"--headless", b"\x1b[92m--headless\x1b[0m")
        plain, _ = extractor.convert(raw, "godot", "4.7.2")
        decorated, _ = extractor.convert(colored, "godot", "4.7.2")
        for before, after in zip(plain, decorated):
            self.assertEqual(before["signature"], after["signature"])
            self.assertEqual(before["summary"], after["summary"])
            self.assertEqual(before["constraints"], after["constraints"])
        cards, _ = extractor.convert(b"Options:\n  --arg <X>,<Y>  Keep punctuation.\n", "godot", "4.7.2")
        self.assertEqual(cards[0]["signature"], "--arg <X>,<Y>")

    def test_blender_declarations_aliases_and_nested_playback(self):
        cards, _ = self.cards("blender")
        self.assertEqual(cards["--background"]["signature"], "-b or --background")
        self.assertEqual(cards["--background"]["aliases"], ["--background", "-b"])
        self.assertEqual(cards["--python-expr"]["signature"], "--python-expr <expression>")
        self.assertEqual(cards["--background"]["summary"], "Run in background (often used for UI-less rendering).")
        self.assertEqual(cards["-a"]["signature"], "-a <options> <file(s)>")
        self.assertEqual(cards["--render-anim"]["signature"], "-a or --render-anim")
        self.assertEqual(cards["-f"]["signature"], "-f <fps> <fps_base>")
        self.assertIn("Playback Arguments:", cards["-f"]["constraints"])
        self.assertEqual(cards["--render-frame"]["signature"], "-f or --render-frame <frame>")
        self.assertEqual(cards["--log"]["signature"], "--log <match>")
        self.assertEqual(cards["/?"]["signature"], "/?")
        self.assertNotIn("--background test.blend", cards)

    def test_blender_conditions(self):
        cards, _ = self.cards("blender")
        condition = "Cycles add-on options must be specified following a double dash."
        for flag in ("--cycles-device", "--cycles-print-stats"):
            self.assertIn(condition, cards[flag]["constraints"])
        for card in cards.values():
            self.assertIn("Arguments are executed in the order they are given. eg:", card["constraints"])
        self.assertIn("ignored if '-b' is set", " ".join(cards["-a"]["constraints"]))
        self.assertIn("only for scripts", " ".join(cards["--python-exit-code"]["constraints"]))
        self.assertIn("must be last argument", " ".join(cards["--last"]["constraints"]))
        self.assertNotIn("Environment Variables", cards["--last"]["summary"])

    def test_summary_cap_keeps_full_conditions(self):
        description = "x" * 310 + " only with --editor."
        cards, _ = extractor.convert(("Options:\n  --long  " + description).encode(), "godot", "4.7.2")
        self.assertEqual(len(cards[0]["summary"]), 300)
        self.assertEqual(cards[0]["constraints"], [description])

    def test_deterministic_output_relocated_input_and_raw_hash(self):
        for product, version in (("godot", "4.7.2"), ("blender", "5.2.3")):
            source = FIXTURES / (product + ".txt")
            relocated = self.base / "relocated.txt"
            shutil.copyfile(source, relocated)
            first, second = self.base / "first", self.base / "second"
            manifest = extractor.extract(product, None, version, first, source)
            self.assertEqual(manifest, extractor.extract(product, "/never/run", version, second, relocated))
            for filename in ("cards.jsonl", "manifest.json"):
                self.assertEqual((first / filename).read_bytes(), (second / filename).read_bytes())
            relocated.write_bytes(source.read_bytes() + b"\n")
            changed = extractor.extract(product, None, version, second, relocated)
            self.assertNotEqual(manifest["input_sha256"], changed["input_sha256"])

    def test_cli_saved_help_and_failures(self):
        command = [sys.executable, "-B", str(SCRIPT), "--product", "blender", "--version", "5.2.3",
                   "--out", str(self.base / "out"), "--help-file", str(FIXTURES / "blender.txt")]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["total_cards"], 15)
        for args in (command[:-2], command[:-1] + [str(self.base / "missing")],
                     command[:6] + ["5.2"] + command[7:]):
            result = subprocess.run(args, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("cli_extract:", result.stderr)

    def test_binary_command_timeout_and_nonzero_exit(self):
        for product, expected in (("godot", ["--headless", "--help"]), ("blender", ["--help"])):
            raw = (FIXTURES / (product + ".txt")).read_bytes()
            with mock.patch.object(extractor.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, raw)) as run:
                extractor.extract(product, "/tool", "1.2.3", self.base / product)
                self.assertEqual(run.call_args.args[0], ["/tool"] + expected)
                self.assertTrue(run.call_args.kwargs["check"])
                self.assertEqual(run.call_args.kwargs["timeout"], extractor.HELP_TIMEOUT)
            for error in (subprocess.TimeoutExpired(["/tool"], 180), subprocess.CalledProcessError(1, ["/tool"])):
                with mock.patch.object(extractor.subprocess, "run", side_effect=error):
                    with self.assertRaises(subprocess.SubprocessError):
                        extractor.extract(product, "/tool", "1.2.3", self.base / "failed")
                    self.assertFalse((self.base / "failed").exists())

    def test_reject_invalid_inputs_and_duplicates(self):
        for raw, product, version in ((b"", "godot", "4.7.2"), (b"No options.", "blender", "5.2.3"),
                                      (b"--flag", "other", "1.2.3"), (b"--flag", "godot", "4.7"),
                                      (b"--flag", "godot", "4.7.2-dev"),
                                      (b"Options:\n  --same  First.\n  --same  Second.", "godot", "4.7.2")):
            with self.subTest(raw=raw, product=product, version=version), self.assertRaises(ValueError):
                extractor.convert(raw, product, version)

    def test_schema_rejections(self):
        cards, _ = self.cards("godot")
        for key, value in (("product", "other"), ("kind", "api_method"), ("language", "python"),
                           ("version", "4.7"), ("id", "bad"), ("summary", "x" * 301),
                           ("signature", ""), ("params", [{}]), ("source", {}),
                           ("returns", 1), ("constraints", [None]), ("aliases", [1]),
                           ("deprecated", "false"), ("trust_tier", "untrusted")):
            card = copy.deepcopy(cards["--help"])
            card[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                extractor.validate(card)


if __name__ == "__main__":
    unittest.main()
