# watoom-language-knowledge (wlk) — v1 contract

Plan: /data/ai/artifacts/WatooM_OpenCode_V2_Language_Knowledge_Plugin_Implementation_Plan.md.
Audit (WP0): fork = upstream opencode v2.2.5 + 25 commits; plugins are packages listed in `opencode.json` `plugins`
(`{package, options}`), default export `{id, setup(ctx)}`; tools via `ctx.tool.transform(editor=>editor.add(...))`
(see ansible/roles/watoom-code/files/coordinator-guard/index.js). Live app pod has no spare plugin ABI beyond that.

## Card (one JSON object per line in `cards.jsonl`)
Required keys: `id` (unique, `<product>.<symbol>@<version>`), `product` (`godot`|`blender`), `language`, `version`
(exact installed tool version, e.g. `4.7.2`), `kind` (`api_class`|`api_method`|`api_property`|`api_signal`|`api_constant`|
`api_enum`|`cli_flag`|`import_option`|`operator`|`rna_struct`|`rna_property`), `symbol` (fully-qualified, e.g. `Node.add_child`,
`bpy.ops.mesh.primitive_cube_add`), `signature` (EXACT, generated from the tool, never paraphrased),
`summary` (<= 300 chars, may be empty if the tool gives no text), `params` (list of `{name,type,default,doc}`),
`returns` (string or null), `aliases` (list; lowercase variants allowed), `constraints` (list), `examples` (list),
`source` (`{uri, revision, span}` where revision is the tool version + doc-dump sha256 and span names the XML
element / RNA path), `license`, `trust_tier` (`official`), `status` (`source_checked`), `deprecated` (bool, optional).
Cards are generated deterministically: same input -> byte-identical output (sorted, no timestamps in card bodies).

## Extractors (`extract/`)
Each extractor is a standalone Python 3 script, stdlib only, with `--out <dir>` and writes `<dir>/cards.jsonl`
plus `<dir>/manifest.json` (counts per kind, tool version, input sha256, generator version). Exits non-zero on any
card that fails the schema above. Tests live in `tests/` and use small fixtures in `tests/fixtures/` only.
Never executes project/template code; never touches the network.

## Import-option cards (`extract/godot_import_extract.py`)
`kind` is `import_option`, `language` is `import`, `symbol` is `<importer>:<option key>` (e.g. `scene:fbx/embedded_image_handling`). The engine is the source:
tiny generated sample assets are imported headless and the `[params]` of each `.import` file give the exact option names and defaults (signature is the `key=value` line;
when the default differs by file type, one `ext: key=value` per type). One card covers every file type that shares the option (`constraints` lists them). Enum value labels
come from hint strings in the engine binary; the option-to-string mapping (`HINTS`) is curated, but a label is emitted only if the exact string is present in the binary,
otherwise it is dropped and listed in the manifest (`labels_dropped`). Source uri `godot://import/<importer>`; revision = version + sha256 of the `[params]` blocks and verified hints.
Run with the installed Godot; `--imports-dir` reads existing `.import` files instead (tests). Output is byte-identical across runs.

## Vendor manuals / condensed syntax guides (`extract/manual_extract.py`) — adding a different tool
Every other extractor above introspects a running binary. This one has no binary to run, so it is the integrity gate instead of the generator: a human (or
an agent acting for the owner) authors `manuals/<product>/entries.jsonl` by hand, and the script REJECTS the whole build if any entry's `source_span` cannot
be found (after whitespace normalisation) in the exact bytes of its named `source_file` under `manuals/<product>/sources/`. That check is what still makes
`"status": "source_checked"` true here — checked against stored bytes, just not against a live tool. `trust_tier` is the signal that distinguishes this from
the other extractors' `"official"` tier: use `"vendor_doc"` for a manual the owner (or an agent) actually read verbatim and stored byte-for-byte, or
`"vendor_doc_paraphrase"` when the stored `sources/*` text is itself a restatement rather than the original bytes (say so in that file's own header comment
and in `source.json`'s `pages[].verbatim: false`) — never claim `"official"` for either. `kind`/`symbol`/`signature` are free-form (pick whatever is
honest for the content: `pin_map`, `setup_step`, `feature`, `board_setting`, or reuse an existing kind); `id` is still `<product>.<symbol>@<version>`.

To add a new tool: `mkdir -p manuals/<product>/sources`, drop the guide text in there, write `manuals/<product>/source.json`
(`product`,`version`,`language`,`license`,`trust_tier`,`pages:[{uri,file,verbatim}]`), write `entries.jsonl` (one JSON object per line: required
`symbol`,`kind`,`signature`,`summary`,`source_file`,`source_span`; optional `params`,`returns`,`aliases`,`constraints`,`examples`,`deprecated`,`meta`),
add `"<product>"` to `manuals/registry.json`'s `products` list. `build.sh` then builds it automatically alongside Godot/Blender; no code change needed.
Tests: `tests/test_manual_extract.py`.
