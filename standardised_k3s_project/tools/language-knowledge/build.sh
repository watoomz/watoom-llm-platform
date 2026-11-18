#!/usr/bin/env bash
# Regenerate /data/ai/knowledge/cards.jsonl from the installed Godot and Blender toolchains (offline, deterministic).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
GODOT_VERSION="${GODOT_VERSION:-4.7.2}"; BLENDER_VERSION="${BLENDER_VERSION:-5.2.3}"
OUT="${WLK_OUT:-/data/ai/knowledge}"; WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
mkdir -p "$OUT" "$WORK/doc" "$WORK/g" "$WORK/b" "$WORK/gc" "$WORK/bc" "$WORK/gi"
(cd "$WORK/doc" && /data/ai/toolchains/godot/$GODOT_VERSION/godot --headless --doctool . >/dev/null 2>&1)
python3 "$HERE/extract/godot_extract.py" --classes "$WORK/doc/doc/classes" --version "$GODOT_VERSION" --out "$WORK/g"
python3 "$HERE/extract/godot_import_extract.py" --binary /data/ai/toolchains/godot/$GODOT_VERSION/godot --version "$GODOT_VERSION" --out "$WORK/gi"
python3 "$HERE/extract/blender_extract.py" --version "$BLENDER_VERSION" --out "$WORK/b"
python3 "$HERE/extract/cli_extract.py" --product godot --binary /data/ai/toolchains/godot/$GODOT_VERSION/godot --version "$GODOT_VERSION" --out "$WORK/gc"
python3 "$HERE/extract/cli_extract.py" --product blender --binary /data/ai/toolchains/blender/$BLENDER_VERSION/blender-$BLENDER_VERSION-linux-x64/blender --version "$BLENDER_VERSION" --out "$WORK/bc"
# Manual/vendor-doc products (extract/manual_extract.py): any product listed in manuals/registry.json gets built
# the same way, with no code change needed to add a new one. A failed verification (bad source_span) aborts the
# whole build, same as a godot/blender extraction failure would.
mkdir -p "$WORK/manual"
: > "$WORK/manual-cards.jsonl"
if [ -f "$HERE/manuals/registry.json" ]; then
  for product in $(python3 -c "import json;print('\n'.join(json.load(open('$HERE/manuals/registry.json'))['products']))"); do
    mkdir -p "$WORK/manual/$product"
    python3 "$HERE/extract/manual_extract.py" --manuals-root "$HERE/manuals" --product "$product" --out "$WORK/manual/$product"
    cat "$WORK/manual/$product/cards.jsonl" >> "$WORK/manual-cards.jsonl"
    cp "$WORK/manual/$product/manifest.json" "$OUT/manifest-manual-$product.json"
  done
fi
cat "$WORK/g/cards.jsonl" "$WORK/gc/cards.jsonl" "$WORK/gi/cards.jsonl" "$WORK/b/cards.jsonl" "$WORK/bc/cards.jsonl" "$WORK/manual-cards.jsonl" > "$WORK/cards.jsonl"
cat "$WORK/g/cards.jsonl" "$WORK/gc/cards.jsonl" "$WORK/gi/cards.jsonl" > "$WORK/cards-godot.jsonl"
install -m 0644 "$WORK/cards-godot.jsonl" "$OUT/cards-godot.jsonl.new" && mv "$OUT/cards-godot.jsonl.new" "$OUT/cards-godot.jsonl"
install -m 0644 "$WORK/cards.jsonl" "$OUT/cards.jsonl.new" && mv "$OUT/cards.jsonl.new" "$OUT/cards.jsonl"
cp "$WORK/g/manifest.json" "$OUT/manifest-godot.json"; cp "$WORK/gi/manifest.json" "$OUT/manifest-godot-import.json"; cp "$WORK/b/manifest.json" "$OUT/manifest-blender.json"
sha256sum "$OUT/cards.jsonl"
