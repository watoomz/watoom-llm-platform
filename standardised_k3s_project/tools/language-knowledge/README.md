# WatooM language knowledge

RAM-resident, version-pinned API/CLI reference for native agents. Maintained source is `package/`; extraction/build/admin/procedure tooling and tests live beside it. The role task `language_knowledge.yml` selects an immutable plugin package independently of the application image.

## Current interfaces

`wlk_search`, `wlk_symbol`, `wlk_command`, `wlk_get`, `wlk_status` and `wlk_feedback` are registered by the current native plugin. Feedback/procedure ingestion retains its own validation boundary; a lookup is inert reference data, not permission to execute a suggested command.

Lexical lookup remains available when optional vector files or the configured embedding endpoint are unavailable. `wlk_status` reports loading/vector errors. Preserve configured cards, vector/procedure data and extraction/version metadata in the private recovery bundle; source availability is not a backup of generated knowledge.

The trigger module recognises selected tool-error patterns and uncertainty near API/CLI-looking terms, and doubts about importer behaviour ("does the FBX importer overwrite ...", or an option key such as `fbx/embedded_image_handling` near a doubt), which it answers from the import-option cards (`kind=import_option`: defaults and value labels read from the engine). The behaviour lookup stays silent unless a card clearly matches the file type and wording. Hooks insert bounded reference context, skip the knowledge tools themselves and avoid turning arbitrary output into execution authority. See `package/triggers.js` and its focused tests for exact rules and limits.

## Deployment and rollback

Use `watoom_code_language_knowledge_enabled` and the owning role/production vars. The current configuration loads the full Godot and Blender card set (`cards.jsonl`; `cards-godot.jsonl` is the Godot-only subset, about 650 MiB less resident memory) and selects a hash-versioned plugin; don't infer that every extractor/data source or optional vector feature is active. Rollback disables the feature and reapplies through the idle/admission-controlled owner. Do not interrupt an active session to reload code.

## Validation

From the project root:

```bash
python3 -m unittest discover -s tools/language-knowledge/tests
node --test tools/language-knowledge/tests/*.mjs
```

These are source tests; actual tool registration and the configured card/vector data must be verified separately against native status. Historical benchmark numbers and the original v1 feature limitations are not current runtime acceptance.
