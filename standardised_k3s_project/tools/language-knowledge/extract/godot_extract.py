#!/usr/bin/env python3
"""Extract v1 knowledge cards from Godot class-reference XML, offline.

Input SHA256 covers sorted filenames and raw bytes, each length-prefixed to
avoid ambiguous concatenations. Enum declarations are reconstructed from their
constants in XML order. Signatures use local enum names within their own class,
qualified names elsewhere, and append XML method qualifiers after the return.
"""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


GENERATOR_VERSION = "1.0.0"
KINDS = ("api_class", "api_method", "api_property", "api_signal",
         "api_constant", "api_enum")


def plain_text(text):
    # Protect Godot's escaped literal brackets before removing BBCode.
    text = text.replace("[lb]", "\x00").replace("[rb]", "\x01")
    text = re.sub(r"\[(?:method|member|signal|constant|enum|param) ([^\]]+)\]",
                  r"\1", text)
    text = re.sub(r"\[([A-Z][A-Za-z0-9_.]*)\]", r"\1", text)
    text = text.replace("[br]", " ")
    text = re.sub(r"\[/?[A-Za-z_][^\]\n]*\]", "", text)
    return " ".join(text.replace("\x00", "[").replace("\x01", "]").split())


def summary(element):
    for tag in ("brief_description", "description"):
        child = element.find(tag)
        if child is not None:
            text = plain_text("".join(child.itertext()))
            if text:
                return text[:300]
    return plain_text(element.text or "")[:300]


def aliases(symbol):
    def snake(name):
        name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
        return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()

    def pascal(name):
        return "".join(part[:1].upper() + part[1:] for part in name.split("_"))

    parts = symbol.split(".")
    return sorted({symbol.lower(), ".".join(map(snake, parts)),
                   ".".join(map(pascal, parts))})


def type_name(element, owner):
    name = element.get("enum", element.get("type"))
    if not name:
        raise ValueError("missing XML type")
    if name.startswith(owner + "."):
        name = name[len(owner) + 1:]
    if element.get("is_bitfield") == "true":
        name = "BitField[" + name + "]"
    return name


def markers(*elements):
    constraints = []
    deprecated = False
    for element in elements:
        for attr in ("deprecated", "experimental"):
            # Godot uses presence (including an empty reason) as the marker.
            if attr in element.attrib:
                deprecated = True
                reason = plain_text(element.attrib[attr])
                entry = attr + (": " + reason if reason else "")
                if entry not in constraints:
                    constraints.append(entry)
    return deprecated, constraints


def class_cards(root, version, digest):
    owner = root.attrib["name"]
    if root.tag != "class" or not owner:
        raise ValueError("expected named class root")

    def card(element, kind, symbol, signature, span, params=None, returns=None,
             marked=None):
        deprecated, constraints = markers(*(marked or [element]))
        return {
            "id": "godot." + symbol + "@" + version,
            "product": "godot", "language": "gdscript", "version": version,
            "kind": kind, "symbol": symbol, "signature": signature,
            "summary": summary(element), "params": params or [],
            "returns": returns, "aliases": aliases(symbol),
            "constraints": constraints, "examples": [],
            "source": {
                "uri": "https://docs.godotengine.org/en/" +
                       ".".join(version.split(".")[:2]) +
                       "/classes/class_" + owner.lower() + ".html",
                "revision": version + "+sha256:" + digest,
                "span": owner + ".xml#" + span,
            },
            "license": "MIT", "trust_tier": "official",
            "status": "source_checked", "deprecated": deprecated,
        }

    signature = "class " + owner
    if root.get("inherits"):
        signature += " extends " + root.attrib["inherits"]
    yield card(root, "api_class", owner, signature, "class")

    for tag, kind in (("method", "api_method"), ("signal", "api_signal")):
        for element in root.findall("./" + tag + "s/" + tag):
            symbol = owner + "." + element.attrib["name"]
            params = []
            for param in sorted(element.findall("param"),
                                key=lambda p: int(p.attrib["index"])):
                params.append({"name": param.attrib["name"],
                               "type": type_name(param, owner),
                               "default": param.get("default"),
                               "doc": summary(param)})
            arguments = [p["name"] + ": " + p["type"] +
                         (" = " + p["default"] if p["default"] is not None else "")
                         for p in params]
            qualifiers = element.get("qualifiers", "")
            if "vararg" in qualifiers.split():
                arguments.append("...")
            signature = symbol + "(" + ", ".join(arguments) + ")"
            returns = None
            if tag == "method":
                ret = element.find("return")
                if ret is None:
                    raise ValueError(symbol + ": missing return element")
                returns = type_name(ret, owner)
                signature += " -> " + returns
            if qualifiers:
                signature += " " + qualifiers
            yield card(element, kind, symbol, signature,
                       tag + "[@name='" + element.attrib["name"] + "']",
                       params, returns)

    for element in root.findall("./members/member"):
        symbol = owner + "." + element.attrib["name"]
        signature = symbol + ": " + type_name(element, owner)
        if "default" in element.attrib:
            signature += " = " + element.attrib["default"]
        yield card(element, "api_property", symbol, signature,
                   "member[@name='" + element.attrib["name"] + "']")

    enums = {}
    for element in root.findall("./constants/constant"):
        symbol = owner + "." + element.attrib["name"]
        signature = symbol + " = " + element.attrib["value"]
        yield card(element, "api_constant", symbol, signature,
                   "constant[@name='" + element.attrib["name"] + "']")
        if element.get("enum"):
            enums.setdefault(element.attrib["enum"], []).append(element)
    for name, elements in enums.items():
        symbol = name if name.startswith(owner + ".") else owner + "." + name
        values = ", ".join(e.attrib["name"] + " = " + e.attrib["value"]
                           for e in elements)
        result = card(elements[0], "api_enum", symbol,
                      "enum " + symbol + " { " + values + " }",
                      "constants/constant[@enum='" + name + "']", marked=elements)
        # Constants document their own values, not the inferred enum declaration.
        result["summary"] = ""
        if any(e.get("is_bitfield") == "true" for e in elements):
            result["constraints"].append("bitfield")
        yield result


def validate(card):
    strings = ("id", "product", "language", "version", "kind", "symbol",
               "signature", "summary", "license", "trust_tier", "status")
    if any(not isinstance(card.get(k), str) for k in strings):
        raise ValueError("missing or invalid string field")
    if (card["product"] != "godot" or card["kind"] not in KINDS or
            card["trust_tier"] != "official" or card["status"] != "source_checked" or
            len(card["summary"]) > 300 or not card["signature"] or
            card["id"] != "godot." + card["symbol"] + "@" + card["version"]):
        raise ValueError("invalid card: " + card["id"])
    for key in ("aliases", "constraints", "examples"):
        if not isinstance(card.get(key), list) or any(
                not isinstance(v, str) for v in card[key]):
            raise ValueError("invalid " + key)
    if not isinstance(card.get("params"), list):
        raise ValueError("invalid params")
    for param in card["params"]:
        if (set(param) != {"name", "type", "default", "doc"} or
                any(not isinstance(param[k], str) for k in ("name", "type", "doc")) or
                not isinstance(param["default"], (str, type(None)))):
            raise ValueError("invalid param")
    if not isinstance(card.get("returns"), (str, type(None))):
        raise ValueError("invalid returns")
    source = card.get("source")
    if (not isinstance(source, dict) or set(source) != {"uri", "revision", "span"}
            or any(not isinstance(v, str) or not v for v in source.values())):
        raise ValueError("invalid source")
    if not isinstance(card.get("deprecated"), bool):
        raise ValueError("invalid deprecated")


def extract(classes, version, out):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("version must be x.y.z")
    if not classes.is_dir():
        raise ValueError("classes must be a directory")
    files = sorted(classes.glob("*.xml"), key=lambda p: p.name)
    if not files:
        raise ValueError("no class XML files found")
    digest = hashlib.sha256()
    roots = []
    for path in files:
        data = path.read_bytes()
        for part in (path.name.encode("utf-8"), data):
            digest.update(len(part).to_bytes(8, "big"))
            digest.update(part)
        roots.append(ET.fromstring(data))
    input_sha256 = digest.hexdigest()
    cards = sorted((card for root in roots
                    for card in class_cards(root, version, input_sha256)),
                   key=lambda card: card["id"])
    seen = set()
    for card in cards:
        validate(card)
        if card["id"] in seen:
            raise ValueError("duplicate card id: " + card["id"])
        seen.add(card["id"])
    counts = Counter(card["kind"] for card in cards)
    manifest = {"product": "godot", "tool_version": version,
                "input_sha256": input_sha256, "generator_version": GENERATOR_VERSION,
                "input_files": len(files), "total_cards": len(cards),
                "counts": {kind: counts[kind] for kind in KINDS}}
    out.mkdir(parents=True, exist_ok=True)
    with (out / "cards.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for card in cards:
            stream.write(json.dumps(card, ensure_ascii=False, sort_keys=True) + "\n")
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classes", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        manifest = extract(args.classes, args.version, args.out)
    except (OSError, ET.ParseError, ValueError, KeyError) as exc:
        parser.exit(1, "godot_extract: " + str(exc) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
