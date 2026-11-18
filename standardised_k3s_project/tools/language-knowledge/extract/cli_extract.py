#!/usr/bin/env python3
"""Extract CLI cards from installed Godot/Blender --help, or saved help bytes.

Signatures are the help's declaration columns (including wrapped arguments),
with ANSI presentation removed and whitespace collapsed, never reconstructed.
One card represents a declaration and its aliases. Blender's separate animation
player declarations retain their short names and Playback Arguments context.
The input hash covers the exact stdout/help-file bytes, independent of its path.
"""

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess


GENERATOR_VERSION = "1.0.0"
HELP_TIMEOUT = 180
_spec = importlib.util.spec_from_file_location(
    "_cli_godot_schema", Path(__file__).with_name("godot_extract.py"))
_schema = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_schema)
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
FLAG = r"(?:--[A-Za-z0-9][\w-]*|-[A-Za-z0-9][\w-]*|--|\+\+|/\?)"
DECLARATION = re.compile(r"^(" + FLAG + r"(?:\s*(?:,|\bor\b)\s*" + FLAG + r")*)")
CONDITION = re.compile(
    r"\b(?:only|must|requires?|ignored|implies|following|depends|supported|"
    r"should|unless|when|if|used with|use with|in conjunction|consumes all|"
    r"do not|order)\b", re.I)


def normalize(text):
    return " ".join(text.split())


def declarations(text, product):
    """Yield (verbatim declaration, aliases, paragraphs, contextual conditions)."""
    lines = ANSI.sub("", text).splitlines()
    legends = {}
    if product == "godot":
        for line in lines:
            match = re.match(r"^\s+([RDXE])\s{2,}(.+)$", line)
            if match:
                legends[match[1]] = normalize(match[2])
    current = None
    playback = False
    section_conditions = []
    for line in lines:
        stripped = line.strip()
        if stripped and not line[0].isspace() and not DECLARATION.match(stripped):
            if current:
                yield current
                current = None
            playback = False
            section_conditions = []
            continue
        if product == "blender" and stripped == "Playback Arguments:":
            playback = True
            continue
        # Blender indents documentation and examples, but its playback flags
        # have exactly one tab and their documentation two tabs.
        is_flag = bool(DECLARATION.match(stripped)) and (
            product == "godot" and line.startswith("  ") and not line.startswith("    ")
            or product == "blender" and (
                not line[0].isspace() or playback and line.startswith("\t")
                and not line.startswith("\t\t")))
        if is_flag:
            if current:
                yield current
            signature, description, marker = stripped, "", None
            if product == "godot":
                columns = re.split(r"\s{2,}", stripped, maxsplit=1)
                signature = columns[0]
                if len(columns) == 2:
                    description = columns[1]
                    marked = re.match(r"^([RDXE])(?:\s+|$)(.*)", description)
                    if marked:
                        marker, description = marked.groups()
            names = re.findall(FLAG, DECLARATION.match(signature)[1])
            context = list(section_conditions)
            if playback:
                context.append("Playback Arguments:")
            if marker in legends:
                context.append(legends[marker])
            current = [signature, names, [description] if description else [], context]
        elif current:
            if product == "godot":
                # Conversion options put optional arguments on a second row.
                wrapped = re.match(r"^\s+(\[.+?\])\s{2,}([RDXE])\s+(.+)$", line)
                if wrapped:
                    current[0] += " " + wrapped[1]
                    current[2].append(wrapped[3])
                    if wrapped[2] in legends:
                        current[3].append(legends[wrapped[2]])
                    continue
            if stripped:
                if current[2] and current[2][-1]:
                    current[2][-1] += " " + stripped
                else:
                    current[2].append(stripped)
            elif current[2] and current[2][-1]:
                current[2].append("")
        elif stripped and CONDITION.search(stripped):
            # Cycles' placement requirement precedes both of its flags.
            section_conditions.append(normalize(stripped))
    if current:
        yield current


def validate(card):
    """Reuse the existing strict field validator via an identity-only adapter."""
    if (card.get("product") not in {"godot", "blender"}
            or card.get("kind") != "cli_flag" or card.get("language") != "cli"
            or not re.fullmatch(r"\d+\.\d+\.\d+", card.get("version", ""))
            or not card.get("symbol", "").startswith(card["product"] + " ")
            or card.get("id") != card["product"] + "." + card["symbol"] + "@" + card["version"]):
        raise ValueError("invalid CLI card identity")
    adapted = dict(card, product="godot", kind="api_method",
                   id="godot." + card["symbol"] + "@" + card["version"])
    _schema.validate(adapted)


def convert(raw, product, version):
    if product not in {"godot", "blender"}:
        raise ValueError("product must be godot or blender")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("version must be x.y.z")
    digest = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8")
    global_conditions = []
    if product == "blender":
        # These sections state rules for all Blender arguments. Keep the prose
        # before examples; command examples themselves are not declarations.
        for match in re.finditer(
                r"^Argument (?:Parsing|Order):\s*\n((?:[ \t].*\n|\n)*)",
                ANSI.sub("", text) + "\n", re.M):
            prose = []
            for line in match[1].splitlines():
                if not line.strip() or line.lstrip().startswith("#"):
                    break
                prose.append(line)
            if prose:
                global_conditions.append(normalize(" ".join(prose)))
    cards = []
    for signature, names, paragraphs, context in declarations(text, product):
        flag = next((name for name in names if name.startswith("--") and name != "--"), names[0])
        symbol = product + " " + flag
        paragraphs = [normalize(p) for p in paragraphs if p]
        constraints = list(dict.fromkeys(global_conditions + context + [
            p for p in paragraphs if CONDITION.search(p)]))
        card = {
            "id": product + "." + symbol + "@" + version,
            "product": product, "language": "cli", "version": version,
            "kind": "cli_flag", "symbol": symbol,
            "signature": normalize(signature),
            "summary": (paragraphs[0] if paragraphs else "")[:300],
            "params": [], "returns": None, "aliases": sorted(set(names)),
            "constraints": constraints, "examples": [],
            "source": {"uri": product + "://--help",
                       "revision": version + "+sha256:" + digest,
                       "span": "--help " + flag},
            "license": "MIT" if product == "godot" else "GPL-2.0-or-later",
            "trust_tier": "official", "status": "source_checked",
            "deprecated": False,
        }
        validate(card)
        cards.append(card)
    if not cards:
        raise ValueError("no CLI flags found in help text")
    cards.sort(key=lambda c: c["id"])
    if len({c["id"] for c in cards}) != len(cards):
        raise ValueError("duplicate card id in help text")
    manifest = {"product": product, "tool_version": version,
                "input_sha256": digest, "generator_version": GENERATOR_VERSION,
                "input_files": 1, "total_cards": len(cards),
                "counts": dict(Counter(c["kind"] for c in cards))}
    return cards, manifest


def extract(product, binary, version, out, help_file=None):
    # Validate arguments before running anything.
    if product not in {"godot", "blender"} or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("expected product godot|blender and version x.y.z")
    if help_file is not None:
        raw = Path(help_file).read_bytes()
    else:
        if not binary:
            raise ValueError("--binary is required unless --help-file is supplied")
        command = [str(binary)] + (["--headless"] if product == "godot" else []) + ["--help"]
        raw = subprocess.run(command, check=True, timeout=HELP_TIMEOUT,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
    cards, manifest = convert(raw, product, version)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "cards.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for card in cards:
            stream.write(json.dumps(card, sort_keys=True, ensure_ascii=False) + "\n")
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product", required=True, choices=("godot", "blender"))
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--help-file", type=Path)
    args = parser.parse_args(argv)
    try:
        manifest = extract(args.product, args.binary, args.version, args.out, args.help_file)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(1, "cli_extract: " + str(exc) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
