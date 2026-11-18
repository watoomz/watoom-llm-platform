"""Host extractor tests; Blender is not needed for fixture conversion."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "extract" / "blender_extract.py"
FIXTURE = Path(__file__).with_name("fixtures") / "blender_rna.json"
SPEC = importlib.util.spec_from_file_location("blender_extract", SCRIPT)
extract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extract)


class BlenderExtractTests(unittest.TestCase):
    def setUp(self):
        self.raw = FIXTURE.read_bytes()
        self.cards, self.manifest = extract.convert(self.raw, "5.2.3")
        self.by_symbol = {card["symbol"]: card for card in self.cards}

    def test_operator_exact_signature_and_params(self):
        card = self.by_symbol["bpy.ops.mesh.primitive_cube_add"]
        self.assertEqual(card["signature"],
                         "bpy.ops.mesh.primitive_cube_add(*, size: float = 2.0, "
                         "calc_uvs: bool = True, enter_editmode: bool = False, "
                         "location: tuple[float, ...] = (0.0, 0.0, 0.0), "
                         "align: str = 'WORLD') -> set[str]")
        self.assertEqual(card["params"][0],
                         {"name": "size", "type": "float", "default": 2.0, "doc": "Size"})
        self.assertEqual(card["returns"], "set[str]")
        self.assertEqual(card["constraints"][0]["parameter"], "align")

    def test_macro_and_collection_defaults_from_native_introspection(self):
        op = {"properties": [
            {"name": "TRANSFORM_OT_translate", "type": "POINTER",
             "fixed_type": "OperatorProperties", "default": None, "description": "Move"},
            {"name": "path", "type": "COLLECTION", "description": "Path"}],
            "rna_signature": "bpy.ops.fixture.move(TRANSFORM_OT_translate="
                             "{'value': (0, 0, 0), 'snap_elements': {'INCREMENT'}}, path=[])"}
        props = extract.operator_properties(op)
        signature, _ = extract.callable_signature("bpy.ops.fixture.move", props, operator=True)
        self.assertEqual(signature,
                         "bpy.ops.fixture.move(*, TRANSFORM_OT_translate: dict[str, object] = "
                         "{'value': (0, 0, 0), 'snap_elements': {'INCREMENT'}}, "
                         "path: list[dict[str, object]] = []) -> set[str]")
        self.assertEqual(props[0]["default"]["snap_elements"], ["INCREMENT"])
        self.assertIsNone(op["properties"][0]["default"])
        op["rna_signature"] = "bpy.ops.fixture.move(TRANSFORM_OT_translate=run_code(), path=[])"
        with self.assertRaises(ValueError):
            extract.operator_properties(op)

    def test_function_inputs_and_outputs(self):
        card = self.by_symbol["bpy.types.Fixture.lookup"]
        self.assertEqual(card["signature"],
                         "bpy.types.Fixture.lookup(name: str, *, index: int = 0) "
                         "-> tuple[bpy.types.Object, bool]")
        self.assertEqual([p["name"] for p in card["params"]], ["name", "index"])
        self.assertEqual(card["kind"], "api_method")
        self.assertIsNone(card["params"][0]["default"])

    def test_property_function_name_collision_keeps_both_cards(self):
        dump = json.loads(self.raw)
        dump["structs"][0]["properties"][0]["name"] = "lookup"
        cards, _ = extract.convert(json.dumps(dump).encode(), "5.2.3")
        by_symbol = {c["symbol"]: c for c in cards}
        path = "bpy.types.Fixture.bl_rna.properties['lookup']"
        self.assertEqual(by_symbol[path]["kind"], "rna_property")
        self.assertEqual(by_symbol[path]["source"]["span"], path)
        self.assertEqual(by_symbol["bpy.types.Fixture.lookup"]["kind"], "api_method")
        self.assertEqual(len(cards), len(by_symbol))

    def test_properties_flags_arrays_readonly_and_enums(self):
        card = self.by_symbol["bpy.types.Fixture.options"]
        self.assertEqual(card["signature"],
                         "bpy.types.Fixture.options: set[str] = {'A', 'B'}")
        self.assertEqual(card["constraints"][0]["enum_items"][0]["description"], "First flag")
        self.assertEqual(self.by_symbol["bpy.types.Fixture.name"]["constraints"], ["read-only"])
        self.assertEqual(self.by_symbol["bpy.types.Fixture.matrix"]["signature"],
                         "bpy.types.Fixture.matrix: tuple[tuple[float, ...], ...] "
                         "= ((1.0, 0.0), (0.0, 1.0))")

    def test_manifest_schema_provenance_and_sorted_ids(self):
        digest = hashlib.sha256(self.raw).hexdigest()
        self.assertEqual(self.manifest["input_sha256"], digest)
        self.assertEqual(self.manifest["counts"],
                         {"operator": 2, "rna_struct": 1, "rna_property": 3, "api_method": 1})
        self.assertEqual(self.manifest["total_cards"], 7)
        ids = [c["id"] for c in self.cards]
        self.assertEqual(ids, sorted(set(ids)))
        for card in self.cards:
            extract.validate_card(card)
            self.assertEqual(card["source"]["span"], card["symbol"])
            self.assertEqual(card["source"]["revision"], "5.2.3+sha256:" + digest)

    def test_cli_dump_determinism_without_blender(self):
        with tempfile.TemporaryDirectory() as temporary:
            outputs = [Path(temporary) / name for name in ("one", "two")]
            for output in outputs:
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "--blender", "/does/not/exist",
                     "--dump", str(FIXTURE), "--version", "5.2.3", "--out", str(output)],
                    capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            for name in ("cards.jsonl", "manifest.json"):
                self.assertEqual((outputs[0] / name).read_bytes(),
                                 (outputs[1] / name).read_bytes())
            self.assertEqual(json.loads((outputs[0] / "manifest.json").read_text()),
                             self.manifest)

    def test_invalid_dump_and_version_fail_before_writing(self):
        with self.assertRaisesRegex(ValueError, "dump reports"):
            extract.convert(self.raw, "5.2.4")
        broken = json.loads(self.raw)
        broken["operators"].append(copy.deepcopy(broken["operators"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            extract.convert(json.dumps(broken).encode(), "5.2.3")
        broken["operators"][0]["properties"][0]["type"] = "UNKNOWN"
        with self.assertRaises(KeyError):
            extract.convert(json.dumps(broken).encode(), "5.2.3")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "unwritten"
            with mock.patch("sys.stderr"):
                self.assertEqual(extract.main(["--dump", str(FIXTURE), "--version", "5.2.4",
                                               "--out", str(output)]), 1)
            self.assertFalse(output.exists())

    def test_schema_rejects_bad_cards(self):
        for key, value in (("summary", "x" * 301), ("params", [{}]),
                           ("source", {}), ("kind", "invented"), ("returns", [])):
            with self.subTest(key=key):
                card = dict(self.cards[0], **{key: value})
                with self.assertRaises(ValueError):
                    extract.validate_card(card)

    def test_launch_arguments_cpu_and_timeout(self):
        def launch(command, **kwargs):
            self.assertEqual(command[:7],
                             ["/custom/blender", "-b", "--factory-startup",
                              "-noaudio", "--python-exit-code", "1", "--python"])
            self.assertEqual(Path(command[7]).name, "blender_inner.py")
            self.assertEqual(command[8], "--")
            self.assertEqual(kwargs["timeout"], 600)
            self.assertTrue(kwargs["check"])
            self.assertEqual(kwargs["env"]["CUDA_VISIBLE_DEVICES"], "")
            self.assertEqual(kwargs["env"]["LIBGL_ALWAYS_SOFTWARE"], "1")
            Path(command[-1]).write_bytes(self.raw)

        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.object(extract.subprocess, "run", side_effect=launch) as run:
                self.assertEqual(extract.main(["--blender", "/custom/blender",
                                               "--version", "5.2.3", "--out", temporary]), 0)
                run.assert_called_once()

    def test_inner_resolves_shadowed_rna_members(self):
        spec = importlib.util.spec_from_file_location(
            "blender_inner", ROOT / "extract" / "blender_inner.py")
        inner = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, {"bpy": mock.Mock()}):
            spec.loader.exec_module(inner)
        inherited = SimpleNamespace(identifier="poll", description="Base")
        override = SimpleNamespace(identifier="poll", description="Derived")
        other = SimpleNamespace(identifier="update", description="Update")

        class Collection:
            def __iter__(self):
                return iter([inherited, other, override])

            def __getitem__(self, name):
                return {"poll": override, "update": other}[name]

        self.assertEqual(inner.members(Collection()), [override, other])

    def test_inner_flag_default_uses_default_flag_and_live_enum_items(self):
        spec = importlib.util.spec_from_file_location(
            "blender_inner", ROOT / "extract" / "blender_inner.py")
        inner = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, {"bpy": mock.Mock()}):
            spec.loader.exec_module(inner)
        prop = SimpleNamespace(
            identifier="flags", type="ENUM", description="Options",
            is_readonly=False, is_required=False, is_output=False,
            is_enum_flag=True, default="", default_flag={"B", "A"},
            enum_items=[SimpleNamespace(identifier="A", name="Alpha",
                                        description="First", value=1)],
            enum_items_static=[])
        result = inner.property_definition(prop)
        self.assertEqual(result["default"], ["A", "B"])
        self.assertEqual(result["enum_items"], [
            {"identifier": "A", "name": "Alpha", "description": "First", "value": 1}])

    def test_dynamic_arrays_and_empty_flags(self):
        prop = {"name": "values", "type": "FLOAT", "is_array": True,
                "array_length": 0, "default": [], "description": "Values"}
        self.assertEqual(extract.declaration(prop), "values: tuple[float, ...] = ()")
        self.assertEqual(extract.default_literal({"is_enum_flag": True, "default": []}),
                         "set()")

    def test_subprocess_failure_and_timeout_do_not_write(self):
        for failure in (subprocess.CalledProcessError(1, ["blender"], output=b"RNA failure"),
                        subprocess.TimeoutExpired(["blender"], 600)):
            with self.subTest(failure=type(failure).__name__):
                with tempfile.TemporaryDirectory() as temporary:
                    output = Path(temporary) / "unwritten"
                    with mock.patch.object(extract.subprocess, "run", side_effect=failure):
                        with mock.patch("sys.stderr"):
                            self.assertEqual(extract.main(["--version", "5.2.3",
                                                           "--out", str(output)]), 1)
                    self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
