---
name: blender-animation
description: Animation in Blender - version-specific legacy F-Curves or layered Action/channelbag
  API, Python keyframing, F-curves, game loops, NLA clips, pose library, mocap/BVH
  retargeting via constraints, baking control rigs to export skeletons, root motion,
  per-clip export. Use for any keyframe, action, NLA, mocap, or animation-export task.
license: MIT
---

# WatooM production: blender-animation

Use the existing watoom-workflow -> watoom-builder serial hierarchy. Load this skill on demand. Production uses pinned Blender 5.2.1 after CPU compatibility qualification. Inspect actual APIs; the retained 4.2 runtime is rollback-only.

Use installed scripts through a verified external worker with pinned Blender 5.2.1. In a game project that worker is the native `watoom_game_worker` operation `blender`: write `.opencode/blender-jobs/<job>/request.json` with `script` `skill:<this-skill>/scripts/<file>.py`, optional `blend` and `args` (`{out}` is the writable output folder), then request it; the receipt gives the script's @@JSON@@ result, traceback and output files (see watoom-blender-asset-builder). The server profile uses CPU, 4GiB and two threads; the RIG profile uses an 8GiB Windows Job Object, four threads and OptiX (or explicit CPU). Component stages have a maximum 300-second deadline. The 2GiB application shell must never execute non-dry-run Blender stages. GPU-context checks run on a qualified RIG context and may skip only on the CPU profile; a skip is not GPU qualification. Preserve acquired sources and versioned outputs under /data/ai/projects/llm/pipelines/blender-asset-builder/<revision>. Do not install inherited addons/MCP/software or use the inference GPU. Changed scripts, inputs or execution profiles invalidate resume validation; inspect retained failures and use at most one explicit --retry-failed. Follow references/worker-execution.md.

Scripts: bake_action.py, creature_gait.py.

Unanimated creatures: `creature_gait.py -- --armature N_Rig [--walk-speed 2.0] --export-dir DIR --mesh N_Body --prefix N` makes looping in-place Idle/Walk/Run/Roar/Attack for a creature_rig.py skeleton and writes one FBX per clip (unreal_skeletal preset, textures embedded) for tools/rig-ue-mcp/rig_import_fbx_character.py. Leg angles are world side-plane targets minus rest angles, so a statue's staggered rest pose still walks symmetrically; the walk cycle length follows --walk-speed so the feet do not skate at the engine's move speed. Inspect script help and current APIs before choosing parameters. CLI scripts print @@JSON@@; inspect ok/pass as well as exit status. Save and hash source checkpoints after each stage. Use /config/skills as S when sibling paths are needed.

Read references/upstream-SKILL.md and only relevant reference files when more detail is needed. The pinned original and MIT provenance are preserved; shared provenance is ../blender-source.json. Compatibility tests cover supported CPU paths, not every upstream feature. Blender 5.2-only cloth/mesh-bevel nodes and GPU-context previews are unsupported here. Use Cycles CPU. Export compression fallbacks warn; approximate Nishita sky is not calibrated photometry; white-point temperature grading is unsupported.

For full tasks load watoom-blender-asset-builder. Actual Godot/Unreal validation uses the existing local-toolkit specialist 3d.inspect path; FBX existence is not engine validation. Visual/reference/deformation review remains a separate actual-image assessment. Never infer visual PASS from technical QA.

## Additional animation, render and scripting guidance

For version-sensitive Action APIs, render setup and scripting failure handling, read [reviewed TerminalSkills guidance](../blender-core/references/terminalskills-review.md). Existing-asset captures use asset-image-clip-capture and its native worker; builder scripts keep their separately qualified runtime and limits.

## Rig-aware pose preparation

For detailed humanoid inspection, calibrated quaternion channels or FK endpoint goals, use [human-pose-agent](../human-pose-agent/SKILL.md). Submit fixed `pose-inspect` or `pose-prepare` manifests through the SAME native `watoom_asset_capture` request/status tool and existing 4GiB worker. `pose-inspect` emits human-pose `inspection.json`; normal `inspect` emits capture `inventory.json`. `pose-prepare` accepts only declarative auto/recipe plans, never script paths or commands, and returns a new `.blend` plus validation and hashes. Review pose/anatomy/clothing before accepting it, then use its exact path/hash for a separate still/clip request. WARN and PREPARED_REVIEW_PENDING are candidates, not visual PASS. Do not invoke the app-shell builder runner for preparation; arbitrary builder stages still have no verified dispatcher. Constrained rigs still require a qualified adapter.

For Shadowheart MHX, use the fingerprinted `human-pose-agent` rig-adapter route when `adapter-inventory.json` matches. It supports the observed IK/FK switches, real hand/foot targets, poles and hip control. Read its contract before authoring a plan; deep hip bends can fail garment review despite exact endpoint checks.

For Sims 4 binary clips, load `sims4-animation` and its `references/ts4-retarget.md`. The fixed native pose-prepare method `ts4-retarget` supplies the verified adult-female reference-to-Shadowheart body Action path on the external4GiB worker. It does not supply finger/face/contact or garment correction. Do not run an invented importer in the app shell.
