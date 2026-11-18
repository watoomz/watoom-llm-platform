#!/usr/bin/env python3
"""Extract versioned Blender knowledge cards using only the host stdlib.

RNA supplies types, defaults and parameter order; no hand-written API signatures
are used. Operators accept keyword arguments only. RNA function output parameters
become return annotations, while required inputs have no default in signatures.
"""

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from collections import Counter


GENERATOR_VERSION = "1.0.0"
DEFAULT_BLENDER = "/data/ai/toolchains/blender/5.2.3/blender-5.2.3-linux-x64/blender"
KINDS = {"operator", "rna_struct", "rna_property", "api_method"}


ENUM_ITEM_CAP = 64


def cap_enum(items):
    """Huge enums (UI icons, ~1000 items repeated per parameter) bloat the index; keep the first ENUM_ITEM_CAP verbatim
    and record the true total so truncation is explicit, never silent."""
    if len(items) <= ENUM_ITEM_CAP:
        return {"enum_items": items}
    return {"enum_items": items[:ENUM_ITEM_CAP], "enum_items_total": len(items), "enum_items_truncated": True}


def rna_type(prop):
    if "python_type" in prop:
        return prop["python_type"]
    scalar = {"BOOLEAN": "bool", "INT": "int", "FLOAT": "float",
              "STRING": "str", "ENUM": "str", "POINTER": "None",
              "COLLECTION": "bpy_prop_collection"}[prop["type"]]
    if prop["type"] in {"POINTER", "COLLECTION"} and prop.get("fixed_type"):
        scalar = "bpy.types." + prop["fixed_type"]
        if prop["type"] == "COLLECTION":
            scalar = f"bpy_prop_collection[{scalar}]"
    if prop.get("is_enum_flag"):
        scalar = "set[str]"
    if prop.get("subtype") == "BYTE_STRING":
        scalar = "bytes"
    if prop.get("is_array") or prop.get("array_length"):
        dimensions = [d for d in prop.get("array_dimensions", []) if d]
        for _ in dimensions or [prop["array_length"]]:
            scalar = f"tuple[{scalar}, ...]"
    return scalar


def default_literal(prop):
    if "native_default" in prop:
        return prop["native_default"]
    value = prop["default"]
    if prop.get("is_enum_flag"):
        return "{" + ", ".join(repr(v) for v in sorted(value)) + "}" if value else "set()"
    if prop.get("subtype") == "BYTE_STRING":
        return repr(value.encode("utf-8"))
    if prop.get("is_array") or prop.get("array_length"):
        dimensions = [d for d in prop.get("array_dimensions", []) if d]

        def shape(values, dims):
            if len(dims) <= 1:
                return tuple(values)
            stride = len(values) // dims[0]
            return tuple(shape(values[i:i + stride], dims[1:])
                         for i in range(0, len(values), stride))

        value = shape(value, dimensions)
    return repr(value)


def parameter(prop):
    return {"name": prop["name"], "type": rna_type(prop),
            "default": None if prop.get("is_required") else prop.get("default"),
            "doc": prop["description"]}


def declaration(prop, required=False):
    text = f"{prop['name']}: {rna_type(prop)}"
    if "default" in prop and not required:
        text += " = " + default_literal(prop)
    return text


def operator_properties(op):
    """Macro dictionaries/collection defaults come from Blender's own signature.

    RNA alone cannot describe overridden defaults on nested macro operators.
    Parse the generated signature as data; never evaluate API or project code.
    """
    props = [dict(p) for p in op["properties"]]
    complex_props = [p for p in props if p["type"] in {"POINTER", "COLLECTION"}]
    if not complex_props:
        return props
    signature = op["rna_signature"]
    call = ast.parse(signature, mode="eval").body
    if not isinstance(call, ast.Call):
        raise ValueError("Expected Blender-generated operator call signature")
    defaults = {kw.arg: kw.value for kw in call.keywords}

    def json_value(value):
        if isinstance(value, set):
            return sorted(value)
        if isinstance(value, (tuple, list)):
            return [json_value(v) for v in value]
        if isinstance(value, dict):
            return {k: json_value(v) for k, v in value.items()}
        return value

    for prop in complex_props:
        node = defaults[prop["name"]]
        prop["native_default"] = ast.get_source_segment(signature, node)
        prop["default"] = json_value(ast.literal_eval(node))
        prop["python_type"] = ("dict[str, object]" if prop["type"] == "POINTER"
                               else "list[dict[str, object]]")
    return props


def callable_signature(symbol, inputs, outputs=(), operator=False):
    args = []
    if operator and inputs:
        args.append("*")
    optional_seen = False
    for prop in inputs:
        required = prop.get("is_required", False) and not operator
        # RNA optional function parameters are keyword-only after required inputs.
        if not operator and not required and not optional_seen:
            args.append("*")
            optional_seen = True
        args.append(declaration(prop, required))
    returns = None
    if outputs:
        types = [rna_type(prop) for prop in outputs]
        returns = types[0] if len(types) == 1 else "tuple[" + ", ".join(types) + "]"
    elif operator:
        returns = "set[str]"
    signature = symbol + "(" + ", ".join(args) + ")"
    if returns:
        signature += " -> " + returns
    return signature, returns


def validate_card(card):
    strings = ("id", "product", "language", "version", "kind", "symbol",
               "signature", "summary", "license", "trust_tier", "status")
    for key in strings:
        if not isinstance(card.get(key), str):
            raise ValueError(f"Invalid card {key}: {card.get('symbol')}")
    if "returns" not in card:
        raise ValueError("Missing returns")
    for key in ("params", "aliases", "constraints", "examples"):
        if not isinstance(card.get(key), list):
            raise ValueError(f"Invalid card {key}")
    if (card["product"] != "blender" or card["language"] != "python"
            or card["kind"] not in KINDS or len(card["summary"]) > 300
            or card["id"] != f"blender.{card['symbol']}@{card['version']}"
            or card["trust_tier"] != "official" or card["status"] != "source_checked"):
        raise ValueError(f"Invalid card identity: {card['symbol']}")
    if card.get("returns") is not None and not isinstance(card["returns"], str):
        raise ValueError("Invalid returns")
    for param in card["params"]:
        if set(param) != {"name", "type", "default", "doc"} or not all(
                isinstance(param[k], str) for k in ("name", "type", "doc")):
            raise ValueError("Invalid parameter")
    source = card.get("source", {})
    if set(source) != {"uri", "revision", "span"} or not all(
            isinstance(v, str) and v for v in source.values()):
        raise ValueError("Invalid source")
    if "deprecated" in card and not isinstance(card["deprecated"], bool):
        raise ValueError("Invalid deprecated flag")
    json.dumps(card, allow_nan=False)


def convert(raw, version):
    dump = json.loads(raw)
    if dump["version"] != version:
        raise ValueError(f"Requested Blender {version}, dump reports {dump['version']}")
    digest = hashlib.sha256(raw).hexdigest()
    cards = []

    def enum_constraints(props):
        return [dict({"parameter": p["name"]}, **cap_enum(p["enum_items"]))
                for p in props if p.get("enum_items")]

    def add(kind, symbol, signature, description, params=(), returns=None,
            constraints=()):
        card = {
            "id": f"blender.{symbol}@{version}", "product": "blender",
            "language": "python", "version": version, "kind": kind,
            "symbol": symbol, "signature": signature,
            "summary": description[:300], "params": list(params),
            "returns": returns, "aliases": [], "constraints": list(constraints),
            "examples": [], "source": {
                "uri": f"https://docs.blender.org/api/{version.rsplit('.', 1)[0]}/",
                "revision": f"{version}+sha256:{digest}", "span": symbol},
            "license": "GPL-2.0-or-later", "trust_tier": "official",
            "status": "source_checked",
        }
        validate_card(card)
        cards.append(card)

    for op in dump["operators"]:
        symbol = f"bpy.ops.{op['module']}.{op['name']}"
        props = operator_properties(op)
        signature, returns = callable_signature(symbol, props, operator=True)
        add("operator", symbol, signature, op["description"],
            [parameter(p) for p in props], returns, enum_constraints(props))
    for struct in dump["structs"]:
        symbol = "bpy.types." + struct["name"]
        add("rna_struct", symbol, symbol, struct["description"])
        function_names = {fn["name"] for fn in struct["functions"]}
        for prop in struct["properties"]:
            path = symbol + "." + prop["name"]
            # RenderEngine.render exists as both a property and a function in
            # live RNA. Use the explicit property RNA path to keep both cards
            # while satisfying the contract's unique product.symbol@version ID.
            if prop["name"] in function_names:
                path = symbol + ".bl_rna.properties[" + repr(prop["name"]) + "]"
            constraints = ["read-only"] if prop["is_readonly"] else []
            if prop.get("enum_items"):
                constraints.append(cap_enum(prop["enum_items"]))
            add("rna_property", path, symbol + "." + declaration(prop),
                prop["description"], constraints=constraints)
        for fn in struct["functions"]:
            path = symbol + "." + fn["name"]
            inputs = [p for p in fn["parameters"] if not p["is_output"]]
            outputs = [p for p in fn["parameters"] if p["is_output"]]
            signature, returns = callable_signature(path, inputs, outputs)
            add("api_method", path, signature, fn["description"],
                [parameter(p) for p in inputs], returns, enum_constraints(inputs))
    cards.sort(key=lambda card: card["id"])
    if len({card["id"] for card in cards}) != len(cards):
        duplicates = [key for key, count in Counter(c["id"] for c in cards).items()
                      if count > 1]
        raise ValueError("Duplicate card IDs in RNA dump: " + ", ".join(duplicates[:10]))
    manifest = {"product": "blender", "tool_version": version,
                "input_sha256": digest, "generator_version": GENERATOR_VERSION,
                "counts": dict(sorted(Counter(c["kind"] for c in cards).items())),
                "total_cards": len(cards)}
    return cards, manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", default=DEFAULT_BLENDER)
    parser.add_argument("--version", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--dump", type=Path)
    args = parser.parse_args(argv)
    try:
        if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
            raise ValueError("--version must be x.y.z")
        if args.dump:
            raw = args.dump.read_bytes()
        else:
            with tempfile.TemporaryDirectory(prefix="blender-rna-") as temporary:
                output = Path(temporary) / "rna.json"
                env = os.environ.copy()
                env.update({"CUDA_VISIBLE_DEVICES": "", "HIP_VISIBLE_DEVICES": "",
                            "ROCR_VISIBLE_DEVICES": "", "LIBGL_ALWAYS_SOFTWARE": "1"})
                subprocess.run([
                    args.blender, "-b", "--factory-startup", "-noaudio",
                    "--python-exit-code", "1",
                    "--python", str(Path(__file__).with_name("blender_inner.py")),
                    "--", str(output)], check=True, timeout=600, env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                raw = output.read_bytes()
        cards, manifest = convert(raw, args.version)
        args.out.mkdir(parents=True, exist_ok=True)
        with (args.out / "cards.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
            for card in cards:
                stream.write(json.dumps(card, sort_keys=True, ensure_ascii=True,
                                        allow_nan=False) + "\n")
        (args.out / "manifest.json").write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return 0
    except (OSError, ValueError, KeyError, TypeError, SyntaxError,
            subprocess.SubprocessError) as exc:
        print(f"blender_extract: {exc}", file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError) and exc.stdout:
            print(exc.stdout[-4000:].decode("utf-8", errors="replace"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
