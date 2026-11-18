---
name: sims4-animation
description: Extract TS4 binary clips and prepare bounded body animation Actions for the verified Shadowheart MHX rig using the external worker; normally selected by sims.
---
# Rigging / Animation / Retargeting

Reuse the sims handoff and ask only for essential missing information. Confirm the source rig/action, requested pose/motion/timing and target format.

Use blender-character-rigging or blender-animation for supported authorized Blender work. Require exact bone mapping and actual motion/deformation checks. TS4 binary extraction and bounded Shadowheart body retargeting use the fixed adapters documented below. Other rigs require their own verified skeleton map.

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

## TS4 to Shadowheart body Action preparation

For the Quin subset profile and data-only profile extension, read `references/retarget-profiles.md`. Use `ts4-af-shadowheart-mhx-v2-quin` for the qualified Quin rig; report torso/head animation with no dedicated limb animation. New qualified JSON profiles can be added without a Python allowlist edit.


Any other target (Rigify/metarig, Mixamo, Unreal, Toolkit humanoids, quadrupeds) and any TS4 skeleton (adult, child, toddler, infant, werewolf, mermaid, fairy) or Blender Action source: use the generic v3 engine, `preparation.method="retarget"`; read `references/retarget-any.md`.

The fixed external 4GiB capture worker supports `pose-prepare`, `preparation.method="ts4-retarget"`. Read `references/ts4-retarget.md` for the exact manifest. This is a native `watoom_asset_capture` job in `/data/ai/projects/images`; it is not an app-shell Blender command or a new executable. Prepare a fresh capture-jobs request before one request call, then yield. Match root-owned terminal receipts. Reconcile uncertain jobs; do not replay them.

The adapter imports parent-local TS4 animation onto a reference skeleton and bakes mapped MHX body control rotations to a separate Action. Optional root displacement is scaled; in-place retains the original target placement. Source/target rest differences are accounted for. It preserves control rotation modes, constraints and drivers, rejects constraint-blocked rotations, and checks all mapped controls after reopening. Clothing fitting, finger/face tracks, prop/contact/partner alignment and game compatibility are not supplied. Unknown tracks are reported, never represented as fully retargeted. Validate with a neutral clip and compare visible motion before accepting a new package clip or profile. Originals stay unchanged.
