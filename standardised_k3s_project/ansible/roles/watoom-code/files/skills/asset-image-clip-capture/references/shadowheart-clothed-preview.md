# Shadowheart dressed preview recipe v1

Use for a neutral, fully clothed preview of the existing Shadowheart asset in her camp shirt, pants and shoes. Reuses the accepted 512x768,16-sample still capture. It is an optional asset-specific shortcut; other assets and views use the generic capture procedure.

Recipe ID: `shadowheart-clothed-preview-v1`.
Canonical recipe folder: `/data/ai/archive/projects-20261029/pipelines/sims4-mod-studio-staging-20261024T082059Z/implementation/recipes/shadowheart-clothed-preview-v1`.

## Verified preparation

`recipe.json` pins the original and prepared .blend identities, compatible Blender binary, worker budget, actual successful receipt and visual acceptance. `dependencies.json` pins the preserved 1k texture cache and original-to-derived rebinding record. `request-template.json` is the exact successful declarative request, not executable code.

The full camp outfit requires the shirt, pants and shoes in `visibility.show`, plus the existing MASK modifier named `Shadowheart BG Camp Outfit - Pants` on `Shadowheart Body`. Its explicit enable removes the large body intersections through the pants. Preserve the named mask selection. The worker applies changes in memory; originals and historical prepared files remain unchanged.

Camera: front, full figure, margin1.15. Neutral authored A-pose; no action or pose edits. Inherited studio lighting procedure, CPU Cycles,2threads,16samples,512x768 PNG. Worker caps subdivision1 and texture limit1k. The accepted preview is not final-quality clothing fitting or high-resolution qualification.

## Reuse for a new dressed capture

1. Read `recipe.json`; verify the selected project, source/derivative and Blender SHA-256, and all cached dependency hashes. If any differ, stop recipe reuse and use the generic inventory/preparation procedure. Do not silently select another derivative.
2. For the authorized dressed request, choose a fresh stable job ID. Copy `request-template.json` to `/data/ai/projects/images/.opencode/capture-jobs/<new-job>/request.json`. Keep the source and outfit/mask selections for exact reproduction. Do not reuse either historical test job ID or output directory.
3. As workflow/builder in that selected project, invoke native `watoom_asset_capture` with exactly `{action:"request",job:"<new-job>"}`. No direct Blender shell launch. The existing dispatcher verifies persisted native proof and runs a separate systemd worker with actual4GiB memory.max, zero swap,2CPU and900second timeout. It waits for2GiB extra headroom and leaves inference running.
4. Yield after QUEUED. The dispatcher notifies the existing coordinator. Read the root-owned status/receipt; status requests use `{action:"status",job:"<same-job>"}`. Do not resubmit while running or replay uncertain requests after restart. Changed requests require a fresh reviewed job identity.
5. Require COMPLETED,exit0,cgroup_limit_verified=true,cgroup_memory_max4294967296,source_unchanged=true and the fresh image/hash. Output: `/data/ai/projects/images/.opencode/captures/<new-job>/capture.png`. Inspect the real pixels for clothing coverage, textures, framing and clipping. Prior visual acceptance does not accept a new render.

The host runner uses journal transport; --pipe previously failed because SELinux rejected init_t writing an unlabeled report FD. Keep journal transport, --python-exit-code1 and the subdivision cap. Do not change SELinux policy, worker memory or app resources to reuse this recipe.

No render is started by saving or reading the recipe. New pose, camera, resolution, detail, animation or export requests require their own validation; do not describe them as the already validated still.
