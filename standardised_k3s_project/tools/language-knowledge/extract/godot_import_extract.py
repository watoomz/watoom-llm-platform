#!/usr/bin/env python3
"""Extract Godot import-option cards from the installed engine, offline.

The engine itself is the source of truth: tiny sample assets (generated here, no project code) are imported headless, and the `.import` file the editor
writes for each one lists every option of its importer with its default. One card describes one (importer, option) pair across the file types that use it,
for example the `scene` importer's `fbx/embedded_image_handling` for .fbx files. Signatures are the exact `key=value` lines from `[params]`.

Enum value labels come from the engine binary's own hint strings. The mapping from an option to its hint string is curated (HINTS below), but a label is
only emitted when that exact string is present in the binary; otherwise it is dropped and recorded in the manifest. The input hash covers the sorted
`[params]` blocks (the only deterministic part of a `.import` file) and the verified hint strings, independent of paths.
With --imports-dir the engine is not run: previously written `.import` files are read instead (used by the tests).
"""

import argparse
from collections import Counter, OrderedDict
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import wave
import zlib

GENERATOR_VERSION = "1.0.0"
IMPORT_TIMEOUT = 300
KIND = "import_option"
_spec = importlib.util.spec_from_file_location("_import_godot_schema", Path(__file__).with_name("godot_extract.py"))
_schema = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_schema)

EMBEDDED = "Discard All Textures,Extract Textures,Embed as Basis Universal,Embed as Uncompressed"
NAMING = "Godot 4.0 or 4.1,Godot 4.2 to 4.4,Godot 4.5 or later"
# (importer, option) -> the engine's enum hint string for it. Verified against the binary at extraction time.
HINTS = {
    ("scene", "fbx/embedded_image_handling"): EMBEDDED,
    ("scene", "gltf/embedded_image_handling"): EMBEDDED,
    ("scene", "fbx/naming_version"): NAMING,
    ("scene", "gltf/naming_version"): NAMING,
    ("scene", "fbx/importer"): "ufbx,FBX2glTF",
    ("scene", "materials/extract"): "Keep Internal,Extract Once,Extract and Overwrite",
    ("scene", "materials/extract_format"): "Text (*.tres),Binary (*.res),Material (*.material)",
    ("scene", "meshes/light_baking"): "Disabled,Static,Static Lightmaps,Dynamic",
    ("texture", "compress/mode"): "Lossless,Lossy,VRAM Compressed,VRAM Uncompressed,Basis Universal",
}


def _png():
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + chunk(b"IEND", b""))


def _gltf_json():
    buffer = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    return {"asset": {"version": "2.0"},
            "buffers": [{"uri": "data:application/octet-stream;base64," + base64.b64encode(buffer).decode(), "byteLength": 36}],
            "bufferViews": [{"buffer": 0, "byteLength": 36}],
            "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3", "min": [0, 0, 0], "max": [1, 1, 0]}],
            "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}], "nodes": [{"mesh": 0}], "scenes": [{"nodes": [0]}], "scene": 0}


def _glb():
    body = json.dumps(_gltf_json(), separators=(",", ":")).encode()
    body += b" " * (-len(body) % 4)
    return b"glTF" + struct.pack("<II", 2, 12 + 8 + len(body)) + struct.pack("<I", len(body)) + b"JSON" + body


def write_samples(directory):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "project.godot").write_text('config_version=5\n\n[application]\nconfig/name="wlk-import-probe"\n')
    (directory / "s.png").write_bytes(_png())
    with wave.open(str(directory / "s.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 80)
    (directory / "s.obj").write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    (directory / "s.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"><rect width="4" height="4"/></svg>')
    (directory / "s.csv").write_text("keys,en\nA,Hello\n")
    (directory / "s.gltf").write_text(json.dumps(_gltf_json(), sort_keys=True))
    (directory / "s.glb").write_bytes(_glb())
    (directory / "s.fbx").write_text("; FBX 7.4.0 project file\nFBXHeaderExtension:  {\n\tFBXHeaderVersion: 1003\n\tFBXVersion: 7400\n}\nObjects:  {\n}\n")


def parse_import(text):
    """Return (importer, resource type, ordered [params] {key: raw value text})."""
    importer = re.search(r'^importer="([^"]+)"', text, re.M)
    rtype = re.search(r'^type="([^"]+)"', text, re.M)
    params = OrderedDict()
    block = re.search(r"^\[params\]\s*$(.*)", text, re.M | re.S)
    if block:
        for line in block.group(1).splitlines():
            match = re.match(r"^([A-Za-z_][\w/]*)=(.*)$", line)
            if match:
                params[match[1]] = match[2]
    return (importer[1] if importer else None), (rtype[1] if rtype else None), params


def value_type(raw):
    if raw in ("true", "false"):
        return "bool"
    if re.fullmatch(r"-?\d+", raw):
        return "int"
    if re.fullmatch(r"-?\d+\.\d*(?:e[+-]?\d+)?|-?\d*\.\d+", raw):
        return "float"
    if raw.startswith('"'):
        return "String"
    if raw == "null":
        return "null"
    if raw.startswith("{"):
        return "Dictionary"
    if raw.startswith("Packed") or raw.startswith("Array") or raw.startswith("["):
        return "Array"
    return "Variant"


def labels(hint):
    return hint.split(",")


def build_cards(entries, binary_bytes, version):
    """entries: [(ext, importer, params)]. Returns (cards, manifest-extras)."""
    grouped = OrderedDict()
    for ext, importer, params in entries:
        for key, raw in params.items():
            if key.startswith("_"):
                continue  # internal bookkeeping such as _subresources
            grouped.setdefault((importer, key), OrderedDict())[ext] = raw
    verified, dropped = {}, []
    for pair, hint in sorted(HINTS.items()):
        (verified.__setitem__(pair, hint) if hint.encode() in binary_bytes else dropped.append("%s:%s" % pair))
    digest = hashlib.sha256()
    for ext, importer, params in sorted(entries, key=lambda e: e[0]):
        for part in (ext, importer, "\n".join("%s=%s" % kv for kv in sorted(params.items()))):
            digest.update(len(part.encode()).to_bytes(8, "big"))
            digest.update(part.encode())
    for pair, hint in sorted(verified.items()):
        digest.update(("%s:%s=%s" % (pair[0], pair[1], hint)).encode())
    input_sha = digest.hexdigest()
    cards = []
    for (importer, key), by_ext in sorted(grouped.items()):
        exts = sorted(by_ext)
        defaults = {ext: by_ext[ext] for ext in exts}
        same = len(set(defaults.values())) == 1
        first = defaults[exts[0]]
        signature = "%s=%s" % (key, first) if same else "; ".join("%s: %s=%s" % (ext, key, defaults[ext]) for ext in exts)
        hint = verified.get((importer, key))
        values = labels(hint) if hint else []
        constraints = ["Set under [params] in the asset's `<file>.import` (also in the Import dock); the editor writes it with the default shown when the file is first imported.",
                       "Importer: `%s`; applies to: %s." % (importer, ", ".join("." + e for e in exts))]
        if values:
            constraints.append("Values: " + "; ".join("%d = %s" % (i, v) for i, v in enumerate(values)) + ".")
        if not same:
            constraints.append("Default differs by file type: " + ", ".join("." + e + " " + defaults[e] for e in exts) + ".")
        default_text = first if same else ", ".join("." + e + " " + defaults[e] for e in exts)
        label = ""
        if values and same and re.fullmatch(r"\d+", first) and int(first) < len(values):
            label = " = " + values[int(first)]
        summary = "Import option of the `%s` importer (%s). Default: %s%s." % (importer, ", ".join("." + e for e in exts), default_text, label)
        if values:
            summary += " Values: " + "; ".join("%d %s" % (i, v) for i, v in enumerate(values)) + "."
        symbol = "%s:%s" % (importer, key)
        words = re.sub(r"[/_]+", " ", key).strip()
        bare = key.split("/")[-1]
        bare_words = re.sub(r"[_]+", " ", bare).strip()
        aliases = sorted({key.lower(), symbol.lower(), words.lower(), bare.lower(), bare_words.lower()} | {"%s:%s" % (e, key.lower()) for e in exts} | {"%s %s" % (e, bare_words.lower()) for e in exts})
        card = {
            "id": "godot." + symbol + "@" + version, "product": "godot", "language": "import", "version": version, "kind": KIND,
            "symbol": symbol, "signature": signature, "summary": summary[:300],
            "params": [{"name": key, "type": value_type(first), "default": first if same else None,
                        "doc": ("; ".join("%d = %s" % (i, v) for i, v in enumerate(values))) if values else ""}],
            "returns": None, "aliases": aliases, "constraints": constraints, "examples": [],
            "source": {"uri": "godot://import/" + importer, "revision": version + "+sha256:" + input_sha,
                       "span": "%s.import#params/%s" % (exts[0], key)},
            "license": "MIT", "trust_tier": "official", "status": "source_checked", "deprecated": False,
        }
        cards.append(card)
    return cards, {"input_sha256": input_sha, "labels_verified": len(verified), "labels_dropped": dropped}


def validate(card):
    if card.get("kind") != KIND or card.get("language") != "import" or not card.get("symbol", "").count(":") == 1:
        raise ValueError("invalid import card identity")
    _schema.validate(dict(card, kind="api_property"))


def extract(binary, version, out, imports_dir=None):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("version must be x.y.z")
    binary_bytes = Path(binary).read_bytes()
    cleanup = None
    if imports_dir is None:
        cleanup = tempfile.TemporaryDirectory(prefix="wlk-import-")
        project = Path(cleanup.name)
        write_samples(project)
        env = dict(os.environ, GODOT_SILENCE_ROOT_WARNING="1")
        subprocess.run([str(binary), "--headless", "--path", str(project), "--import"], check=False, timeout=IMPORT_TIMEOUT,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        imports_dir = project
    try:
        entries = []
        for path in sorted(Path(imports_dir).glob("*.import")):
            ext = path.name[:-len(".import")].rsplit(".", 1)[-1].lower()
            importer, _, params = parse_import(path.read_text(encoding="utf-8"))
            if importer and params:
                entries.append((ext, importer, params))
        if not entries:
            raise ValueError("no .import files with [params] found (did the engine import the samples?)")
        cards, extras = build_cards(entries, binary_bytes, version)
        seen = set()
        for card in cards:
            validate(card)
            if card["id"] in seen:
                raise ValueError("duplicate card id: " + card["id"])
            seen.add(card["id"])
        counts = Counter(card["kind"] for card in cards)
        manifest = {"product": "godot", "tool_version": version, "generator_version": GENERATOR_VERSION, "input_files": len(entries),
                    "total_cards": len(cards), "counts": {KIND: counts[KIND]}, "file_types": sorted(e[0] for e in entries), **extras}
        out.mkdir(parents=True, exist_ok=True)
        with (out / "cards.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
            for card in cards:
                stream.write(json.dumps(card, ensure_ascii=False, sort_keys=True) + "\n")
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return manifest
    finally:
        if cleanup:
            cleanup.cleanup()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--imports-dir", type=Path, help="read existing .import files instead of running the engine")
    args = parser.parse_args(argv)
    try:
        manifest = extract(args.binary, args.version, args.out, args.imports_dir)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(1, "godot_import_extract: " + str(exc) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
