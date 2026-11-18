---
name: blender-game-optimization
description: Optimize Blender assets for real-time engines - triangle/material/texture/bone
  budgets per platform (mobile, Roblox, web, VR, console, PC), LOD chains, decimation
  modes, mesh cleanup, draw-call reduction (material merging, atlases, trim sheets),
  instancing, vertex-split costs, collision proxies, texture memory. Use when an asset
  is too heavy, before export, or when targeting a platform budget.
license: MIT
---

# WatooM production: blender-game-optimization

Use the existing watoom-workflow -> watoom-builder serial hierarchy. Load this skill on demand. Production uses pinned Blender 5.2.1 after CPU compatibility qualification. Inspect actual APIs; the retained 4.2 runtime is rollback-only.

Use installed scripts through a verified external worker with pinned Blender 5.2.1. In a game project that worker is the native `watoom_game_worker` operation `blender`: write `.opencode/blender-jobs/<job>/request.json` with `script` `skill:<this-skill>/scripts/<file>.py`, optional `blend` and `args` (`{out}` is the writable output folder), then request it; the receipt gives the script's @@JSON@@ result, traceback and output files (see watoom-blender-asset-builder). The server profile uses CPU, 4GiB and two threads; the RIG profile uses an 8GiB Windows Job Object, four threads and OptiX (or explicit CPU). Component stages have a maximum 300-second deadline. The 2GiB application shell must never execute non-dry-run Blender stages. GPU-context checks run on a qualified RIG context and may skip only on the CPU profile; a skip is not GPU qualification. Preserve acquired sources and versioned outputs under /data/ai/projects/llm/pipelines/blender-asset-builder/<revision>. Do not install inherited addons/MCP/software or use the inference GPU. Changed scripts, inputs or execution profiles invalidate resume validation; inspect retained failures and use at most one explicit --retry-failed. Follow references/worker-execution.md.

Scripts: make_lods.py, mesh_stats.py, collision_mesh.py (WatooM-local addition, not from upstream -- generates convex hull or per-island compound collision proxies, named/tagged for each engine's own auto-detection: UCX_ prefix for Unreal's FBX importer, -convcolonly/-colonly suffix for Godot's scene importer). Inspect script help and current APIs before choosing parameters. CLI scripts print @@JSON@@; inspect ok/pass as well as exit status. Save and hash source checkpoints after each stage. Use /config/skills as S when sibling paths are needed.

Read references/upstream-SKILL.md and only relevant reference files when more detail is needed. The pinned original and MIT provenance are preserved; shared provenance is ../blender-source.json. Compatibility tests cover supported CPU paths, not every upstream feature. Blender 5.2-only cloth/mesh-bevel nodes and GPU-context previews are unsupported here. Use Cycles CPU. Export compression fallbacks warn; approximate Nishita sky is not calibrated photometry; white-point temperature grading is unsupported.

For full tasks load watoom-blender-asset-builder. Actual Godot/Unreal validation uses the existing local-toolkit specialist 3d.inspect path; FBX existence is not engine validation. Visual/reference/deformation review remains a separate actual-image assessment. Never infer visual PASS from technical QA.
