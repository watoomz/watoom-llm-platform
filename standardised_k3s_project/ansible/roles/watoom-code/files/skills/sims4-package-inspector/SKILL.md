---
name: sims4-package-inspector
description: Route a specified Sims 4 package inspector / extractor job to verified available skills and workers; normally selected by sims.
---
# Package Inspector / Extractor

Reuse the sims handoff and ask only for essential missing information. Confirm the selected package and inventory versus selected resource extraction.

No game-specific parser capability is implied. Discover package inventory/extraction support; opaque unsupported resources stay raw. Do not use asset.inspect as an invented package decoder.

Before execution, read the parent sims references/recipe-selection.md when reusing an existing asset or receipt. Verify current skill assignment, operation schema, source compatibility, worker readiness, output scope and resource limits. User intent/authorization, available agent tools, skill selection and worker capability are distinct. Coordinator owns progress; one execution-authorized builder handles a bounded edit, investigators clarify gaps read-only and reviewers inspect actual results read-only. Skill delegation does not create extra agents by itself.

Preserve originals and accepted checkpoints; use new versioned outputs. Reconcile uncertain native jobs instead of replaying. Report BLOCKED, unsupported and NOT_RUN precisely. A staged adapter or an authored PASS file is not a native receipt. Do not deploy, alter running services, bypass guards or launch heavy engines in the app shell.

## Installed TS4 binary tools

Use Python 3 (stdlib only), not pip discovery, an invented executable, or the old staging venv:

```sh
python3 /config/skills/sims4-animation/scripts/ts4_animation.py inspect --source /data/ai/assets/animations/SELECTED.package
python3 /config/skills/sims4-animation/scripts/ts4_animation.py extract --source /data/ai/assets/animations/SELECTED.package --output /data/ai/projects/PROJECT/FRESH_OUTPUT --decode-clips
python3 /config/skills/sims4-animation/scripts/ts4_animation.py decode --source INPUT.resource --output FRESH.clip.json
python3 /config/skills/sims4-animation/scripts/ts4_animation.py encode --source ORIGINAL.resource --document EDITED.clip.json --output FRESH.resource
```

Replace placeholders with the user-selected input and an existing authorized project parent. Output directories/files must be fresh; preserve incomplete outputs and inspect errors before a new attempt. No Blender, GPU or capture dispatcher is needed for binary extraction. Process one package serially; do not load all JSON clips together. Inventory includes every resource; `.stored` preserves compressed bytes, `.resource` is decoded container content, `.clip.json` is numeric animation tracks. Inspect `result.json`: exit 2/PARTIAL means some resources could not be decoded, not success. These are CLI results, not native capture receipts.

Verified family: DBPF 2.0/2.1, uncompressed/0x5A42 zlib; CLIP type 6B20C4F3, clip-header type BC4A5044. Wrapper v14 / body `_pilC3S_` v2; encoding 18 translation and 20 XYZW quaternion. Zero-track clips are valid preserved resources. Unknown compression stays raw; unknown encodings fail explicitly. Limits: 64 MiB per binary resource, 4096 tracks, 250000 frames per clip. Large packages may require disk space for raw, decompressed and JSON copies; inspect inventory first.

Encoding edits existing frame values only; timing, channels and opaque wrapper/events remain preserved. Unchanged documents round-trip exactly. No automatic rig/bone-name mapping, Blender Action conversion, retargeting or in-game compatibility is claimed. Use a verified separate adapter for those operations; never label numeric extraction as a playable Blender animation. Preserve original packages.
