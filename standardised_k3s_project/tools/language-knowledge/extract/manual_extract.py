#!/usr/bin/env python3
"""Extract cards from a registered vendor manual / condensed syntax guide (generic "add a new tool" path).

Unlike blender_extract.py / godot_extract.py / cli_extract.py, this extractor has no running tool to introspect, so
it cannot regenerate cards from a live binary. Instead each card's `signature`/key facts are authored by hand into
an `entries.jsonl` file, and this script is the integrity gate: every entry must name a `source_file` under the
product's `sources/` directory and a `source_span` that is found, byte-for-byte after whitespace normalisation, in
that file. An entry whose span cannot be found fails the whole run (same "never paraphrased, always checked
against the stored bytes" rule the other extractors enforce against a live tool's output). This is what makes
"status": "source_checked" true here too: checked against the exact bytes on disk, just not against a live binary.

Adding a new tool/manual to the knowledge base:
  1. mkdir -p manuals/<product>/sources
  2. Drop the manual/guide text into manuals/<product>/sources/*.md (or .txt); if you did not read it yourself
     verbatim, say so plainly in a comment at the top of the file and in source.json ("verbatim": false) rather
     than let anyone assume it is the original bytes.
  3. Write manuals/<product>/source.json: {"product","version","language","license","trust_tier","pages":[...]}
  4. Write manuals/<product>/entries.jsonl, one JSON object per line: required keys symbol, kind, signature,
     summary, source_file, source_span; optional params, returns, aliases, constraints, examples, deprecated, meta.
  5. Add "<product>" to manuals/registry.json "products", then run:
       python3 extract/manual_extract.py --manuals-root manuals --product <product> --out <dir>
     (build.sh loops the registry automatically.)
"""

import argparse
import hashlib
import json
import pathlib
import re
import sys

GENERATOR_VERSION = "1.0.0"
REQUIRED_ENTRY_KEYS = ("symbol", "kind", "signature", "summary", "source_file", "source_span")
OPTIONAL_LIST_KEYS = ("params", "aliases", "constraints", "examples")


def normalize(text):
    return " ".join(text.split())


def load_json(path, what):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit("%s not found: %s" % (what, path))
    except (ValueError, UnicodeDecodeError) as exc:
        raise SystemExit("%s is not valid JSON/UTF-8 (%s): %s" % (what, exc, path))


def load_entries(path):
    entries = []
    if not path.is_file():
        raise SystemExit("entries file not found: %s" % path)
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError as exc:
            raise SystemExit("entries.jsonl line %d is not valid JSON (%s)" % (lineno, exc))
        entry["_line"] = lineno
        entries.append(entry)
    return entries


def verify_and_build(product_dir, source_meta, entries, version):
    pages_by_file = {p["file"]: p for p in source_meta.get("pages", [])}
    source_cache = {}
    source_hash_cache = {}
    cards = []
    failures = []
    seen_ids = set()

    for entry in entries:
        line = entry.pop("_line")
        missing = [k for k in REQUIRED_ENTRY_KEYS if not entry.get(k)]
        if missing:
            failures.append("line %d: missing required key(s) %s" % (line, ", ".join(missing)))
            continue
        source_file = entry["source_file"]
        page = pages_by_file.get(source_file)
        if page is None:
            failures.append("line %d: source_file %r is not listed in source.json pages" % (line, source_file))
            continue
        if source_file not in source_cache:
            source_path = product_dir / "sources" / source_file
            if not source_path.is_file():
                failures.append("line %d: source_file %r does not exist under sources/" % (line, source_file))
                source_cache[source_file] = None
                continue
            raw = source_path.read_bytes()
            source_cache[source_file] = normalize(raw.decode("utf-8", "replace"))
            source_hash_cache[source_file] = hashlib.sha256(raw).hexdigest()
        haystack = source_cache[source_file]
        if haystack is None:
            continue
        needle = normalize(entry["source_span"])
        if not needle or needle not in haystack:
            failures.append("line %d: source_span not found (after whitespace normalisation) in %s" % (line, source_file))
            continue

        card_id = "%s.%s@%s" % (source_meta["product"], entry["symbol"], version)
        if card_id in seen_ids:
            failures.append("line %d: duplicate card id %s" % (line, card_id))
            continue
        seen_ids.add(card_id)

        card = {
            "id": card_id,
            "product": source_meta["product"],
            "language": source_meta["language"],
            "version": version,
            "kind": entry["kind"],
            "symbol": entry["symbol"],
            "signature": entry["signature"],
            "summary": entry["summary"][:300],
            "params": entry.get("params", []),
            "returns": entry.get("returns"),
            "aliases": entry.get("aliases", []),
            "constraints": entry.get("constraints", []),
            "examples": entry.get("examples", []),
            "source": {
                "uri": page["uri"],
                "revision": "%s+sha256:%s" % (version, source_hash_cache[source_file]),
                "span": "%s#%s" % (source_file, hashlib.sha256(needle.encode()).hexdigest()[:16]),
            },
            "license": source_meta.get("license", "unknown"),
            "trust_tier": source_meta.get("trust_tier", "vendor_doc"),
            "status": "source_checked",
        }
        if "deprecated" in entry:
            card["deprecated"] = bool(entry["deprecated"])
        if "meta" in entry:
            card["meta"] = entry["meta"]
        cards.append(card)

    return cards, failures


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manuals-root", required=True, type=pathlib.Path)
    ap.add_argument("--product", required=True)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    args = ap.parse_args()

    product_dir = args.manuals_root / args.product
    source_meta = load_json(product_dir / "source.json", "source.json")
    for key in ("product", "version", "language"):
        if key not in source_meta:
            raise SystemExit("source.json is missing required key %r" % key)
    if source_meta["product"] != args.product:
        raise SystemExit("source.json product %r does not match --product %r" % (source_meta["product"], args.product))

    entries = load_entries(product_dir / "entries.jsonl")
    cards, failures = verify_and_build(product_dir, source_meta, entries, source_meta["version"])

    args.out.mkdir(parents=True, exist_ok=True)
    cards.sort(key=lambda c: c["id"])
    out_path = args.out / "cards.jsonl"
    out_path.write_text("".join(json.dumps(c, sort_keys=True) + "\n" for c in cards), encoding="utf-8")

    manifest = {
        "generator": "manual_extract.py",
        "generator_version": GENERATOR_VERSION,
        "product": args.product,
        "version": source_meta["version"],
        "trust_tier": source_meta.get("trust_tier", "vendor_doc"),
        "entries_total": len(entries),
        "cards_written": len(cards),
        "failures": len(failures),
        "entries_sha256": hashlib.sha256((product_dir / "entries.jsonl").read_bytes()).hexdigest(),
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    if failures:
        for message in failures:
            print("FAIL: %s" % message, file=sys.stderr)
        print("manual_extract.py: %d of %d entries failed verification; see above" % (len(failures), len(entries)), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
