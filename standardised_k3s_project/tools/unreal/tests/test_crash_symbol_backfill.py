"""Exercise stale-symbol guards with genuinely different ELF build IDs."""
import hashlib
import importlib.util
import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("symbol_check", pathlib.Path(__file__).parents[1] / "check-crash-symbols.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

@unittest.skipUnless(shutil.which("gcc") and shutil.which("readelf"), "ELF fixture toolchain required")
class SymbolReplacementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = pathlib.Path(self.temp.name)
        self.root = self.base / "runtime"
        self.old = self.base / "baseline"
        self.out = self.base / "evidence"
        self.out.mkdir()
        self.relative = "Engine/Binaries/Linux/libFixture.so"
        for root, number in [(self.root, 2), (self.old, 1)]:
            binary = root / self.relative
            binary.parent.mkdir(parents=True)
            subprocess.run(["gcc", "-shared", "-fPIC", "-Wl,--build-id", "-x", "c", "-o", str(binary), "-"],
                           input=("int fixture(void){return %d;}" % number).encode(), check=True, capture_output=True)
        self.binary = self.root / self.relative
        self.target = self.binary.with_suffix(".sym")
        self.before = b"previous verified encoded symbol data" * 10
        self.target.write_bytes(self.before)
        (self.old / self.relative).with_suffix(".sym").write_bytes(self.before)
        self.generated = b"new verified encoded symbol data" * 10
        (self.out / "module.sym").write_bytes(self.generated)
        digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
        self.receipt = {"module":self.relative, "matching_debug_sidecar":True,
                        "symbol_records":{"FILE":1,"FUNC":1},
                        "binary_sha256":digest(self.binary),
                        "encoded_sha256":digest(self.out / "module.sym")}
        actual = subprocess.check_output
        def output(argv, **kwargs):
            if argv[0] == "findmnt":
                return json.dumps({"filesystems":[{"fstype":"overlay"}]}).encode()
            return actual(argv, **kwargs)
        self.addCleanup(patch.stopall)
        patch.object(module.subprocess, "check_output", side_effect=output).start()
        patch.object(module.os, "fchown").start()

    def test_existing_real_symbols_require_baseline_provenance(self):
        with self.assertRaises(AssertionError):
            module.backfill(self.root, self.receipt, self.out)
        self.assertEqual(self.target.read_bytes(), self.before)

    def test_unrelated_symbols_are_never_overwritten(self):
        self.target.write_bytes(b"independent symbol owner")
        with self.assertRaises(AssertionError):
            module.backfill(self.root, self.receipt, self.out, self.old)
        self.assertEqual(self.target.read_bytes(), b"independent symbol owner")

    def test_matching_build_symbols_are_preserved(self):
        shutil.copy2(self.binary, self.old / self.relative)
        with self.assertRaises(AssertionError):
            module.backfill(self.root, self.receipt, self.out, self.old)
        self.assertEqual(self.target.read_bytes(), self.before)

    def test_changed_build_replaces_only_proven_stale_symbols_and_is_idempotent(self):
        module.backfill(self.root, self.receipt, self.out, self.old)
        self.assertEqual(self.target.read_bytes(), self.generated)
        self.assertEqual((self.out / "stale-symbol.before").read_bytes(), self.before)
        self.assertEqual(hashlib.sha256(self.binary.read_bytes()).hexdigest(), self.receipt["binary_sha256"])
        module.backfill(self.root, self.receipt, self.out, self.old)
        self.assertEqual(self.target.read_bytes(), self.generated)

    @staticmethod
    def encoded(file, line=4, address=256):
        import struct
        files=file.encode()+bytes([10])
        return struct.pack("<I",1)+struct.pack("<QIII",address,line,0,len(files))+files+b"fixture"+bytes([10])

    def test_source_prefix_normalization_preserves_exact_mapping_but_not_changed_lines(self):
        a=self.base/"a.sym";b=self.base/"b.sym"
        a.write_bytes(self.encoded("/old/Engine/Source/Fixture.cpp"))
        b.write_bytes(self.encoded("/new/Engine/Source/Fixture.cpp"))
        self.assertEqual(module.semantic_symbol_digest(a),module.semantic_symbol_digest(b))
        b.write_bytes(self.encoded("/new/Engine/Source/Fixture.cpp",line=5))
        self.assertNotEqual(module.semantic_symbol_digest(a),module.semantic_symbol_digest(b))

    def test_equivalent_real_symbols_are_verified_without_replacement(self):
        existing=self.encoded("/old/Engine/Source/Fixture.cpp")
        self.target.write_bytes(existing)
        generated=self.encoded("/new/Engine/Source/Fixture.cpp")
        (self.out/"module.sym").write_bytes(generated)
        self.receipt["encoded_sha256"]=hashlib.sha256(generated).hexdigest()
        module.backfill(self.root,self.receipt,self.out)
        self.assertEqual(self.target.read_bytes(),existing)
        self.assertTrue(json.loads((self.out/"placeholder-backfill.json").read_text())["existing_real_symbols_preserved"])

    def test_changed_build_requires_full_baseline_mapping_when_prefix_bytes_differ(self):
        previous=self.encoded("/copied/Engine/Source/Fixture.cpp")
        self.target.write_bytes(previous)
        (self.old/self.relative).with_suffix(".sym").write_bytes(self.encoded("/baseline/Engine/Source/Fixture.cpp"))
        generated=self.encoded("/new/Engine/Source/Fixture.cpp",line=5)
        (self.out/"module.sym").write_bytes(generated)
        self.receipt["encoded_sha256"]=hashlib.sha256(generated).hexdigest()
        module.backfill(self.root,self.receipt,self.out,self.old)
        self.assertEqual(self.target.read_bytes(),generated)
        self.assertEqual((self.out/"stale-symbol.before").read_bytes(),previous)

if __name__ == "__main__":
    unittest.main()
