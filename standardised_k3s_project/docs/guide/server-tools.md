---
title: Tool and validation reference
nav: Tools
summary: Source-backed purpose and interfaces for each tracked component; inspect gates and configuration before running.
---

This catalogue is generated from tracked source and untracked code candidates by `scripts/render-server-catalogue.py`. It does not run programs or certify their deployment. Source links use the configured WatooM source repository; the separate LLM repository retains the same `standardised_k3s_project/` paths. Descriptions name their evidence basis; a filename summary is not a verified operational contract.

Read [Operations](operations.md), [installation and configuration](llm-project.md), and [the software design](software-design.md) before executing deployment or recovery helpers. Run no bulk scripts from this list.

## tools/agentmemory/prune_checkpoints.js

Source component: prune checkpoints. Inspect the source before use.

Source: [`tools/agentmemory/prune_checkpoints.js`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/agentmemory/prune_checkpoints.js). Description basis: filename summary.

## tools/bazzite-render-worker/install-blender.py

Source component: install blender. Inspect the source before use.

Source: [`tools/bazzite-render-worker/install-blender.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/bazzite-render-worker/install-blender.py). Description basis: filename summary.

## tools/bazzite-render-worker/qualify-godot-gpu.py

Source component: qualify godot gpu. Inspect the source before use.

Source: [`tools/bazzite-render-worker/qualify-godot-gpu.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/bazzite-render-worker/qualify-godot-gpu.py). Description basis: filename summary.

## tools/bazzite-render-worker/qualify-resources.py

Source component: qualify resources. Inspect the source before use.

Source: [`tools/bazzite-render-worker/qualify-resources.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/bazzite-render-worker/qualify-resources.py). Description basis: filename summary.

## tools/bazzite-render-worker/remote.py

Existing server-held credentials; pinned SSH host key; no credential arguments/logs.

Source: [`tools/bazzite-render-worker/remote.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/bazzite-render-worker/remote.py). Description basis: module docstring.

## tools/bazzite-render-worker/result_delivery.py

Idempotent receipt collection. Network retries never launch or replay a render.

Source: [`tools/bazzite-render-worker/result_delivery.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/bazzite-render-worker/result_delivery.py). Description basis: module docstring.

## tools/bazzite-render-worker/test_result_delivery.py

Test fixture/check: test result delivery. Inspect the source before use.

Source: [`tools/bazzite-render-worker/test_result_delivery.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/bazzite-render-worker/test_result_delivery.py). Description basis: filename summary.

## tools/blender-asset-builder/asset-build.py

Blender 4.2 request adapter. Writes only a fresh version directory.

Source: [`tools/blender-asset-builder/asset-build.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/blender-asset-builder/asset-build.py). Description basis: module docstring.

## tools/blender-asset-builder/audit-host.py

Read-only WatooM Blender readiness audit. Python stdlib, no installs/fetches/mutations of host configuration.

Source: [`tools/blender-asset-builder/audit-host.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/blender-asset-builder/audit-host.py). Description basis: module docstring.

## tools/blender-asset-builder/audit-runtime.py

Read-only bounded host/container audit. Writes redacted evidence only.

Source: [`tools/blender-asset-builder/audit-runtime.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/blender-asset-builder/audit-runtime.py). Description basis: module docstring.

## tools/blender-asset-builder/audit-watoom-blender.py

Source component: audit watoom blender. Inspect the source before use.

Source: [`tools/blender-asset-builder/audit-watoom-blender.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/blender-asset-builder/audit-watoom-blender.py). Description basis: filename summary.

## tools/blender-asset-builder/contact.py

Source component: contact. Inspect the source before use.

Source: [`tools/blender-asset-builder/contact.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/blender-asset-builder/contact.py). Description basis: filename summary.

## tools/blender-asset-builder/engine-playback.gd

Source component: engine playback. Inspect the source before use.

Source: [`tools/blender-asset-builder/engine-playback.gd`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/blender-asset-builder/engine-playback.gd). Description basis: filename summary.

## tools/blender-asset-builder/fix-watoom-blender.py

Unattended, reversible STAGING installer. Never changes deployments or active jobs.

Source: [`tools/blender-asset-builder/fix-watoom-blender.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/blender-asset-builder/fix-watoom-blender.py). Description basis: module docstring.

Declared CLI options: `--action`, `--audit-report`, `--dry-run`, `--i-approve`, `--snapshot`.

## tools/blender-asset-builder/import.gd

Source component: import. Inspect the source before use.

Source: [`tools/blender-asset-builder/import.gd`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/blender-asset-builder/import.gd). Description basis: filename summary.

## tools/blender-asset-builder/magpie.py

Source component: magpie. Inspect the source before use.

Source: [`tools/blender-asset-builder/magpie.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/blender-asset-builder/magpie.py). Description basis: filename summary.

## tools/blender-asset-builder/memory.py

Existing AgentMemory HTTP contract inspected from installed v0.9.29 source.

Source: [`tools/blender-asset-builder/memory.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/blender-asset-builder/memory.py). Description basis: module docstring.

## tools/blender-asset-builder/pipeline.py

Production request entry point.

Source: [`tools/blender-asset-builder/pipeline.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/blender-asset-builder/pipeline.py). Description basis: module docstring.

## tools/blender-asset-builder/port-el4cteo-42.py

Source component: port el4cteo 42. Inspect the source before use.

Source: [`tools/blender-asset-builder/port-el4cteo-42.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/blender-asset-builder/port-el4cteo-42.py). Description basis: filename summary.

## tools/blender-asset-builder/preview-runtime.py

Source component: preview runtime. Inspect the source before use.

Source: [`tools/blender-asset-builder/preview-runtime.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/blender-asset-builder/preview-runtime.py). Description basis: filename summary.

## tools/blender-asset-builder/request_pipeline.py

Request-driven production checkpoints. Native tools perform engine validation separately.

Source: [`tools/blender-asset-builder/request_pipeline.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/blender-asset-builder/request_pipeline.py). Description basis: module docstring.

Declared CLI options: `--dry-run`, `--engine-job`, `--request`, `--resume`, `--retry-failed`.

## tools/blender-asset-builder/run-watoom-blender.py

Production entry information, native request planning, and exact scoped rollback.

Source: [`tools/blender-asset-builder/run-watoom-blender.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/blender-asset-builder/run-watoom-blender.py). Description basis: module docstring.

Declared CLI options: `--dry-run`, `--engine-job`, `--i-approve`, `--request`, `--resume`, `--retry-failed`, `--rollback-production`, `--root`, `--vendor`.

## tools/blender-asset-builder/test-rollback.py

Test fixture/check: test rollback. Inspect the source before use.

Source: [`tools/blender-asset-builder/test-rollback.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/blender-asset-builder/test-rollback.py). Description basis: filename summary.

## tools/blender-asset-builder/test_request_pipeline.py

Test fixture/check: test request pipeline. Inspect the source before use.

Source: [`tools/blender-asset-builder/test_request_pipeline.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/blender-asset-builder/test_request_pipeline.py). Description basis: filename summary.

## tools/blender-asset-builder/unreal-import.py

Run with the discovered UE PythonScript commandlet, in an isolated project.

Source: [`tools/blender-asset-builder/unreal-import.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/blender-asset-builder/unreal-import.py). Description basis: module docstring.

## tools/blender-asset-builder/validate.py

Source component: validate. Inspect the source before use.

Source: [`tools/blender-asset-builder/validate.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/blender-asset-builder/validate.py). Description basis: filename summary.

## tools/blender-asset-builder/vendor-upstreams.py

Reproducibly snapshot upstream public skills. Network fetch only with --i-approve.

Source: [`tools/blender-asset-builder/vendor-upstreams.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/blender-asset-builder/vendor-upstreams.py). Description basis: module docstring.

Declared CLI options: `--dry-run`, `--i-approve`.

## tools/break-glass/break_glass.py

Break-glass recovery for the LLM / inference stack.

Source: [`tools/break-glass/break_glass.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/break-glass/break_glass.py). Description basis: module docstring.

Declared CLI options: `--i-approve`, `--mode`.

## tools/break-glass/test_break_glass.py

Test fixture/check: test break glass. Inspect the source before use.

Source: [`tools/break-glass/test_break_glass.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/break-glass/test_break_glass.py). Description basis: filename summary.

## tools/change-requests/change_request.py

Audited, human-approved host change requests for models.

Source: [`tools/change-requests/change_request.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/change-requests/change_request.py). Description basis: module docstring.

Declared CLI options: `--no-push`, `--project`, `--reason`.

## tools/change-requests/test_change_request.py

Test fixture/check: test change request. Inspect the source before use.

Source: [`tools/change-requests/test_change_request.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/change-requests/test_change_request.py). Description basis: filename summary.

## tools/creation-studio/creation_studio_service.py

Creation Studio: a standalone web page for image and 3D-mesh generation.

Source: [`tools/creation-studio/creation_studio_service.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/creation-studio/creation_studio_service.py). Description basis: module docstring.

Declared CLI options: `--glb-model`, `--glb-output-dir`, `--glb-router-base`, `--host`, `--mesh-bridge-socket`, `--mesh-observability-path`, `--model-manager-base`, `--model-manager-ca-file`, `--model-manager-origin`, `--model-manager-password-file`, `--moss-base`, `--port`.

## tools/creation-studio/tests/fakes.py

Offline fake HTTP backends standing in for Model Manager and MOSS Image Studio.

Source: [`tools/creation-studio/tests/fakes.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/creation-studio/tests/fakes.py). Description basis: module docstring.

## tools/creation-studio/tests/test_service.py

Test fixture/check: test service. Inspect the source before use.

Source: [`tools/creation-studio/tests/test_service.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/creation-studio/tests/test_service.py). Description basis: filename summary.

## tools/dispatcharr/test_ts_dedupe.py

Test fixture/check: test ts dedupe. Inspect the source before use.

Source: [`tools/dispatcharr/test_ts_dedupe.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/dispatcharr/test_ts_dedupe.py). Description basis: filename summary.

## tools/dispatcharr/ts_dedupe.py

Seamless live MPEG-TS relay for providers that cap a connection \(for example every 120 s\) and restart each new connection about 25 s earlier on the live timeline.

Source: [`tools/dispatcharr/ts_dedupe.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/dispatcharr/ts_dedupe.py). Description basis: module docstring.

## tools/dispatcharr/vlc/refresh-playlist.sh

Source component: refresh playlist. Inspect the source before use.

Source: [`tools/dispatcharr/vlc/refresh-playlist.sh`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/dispatcharr/vlc/refresh-playlist.sh). Description basis: filename summary.

## tools/fab/accept-bloodfx.py

Single bounded CPU-only BloodFX acceptance; waits for actual spare RAM.

Source: [`tools/fab/accept-bloodfx.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/accept-bloodfx.py). Description basis: module docstring.

Declared CLI options: `--content`, `--engine`, `--godot`, `--project`, `--wait-seconds`.

## tools/fab/accept-hyper-combat.py

Bounded isolated Hyper project Blueprint acceptance; no source pack writes or GPU.

Source: [`tools/fab/accept-hyper-combat.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/accept-hyper-combat.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/fab/accept-owned.py

Serial receipt-backed CPU compatibility probes beside the single existing FAB queue.

Source: [`tools/fab/accept-owned.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/accept-owned.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/fab/animation_catalog.py

Owned animation catalogue \(SQLite\) built from the Fab library, grouped by what the animations are for.

Source: [`tools/fab/animation_catalog.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/animation_catalog.py). Description basis: module docstring.

Declared CLI options: `--db`, `--listings`, `--owner-list`, `--raw`.

## tools/fab/approval_worker.py

Poll only project Fab requests; trust native completed question answers, never agent prose.

Source: [`tools/fab/approval_worker.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/approval_worker.py). Description basis: module docstring.

## tools/fab/bloodfx-bake.py

Bake bounded native RGBA cache frames into a namespaced Godot sprite library.

Source: [`tools/fab/bloodfx-bake.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/bloodfx-bake.py). Description basis: module docstring.

Declared CLI options: `--destination`, `--source`.

## tools/fab/bloodfx-godot.py

Actual CPU-only Godot Sprite3D playback/capture using a verified installed binary.

Source: [`tools/fab/bloodfx-godot.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/bloodfx-godot.py). Description basis: module docstring.

Declared CLI options: `--godot`, `--project`.

## tools/fab/bloodfx-inspect.py

Source component: bloodfx inspect. Inspect the source before use.

Source: [`tools/fab/bloodfx-inspect.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/bloodfx-inspect.py). Description basis: filename summary.

## tools/fab/bloodfx-playback.gd

Source component: bloodfx playback. Inspect the source before use.

Source: [`tools/fab/bloodfx-playback.gd`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/bloodfx-playback.gd). Description basis: filename summary.

## tools/fab/bloodfx-render.py

Render source GeometryCache samples to RGBA frames; no static-GLTF animation claim.

Source: [`tools/fab/bloodfx-render.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/bloodfx-render.py). Description basis: module docstring.

## tools/fab/bloodfx-software-runner.py

Bounded software-only Unreal renderer; private RO mounts, no GPU-controller changes.

Source: [`tools/fab/bloodfx-software-runner.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/bloodfx-software-runner.py). Description basis: module docstring.

Declared CLI options: `--inside`.

## tools/fab/build_model_index.py

Index every model file a Godot project can use without Unreal: .glb/.gltf/.fbx under the owned packs and the loose files in humble\_assets.

Source: [`tools/fab/build_model_index.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/build_model_index.py). Description basis: module docstring.

Declared CLI options: `--fab`, `--humble`, `--out`.

## tools/fab/download-owned.py

Bounded sequential acquisition using the existing authenticated epic-fab CLI.

Source: [`tools/fab/download-owned.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/download-owned.py). Description basis: module docstring.

Declared CLI options: `--asset-hours`, `--concurrency`, `--continue-on-error`, `--engine`, `--evidence`.

## tools/fab/export-poo-vfx.py

Fixed owned-Poo VFX portable export; source read-only, isolated bounded worker.

Source: [`tools/fab/export-poo-vfx.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/export-poo-vfx.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--i-approve`, `--project`.

## tools/fab/fab-library-dump.ts

Source component: fab library dump. Inspect the source before use.

Source: [`tools/fab/fab-library-dump.ts`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/fab-library-dump.ts). Description basis: filename summary.

## tools/fab/fab-listing-detail.ts

Source component: fab listing detail. Inspect the source before use.

Source: [`tools/fab/fab-listing-detail.ts`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/fab-listing-detail.ts). Description basis: filename summary.

## tools/fab/fab-listing-download.ts

Source component: fab listing download. Inspect the source before use.

Source: [`tools/fab/fab-listing-download.ts`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/fab-listing-download.ts). Description basis: filename summary.

## tools/fab/fab_listing_facts.ts

Source component: fab listing facts. Inspect the source before use.

Source: [`tools/fab/fab_listing_facts.ts`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/fab_listing_facts.ts). Description basis: filename summary.

## tools/fab/index-receipt.py

Index only receipt-verified acquired resources through the installed Catalog API.

Source: [`tools/fab/index-receipt.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/index-receipt.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/fab/inspect-game-framework.py

Receipt-gated, read-only Unreal project integration inspection; never executes plugins.

Source: [`tools/fab/inspect-game-framework.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/inspect-game-framework.py). Description basis: module docstring.

Declared CLI options: `--asset-id`, `--evidence`.

## tools/fab/inspect-poo-vfx.py

Fixed owned-Poo VFX native inspection; source read-only, no generation/export.

Source: [`tools/fab/inspect-poo-vfx.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/inspect-poo-vfx.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--i-approve`, `--project`.

## tools/fab/lend-game-capacity.py

Temporarily lend game RAM to the existing FAB owners; preserve active inference.

Source: [`tools/fab/lend-game-capacity.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/lend-game-capacity.py). Description basis: module docstring.

Declared CLI options: `--completion-file`, `--evidence`.

## tools/fab/lend-model-capacity.py

Lend idle primary model memory through the existing fenced GPU operator protocol.

Source: [`tools/fab/lend-model-capacity.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/lend-model-capacity.py). Description basis: module docstring.

Declared CLI options: `--allow-loading-primary`, `--evidence`.

## tools/fab/owned_catalog.py

Owned Fab catalog and operator-approved acquisition. No new service or credentials.

Source: [`tools/fab/owned_catalog.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/owned_catalog.py). Description basis: module docstring.

Declared CLI options: `--approval`, `--asset-id`, `--format-selection-json`, `--from-owned-json`, `--owner-approval-evidence`, `--preparation-plan`, `--project`, `--reason`, `--request`, `--session-id`.

## tools/fab/pack-geometry.gd

Source component: pack geometry. Inspect the source before use.

Source: [`tools/fab/pack-geometry.gd`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/pack-geometry.gd). Description basis: filename summary.

## tools/fab/pack-native-probe.py

Bounded read-only native format probe. Does not certify shader fidelity or gameplay.

Source: [`tools/fab/pack-native-probe.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/pack-native-probe.py). Description basis: module docstring.

## tools/fab/pipeline_candidates.py

Source component: pipeline candidates. Inspect the source before use.

Source: [`tools/fab/pipeline_candidates.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/pipeline_candidates.py). Description basis: filename summary.

## tools/fab/qualify-landscape.py

Landscape Mesh Builder: bounded native load/compile qualification, no generation.

Source: [`tools/fab/qualify-landscape.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/qualify-landscape.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--memory-gib`.

## tools/fab/reconcile-catalog.py

Refresh the single live Catalog through its supported bounded Toolkit job API.

Source: [`tools/fab/reconcile-catalog.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/reconcile-catalog.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/fab/repair-downloader.py

Verify/apply the exact JSON SHA1 repair to the existing server downloader; no auth changes.

Source: [`tools/fab/repair-downloader.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/repair-downloader.py). Description basis: module docstring.

Declared CLI options: `--apply`.

## tools/fab/repair-hyper-engine.py

Genuine plugin-only target build in an isolated accepted-engine CoW overlay.

Source: [`tools/fab/repair-hyper-engine.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/repair-hyper-engine.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/fab/resume-hyper-after-restoration.py

Resume an interrupted cached Hyper target only after existing guardians restore.

Source: [`tools/fab/resume-hyper-after-restoration.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/resume-hyper-after-restoration.py). Description basis: module docstring.

Declared CLI options: `--acquisition-evidence`, `--capacity-evidence`.

## tools/fab/rig_vault_fetch.py

Copy non-Unreal Fab downloads \(FBX/GLB/OBJ\) from the rig's Epic vault to the server \(stdlib only\).

Source: [`tools/fab/rig_vault_fetch.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/rig_vault_fetch.py). Description basis: module docstring.

Declared CLI options: `--dest`, `--match`.

## tools/fab/test-manifest-hash.ts

Test fixture/check: test manifest hash. Inspect the source before use.

Source: [`tools/fab/test-manifest-hash.ts`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/test-manifest-hash.ts). Description basis: filename summary.

## tools/fab/test_asset_advisor.py

Offline regression tests; fixtures preserve real catalogue titles and format labels.

Source: [`tools/fab/test_asset_advisor.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/test_asset_advisor.py). Description basis: module docstring.

## tools/fab/test_bloodfx.py

Test fixture/check: test bloodfx. Inspect the source before use.

Source: [`tools/fab/test_bloodfx.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/test_bloodfx.py). Description basis: filename summary.

## tools/fab/test_build_model_index.py

Test fixture/check: test build model index. Inspect the source before use.

Source: [`tools/fab/test_build_model_index.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/test_build_model_index.py). Description basis: filename summary.

## tools/fab/test_owned_catalog.py

Test fixture/check: test owned catalog. Inspect the source before use.

Source: [`tools/fab/test_owned_catalog.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/test_owned_catalog.py). Description basis: filename summary.

## tools/fab/test_rig_vault_fetch.py

Test fixture/check: test rig vault fetch. Inspect the source before use.

Source: [`tools/fab/test_rig_vault_fetch.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/fab/test_rig_vault_fetch.py). Description basis: filename summary.

## tools/game-template-catalogue/archive.py

Safe ZIP extraction shared by the Godot and Unreal installers; never executes archive content.

Source: [`tools/game-template-catalogue/archive.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/game-template-catalogue/archive.py). Description basis: module docstring.

## tools/game-template-catalogue/catalogue.py

Combine installed records and publish short, searchable native skill entries.

Source: [`tools/game-template-catalogue/catalogue.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/game-template-catalogue/catalogue.py). Description basis: module docstring.

Declared CLI options: `--root`, `--skills`.

## tools/game-template-catalogue/download-itch.py

Download owner-requested free itch.io archives pinned in sources.json; skips verified downloads, executes nothing.

Source: [`tools/game-template-catalogue/download-itch.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/game-template-catalogue/download-itch.py). Description basis: module docstring.

## tools/game-template-catalogue/download-unreal.py

Source component: download unreal. Inspect the source before use.

Source: [`tools/game-template-catalogue/download-unreal.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/game-template-catalogue/download-unreal.py). Description basis: filename summary.

## tools/game-template-catalogue/install-unreal.py

Safely extract owner-requested archives without executing their code.

Source: [`tools/game-template-catalogue/install-unreal.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/game-template-catalogue/install-unreal.py). Description basis: module docstring.

## tools/game-template-catalogue/install.py

Install pinned independent upstream projects \(Git or owner-requested archive\); never execute template code.

Source: [`tools/game-template-catalogue/install.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/game-template-catalogue/install.py). Description basis: module docstring.

## tools/game-template-catalogue/search.py

Read-only intent search across installed game templates.

Source: [`tools/game-template-catalogue/search.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/game-template-catalogue/search.py). Description basis: module docstring.

Declared CLI options: `--catalogue`, `--category`, `--engine`, `--limit`.

## tools/git/export-llm-platform.py

Export a fresh LLM platform source snapshot; never commit, push or deploy.

Source: [`tools/git/export-llm-platform.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/git/export-llm-platform.py). Description basis: module docstring.

Declared CLI options: `--application`, `--include-new`, `--output`.

## tools/git/install-main-protection.sh

Source component: install main protection. Inspect the source before use.

Source: [`tools/git/install-main-protection.sh`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/git/install-main-protection.sh). Description basis: filename summary.

## tools/git/prune-glance.py

Trim the Glance dashboard source to the AI platform for the public export.

Source: [`tools/git/prune-glance.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/git/prune-glance.py). Description basis: module docstring.

## tools/git/prune-manifests.py

Remove out-of-scope service entries from shared manifests, inventories and scripts in the public export.

Source: [`tools/git/prune-manifests.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/git/prune-manifests.py). Description basis: module docstring.

## tools/git/publish-private-safe.py

Publish a filtered current snapshot from fresh Git objects, without private ancestry.

Source: [`tools/git/publish-private-safe.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/git/publish-private-safe.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--publish-main`.

## tools/human-pose-agent/test_adapter_profile.py

Operator test inside pinned external Blender; never an app-shell command.

Source: [`tools/human-pose-agent/test_adapter_profile.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/human-pose-agent/test_adapter_profile.py). Description basis: module docstring.

## tools/human-pose-agent/test_runtime.py

Test fixture/check: test runtime. Inspect the source before use.

Source: [`tools/human-pose-agent/test_runtime.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/human-pose-agent/test_runtime.py). Description basis: filename summary.

Declared CLI options: `--output`, `--scripts`.

## tools/language-knowledge/admin/procedures.py

Verified local procedures, never official reference data.

Source: [`tools/language-knowledge/admin/procedures.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/admin/procedures.py). Description basis: module docstring.

Declared CLI options: `--cards`, `--receipts-dir`, `--runtime`, `--store`.

## tools/language-knowledge/admin/wlk.py

Offline card administration. All managed paths stay within root.

Source: [`tools/language-knowledge/admin/wlk.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/admin/wlk.py). Description basis: module docstring.

Declared CLI options: `--apply`, `--cards`, `--keep`, `--root`.

## tools/language-knowledge/build.sh

Source component: build. Inspect the source before use.

Source: [`tools/language-knowledge/build.sh`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/build.sh). Description basis: filename summary.

## tools/language-knowledge/embed/embed_cards.py

Embed cards with the existing in-cluster BGE service into an Int8, L2-normalised matrix for the RAM engine.

Source: [`tools/language-knowledge/embed/embed_cards.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/embed/embed_cards.py). Description basis: module docstring.

Declared CLI options: `--batch`, `--cards`, `--delay`, `--dim`, `--limit`, `--model`, `--out`, `--url`.

## tools/language-knowledge/extract/blender_extract.py

Extract versioned Blender knowledge cards using only the host stdlib.

Source: [`tools/language-knowledge/extract/blender_extract.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/extract/blender_extract.py). Description basis: module docstring.

Declared CLI options: `--blender`, `--dump`, `--out`, `--version`.

## tools/language-knowledge/extract/blender_inner.py

Dump live RNA metadata. Execute with Blender, never with project files loaded.

Source: [`tools/language-knowledge/extract/blender_inner.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/extract/blender_inner.py). Description basis: module docstring.

## tools/language-knowledge/extract/cli_extract.py

Extract CLI cards from installed Godot/Blender --help, or saved help bytes.

Source: [`tools/language-knowledge/extract/cli_extract.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/extract/cli_extract.py). Description basis: module docstring.

Declared CLI options: `--binary`, `--help-file`, `--out`, `--product`, `--version`.

## tools/language-knowledge/extract/godot_extract.py

Extract v1 knowledge cards from Godot class-reference XML, offline.

Source: [`tools/language-knowledge/extract/godot_extract.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/extract/godot_extract.py). Description basis: module docstring.

Declared CLI options: `--classes`, `--out`, `--version`.

## tools/language-knowledge/extract/godot_import_extract.py

Extract Godot import-option cards from the installed engine, offline.

Source: [`tools/language-knowledge/extract/godot_import_extract.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/extract/godot_import_extract.py). Description basis: module docstring.

Declared CLI options: `--binary`, `--imports-dir`, `--out`, `--version`.

## tools/language-knowledge/extract/godot_mcp_entries.py

Generate manuals/godot-mcp-toolkit/entries.jsonl and manuals/watoom-godot-route/entries.jsonl.

Source: [`tools/language-knowledge/extract/godot_mcp_entries.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/extract/godot_mcp_entries.py). Description basis: module docstring.

Declared CLI options: `--manuals-root`.

## tools/language-knowledge/extract/manual_extract.py

Extract cards from a registered vendor manual / condensed syntax guide \(generic "add a new tool" path\).

Source: [`tools/language-knowledge/extract/manual_extract.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/extract/manual_extract.py). Description basis: module docstring.

Declared CLI options: `--manuals-root`, `--out`, `--product`.

## tools/language-knowledge/extract/ue_mcp_entries.py

Generate the ue-mcp language-knowledge cards, the effects table and the reviewed rig policy.

Source: [`tools/language-knowledge/extract/ue_mcp_entries.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/extract/ue_mcp_entries.py). Description basis: module docstring.

Declared CLI options: `--manuals-root`, `--package`, `--policy-out`.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.add_host.py

Source component: ansible.builtin.add host. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.add_host.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.add_host.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.assemble.py

Source component: ansible.builtin.assemble. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.assemble.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.assemble.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.assert.py

Source component: ansible.builtin.assert. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.assert.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.assert.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.async_status.py

Source component: ansible.builtin.async status. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.async_status.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.async_status.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.blockinfile.py

Source component: ansible.builtin.blockinfile. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.blockinfile.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.blockinfile.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.command.py

Source component: ansible.builtin.command. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.command.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.command.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.copy.py

Source component: ansible.builtin.copy. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.copy.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.copy.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.cron.py

Source component: ansible.builtin.cron. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.cron.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.cron.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.debug.py

Source component: ansible.builtin.debug. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.debug.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.debug.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.dnf.py

Source component: ansible.builtin.dnf. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.dnf.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.dnf.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.expect.py

Source component: ansible.builtin.expect. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.expect.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.expect.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.fail.py

Source component: ansible.builtin.fail. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.fail.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.fail.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.fetch.py

Source component: ansible.builtin.fetch. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.fetch.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.fetch.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.file.py

Source component: ansible.builtin.file. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.file.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.file.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.find.py

Source component: ansible.builtin.find. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.find.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.find.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.gather_facts.py

Source component: ansible.builtin.gather facts. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.gather_facts.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.gather_facts.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.get_url.py

Source component: ansible.builtin.get url. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.get_url.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.get_url.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.getent.py

Source component: ansible.builtin.getent. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.getent.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.getent.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.git.py

Source component: ansible.builtin.git. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.git.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.git.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.group.py

Source component: ansible.builtin.group. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.group.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.group.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.group_by.py

Source component: ansible.builtin.group by. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.group_by.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.group_by.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.hostname.py

Source component: ansible.builtin.hostname. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.hostname.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.hostname.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.import_playbook.py

Source component: ansible.builtin.import playbook. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.import_playbook.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.import_playbook.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.import_role.py

Source component: ansible.builtin.import role. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.import_role.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.import_role.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.import_tasks.py

Source component: ansible.builtin.import tasks. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.import_tasks.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.import_tasks.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.include_role.py

Source component: ansible.builtin.include role. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.include_role.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.include_role.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.include_tasks.py

Source component: ansible.builtin.include tasks. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.include_tasks.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.include_tasks.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.include_vars.py

Source component: ansible.builtin.include vars. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.include_vars.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.include_vars.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.iptables.py

Source component: ansible.builtin.iptables. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.iptables.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.iptables.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.known_hosts.py

Source component: ansible.builtin.known hosts. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.known_hosts.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.known_hosts.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.lineinfile.py

Source component: ansible.builtin.lineinfile. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.lineinfile.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.lineinfile.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.meta.py

Source component: ansible.builtin.meta. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.meta.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.meta.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.mount_facts.py

Source component: ansible.builtin.mount facts. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.mount_facts.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.mount_facts.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.package.py

Source component: ansible.builtin.package. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.package.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.package.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.package_facts.py

Source component: ansible.builtin.package facts. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.package_facts.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.package_facts.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.pause.py

Source component: ansible.builtin.pause. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.pause.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.pause.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.ping.py

Source component: ansible.builtin.ping. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.ping.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.ping.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.pip.py

Source component: ansible.builtin.pip. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.pip.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.pip.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.raw.py

Source component: ansible.builtin.raw. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.raw.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.raw.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.reboot.py

Source component: ansible.builtin.reboot. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.reboot.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.reboot.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.replace.py

Source component: ansible.builtin.replace. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.replace.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.replace.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.rpm_key.py

Source component: ansible.builtin.rpm key. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.rpm_key.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.rpm_key.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.script.py

Source component: ansible.builtin.script. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.script.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.script.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.service.py

Source component: ansible.builtin.service. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.service.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.service.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.service_facts.py

Source component: ansible.builtin.service facts. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.service_facts.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.service_facts.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.set_fact.py

Source component: ansible.builtin.set fact. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.set_fact.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.set_fact.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.setup.py

Source component: ansible.builtin.setup. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.setup.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.setup.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.shell.py

Source component: ansible.builtin.shell. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.shell.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.shell.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.slurp.py

Source component: ansible.builtin.slurp. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.slurp.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.slurp.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.stat.py

Source component: ansible.builtin.stat. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.stat.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.stat.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.systemd.py

Source component: ansible.builtin.systemd. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.systemd.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.systemd.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.systemd_service.py

Source component: ansible.builtin.systemd service. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.systemd_service.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.systemd_service.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.tempfile.py

Source component: ansible.builtin.tempfile. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.tempfile.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.tempfile.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.template.py

Source component: ansible.builtin.template. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.template.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.template.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.unarchive.py

Source component: ansible.builtin.unarchive. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.unarchive.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.unarchive.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.uri.py

Source component: ansible.builtin.uri. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.uri.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.uri.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.user.py

Source component: ansible.builtin.user. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.user.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.user.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.validate_argument_spec.py

Source component: ansible.builtin.validate argument spec. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.validate_argument_spec.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.validate_argument_spec.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.wait_for.py

Source component: ansible.builtin.wait for. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.wait_for.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.wait_for.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.wait_for_connection.py

Source component: ansible.builtin.wait for connection. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.wait_for_connection.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.wait_for_connection.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.yum_repository.py

Source component: ansible.builtin.yum repository. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.yum_repository.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.builtin.yum_repository.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.posix.at.py

Source component: ansible.posix.at. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.posix.at.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.posix.at.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.posix.authorized_key.py

Source component: ansible.posix.authorized key. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.posix.authorized_key.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.posix.authorized_key.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.posix.firewalld.py

Source component: ansible.posix.firewalld. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.posix.firewalld.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.posix.firewalld.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.posix.mount.py

Source component: ansible.posix.mount. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.posix.mount.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.posix.mount.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.posix.seboolean.py

Source component: ansible.posix.seboolean. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.posix.seboolean.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.posix.seboolean.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.posix.selinux.py

Source component: ansible.posix.selinux. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.posix.selinux.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.posix.selinux.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.posix.synchronize.py

Source component: ansible.posix.synchronize. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.posix.synchronize.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.posix.synchronize.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/ansible.posix.sysctl.py

Source component: ansible.posix.sysctl. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/ansible.posix.sysctl.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/ansible.posix.sysctl.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/community.general.filesystem.py

Source component: community.general.filesystem. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/community.general.filesystem.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/community.general.filesystem.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/community.general.ini_file.py

Source component: community.general.ini file. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/community.general.ini_file.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/community.general.ini_file.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/community.general.lvg.py

Source component: community.general.lvg. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/community.general.lvg.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/community.general.lvg.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/community.general.lvol.py

Source component: community.general.lvol. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/community.general.lvol.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/community.general.lvol.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/community.general.modprobe.py

Source component: community.general.modprobe. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/community.general.modprobe.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/community.general.modprobe.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/community.general.nmcli.py

Source component: community.general.nmcli. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/community.general.nmcli.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/community.general.nmcli.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/community.general.parted.py

Source component: community.general.parted. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/community.general.parted.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/community.general.parted.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/community.general.sefcontext.py

Source component: community.general.sefcontext. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/community.general.sefcontext.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/community.general.sefcontext.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/community.general.timezone.py

Source component: community.general.timezone. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/community.general.timezone.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/community.general.timezone.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/kubernetes.core.helm.py

Source component: kubernetes.core.helm. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/kubernetes.core.helm.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/kubernetes.core.helm.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/kubernetes.core.helm_info.py

Source component: kubernetes.core.helm info. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/kubernetes.core.helm_info.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/kubernetes.core.helm_info.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/kubernetes.core.k8s.py

Source component: kubernetes.core.k8s. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/kubernetes.core.k8s.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/kubernetes.core.k8s.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/kubernetes.core.k8s_drain.py

Source component: kubernetes.core.k8s drain. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/kubernetes.core.k8s_drain.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/kubernetes.core.k8s_drain.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/kubernetes.core.k8s_exec.py

Source component: kubernetes.core.k8s exec. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/kubernetes.core.k8s_exec.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/kubernetes.core.k8s_exec.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/kubernetes.core.k8s_info.py

Source component: kubernetes.core.k8s info. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/kubernetes.core.k8s_info.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/kubernetes.core.k8s_info.py). Description basis: filename summary.

## tools/language-knowledge/manuals/ansible/sources/modules/kubernetes.core.k8s_scale.py

Source component: kubernetes.core.k8s scale. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/ansible/sources/modules/kubernetes.core.k8s_scale.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/ansible/sources/modules/kubernetes.core.k8s_scale.py). Description basis: filename summary.

## tools/language-knowledge/manuals/watoom-godot-route/sources/Setup-RigAccount.ps1

Source component: Setup RigAccount. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/watoom-godot-route/sources/Setup-RigAccount.ps1`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/watoom-godot-route/sources/Setup-RigAccount.ps1). Description basis: filename summary.

## tools/language-knowledge/manuals/watoom-pipelines/sources/blender-job-spec.py

Declarative headless Blender job for a game project: which script, its arguments and limits; no paths outside the project.

Source: [`tools/language-knowledge/manuals/watoom-pipelines/sources/blender-job-spec.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/watoom-pipelines/sources/blender-job-spec.py). Description basis: module docstring.

## tools/language-knowledge/manuals/watoom-pipelines/sources/game-worker-bridge.py

Validate native worker requests and dispatch fixed operator-owned helpers.

Source: [`tools/language-knowledge/manuals/watoom-pipelines/sources/game-worker-bridge.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/watoom-pipelines/sources/game-worker-bridge.py). Description basis: module docstring.

## tools/language-knowledge/manuals/watoom-pipelines/sources/terrain-spec-test.py

Source component: terrain spec test. Inspect the source before use.

Source: [`tools/language-knowledge/manuals/watoom-pipelines/sources/terrain-spec-test.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/watoom-pipelines/sources/terrain-spec-test.py). Description basis: filename summary.

## tools/language-knowledge/manuals/watoom-pipelines/sources/terrain-spec.py

Project-neutral declarative terrain/landscape-to-GLB export contract; no caller shell or engine arguments.

Source: [`tools/language-knowledge/manuals/watoom-pipelines/sources/terrain-spec.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/watoom-pipelines/sources/terrain-spec.py). Description basis: module docstring.

## tools/language-knowledge/manuals/watoom-pipelines/sources/unreal-export-spec.py

Declarative Unreal pack export request: which purchased pack, folder and asset classes; no paths or engine arguments.

Source: [`tools/language-knowledge/manuals/watoom-pipelines/sources/unreal-export-spec.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/watoom-pipelines/sources/unreal-export-spec.py). Description basis: module docstring.

## tools/language-knowledge/manuals/watoom-pipelines/sources/unreal-lane-build.py

Build the self-contained bundle to copy to the rig: python3 build\_lane.py \<output dir\> Gathers the lane's sources, the in-engine scripts \(single source of truth: the watoom-metahuman skill\) and the two helpers it reuses from the existing RI

Source: [`tools/language-knowledge/manuals/watoom-pipelines/sources/unreal-lane-build.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/manuals/watoom-pipelines/sources/unreal-lane-build.py). Description basis: module docstring.

## tools/language-knowledge/package/engine.js

Source component: engine. Inspect the source before use.

Source: [`tools/language-knowledge/package/engine.js`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/package/engine.js). Description basis: filename summary.

## tools/language-knowledge/package/index.js

Source component: index. Inspect the source before use.

Source: [`tools/language-knowledge/package/index.js`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/package/index.js). Description basis: filename summary.

## tools/language-knowledge/package/triggers.js

Source component: triggers. Inspect the source before use.

Source: [`tools/language-knowledge/package/triggers.js`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/package/triggers.js). Description basis: filename summary.

## tools/language-knowledge/tests/engine.test.mjs

Test fixture/check: engine.test. Inspect the source before use.

Source: [`tools/language-knowledge/tests/engine.test.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/tests/engine.test.mjs). Description basis: filename summary.

## tools/language-knowledge/tests/import_triggers.test.mjs

Test fixture/check: import triggers.test. Inspect the source before use.

Source: [`tools/language-knowledge/tests/import_triggers.test.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/tests/import_triggers.test.mjs). Description basis: filename summary.

## tools/language-knowledge/tests/plugin.test.mjs

Test fixture/check: plugin.test. Inspect the source before use.

Source: [`tools/language-knowledge/tests/plugin.test.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/tests/plugin.test.mjs). Description basis: filename summary.

## tools/language-knowledge/tests/test_admin.py

Offline operator CLI and filesystem boundary tests.

Source: [`tools/language-knowledge/tests/test_admin.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/tests/test_admin.py). Description basis: module docstring.

## tools/language-knowledge/tests/test_blender_extract.py

Host extractor tests; Blender is not needed for fixture conversion.

Source: [`tools/language-knowledge/tests/test_blender_extract.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/tests/test_blender_extract.py). Description basis: module docstring.

## tools/language-knowledge/tests/test_cli_extract.py

Offline, stdlib-only CLI extraction tests using small synthetic help fixtures.

Source: [`tools/language-knowledge/tests/test_cli_extract.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/tests/test_cli_extract.py). Description basis: module docstring.

## tools/language-knowledge/tests/test_embed_cards.py

Test fixture/check: test embed cards. Inspect the source before use.

Source: [`tools/language-knowledge/tests/test_embed_cards.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/tests/test_embed_cards.py). Description basis: filename summary.

## tools/language-knowledge/tests/test_godot_extract.py

Offline extractor contract tests; fixtures are deliberately small and synthetic.

Source: [`tools/language-knowledge/tests/test_godot_extract.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/tests/test_godot_extract.py). Description basis: module docstring.

## tools/language-knowledge/tests/test_godot_import_extract.py

Offline, stdlib-only tests for the Godot import-option extractor \(real .import files from the engine, trimmed; fake binaries holding hint strings\).

Source: [`tools/language-knowledge/tests/test_godot_import_extract.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/tests/test_godot_import_extract.py). Description basis: module docstring.

## tools/language-knowledge/tests/test_manual_extract.py

Tests for extract/manual\_extract.py: the generic "add a different tool/manual" extractor.

Source: [`tools/language-knowledge/tests/test_manual_extract.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/tests/test_manual_extract.py). Description basis: module docstring.

## tools/language-knowledge/tests/test_procedures.py

Verified-procedure evidence, secrets, revisions and runtime boundaries.

Source: [`tools/language-knowledge/tests/test_procedures.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/tests/test_procedures.py). Description basis: module docstring.

## tools/language-knowledge/tests/triggers.test.mjs

Test fixture/check: triggers.test. Inspect the source before use.

Source: [`tools/language-knowledge/tests/triggers.test.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/tests/triggers.test.mjs). Description basis: filename summary.

## tools/language-knowledge/tests/vectors.test.mjs

Test fixture/check: vectors.test. Inspect the source before use.

Source: [`tools/language-knowledge/tests/vectors.test.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/language-knowledge/tests/vectors.test.mjs). Description basis: filename summary.

## tools/llm/benchmark-cuda-graphs.py

Benchmark the primary model with CUDA graphs off vs on, through the fenced GPU operator protocol.

Source: [`tools/llm/benchmark-cuda-graphs.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/benchmark-cuda-graphs.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--runs`.

## tools/llm/bge/benchmark/recall_benchmark.py

Recall@3/@5 of AgentMemory search for paraphrased queries, BM25-only vs hybrid.

Source: [`tools/llm/bge/benchmark/recall_benchmark.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/bge/benchmark/recall_benchmark.py). Description basis: module docstring.

Declared CLI options: `--distractors`, `--fixture`, `--secret`, `--target`.

## tools/llm/bge/embed_proxy.py

OpenAI-compatible /v1/embeddings front end for a llama.cpp BGE server.

Source: [`tools/llm/bge/embed_proxy.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/bge/embed_proxy.py). Description basis: module docstring.

Declared CLI options: `--backend`, `--batch-rate`, `--busy-file`, `--busy-rate`, `--cache-size`, `--cls-id`, `--concurrency`, `--host`, `--max-batch-wait`, `--model`, `--port`, `--sep-id`.

## tools/llm/bge/tests/test_embed_proxy.py

Test fixture/check: test embed proxy. Inspect the source before use.

Source: [`tools/llm/bge/tests/test_embed_proxy.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/bge/tests/test_embed_proxy.py). Description basis: filename summary.

## tools/llm/bge/verify_gguf.py

Prove a third-party BGE GGUF is a faithful conversion of the official weights.

Source: [`tools/llm/bge/verify_gguf.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/bge/verify_gguf.py). Description basis: module docstring.

## tools/llm/llama_mesh.py

Explicit offline mesh ingestion/preparation; generation never calls the router.

Source: [`tools/llm/llama_mesh.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/llama_mesh.py). Description basis: module docstring.

Declared CLI options: `--config`, `--confirm-idle`, `--name`, `--prepare`, `--prompt-file`, `--size-cm`.

## tools/llm/llama_mesh_blender.py

Run only through llama\_mesh.py prepare; CPU-only, no downloads or network.

Source: [`tools/llm/llama_mesh_blender.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/llama_mesh_blender.py). Description basis: module docstring.

## tools/llm/test_llama_mesh.py

Test fixture/check: test llama mesh. Inspect the source before use.

Source: [`tools/llm/test_llama_mesh.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/test_llama_mesh.py). Description basis: filename summary.

## tools/llm/watoom-gpu-controller/client.py

G3F client contracts. No Kubernetes calls or fallback to kubectl.

Source: [`tools/llm/watoom-gpu-controller/client.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/client.py). Description basis: module docstring.

## tools/llm/watoom-gpu-controller/controller.py

Offline reference for WatooM GPU controller. NO Kubernetes client / live entrypoint.

Source: [`tools/llm/watoom-gpu-controller/controller.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/controller.py). Description basis: module docstring.

## tools/llm/watoom-gpu-controller/durable_store.py

Crash-resistant single-host state store for offline GPU controller tests.

Source: [`tools/llm/watoom-gpu-controller/durable_store.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/durable_store.py). Description basis: module docstring.

## tools/llm/watoom-gpu-controller/g3h_cutover.py

Reviewed quiescence/barrier checks. No replica mutation is performed here.

Source: [`tools/llm/watoom-gpu-controller/g3h_cutover.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/g3h_cutover.py). Description basis: module docstring.

Declared CLI options: `--config`, `--evidence`.

## tools/llm/watoom-gpu-controller/g3h_ops.py

Bounded offline/live operator checks and fail-closed recovery.

Source: [`tools/llm/watoom-gpu-controller/g3h_ops.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/g3h_ops.py). Description basis: module docstring.

Declared CLI options: `--candidate`, `--snapshot`.

## tools/llm/watoom-gpu-controller/g3h_service.py

Production host gateway; no credential discovery and no simulation fallback.

Source: [`tools/llm/watoom-gpu-controller/g3h_service.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/g3h_service.py). Description basis: module docstring.

Declared CLI options: `--config`.

## tools/llm/watoom-gpu-controller/gateway.py

Offline GPU ownership gateway. No Kubernetes client or production deployment path. Unix peer authentication, cross-process exclusive file locking and persistent state. For simulation and client-contract tests only.

Source: [`tools/llm/watoom-gpu-controller/gateway.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/gateway.py). Description basis: module docstring.

## tools/llm/watoom-gpu-controller/inference_leases.py

Durable request accounting. Uncertain completion blocks GPU changes.

Source: [`tools/llm/watoom-gpu-controller/inference_leases.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/inference_leases.py). Description basis: module docstring.

## tools/llm/watoom-gpu-controller/kubernetes_actuator.py

Offline-testable conditional Kubernetes actuator; no live CLI or kubeconfig.

Source: [`tools/llm/watoom-gpu-controller/kubernetes_actuator.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/kubernetes_actuator.py). Description basis: module docstring.

## tools/llm/watoom-gpu-controller/kubernetes_api.py

Restricted Kubernetes API transport for the WatooM actuator.

Source: [`tools/llm/watoom-gpu-controller/kubernetes_api.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/kubernetes_api.py). Description basis: module docstring.

## tools/llm/watoom-gpu-controller/live_adapter.py

Explicit-opt-in Kubernetes actuator adapter; NEVER auto-start or acquire credentials. Preconditions: only controller may patch deployments, legacy router writer fenced, quiescence externally established. Unsafe to serve before production cu

Source: [`tools/llm/watoom-gpu-controller/live_adapter.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/live_adapter.py). Description basis: module docstring.

## tools/llm/watoom-gpu-controller/model_lifecycle.py

Never-started enrollment distinct from legacy cutover acknowledgment.

Source: [`tools/llm/watoom-gpu-controller/model_lifecycle.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/model_lifecycle.py). Description basis: module docstring.

## tools/llm/watoom-gpu-controller/observability.py

Read-only status publication by the existing controller; never calls an actuator.

Source: [`tools/llm/watoom-gpu-controller/observability.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/observability.py). Description basis: module docstring.

## tools/llm/watoom-gpu-controller/refresh_credentials.py

Privileged issuer is separate from the controller; never print a token.

Source: [`tools/llm/watoom-gpu-controller/refresh_credentials.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/refresh_credentials.py). Description basis: module docstring.

## tools/llm/watoom-gpu-controller/tests/test_adapters.py

Test fixture/check: test adapters. Inspect the source before use.

Source: [`tools/llm/watoom-gpu-controller/tests/test_adapters.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/tests/test_adapters.py). Description basis: filename summary.

## tools/llm/watoom-gpu-controller/tests/test_controller.py

Test fixture/check: test controller. Inspect the source before use.

Source: [`tools/llm/watoom-gpu-controller/tests/test_controller.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/tests/test_controller.py). Description basis: filename summary.

## tools/llm/watoom-gpu-controller/tests/test_durable_store.py

Test fixture/check: test durable store. Inspect the source before use.

Source: [`tools/llm/watoom-gpu-controller/tests/test_durable_store.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/tests/test_durable_store.py). Description basis: filename summary.

## tools/llm/watoom-gpu-controller/tests/test_g3h_barrier_invariants.py

Negative controls: barried inventory cannot drift in replicas or spec.

Source: [`tools/llm/watoom-gpu-controller/tests/test_g3h_barrier_invariants.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/tests/test_g3h_barrier_invariants.py). Description basis: module docstring.

## tools/llm/watoom-gpu-controller/tests/test_g3h_bridge.py

Test fixture/check: test g3h bridge. Inspect the source before use.

Source: [`tools/llm/watoom-gpu-controller/tests/test_g3h_bridge.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/tests/test_g3h_bridge.py). Description basis: filename summary.

## tools/llm/watoom-gpu-controller/tests/test_g3h_cutover.py

Deterministic storage CAS/admission model; timing alone is never the fence.

Source: [`tools/llm/watoom-gpu-controller/tests/test_g3h_cutover.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/tests/test_g3h_cutover.py). Description basis: module docstring.

## tools/llm/watoom-gpu-controller/tests/test_g3h_integration.py

Test fixture/check: test g3h integration. Inspect the source before use.

Source: [`tools/llm/watoom-gpu-controller/tests/test_g3h_integration.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/tests/test_g3h_integration.py). Description basis: filename summary.

## tools/llm/watoom-gpu-controller/tests/test_g3h_late_write.py

Test fixture/check: test g3h late write. Inspect the source before use.

Source: [`tools/llm/watoom-gpu-controller/tests/test_g3h_late_write.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/tests/test_g3h_late_write.py). Description basis: filename summary.

## tools/llm/watoom-gpu-controller/tests/test_g3h_mcp.py

Test fixture/check: test g3h mcp. Inspect the source before use.

Source: [`tools/llm/watoom-gpu-controller/tests/test_g3h_mcp.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/tests/test_g3h_mcp.py). Description basis: filename summary.

## tools/llm/watoom-gpu-controller/tests/test_g3h_ops.py

Test fixture/check: test g3h ops. Inspect the source before use.

Source: [`tools/llm/watoom-gpu-controller/tests/test_g3h_ops.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/tests/test_g3h_ops.py). Description basis: filename summary.

## tools/llm/watoom-gpu-controller/tests/test_g3h_router_models.py

Test fixture/check: test g3h router models. Inspect the source before use.

Source: [`tools/llm/watoom-gpu-controller/tests/test_g3h_router_models.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/tests/test_g3h_router_models.py). Description basis: filename summary.

## tools/llm/watoom-gpu-controller/tests/test_g3h_runtime.py

Test fixture/check: test g3h runtime. Inspect the source before use.

Source: [`tools/llm/watoom-gpu-controller/tests/test_g3h_runtime.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/tests/test_g3h_runtime.py). Description basis: filename summary.

## tools/llm/watoom-gpu-controller/tests/test_g3h_selftest.py

Test fixture/check: test g3h selftest. Inspect the source before use.

Source: [`tools/llm/watoom-gpu-controller/tests/test_g3h_selftest.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/tests/test_g3h_selftest.py). Description basis: filename summary.

## tools/llm/watoom-gpu-controller/tests/test_gateway.py

Test fixture/check: test gateway. Inspect the source before use.

Source: [`tools/llm/watoom-gpu-controller/tests/test_gateway.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/tests/test_gateway.py). Description basis: filename summary.

## tools/llm/watoom-gpu-controller/tests/test_inference_leases.py

Test fixture/check: test inference leases. Inspect the source before use.

Source: [`tools/llm/watoom-gpu-controller/tests/test_inference_leases.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/tests/test_inference_leases.py). Description basis: filename summary.

## tools/llm/watoom-gpu-controller/tests/test_kubernetes_actuator.py

Test fixture/check: test kubernetes actuator. Inspect the source before use.

Source: [`tools/llm/watoom-gpu-controller/tests/test_kubernetes_actuator.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/tests/test_kubernetes_actuator.py). Description basis: filename summary.

## tools/llm/watoom-gpu-controller/tests/test_kubernetes_api.py

Test fixture/check: test kubernetes api. Inspect the source before use.

Source: [`tools/llm/watoom-gpu-controller/tests/test_kubernetes_api.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/tests/test_kubernetes_api.py). Description basis: filename summary.

## tools/llm/watoom-gpu-controller/tests/test_live_adapter.py

Test fixture/check: test live adapter. Inspect the source before use.

Source: [`tools/llm/watoom-gpu-controller/tests/test_live_adapter.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/tests/test_live_adapter.py). Description basis: filename summary.

## tools/llm/watoom-gpu-controller/tests/test_model_lifecycle.py

Test fixture/check: test model lifecycle. Inspect the source before use.

Source: [`tools/llm/watoom-gpu-controller/tests/test_model_lifecycle.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/tests/test_model_lifecycle.py). Description basis: filename summary.

## tools/llm/watoom-gpu-controller/tests/test_observability.py

Test fixture/check: test observability. Inspect the source before use.

Source: [`tools/llm/watoom-gpu-controller/tests/test_observability.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/llm/watoom-gpu-controller/tests/test_observability.py). Description basis: filename summary.

## tools/model-manager/admission_errors.py

Source component: admission errors. Inspect the source before use.

Source: [`tools/model-manager/admission_errors.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/admission_errors.py). Description basis: filename summary.

## tools/model-manager/broker.py

Root-only bounded registration broker. No scale/exec or arbitrary kubectl API.

Source: [`tools/model-manager/broker.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/broker.py). Description basis: module docstring.

## tools/model-manager/broker_service.py

Private Unix broker: UID-scoped model IDs, no browser/root HTTP endpoint.

Source: [`tools/model-manager/broker_service.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/broker_service.py). Description basis: module docstring.

Declared CLI options: `--config`.

## tools/model-manager/browser-live.cjs

Source component: browser live. Inspect the source before use.

Source: [`tools/model-manager/browser-live.cjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/browser-live.cjs). Description basis: filename summary.

## tools/model-manager/browser-test.py

Isolated production browser acceptance; no global trust or node changes.

Source: [`tools/model-manager/browser-test.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/browser-test.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/model-manager/cutover.py

Explicitly approved controller/router integration; never changes replica policy.

Source: [`tools/model-manager/cutover.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/cutover.py). Description basis: module docstring.

Declared CLI options: `--administrative-quiet`, `--approve`, `--evidence`, `--i-approve`.

## tools/model-manager/deploy-broker-deadline.py

Publish only the reviewed broker-client deadline overlay; preserve other image bytes.

Source: [`tools/model-manager/deploy-broker-deadline.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/deploy-broker-deadline.py). Description basis: module docstring.

Declared CLI options: `--i-approve`.

## tools/model-manager/download.py

Bounded, immutable downloads; credentials never accompany CDN redirects.

Source: [`tools/model-manager/download.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/download.py). Description basis: module docstring.

## tools/model-manager/file_lock.py

OS file locks; Windows support is for isolated browser fixtures.

Source: [`tools/model-manager/file_lock.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/file_lock.py). Description basis: module docstring.

## tools/model-manager/gguf_header.py

Bounded metadata-only GGUF inspection; never loads tensors or executes models.

Source: [`tools/model-manager/gguf_header.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/gguf_header.py). Description basis: module docstring.

## tools/model-manager/hf.py

Source component: hf. Inspect the source before use.

Source: [`tools/model-manager/hf.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/hf.py). Description basis: filename summary.

## tools/model-manager/image_mcp.py

Scoped MCP surface: installed image models, idempotent queue, status and PNGs. No installation/removal, arbitrary paths, URLs, shell execution or admin password.

Source: [`tools/model-manager/image_mcp.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/image_mcp.py). Description basis: module docstring.

## tools/model-manager/image_publish.py

Publish verified generated bytes only beneath the configured dedicated directory.

Source: [`tools/model-manager/image_publish.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/image_publish.py). Description basis: module docstring.

## tools/model-manager/manage.py

Bounded build, isolated staging, validation and identity-scoped rollback.

Source: [`tools/model-manager/manage.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/manage.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/model-manager/native_admission.py

Use the existing durable native admission contract; never alter networking.

Source: [`tools/model-manager/native_admission.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/native_admission.py). Description basis: module docstring.

## tools/model-manager/operations.py

Serialized managed artifact installation/removal, preserving shared references.

Source: [`tools/model-manager/operations.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/operations.py). Description basis: module docstring.

## tools/model-manager/render_router_manifest.py

Render the tracked router manifests from the authored router source.

Source: [`tools/model-manager/render_router_manifest.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/render_router_manifest.py). Description basis: module docstring.

## tools/model-manager/reregister.py

Operator entry point for Operations.reregister \(T-0123\): retire \+ register a Model Manager model again so it picks up the broker's current workload \(e.g. --metrics, Swift's runtime\), files and mm-\* identity kept.

Source: [`tools/model-manager/reregister.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/reregister.py). Description basis: module docstring.

Declared CLI options: `--list`, `--set`.

## tools/model-manager/runtime_payload.py

Pinned SDXL runtime publication on /data, not node imagefs.

Source: [`tools/model-manager/runtime_payload.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/runtime_payload.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/model-manager/sdxl_backend.py

Local-files-only SDXL backend; controller grants exclusive GPU ownership.

Source: [`tools/model-manager/sdxl_backend.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/sdxl_backend.py). Description basis: module docstring.

Declared CLI options: `--adapter`, `--alias`, `--base`, `--checkpoint`, `--key-file`, `--output`, `--precision`.

## tools/model-manager/server.py

Authenticated manager. UI has no Kubernetes or GPU-write privileges.

Source: [`tools/model-manager/server.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/server.py). Description basis: module docstring.

Declared CLI options: `--broker-socket`, `--hf-token-file`, `--image-mcp-token-file`, `--listen`, `--maintenance-file`, `--models`, `--origin`, `--password-file`, `--port`, `--prefix`, `--session-ttl-sec`, `--state`.

## tools/model-manager/settings.py

Typed settings and explicit, revision-scoped provenance.

Source: [`tools/model-manager/settings.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/settings.py). Description basis: module docstring.

## tools/model-manager/stage_fixture.py

Isolated browser acceptance. Never uses production models/controller.

Source: [`tools/model-manager/stage_fixture.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/stage_fixture.py). Description basis: module docstring.

Declared CLI options: `--password-file`, `--port`, `--state`.

## tools/model-manager/store.py

Single durable queue/catalog, revision-scoped overrides and dependency references.

Source: [`tools/model-manager/store.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/store.py). Description basis: module docstring.

## tools/model-manager/test_broker.py

Test fixture/check: test broker. Inspect the source before use.

Source: [`tools/model-manager/test_broker.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/test_broker.py). Description basis: filename summary.

## tools/model-manager/test_broker_deadline.py

Test fixture/check: test broker deadline. Inspect the source before use.

Source: [`tools/model-manager/test_broker_deadline.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/test_broker_deadline.py). Description basis: filename summary.

## tools/model-manager/test_core.py

Test fixture/check: test core. Inspect the source before use.

Source: [`tools/model-manager/test_core.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/test_core.py). Description basis: filename summary.

## tools/model-manager/test_cutover.py

Test fixture/check: test cutover. Inspect the source before use.

Source: [`tools/model-manager/test_cutover.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/test_cutover.py). Description basis: filename summary.

## tools/model-manager/test_download.py

Test fixture/check: test download. Inspect the source before use.

Source: [`tools/model-manager/test_download.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/test_download.py). Description basis: filename summary.

## tools/model-manager/test_generation_progress.py

Test fixture/check: test generation progress. Inspect the source before use.

Source: [`tools/model-manager/test_generation_progress.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/test_generation_progress.py). Description basis: filename summary.

## tools/model-manager/test_gguf.py

Test fixture/check: test gguf. Inspect the source before use.

Source: [`tools/model-manager/test_gguf.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/test_gguf.py). Description basis: filename summary.

## tools/model-manager/test_gpu_handoff.py

Test fixture/check: test gpu handoff. Inspect the source before use.

Source: [`tools/model-manager/test_gpu_handoff.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/test_gpu_handoff.py). Description basis: filename summary.

## tools/model-manager/test_hf.py

Test fixture/check: test hf. Inspect the source before use.

Source: [`tools/model-manager/test_hf.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/test_hf.py). Description basis: filename summary.

## tools/model-manager/test_http.py

Test fixture/check: test http. Inspect the source before use.

Source: [`tools/model-manager/test_http.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/test_http.py). Description basis: filename summary.

## tools/model-manager/test_image_mcp.py

Test fixture/check: test image mcp. Inspect the source before use.

Source: [`tools/model-manager/test_image_mcp.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/test_image_mcp.py). Description basis: filename summary.

## tools/model-manager/test_image_publish.py

Test fixture/check: test image publish. Inspect the source before use.

Source: [`tools/model-manager/test_image_publish.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/test_image_publish.py). Description basis: filename summary.

## tools/model-manager/test_image_restoration.py

Test fixture/check: test image restoration. Inspect the source before use.

Source: [`tools/model-manager/test_image_restoration.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/test_image_restoration.py). Description basis: filename summary.

## tools/model-manager/test_lora_mtp.py

T-0086: GGUF LoRA adapters on an installed GGUF base, MTP speculation proven from the GGUF header, real names and the read-only all-models inventory row parsing.

Source: [`tools/model-manager/test_lora_mtp.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/test_lora_mtp.py). Description basis: module docstring.

## tools/model-manager/test_native_admission.py

Test fixture/check: test native admission. Inspect the source before use.

Source: [`tools/model-manager/test_native_admission.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/test_native_admission.py). Description basis: filename summary.

## tools/model-manager/test_operations.py

Test fixture/check: test operations. Inspect the source before use.

Source: [`tools/model-manager/test_operations.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/test_operations.py). Description basis: filename summary.

## tools/model-manager/test_reasoning_variants.py

Test fixture/check: test reasoning variants. Inspect the source before use.

Source: [`tools/model-manager/test_reasoning_variants.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/test_reasoning_variants.py). Description basis: filename summary.

## tools/model-manager/test_runtime_payload.py

Test fixture/check: test runtime payload. Inspect the source before use.

Source: [`tools/model-manager/test_runtime_payload.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/test_runtime_payload.py). Description basis: filename summary.

## tools/model-manager/test_scope_transport.py

Test fixture/check: test scope transport. Inspect the source before use.

Source: [`tools/model-manager/test_scope_transport.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/test_scope_transport.py). Description basis: filename summary.

## tools/model-manager/test_sdxl.py

Test fixture/check: test sdxl. Inspect the source before use.

Source: [`tools/model-manager/test_sdxl.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/test_sdxl.py). Description basis: filename summary.

## tools/model-manager/test_worker.py

Test fixture/check: test worker. Inspect the source before use.

Source: [`tools/model-manager/test_worker.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/test_worker.py). Description basis: filename summary.

## tools/model-manager/web/app.js

---------- formatting ----------

Source: [`tools/model-manager/web/app.js`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/web/app.js). Description basis: source comment.

## tools/model-manager/worker.py

Source component: worker. Inspect the source before use.

Source: [`tools/model-manager/worker.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/worker.py). Description basis: filename summary.

## tools/model-manager/workload.py

Fixed owned workloads at replicas zero; no replica writer in this module.

Source: [`tools/model-manager/workload.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/model-manager/workload.py). Description basis: module docstring.

## tools/moss-image/gpu_recover.py

ExecStopPost hook for watoom-moss-image.service: if the service died while it owned the GPU, ask the controller to recover \(restore the LLM\). The controller itself refuses unless the recorded owner process is really gone, so this never take

Source: [`tools/moss-image/gpu_recover.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/moss-image/gpu_recover.py). Description basis: module docstring.

Declared CLI options: `--controller-socket`, `--tools-dir`.

## tools/moss-image/gpu_session.py

GPU session for the MOSS Image service, mediated by the WatooM GPU ownership controller.

Source: [`tools/moss-image/gpu_session.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/moss-image/gpu_session.py). Description basis: module docstring.

## tools/moss-image/moss_image_service.py

MOSS-Image service: a small local web page and JSON API in front of the mossimage.cpp \`moss-server\` sidecar.

Source: [`tools/moss-image/moss_image_service.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/moss-image/moss_image_service.py). Description basis: module docstring.

Declared CLI options: `--controller-socket`, `--dit`, `--engine-dir`, `--gpu-gate`, `--host`, `--idle-release`, `--llm-demand-url`, `--min-free-vram-mib`, `--mode`, `--model-folder`, `--out-dir`, `--port`, `--presets`, `--quiet-seconds`, `--session-idle`, `--session-max`, `--sidecar-cmd`, `--text-encoder`, `--tier`, `--tools-dir`, `--vae`.

## tools/moss-image/plugin/index.js

non-JSON error page

Source: [`tools/moss-image/plugin/index.js`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/moss-image/plugin/index.js). Description basis: source comment.

## tools/moss-image/tests/fake_moss_server.py

Minimal stand-in for mossimage.cpp's moss-server \(protocol 2\) for offline tests. Records every request.

Source: [`tools/moss-image/tests/fake_moss_server.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/moss-image/tests/fake_moss_server.py). Description basis: module docstring.

## tools/moss-image/tests/plugin.test.mjs

Test fixture/check: plugin.test. Inspect the source before use.

Source: [`tools/moss-image/tests/plugin.test.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/moss-image/tests/plugin.test.mjs). Description basis: filename summary.

## tools/moss-image/tests/test_gpu_recover.py

Test fixture/check: test gpu recover. Inspect the source before use.

Source: [`tools/moss-image/tests/test_gpu_recover.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/moss-image/tests/test_gpu_recover.py). Description basis: filename summary.

## tools/moss-image/tests/test_gpu_session.py

Test fixture/check: test gpu session. Inspect the source before use.

Source: [`tools/moss-image/tests/test_gpu_session.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/moss-image/tests/test_gpu_session.py). Description basis: filename summary.

## tools/moss-image/tests/test_service.py

Test fixture/check: test service. Inspect the source before use.

Source: [`tools/moss-image/tests/test_service.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/moss-image/tests/test_service.py). Description basis: filename summary.

## tools/pipeline-tools/install.sh

Source component: install. Inspect the source before use.

Source: [`tools/pipeline-tools/install.sh`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/pipeline-tools/install.sh). Description basis: filename summary.

## tools/recovery/pull-environment-recovery.ps1

Source component: pull environment recovery. Inspect the source before use.

Source: [`tools/recovery/pull-environment-recovery.ps1`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/recovery/pull-environment-recovery.ps1). Description basis: filename summary.

## tools/recovery/recovery.py

Inventory, capture and validate WatooM recovery inputs without changing services.

Source: [`tools/recovery/recovery.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/recovery/recovery.py). Description basis: module docstring.

Declared CLI options: `--backup`, `--evidence`, `--inventory`, `--output`, `--phase`, `--policy`, `--scope`, `--target`, `--vars-file`.

## tools/recovery/test_recovery.py

Offline safety/restore tests. No Kubernetes, Docker, Ansible or live mutation.

Source: [`tools/recovery/test_recovery.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/recovery/test_recovery.py). Description basis: module docstring.

## tools/rig-async-stage/bridge-source/asset_capture_bridge.py

Native declarative capture bridge, dispatched under the existing worker lock.

Source: [`tools/rig-async-stage/bridge-source/asset_capture_bridge.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/bridge-source/asset_capture_bridge.py). Description basis: module docstring.

## tools/rig-async-stage/bridge-source/dispatcher.py

Opt-in staged dispatcher: admit all RIG work, deliver receipts without blocking inference.

Source: [`tools/rig-async-stage/bridge-source/dispatcher.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/bridge-source/dispatcher.py). Description basis: module docstring.

## tools/rig-async-stage/install-runtime.py

Install only the opt-in staged runtime after an operator-held idle queue fence.

Source: [`tools/rig-async-stage/install-runtime.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/install-runtime.py). Description basis: module docstring.

## tools/rig-async-stage/provision-app.py

Source component: provision app. Inspect the source before use.

Source: [`tools/rig-async-stage/provision-app.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/provision-app.py). Description basis: filename summary.

## tools/rig-async-stage/test-asset-capture.mjs

Test fixture/check: test asset capture. Inspect the source before use.

Source: [`tools/rig-async-stage/test-asset-capture.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/test-asset-capture.mjs). Description basis: filename summary.

## tools/rig-async-stage/test-game-worker.mjs

Test fixture/check: test game worker. Inspect the source before use.

Source: [`tools/rig-async-stage/test-game-worker.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/test-game-worker.mjs). Description basis: filename summary.

## tools/rig-async-stage/test-rig-native.mjs

Test fixture/check: test rig native. Inspect the source before use.

Source: [`tools/rig-async-stage/test-rig-native.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/test-rig-native.mjs). Description basis: filename summary.

## tools/rig-async-stage/test-worker-request-integrity.mjs

Test fixture/check: test worker request integrity. Inspect the source before use.

Source: [`tools/rig-async-stage/test-worker-request-integrity.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/test-worker-request-integrity.mjs). Description basis: filename summary.

## tools/rig-async-stage/test_completion_outbox.py

Test fixture/check: test completion outbox. Inspect the source before use.

Source: [`tools/rig-async-stage/test_completion_outbox.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/test_completion_outbox.py). Description basis: filename summary.

## tools/rig-async-stage/unreal-lane/Install-UnrealWorker.ps1

Source component: Install UnrealWorker. Inspect the source before use.

Source: [`tools/rig-async-stage/unreal-lane/Install-UnrealWorker.ps1`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/unreal-lane/Install-UnrealWorker.ps1). Description basis: filename summary.

## tools/rig-async-stage/unreal-lane/build_lane.py

Build the self-contained bundle to copy to the rig: python3 build\_lane.py \<output dir\> Gathers the lane's sources, the in-engine scripts \(single source of truth: the watoom-metahuman skill\) and the two helpers it reuses from the existing RI

Source: [`tools/rig-async-stage/unreal-lane/build_lane.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/unreal-lane/build_lane.py). Description basis: module docstring.

## tools/rig-async-stage/unreal-lane/test_unreal_lane.py

Test fixture/check: test unreal lane. Inspect the source before use.

Source: [`tools/rig-async-stage/unreal-lane/test_unreal_lane.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/unreal-lane/test_unreal_lane.py). Description basis: filename summary.

## tools/rig-async-stage/unreal-lane/worker-source/pin_unreal.py

Run ON THE RIG once after installing Unreal \(and again after any engine/plugin update\): records what the lane is allowed to run. Writes unreal-runtime-provenance.json next to this file: engine version \+ SHA-256 of the editor executables \+ t

Source: [`tools/rig-async-stage/unreal-lane/worker-source/pin_unreal.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/unreal-lane/worker-source/pin_unreal.py). Description basis: module docstring.

Declared CLI options: `--ue-root`.

## tools/rig-async-stage/unreal-lane/worker-source/unreal_job.py

Windows Job Object with a CONFIGURABLE memory limit for the Unreal lane \(windows\_job.run is fixed at 8 GiB for Blender/Godot\). Start suspended, assign limits, resume; the whole process tree dies with the job \(kill-on-close\).

Source: [`tools/rig-async-stage/unreal-lane/worker-source/unreal_job.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/unreal-lane/worker-source/unreal_job.py). Description basis: module docstring.

## tools/rig-async-stage/unreal-lane/worker-source/unreal_lane.py

Shared contract of the rig's Unreal lane \(used unchanged by the homelab CLI and the Windows worker\).

Source: [`tools/rig-async-stage/unreal-lane/worker-source/unreal_lane.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/unreal-lane/worker-source/unreal_lane.py). Description basis: module docstring.

## tools/rig-async-stage/unreal-lane/worker-source/unreal_runner.py

Executes ONE fixed Unreal operation inside a Windows Job Object. Invoked by unreal\_worker.py as: python unreal\_runner.py \<plan.json\>. The plan comes from the worker \(never from the manifest directly\): the script is the hash-pinned file ship

Source: [`tools/rig-async-stage/unreal-lane/worker-source/unreal_runner.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/unreal-lane/worker-source/unreal_runner.py). Description basis: module docstring.

## tools/rig-async-stage/unreal-lane/worker-source/unreal_worker.py

Rig-side poller for the Unreal lane. Outbound only: it pulls jobs from, and uploads results to, the homelab's transfer-only SFTP jail. One job at a time; a job that was running when the worker died is NEVER replayed \(it is reported as faile

Source: [`tools/rig-async-stage/unreal-lane/worker-source/unreal_worker.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/unreal-lane/worker-source/unreal_worker.py). Description basis: module docstring.

Declared CLI options: `--config`, `--once`.

## tools/rig-async-stage/update-guard.py

Scoped isolated application guard update, with native idle fence and rollback.

Source: [`tools/rig-async-stage/update-guard.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/update-guard.py). Description basis: module docstring.

## tools/rig-async-stage/worker-source/Install-StageWorker.ps1

Source component: Install StageWorker. Inspect the source before use.

Source: [`tools/rig-async-stage/worker-source/Install-StageWorker.ps1`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/Install-StageWorker.ps1). Description basis: filename summary.

## tools/rig-async-stage/worker-source/Rig-Jobs.ps1

Source component: Rig Jobs. Inspect the source before use.

Source: [`tools/rig-async-stage/worker-source/Rig-Jobs.ps1`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/Rig-Jobs.ps1). Description basis: filename summary.

## tools/rig-async-stage/worker-source/activate.py

Scoped RIG capture activation using the existing native release fence.

Source: [`tools/rig-async-stage/worker-source/activate.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/activate.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--i-approve`, `--iac-root`, `--previous`.

## tools/rig-async-stage/worker-source/animation_sampling.py

Source component: animation sampling. Inspect the source before use.

Source: [`tools/rig-async-stage/worker-source/animation_sampling.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/animation_sampling.py). Description basis: filename summary.

## tools/rig-async-stage/worker-source/asset_capture_contract.py

Declarative asset capture contract shared by the operator and tests.

Source: [`tools/rig-async-stage/worker-source/asset_capture_contract.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/asset_capture_contract.py). Description basis: module docstring.

## tools/rig-async-stage/worker-source/broker.py

Restricted staging spool; stdin JSON over a forced-command SSH key.

Source: [`tools/rig-async-stage/worker-source/broker.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/broker.py). Description basis: module docstring.

Declared CLI options: `--admit-game-native`, `--admit-native`, `--cancel-native`, `--project`, `--root`, `--scan`, `--worker`.

## tools/rig-async-stage/worker-source/build_runtime.py

Build a pinned Windows adapter from the exact maintained server implementation.

Source: [`tools/rig-async-stage/worker-source/build_runtime.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/build_runtime.py). Description basis: module docstring.

Declared CLI options: `--iac-root`, `--output`.

## tools/rig-async-stage/worker-source/completion_outbox.py

Durable, idempotent synthetic completion delivery; never interrupts an active turn.

Source: [`tools/rig-async-stage/worker-source/completion_outbox.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/completion_outbox.py). Description basis: module docstring.

## tools/rig-async-stage/worker-source/game_contract.py

Fixed staged Godot operations, independent of Blender capture schemas.

Source: [`tools/rig-async-stage/worker-source/game_contract.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/game_contract.py). Description basis: module docstring.

## tools/rig-async-stage/worker-source/game_runner.py

Fixed Godot operations inside the inherited Windows Job Object; source is a copy.

Source: [`tools/rig-async-stage/worker-source/game_runner.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/game_runner.py). Description basis: module docstring.

## tools/rig-async-stage/worker-source/game_worker.py

Separate staged Godot consumer sharing the RIG's single leased execution slot.

Source: [`tools/rig-async-stage/worker-source/game_worker.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/game_worker.py). Description basis: module docstring.

Declared CLI options: `--config`, `--once`.

## tools/rig-async-stage/worker-source/input_snapshot.py

Socket-activated root reader for authorized asset snapshots; never executes input.

Source: [`tools/rig-async-stage/worker-source/input_snapshot.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/input_snapshot.py). Description basis: module docstring.

## tools/rig-async-stage/worker-source/native_bridge.py

Root-side native capture adapter. Admission proof stays in the original bridge.

Source: [`tools/rig-async-stage/worker-source/native_bridge.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/native_bridge.py). Description basis: module docstring.

## tools/rig-async-stage/worker-source/package_inputs.py

Bounded input snapshots shared by staging and native-authorized admissions.

Source: [`tools/rig-async-stage/worker-source/package_inputs.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/package_inputs.py). Description basis: module docstring.

## tools/rig-async-stage/worker-source/pause_control.py

Source component: pause control. Inspect the source before use.

Source: [`tools/rig-async-stage/worker-source/pause_control.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/pause_control.py). Description basis: filename summary.

## tools/rig-async-stage/worker-source/portable_inputs.py

Load a source snapshot with explicitly transferred and remapped dependencies.

Source: [`tools/rig-async-stage/worker-source/portable_inputs.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/portable_inputs.py). Description basis: module docstring.

## tools/rig-async-stage/worker-source/portable_package.py

Create a derived glTF copy with local dependency URIs, preserving snapshots.

Source: [`tools/rig-async-stage/worker-source/portable_package.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/portable_package.py). Description basis: module docstring.

## tools/rig-async-stage/worker-source/pose_preparation_contract.py

Fixed pose payload contract; no script paths or executable input.

Source: [`tools/rig-async-stage/worker-source/pose_preparation_contract.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/pose_preparation_contract.py). Description basis: module docstring.

## tools/rig-async-stage/worker-source/pose_preparation_worker.py

Fixed installed pose helper adapter; called only inside the capture cgroup.

Source: [`tools/rig-async-stage/worker-source/pose_preparation_worker.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/pose_preparation_worker.py). Description basis: module docstring.

## tools/rig-async-stage/worker-source/rig_pose_contract.py

Pure schema for the fixed Shadowheart MHX adapter; no executable fields.

Source: [`tools/rig-async-stage/worker-source/rig_pose_contract.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/rig_pose_contract.py). Description basis: module docstring.

## tools/rig-async-stage/worker-source/runtime_helpers/ansible/roles/watoom-code/files/skills/human-pose-agent/scripts/auto_ik_validation.py

Asset-aware Blender IK and geometric validation extension.

Source: [`tools/rig-async-stage/worker-source/runtime_helpers/ansible/roles/watoom-code/files/skills/human-pose-agent/scripts/auto_ik_validation.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/runtime_helpers/ansible/roles/watoom-code/files/skills/human-pose-agent/scripts/auto_ik_validation.py). Description basis: module docstring.

## tools/rig-async-stage/worker-source/runtime_helpers/ansible/roles/watoom-code/files/skills/human-pose-agent/scripts/human_pose_agent.py

WatooM Human Pose Asset Inspector and Safe Pose Executor.

Source: [`tools/rig-async-stage/worker-source/runtime_helpers/ansible/roles/watoom-code/files/skills/human-pose-agent/scripts/human_pose_agent.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/runtime_helpers/ansible/roles/watoom-code/files/skills/human-pose-agent/scripts/human_pose_agent.py). Description basis: module docstring.

Declared CLI options: `--auto-plan`, `--output`, `--recipe`, `--report`, `--validation-report`.

## tools/rig-async-stage/worker-source/runtime_helpers/ansible/roles/watoom-code/files/skills/human-pose-agent/scripts/prepare_pose.py

WatooM builder-stage entry; run inside the pinned Blender, never as a shell command.

Source: [`tools/rig-async-stage/worker-source/runtime_helpers/ansible/roles/watoom-code/files/skills/human-pose-agent/scripts/prepare_pose.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/runtime_helpers/ansible/roles/watoom-code/files/skills/human-pose-agent/scripts/prepare_pose.py). Description basis: module docstring.

Declared CLI options: `--mode`, `--output`, `--plan`, `--report`, `--revision`, `--validation`.

## tools/rig-async-stage/worker-source/runtime_helpers/ansible/roles/watoom-code/files/skills/human-pose-agent/scripts/rig_adapter.py

Fixed, fingerprinted MHX control adapter. Run only in the admitted Blender worker.

Source: [`tools/rig-async-stage/worker-source/runtime_helpers/ansible/roles/watoom-code/files/skills/human-pose-agent/scripts/rig_adapter.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/runtime_helpers/ansible/roles/watoom-code/files/skills/human-pose-agent/scripts/rig_adapter.py). Description basis: module docstring.

## tools/rig-async-stage/worker-source/runtime_helpers/tools/ts4-animation/codec.py

Bounded TS4 CLIP wrapper v14 / \_pilC3S\_ v2 channel codec. Format evidence: staged s4animtools serialization/channel/frame implementations. Independent implementation; no addon imports or third-party runtime dependency.

Source: [`tools/rig-async-stage/worker-source/runtime_helpers/tools/ts4-animation/codec.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/runtime_helpers/tools/ts4-animation/codec.py). Description basis: module docstring.

## tools/rig-async-stage/worker-source/runtime_helpers/tools/ts4-animation/dbpf.py

Independent bounded DBPF container implementation; no typed TS4 codecs. Format evidence: Kuree/Sims4Tools wiki DBPF-Format and thequux/s4py reader. Only 2.0/2.1, index v3, shared T/G/instance-high and optional compression tails. Unknown com

Source: [`tools/rig-async-stage/worker-source/runtime_helpers/tools/ts4-animation/dbpf.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/runtime_helpers/tools/ts4-animation/dbpf.py). Description basis: module docstring.

## tools/rig-async-stage/worker-source/runtime_helpers/tools/ts4-animation/retarget_blender.py

Fixed TS4 parent-local Action importer / MHX rest-space rotation retargeter.

Source: [`tools/rig-async-stage/worker-source/runtime_helpers/tools/ts4-animation/retarget_blender.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/runtime_helpers/tools/ts4-animation/retarget_blender.py). Description basis: module docstring.

## tools/rig-async-stage/worker-source/runtime_helpers/tools/ts4-animation/retarget_contract.py

Source component: retarget contract. Inspect the source before use.

Source: [`tools/rig-async-stage/worker-source/runtime_helpers/tools/ts4-animation/retarget_contract.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/runtime_helpers/tools/ts4-animation/retarget_contract.py). Description basis: filename summary.

## tools/rig-async-stage/worker-source/runtime_helpers/tools/ts4-animation/test_codec.py

Test fixture/check: test codec. Inspect the source before use.

Source: [`tools/rig-async-stage/worker-source/runtime_helpers/tools/ts4-animation/test_codec.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/runtime_helpers/tools/ts4-animation/test_codec.py). Description basis: filename summary.

## tools/rig-async-stage/worker-source/runtime_helpers/tools/ts4-animation/test_retarget_contract.py

Test fixture/check: test retarget contract. Inspect the source before use.

Source: [`tools/rig-async-stage/worker-source/runtime_helpers/tools/ts4-animation/test_retarget_contract.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/runtime_helpers/tools/ts4-animation/test_retarget_contract.py). Description basis: filename summary.

## tools/rig-async-stage/worker-source/runtime_helpers/tools/ts4-animation/ts4_animation.py

Stdlib-only, fresh-output TS4 package extraction and bounded CLIP codec CLI.

Source: [`tools/rig-async-stage/worker-source/runtime_helpers/tools/ts4-animation/ts4_animation.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/runtime_helpers/tools/ts4-animation/ts4_animation.py). Description basis: module docstring.

Declared CLI options: `--decode-clips`, `--document`, `--output`, `--source`.

## tools/rig-async-stage/worker-source/runtime_helpers/tools/ts4-animation/verify_retarget_constraints_blender.py

Run in a bounded operator Blender unit; no source assets are loaded.

Source: [`tools/rig-async-stage/worker-source/runtime_helpers/tools/ts4-animation/verify_retarget_constraints_blender.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/runtime_helpers/tools/ts4-animation/verify_retarget_constraints_blender.py). Description basis: module docstring.

## tools/rig-async-stage/worker-source/shared_capture.py

Trusted Blender-side capture implementation; entered only inside the 4GiB unit.

Source: [`tools/rig-async-stage/worker-source/shared_capture.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/shared_capture.py). Description basis: module docstring.

## tools/rig-async-stage/worker-source/stage_renderer.py

Trusted Blender-side capture implementation; entered only inside the 4GiB unit.

Source: [`tools/rig-async-stage/worker-source/stage_renderer.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/stage_renderer.py). Description basis: module docstring.

## tools/rig-async-stage/worker-source/test_async_stage.py

Test fixture/check: test async stage. Inspect the source before use.

Source: [`tools/rig-async-stage/worker-source/test_async_stage.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/test_async_stage.py). Description basis: filename summary.

## tools/rig-async-stage/worker-source/test_broker.py

Test fixture/check: test broker. Inspect the source before use.

Source: [`tools/rig-async-stage/worker-source/test_broker.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/test_broker.py). Description basis: filename summary.

## tools/rig-async-stage/worker-source/windows_job.py

Windows Job Object boundary. Start suspended, assign limits, then resume.

Source: [`tools/rig-async-stage/worker-source/windows_job.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/windows_job.py). Description basis: module docstring.

## tools/rig-async-stage/worker-source/worker.py

One-slot outbound workstation stage worker; claims are never blindly replayed.

Source: [`tools/rig-async-stage/worker-source/worker.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-async-stage/worker-source/worker.py). Description basis: module docstring.

Declared CLI options: `--config`, `--once`.

## tools/rig-godot-mcp/Add-RigAuthorizedKey.ps1

Source component: Add RigAuthorizedKey. Inspect the source before use.

Source: [`tools/rig-godot-mcp/Add-RigAuthorizedKey.ps1`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-godot-mcp/Add-RigAuthorizedKey.ps1). Description basis: filename summary.

## tools/rig-godot-mcp/Setup-RigAccount.ps1

Source component: Setup RigAccount. Inspect the source before use.

Source: [`tools/rig-godot-mcp/Setup-RigAccount.ps1`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-godot-mcp/Setup-RigAccount.ps1). Description basis: filename summary.

## tools/rig-godot-mcp/fake-bridge-child.js

Source component: fake bridge child. Inspect the source before use.

Source: [`tools/rig-godot-mcp/fake-bridge-child.js`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-godot-mcp/fake-bridge-child.js). Description basis: filename summary.

## tools/rig-godot-mcp/godot-mcp-policy-wrapper.js

Source component: godot mcp policy wrapper. Inspect the source before use.

Source: [`tools/rig-godot-mcp/godot-mcp-policy-wrapper.js`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-godot-mcp/godot-mcp-policy-wrapper.js). Description basis: filename summary.

## tools/rig-godot-mcp/test-godot-mcp-policy-wrapper.js

Test fixture/check: test godot mcp policy wrapper. Inspect the source before use.

Source: [`tools/rig-godot-mcp/test-godot-mcp-policy-wrapper.js`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-godot-mcp/test-godot-mcp-policy-wrapper.js). Description basis: filename summary.

## tools/rig-godot-run/Run-GodotProject.ps1

Source component: Run GodotProject. Inspect the source before use.

Source: [`tools/rig-godot-run/Run-GodotProject.ps1`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-godot-run/Run-GodotProject.ps1). Description basis: filename summary.

## tools/rig-godot-viewer/Open-InGodot.ps1

Source component: Open InGodot. Inspect the source before use.

Source: [`tools/rig-godot-viewer/Open-InGodot.ps1`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-godot-viewer/Open-InGodot.ps1). Description basis: filename summary.

## tools/rig-godot-viewer/viewer/viewer.gd

Source component: viewer. Inspect the source before use.

Source: [`tools/rig-godot-viewer/viewer/viewer.gd`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-godot-viewer/viewer/viewer.gd). Description basis: filename summary.

## tools/rig-ue-mcp/Add-RigAuthorizedKey.ps1

Source component: Add RigAuthorizedKey. Inspect the source before use.

Source: [`tools/rig-ue-mcp/Add-RigAuthorizedKey.ps1`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/Add-RigAuthorizedKey.ps1). Description basis: filename summary.

## tools/rig-ue-mcp/Add-RigMaintenanceAccount.ps1

Source component: Add RigMaintenanceAccount. Inspect the source before use.

Source: [`tools/rig-ue-mcp/Add-RigMaintenanceAccount.ps1`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/Add-RigMaintenanceAccount.ps1). Description basis: filename summary.

## tools/rig-ue-mcp/Setup-RigAccount.ps1

Source component: Setup RigAccount. Inspect the source before use.

Source: [`tools/rig-ue-mcp/Setup-RigAccount.ps1`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/Setup-RigAccount.ps1). Description basis: filename summary.

## tools/rig-ue-mcp/fake-ue-mcp-child.js

Source component: fake ue mcp child. Inspect the source before use.

Source: [`tools/rig-ue-mcp/fake-ue-mcp-child.js`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/fake-ue-mcp-child.js). Description basis: filename summary.

## tools/rig-ue-mcp/heights_freshness.py

T-0055 item 3: a \`--heights\` png is only as good as the moment it was fetched; this gives tools a way to notice it is stale.

Source: [`tools/rig-ue-mcp/heights_freshness.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/heights_freshness.py). Description basis: module docstring.

## tools/rig-ue-mcp/rig_build_plugin.py

Build a C\+\+ code plugin for the rig project and \(optionally\) install it: the whole cycle of README "Building a C\+\+ code plugin".

Source: [`tools/rig-ue-mcp/rig_build_plugin.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/rig_build_plugin.py). Description basis: module docstring.

Declared CLI options: `--check-class`, `--check-prop`, `--install`, `--project-dir`, `--project-plugins`, `--reuse-build`, `--ue-mcp-version`.

## tools/rig-ue-mcp/rig_copy_pack.py

Copy downloaded Fab UE packs into the rig project's Content folder over scp \(the key-only \`migrate\` maintenance account, created on the rig with Add-RigMaintenanceAccount.ps1 -Admin; it has no expiry unless that was run with -Hours N, see R

Source: [`tools/rig-ue-mcp/rig_copy_pack.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/rig_copy_pack.py). Description basis: module docstring.

Declared CLI options: `--apply`, `--dest`, `--dry-run`, `--no-asset-check`, `--plugin`.

## tools/rig-ue-mcp/rig_import_fbx_character.py

Bring a rigged FBX character \(creature, NPC\) into the rig project: copy the files, import the skeletal mesh with its own skeleton, import its clips onto that skeleton.

Source: [`tools/rig-ue-mcp/rig_import_fbx_character.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/rig_import_fbx_character.py). Description basis: module docstring.

Declared CLI options: `--anim`, `--apply`, `--copy-only`, `--dest`, `--mesh`, `--name`, `--out`, `--scale`, `--static`, `--textures-from`.

## tools/rig-ue-mcp/rig_project_plugins.py

Keep the rig project's plugin switches \(the .uproject "Plugins" list\) as code: project\_plugins.json is the source of truth.

Source: [`tools/rig-ue-mcp/rig_project_plugins.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/rig_project_plugins.py). Description basis: module docstring.

Declared CLI options: `--apply`, `--spec`.

## tools/rig-ue-mcp/test-ue-mcp-policy-wrapper.js

Test fixture/check: test ue mcp policy wrapper. Inspect the source before use.

Source: [`tools/rig-ue-mcp/test-ue-mcp-policy-wrapper.js`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test-ue-mcp-policy-wrapper.js). Description basis: filename summary.

## tools/rig-ue-mcp/test_heights_freshness.py

Test fixture/check: test heights freshness. Inspect the source before use.

Source: [`tools/rig-ue-mcp/test_heights_freshness.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_heights_freshness.py). Description basis: filename summary.

## tools/rig-ue-mcp/test_rig_build_plugin.py

Test fixture/check: test rig build plugin. Inspect the source before use.

Source: [`tools/rig-ue-mcp/test_rig_build_plugin.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_rig_build_plugin.py). Description basis: filename summary.

## tools/rig-ue-mcp/test_rig_copy_pack.py

Test fixture/check: test rig copy pack. Inspect the source before use.

Source: [`tools/rig-ue-mcp/test_rig_copy_pack.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_rig_copy_pack.py). Description basis: filename summary.

## tools/rig-ue-mcp/test_rig_import_fbx_character.py

Test fixture/check: test rig import fbx character. Inspect the source before use.

Source: [`tools/rig-ue-mcp/test_rig_import_fbx_character.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_rig_import_fbx_character.py). Description basis: filename summary.

## tools/rig-ue-mcp/test_rig_project_plugins.py

Test fixture/check: test rig project plugins. Inspect the source before use.

Source: [`tools/rig-ue-mcp/test_rig_project_plugins.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_rig_project_plugins.py). Description basis: filename summary.

## tools/rig-ue-mcp/test_route_failures.py

A failed ue-mcp reply must stop the helpers before they save or build on it \(fake transport, no rig, no network\).

Source: [`tools/rig-ue-mcp/test_route_failures.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_route_failures.py). Description basis: module docstring.

## tools/rig-ue-mcp/test_ue_asset_check.py

ue\_asset\_check.py: every check on a small made-up tree \(no rig, no editor, no network\), and the gate in the three pipeline scripts.

Source: [`tools/rig-ue-mcp/test_ue_asset_check.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_ue_asset_check.py). Description basis: module docstring.

## tools/rig-ue-mcp/test_ue_asset_fix.py

ue\_asset\_fix.py: dry run by default, a new copy and a change log on --apply, the original never touched, unsafe repairs refused.

Source: [`tools/rig-ue-mcp/test_ue_asset_fix.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_ue_asset_fix.py). Description basis: module docstring.

## tools/rig-ue-mcp/test_ue_combat_check.py

Test fixture/check: test ue combat check. Inspect the source before use.

Source: [`tools/rig-ue-mcp/test_ue_combat_check.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_ue_combat_check.py). Description basis: filename summary.

## tools/rig-ue-mcp/test_ue_creek_foliage.py

Test fixture/check: test ue creek foliage. Inspect the source before use.

Source: [`tools/rig-ue-mcp/test_ue_creek_foliage.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_ue_creek_foliage.py). Description basis: filename summary.

## tools/rig-ue-mcp/test_ue_foliage_buried.py

Test fixture/check: test ue foliage buried. Inspect the source before use.

Source: [`tools/rig-ue-mcp/test_ue_foliage_buried.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_ue_foliage_buried.py). Description basis: filename summary.

## tools/rig-ue-mcp/test_ue_foliage_census.py

Test fixture/check: test ue foliage census. Inspect the source before use.

Source: [`tools/rig-ue-mcp/test_ue_foliage_census.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_ue_foliage_census.py). Description basis: filename summary.

## tools/rig-ue-mcp/test_ue_fx_check.py

Test fixture/check: test ue fx check. Inspect the source before use.

Source: [`tools/rig-ue-mcp/test_ue_fx_check.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_ue_fx_check.py). Description basis: filename summary.

## tools/rig-ue-mcp/test_ue_heights_fetch.py

Test fixture/check: test ue heights fetch. Inspect the source before use.

Source: [`tools/rig-ue-mcp/test_ue_heights_fetch.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_ue_heights_fetch.py). Description basis: filename summary.

## tools/rig-ue-mcp/test_ue_lake_as_river.py

Test fixture/check: test ue lake as river. Inspect the source before use.

Source: [`tools/rig-ue-mcp/test_ue_lake_as_river.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_ue_lake_as_river.py). Description basis: filename summary.

## tools/rig-ue-mcp/test_ue_lake_as_waterbody.py

Test fixture/check: test ue lake as waterbody. Inspect the source before use.

Source: [`tools/rig-ue-mcp/test_ue_lake_as_waterbody.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_ue_lake_as_waterbody.py). Description basis: filename summary.

## tools/rig-ue-mcp/test_ue_lake_check.py

Test fixture/check: test ue lake check. Inspect the source before use.

Source: [`tools/rig-ue-mcp/test_ue_lake_check.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_ue_lake_check.py). Description basis: filename summary.

## tools/rig-ue-mcp/test_ue_look_check.py

Test fixture/check: test ue look check. Inspect the source before use.

Source: [`tools/rig-ue-mcp/test_ue_look_check.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_ue_look_check.py). Description basis: filename summary.

## tools/rig-ue-mcp/test_ue_look_probe.py

Test fixture/check: test ue look probe. Inspect the source before use.

Source: [`tools/rig-ue-mcp/test_ue_look_probe.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_ue_look_probe.py). Description basis: filename summary.

## tools/rig-ue-mcp/test_ue_mesh_body.py

Test fixture/check: test ue mesh body. Inspect the source before use.

Source: [`tools/rig-ue-mcp/test_ue_mesh_body.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_ue_mesh_body.py). Description basis: filename summary.

## tools/rig-ue-mcp/test_ue_place_assets.py

Test fixture/check: test ue place assets. Inspect the source before use.

Source: [`tools/rig-ue-mcp/test_ue_place_assets.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_ue_place_assets.py). Description basis: filename summary.

## tools/rig-ue-mcp/test_ue_roam_check.py

Test fixture/check: test ue roam check. Inspect the source before use.

Source: [`tools/rig-ue-mcp/test_ue_roam_check.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_ue_roam_check.py). Description basis: filename summary.

## tools/rig-ue-mcp/test_ue_route.py

Test fixture/check: test ue route. Inspect the source before use.

Source: [`tools/rig-ue-mcp/test_ue_route.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_ue_route.py). Description basis: filename summary.

## tools/rig-ue-mcp/test_ue_stray_check.py

Test fixture/check: test ue stray check. Inspect the source before use.

Source: [`tools/rig-ue-mcp/test_ue_stray_check.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_ue_stray_check.py). Description basis: filename summary.

Declared CLI options: `--underground-prefixes`.

## tools/rig-ue-mcp/test_ue_viewport_shot.py

ue\_viewport\_shot.capture with a fake route session and a fake scp runner \(no rig, no network\).

Source: [`tools/rig-ue-mcp/test_ue_viewport_shot.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_ue_viewport_shot.py). Description basis: module docstring.

## tools/rig-ue-mcp/test_ue_village_build.py

Test fixture/check: test ue village build. Inspect the source before use.

Source: [`tools/rig-ue-mcp/test_ue_village_build.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_ue_village_build.py). Description basis: filename summary.

## tools/rig-ue-mcp/test_ue_water_fetch.py

Test fixture/check: test ue water fetch. Inspect the source before use.

Source: [`tools/rig-ue-mcp/test_ue_water_fetch.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/test_ue_water_fetch.py). Description basis: filename summary.

## tools/rig-ue-mcp/ue-mcp-policy-wrapper.js

Source component: ue mcp policy wrapper. Inspect the source before use.

Source: [`tools/rig-ue-mcp/ue-mcp-policy-wrapper.js`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/ue-mcp-policy-wrapper.js). Description basis: filename summary.

## tools/rig-ue-mcp/ue_asset_check.py

Check assets before they enter the Unreal pipeline: read-only, offline, no rig and no editor \(stdlib only\).

Source: [`tools/rig-ue-mcp/ue_asset_check.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/ue_asset_check.py). Description basis: module docstring.

Declared CLI options: `--dest`, `--heights`, `--layout`, `--manifest`, `--mesh-dir`, `--pack`, `--report`, `--size-m`, `--sources`, `--strict`.

## tools/rig-ue-mcp/ue_asset_fix.py

Repair what ue\_asset\_check.py marks \`fixable\`, in a COPY: the original is never written to \(stdlib only, offline, no rig\).

Source: [`tools/rig-ue-mcp/ue_asset_fix.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/ue_asset_fix.py). Description basis: module docstring.

Declared CLI options: `--apply`, `--dest`, `--dry-run`, `--out`.

## tools/rig-ue-mcp/ue_combat_check.py

Live combat check in PIE for a slice made by unreal\_combat.py: melee, spells, pickups, and \(--net\) client authority \+ teams.

Source: [`tools/rig-ue-mcp/ue_combat_check.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/ue_combat_check.py). Description basis: module docstring.

Declared CLI options: `--from-calls`, `--keep-pie`, `--key-dir`, `--net`, `--no-warmup`.

## tools/rig-ue-mcp/ue_creek_foliage.py

Refit foliage to a carved creek through the ue-mcp route \(driver for scripts/unreal\_creek\_foliage\_fit.py in the watoom-texture-layering skill\).

Source: [`tools/rig-ue-mcp/ue_creek_foliage.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/ue_creek_foliage.py). Description basis: module docstring.

Declared CLI options: `--add-batch`, `--apply`, `--host`, `--keep-depth-cm`, `--key-dir`, `--lake`, `--lake-rim-m`, `--new-heights`, `--out-removed`, `--port`, `--raw-per-cm`, `--reach-m`, `--size-m`, `--spline`, `--user`, `--z0`.

## tools/rig-ue-mcp/ue_foliage_buried.py

Find \(and with --apply remove\) foliage instances sunk into the ground, so they stop costing render time.

Source: [`tools/rig-ue-mcp/ue_foliage_buried.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/ue_foliage_buried.py). Description basis: module docstring.

Declared CLI options: `--apply`, `--edge-connected-sea`, `--heights`, `--host`, `--in-sea`, `--key-dir`, `--landscape`, `--out-removed`, `--port`, `--raw-per-cm`, `--sea-cm`, `--sea-margin-cm`, `--sink-cm`, `--size-m`, `--skip-freshness-check`, `--types`, `--user`, `--z0`.

## tools/rig-ue-mcp/ue_foliage_census.py

Census of the foliage in the live level, grouped by plant family, with where each family actually stands.

Source: [`tools/rig-ue-mcp/ue_foliage_census.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/ue_foliage_census.py). Description basis: module docstring.

Declared CLI options: `--catalog`, `--heights`, `--host`, `--key-dir`, `--out`, `--port`, `--raw-per-cm`, `--sea-cm`, `--size-m`, `--user`, `--water-mask`, `--z0`.

## tools/rig-ue-mcp/ue_fx_check.py

Check Niagara systems made by unreal\_niagara\_fx.py \(or any calls file with niagara.create\_system\_from\_spec\) on the rig.

Source: [`tools/rig-ue-mcp/ue_fx_check.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/ue_fx_check.py). Description basis: module docstring.

Declared CLI options: `--at`, `--from-calls`, `--keep`, `--key-dir`.

## tools/rig-ue-mcp/ue_ground_fetch.py

Read the live landscape layer weights \(grass, dry\_grass, dirt, mud, rock\) into an npz for unreal\_ground\_paint.py plan.

Source: [`tools/rig-ue-mcp/ue_ground_fetch.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/ue_ground_fetch.py). Description basis: module docstring.

Declared CLI options: `--landscape`, `--out`, `--size`, `--tile`.

## tools/rig-ue-mcp/ue_heights_fetch.py

Read the live landscape heights into a 16-bit PNG \(the \`--heights\` input of every unreal\_\*.py helper\). Host-side; numpy \+ pillow.

Source: [`tools/rig-ue-mcp/ue_heights_fetch.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/ue_heights_fetch.py). Description basis: module docstring.

Declared CLI options: `--landscape`, `--out`, `--size`, `--tile`.

## tools/rig-ue-mcp/ue_lake_as_river.py

Shared lake library: the landscape carve and spline helpers that ue\_lake\_as\_waterbody.py and ue\_lake\_check.py import.

Source: [`tools/rig-ue-mcp/ue_lake_as_river.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/ue_lake_as_river.py). Description basis: module docstring.

Declared CLI options: `--bank-cm`, `--center-x`, `--center-y`, `--delete-old`, `--depth-cm`, `--host`, `--i-know-this-floods`, `--key-dir`, `--label`, `--landscape`, `--material`, `--no-carve`, `--old-label`, `--out-revert`, `--points`, `--port`, `--px-cm`, `--radius-cm`, `--submerge-cm`, `--user`, `--water-z`, `--width-cm`.

## tools/rig-ue-mcp/ue_lake_as_waterbody.py

Turn a round lake into a native \`WaterBodyLake\` \(driver, not a skill script\).

Source: [`tools/rig-ue-mcp/ue_lake_as_waterbody.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/ue_lake_as_waterbody.py). Description basis: module docstring.

Declared CLI options: `--bank-cm`, `--carve-only`, `--center-x`, `--center-y`, `--clear-water-first`, `--delete-old`, `--depth-cm`, `--host`, `--key-dir`, `--label`, `--landscape`, `--material`, `--materials-only`, `--no-carve`, `--old-label`, `--out-revert`, `--points`, `--port`, `--px-cm`, `--radius-cm`, `--recreate`, `--submerge-cm`, `--user`, `--water-z`.

## tools/rig-ue-mcp/ue_lake_check.py

Read-only health check of a carved lake's landscape bed \(driver, stdlib only\). Run it after every lake carve, clear or recovery.

Source: [`tools/rig-ue-mcp/ue_lake_check.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/ue_lake_check.py). Description basis: module docstring.

Declared CLI options: `--bank-cm`, `--host`, `--json`, `--key-dir`, `--lake`, `--lakes`, `--landscape`, `--max-depth-cm`, `--pad`, `--port`, `--px-cm`, `--seam-cm`, `--user`.

## tools/rig-ue-mcp/ue_look_check.py

Check the level's look settings against the recipe that worked \(read-only; exits 1 on any drift\).

Source: [`tools/rig-ue-mcp/ue_look_check.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/ue_look_check.py). Description basis: module docstring.

Declared CLI options: `--checks`, `--from-calls`, `--host`, `--key-dir`, `--level-path`, `--port`, `--user`.

## tools/rig-ue-mcp/ue_look_probe.py

Measure how bright a level looks from several horizon views, optionally for several locked exposure values \(any game\).

Source: [`tools/rig-ue-mcp/ue_look_probe.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/ue_look_probe.py). Description basis: module docstring.

Declared CLI options: `--at`, `--host`, `--key-dir`, `--out-dir`, `--pitch`, `--port`, `--post-process`, `--sweep-exposure`, `--target`, `--user`, `--yaws`.

## tools/rig-ue-mcp/ue_mesh_body.py

Measure how any skeletal mesh must sit in a Character: facing, capsule size and mesh offset \(biped, quadruped, dragon, ...\).

Source: [`tools/rig-ue-mcp/ue_mesh_body.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/ue_mesh_body.py). Description basis: module docstring.

Declared CLI options: `--host`, `--key-dir`, `--out`, `--port`, `--radius-margin`, `--user`.

## tools/rig-ue-mcp/ue_place_assets.py

Place imported meshes in the level from a manifest, sit them on the ground, clear trees under them, save \(ue-mcp route; stdlib \+ numpy \+ pillow\).

Source: [`tools/rig-ue-mcp/ue_place_assets.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/ue_place_assets.py). Description basis: module docstring.

Declared CLI options: `--dry-run`, `--force-save`, `--heights`, `--host`, `--key-dir`, `--no-save`, `--port`, `--raw-per-cm`, `--size-m`, `--user`, `--z0`.

## tools/rig-ue-mcp/ue_place_river.py

Create a \`WaterBodyRiver\` from a spline through the ue-mcp route \(driver for scripts/unreal\_creek\_river.py in the watoom-texture-layering skill\).

Source: [`tools/rig-ue-mcp/ue_place_river.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/ue_place_river.py). Description basis: module docstring.

Declared CLI options: `--depth-cm`, `--hide-prefix`, `--host`, `--key-dir`, `--label`, `--material`, `--points`, `--port`, `--spline-text`, `--user`, `--width-cm`.

## tools/rig-ue-mcp/ue_roam_check.py

Live check in PIE that the wandering creatures of a spec really roam and animate \(unreal\_combat.py calls file\).

Source: [`tools/rig-ue-mcp/ue_roam_check.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/ue_roam_check.py). Description basis: module docstring.

Declared CLI options: `--below`, `--every`, `--from-calls`, `--keep-pie`, `--key-dir`, `--labels`, `--limb-bones`, `--root-bones`, `--samples`.

## tools/rig-ue-mcp/ue_route.py

Call the rig's Unreal editor through the restricted ue-mcp SSH route, and start the editor first when it is not running \(stdlib only\).

Source: [`tools/rig-ue-mcp/ue_route.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/ue_route.py). Description basis: module docstring.

Declared CLI options: `--host`, `--key-dir`, `--max-wait`, `--port`, `--user`.

## tools/rig-ue-mcp/ue_run_phases.py

Run the phases of a helper's calls json \(unreal\_coast.py, unreal\_creek\_profile.py, unreal\_ocean\_depth.py ...\) through the ue-mcp route.

Source: [`tools/rig-ue-mcp/ue_run_phases.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/ue_run_phases.py). Description basis: module docstring.

Declared CLI options: `--dry-run`, `--host`, `--key-dir`, `--max-load`, `--no-water-compensation`, `--phase`, `--port`, `--start`, `--user`.

## tools/rig-ue-mcp/ue_stray_check.py

Find foliage and placed mesh actors that ended up somewhere wrong: in the sky, under the sea, under the ground or off the map.

Source: [`tools/rig-ue-mcp/ue_stray_check.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/ue_stray_check.py). Description basis: module docstring.

Declared CLI options: `--apply`, `--classes`, `--float-cm`, `--heights`, `--host`, `--inland-low`, `--key-dir`, `--landscape`, `--max-rows`, `--no-actors`, `--no-foliage`, `--out-removed`, `--port`, `--raw-per-cm`, `--sea-cm`, `--sea-margin-cm`, `--seat-cm`, `--sink-cm`, `--size-m`, `--skip-freshness-check`, `--skip-prefixes`, `--types`, `--underground-prefixes`, `--user`, `--z0`.

## tools/rig-ue-mcp/ue_viewport_shot.py

Capture the real editor viewport on the rig and pull the PNG back.

Source: [`tools/rig-ue-mcp/ue_viewport_shot.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/ue_viewport_shot.py). Description basis: module docstring.

Declared CLI options: `--around`, `--camera`, `--key`, `--rig-dir`.

## tools/rig-ue-mcp/ue_village_build.py

Build the village from a unreal\_village.py layout: clear foliage on the pad, move the existing village actors, add the new pieces as foliage instances.

Source: [`tools/rig-ue-mcp/ue_village_build.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/ue_village_build.py). Description basis: module docstring.

Declared CLI options: `--apply`, `--clear-m`, `--force-save`, `--host`, `--key-dir`, `--mesh-dir`, `--new-heights`, `--old-heights`, `--port`, `--raw-per-cm`, `--size-m`, `--type-dir`, `--user`, `--z0`.

## tools/rig-ue-mcp/ue_water_fetch.py

Read every water body in the open level into one json \(read-only; the \`--water\` input of unreal\_water\_berms.py\).

Source: [`tools/rig-ue-mcp/ue_water_fetch.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-ue-mcp/ue_water_fetch.py). Description basis: module docstring.

Declared CLI options: `--host`, `--key-dir`, `--out`, `--port`, `--user`.

## tools/rig-unreal-mcp/Start-NwiroTunnel.ps1

Source component: Start NwiroTunnel. Inspect the source before use.

Source: [`tools/rig-unreal-mcp/Start-NwiroTunnel.ps1`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-unreal-mcp/Start-NwiroTunnel.ps1). Description basis: filename summary.

## tools/rig-unreal-mcp/mcp_proxy.py

Authenticated, tool-filtering proxy in front of an Unreal MCP endpoint reached through a reverse SSH tunnel.

Source: [`tools/rig-unreal-mcp/mcp_proxy.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-unreal-mcp/mcp_proxy.py). Description basis: module docstring.

Declared CLI options: `--listen`, `--policy-file`, `--port`, `--token-file`, `--upstream`.

## tools/rig-unreal-mcp/test_mcp_proxy.py

Test fixture/check: test mcp proxy. Inspect the source before use.

Source: [`tools/rig-unreal-mcp/test_mcp_proxy.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/rig-unreal-mcp/test_mcp_proxy.py). Description basis: filename summary.

## tools/set-domain.py

Point this checkout at your own domain, network and GitHub account.

Source: [`tools/set-domain.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/set-domain.py). Description basis: module docstring.

Declared CLI options: `--agent-domain`, `--agent-name`, `--dmz-address`, `--domain`, `--dry-run`, `--github-owner`, `--host-name`, `--pod-subnet`, `--rig-user`, `--subnet`, `--svc-subnet`.

## tools/set-paths.py

Point this checkout at your own disks.

Source: [`tools/set-paths.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/set-paths.py). Description basis: module docstring.

Declared CLI options: `--app-root`, `--data-root`, `--dry-run`, `--repo-root`.

## tools/skill-editor/broker.py

Root-only skill broker: SKILL.md text edits become single-path Git commits, then live copies.

Source: [`tools/skill-editor/broker.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/skill-editor/broker.py). Description basis: module docstring.

Declared CLI options: `--config`.

## tools/skill-editor/server.py

Authenticated Glance skill editor UI. No Git or filesystem write access: all work goes via the root broker.

Source: [`tools/skill-editor/server.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/skill-editor/server.py). Description basis: module docstring.

Declared CLI options: `--listen`, `--port`, `--prefix`.

## tools/skill-editor/test_skill_editor.py

Test fixture/check: test skill editor. Inspect the source before use.

Source: [`tools/skill-editor/test_skill_editor.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/skill-editor/test_skill_editor.py). Description basis: filename summary.

## tools/skill-editor/web/app.js

Source component: app. Inspect the source before use.

Source: [`tools/skill-editor/web/app.js`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/skill-editor/web/app.js). Description basis: filename summary.

## tools/tickets/board/broker.py

Root ticket-board broker \(stdlib only\): every board read and write goes through ticket.py.

Source: [`tools/tickets/board/broker.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/tickets/board/broker.py). Description basis: module docstring.

Declared CLI options: `--config`.

## tools/tickets/board/server.py

Tickets board UI pod \(stdlib only\). No access to the ticket store or the Discord webhooks: every operation goes to the root broker over a Unix socket \(same split as tools/skill-editor\).

Source: [`tools/tickets/board/server.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/tickets/board/server.py). Description basis: module docstring.

Declared CLI options: `--listen`, `--owner-id`, `--port`, `--prefix`, `--tokens-file`.

## tools/tickets/board/test_board.py

Tickets board tests \(stdlib unittest, same style as tools/skill-editor/test\_skill\_editor.py\). Run from tools/tickets/board: python3 -m unittest test\_board

Source: [`tools/tickets/board/test_board.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/tickets/board/test_board.py). Description basis: module docstring.

## tools/tickets/board/web/app.js

Source component: app. Inspect the source before use.

Source: [`tools/tickets/board/web/app.js`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/tickets/board/web/app.js). Description basis: filename summary.

## tools/tickets/test_ticket.py

Test fixture/check: test ticket. Inspect the source before use.

Source: [`tools/tickets/test_ticket.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/tickets/test_ticket.py). Description basis: filename summary.

## tools/tickets/ticket.py

WatooM to-do tickets with Discord notifications \(stdlib only\).

Source: [`tools/tickets/ticket.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/tickets/ticket.py). Description basis: module docstring.

Declared CLI options: `--all`, `--blocked`, `--body`, `--by`, `--lane`, `--note`, `--pr`, `--priority`, `--project`, `--queue`, `--shared`, `--skip`, `--status`, `--unblocked`.

## tools/unreal/accept-dungeon-worker.py

Verify one completed isolated native worker's receipts and published artifacts.

Source: [`tools/unreal/accept-dungeon-worker.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/accept-dungeon-worker.py). Description basis: module docstring.

Declared CLI options: `--name`, `--visual-reviewed`.

## tools/unreal/accept-render.py

Temporarily claim idle GPU through the existing controller for bounded editor acceptance.

Source: [`tools/unreal/accept-render.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/accept-render.py). Description basis: module docstring.

Declared CLI options: `--detach`, `--dungeon-export`, `--evidence`.

## tools/unreal/backfill-crash-symbols.py

Restartable serial backfill of exact dummy symbols in the accepted overlay only.

Source: [`tools/unreal/backfill-crash-symbols.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/backfill-crash-symbols.py). Description basis: module docstring.

Declared CLI options: `--baseline-root`, `--budget-hours`, `--capacity-status`, `--evidence`, `--selection`.

## tools/unreal/check-crash-symbols.py

Generate one isolated Breakpad/UE symbol artifact without modifying/rebuilding the engine.

Source: [`tools/unreal/check-crash-symbols.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/check-crash-symbols.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--install-placeholder`, `--memory-gib`, `--module`, `--replace-stale-from`, `--seconds`.

## tools/unreal/continue-acceptance.py

Run the prepared isolated C\+\+ fixture and runtime commandlet, without a full engine rebuild.

Source: [`tools/unreal/continue-acceptance.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/continue-acceptance.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/unreal/continue-build.py

One detached coordinator; resume bounded owned build phases, stop on any real fault.

Source: [`tools/unreal/continue-build.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/continue-build.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--max-hours`.

## tools/unreal/continue-render.py

Continue one existing dependency build through isolated render and Godot technical gates.

Source: [`tools/unreal/continue-render.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/continue-render.py). Description basis: module docstring.

Declared CLI options: `--compile-pid`, `--evidence`, `--resume`.

## tools/unreal/dungeon-api-probe.py

Probe actual non-commandlet editor navigation and authored pack blueprints, without GPU.

Source: [`tools/unreal/dungeon-api-probe.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/dungeon-api-probe.py). Description basis: module docstring.

## tools/unreal/dungeon-export-probe.py

Bake selected verified pack modules with the real Vulkan GLTFExporter. Paid sources remain read-only. Generated portable derivatives stay in the private library.

Source: [`tools/unreal/dungeon-export-probe.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/dungeon-export-probe.py). Description basis: module docstring.

## tools/unreal/dungeon-export-runner.py

Bound one owner-authorized pack bake under the existing GPU operator supervisor.

Source: [`tools/unreal/dungeon-export-runner.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/dungeon-export-runner.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/unreal/dungeon-map-reopen.py

Run inside the accepted editor to reopen a generated map without saving it.

Source: [`tools/unreal/dungeon-map-reopen.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/dungeon-map-reopen.py). Description basis: module docstring.

## tools/unreal/dungeon-material-probe.py

Probe native source materials/Blueprint transforms and CPU export; no originals are saved.

Source: [`tools/unreal/dungeon-material-probe.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/dungeon-material-probe.py). Description basis: module docstring.

## tools/unreal/godot-regression.gd

Source component: godot regression. Inspect the source before use.

Source: [`tools/unreal/godot-regression.gd`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/godot-regression.gd). Description basis: filename summary.

## tools/unreal/grid-map-probe.py

Content-only assembly, saved-map verification and actual Vulkan capture.

Source: [`tools/unreal/grid-map-probe.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/grid-map-probe.py). Description basis: module docstring.

## tools/unreal/grid_layout.py

Bounded grid-to-static-actor plan; no Unreal import or build toolchain needed.

Source: [`tools/unreal/grid_layout.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/grid_layout.py). Description basis: module docstring.

## tools/unreal/inspect-dungeon-pack.py

Read-only bounded pack inspection; execute in an isolated Unreal Python commandlet.

Source: [`tools/unreal/inspect-dungeon-pack.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/inspect-dungeon-pack.py). Description basis: module docstring.

## tools/unreal/launch-dungeon-candidate.py

Launch one bounded operator-only dungeon acceptance worker from frozen source.

Source: [`tools/unreal/launch-dungeon-candidate.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/launch-dungeon-candidate.py). Description basis: module docstring.

Declared CLI options: `--anchor`, `--levels`, `--name`, `--rooms`, `--second-anchor`, `--seed`, `--style`.

## tools/unreal/lend-build-capacity.py

Hold the existing GPU ownership lock protocol while lending idle model RAM to Unreal.

Source: [`tools/unreal/lend-build-capacity.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/lend-build-capacity.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--restore`.

## tools/unreal/lend-render-capacity.py

Lend Enshrouded capacity to one checkpointed editor attempt; restore exact replicas.

Source: [`tools/unreal/lend-render-capacity.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/lend-render-capacity.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--keep-game`.

## tools/unreal/persist-engine-mounts.py

Persist only the exact, accepted isolated overlay; never unmount the original engine.

Source: [`tools/unreal/persist-engine-mounts.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/persist-engine-mounts.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--install`.

## tools/unreal/prepare-acceptance.py

Prepare a disposable Unreal acceptance project; never compile or run the engine.

Source: [`tools/unreal/prepare-acceptance.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/prepare-acceptance.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/unreal/prepare-editor.py

Prepare an isolated CoW engine view; never write the original lower tree.

Source: [`tools/unreal/prepare-editor.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/prepare-editor.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/unreal/prime-engine-cache.py

Prime one isolated file DDC from accepted engine cache entries, without replacing live entries.

Source: [`tools/unreal/prime-engine-cache.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/prime-engine-cache.py). Description basis: module docstring.

Declared CLI options: `--receipt`, `--source`, `--target`.

## tools/unreal/recover-editor.py

Restartable isolated Unreal editor build with measured resource boundaries.

Source: [`tools/unreal/recover-editor.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/recover-editor.py). Description basis: module docstring.

Declared CLI options: `--acceptance`, `--evidence`, `--run`, `--target`.

## tools/unreal/render-api-probe.py

Source component: render api probe. Inspect the source before use.

Source: [`tools/unreal/render-api-probe.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/render-api-probe.py). Description basis: filename summary.

## tools/unreal/render-editor.py

Allocate an owned X display, then run the Vulkan editor inside the resource namespace.

Source: [`tools/unreal/render-editor.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/render-editor.py). Description basis: module docstring.

## tools/unreal/render-probe.py

Execute inside Unreal's Python plugin in the disposable acceptance project.

Source: [`tools/unreal/render-probe.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/render-probe.py). Description basis: module docstring.

## tools/unreal/render_resources.py

Measured resource selection for one GPU-fenced editor attempt.

Source: [`tools/unreal/render_resources.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/render_resources.py). Description basis: module docstring.

## tools/unreal/seed-dungeon-adapters.py

Merge receipt-backed adapters into a private copy of the existing global Catalog.

Source: [`tools/unreal/seed-dungeon-adapters.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/seed-dungeon-adapters.py). Description basis: module docstring.

## tools/unreal/test_grid_layout.py

Test fixture/check: test grid layout. Inspect the source before use.

Source: [`tools/unreal/test_grid_layout.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/test_grid_layout.py). Description basis: filename summary.

## tools/unreal/test_render_resources.py

Test fixture/check: test render resources. Inspect the source before use.

Source: [`tools/unreal/test_render_resources.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/test_render_resources.py). Description basis: filename summary.

## tools/unreal/test_render_supervision.py

Test fixture/check: test render supervision. Inspect the source before use.

Source: [`tools/unreal/test_render_supervision.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/test_render_supervision.py). Description basis: filename summary.

## tools/unreal/tests/test_crash_symbol_backfill.py

Exercise stale-symbol guards with genuinely different ELF build IDs.

Source: [`tools/unreal/tests/test_crash_symbol_backfill.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/tests/test_crash_symbol_backfill.py). Description basis: module docstring.

## tools/unreal/tune-build.py

Queue bounded resource changes for the next isolated Unreal phase; never interrupt an active compiler.

Source: [`tools/unreal/tune-build.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/unreal/tune-build.py). Description basis: module docstring.

Declared CLI options: `--apply`, `--evidence`, `--parallel-actions`.

## tools/watoom-code/accept.py

Read-only staging runtime acceptance; no production access or fixture substitution.

Source: [`tools/watoom-code/accept.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/accept.py). Description basis: module docstring.

Declared CLI options: `--output`.

## tools/watoom-code/agentmemory-acceptance.py

Authenticated, no-inference acceptance and fault injection on the owned candidate only.

Source: [`tools/watoom-code/agentmemory-acceptance.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/agentmemory-acceptance.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/watoom-code/agentmemory-browser.cjs

Source component: agentmemory browser. Inspect the source before use.

Source: [`tools/watoom-code/agentmemory-browser.cjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/agentmemory-browser.cjs). Description basis: filename summary.

## tools/watoom-code/agentmemory_transfer.py

Paginated AgentMemory export/import that never exceeds the engine transport frame.

Source: [`tools/watoom-code/agentmemory_transfer.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/agentmemory_transfer.py). Description basis: module docstring.

Declared CLI options: `--export`, `--out`, `--page-bytes`, `--secret-file`, `--store`, `--url`.

## tools/watoom-code/animation_sampling.py

Source component: animation sampling. Inspect the source before use.

Source: [`tools/watoom-code/animation_sampling.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/animation_sampling.py). Description basis: filename summary.

## tools/watoom-code/asset_capture.py

Fixed external 4GiB capture runner; accepts declarative manifests only.

Source: [`tools/watoom-code/asset_capture.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/asset_capture.py). Description basis: module docstring.

Declared CLI options: `--config`, `--evidence`, `--expected-manifest-sha256`, `--i-approve`, `--job`, `--project`.

## tools/watoom-code/asset_capture_bazzite.py

Operator-only declarative asset capture on the Bazzite worker \(keeps the 4 GiB Blender capture off the homelab server\).

Source: [`tools/watoom-code/asset_capture_bazzite.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/asset_capture_bazzite.py). Description basis: module docstring.

Declared CLI options: `--config`, `--evidence`, `--expected-manifest-sha256`, `--i-approve`, `--job`, `--project`.

## tools/watoom-code/asset_capture_blender.py

Trusted Blender-side capture implementation; entered only inside the 4GiB unit.

Source: [`tools/watoom-code/asset_capture_blender.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/asset_capture_blender.py). Description basis: module docstring.

## tools/watoom-code/asset_capture_bridge.py

Native declarative capture bridge, dispatched under the existing worker lock.

Source: [`tools/watoom-code/asset_capture_bridge.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/asset_capture_bridge.py). Description basis: module docstring.

## tools/watoom-code/asset_capture_contract.py

Declarative asset capture contract shared by the operator and tests.

Source: [`tools/watoom-code/asset_capture_contract.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/asset_capture_contract.py). Description basis: module docstring.

## tools/watoom-code/backup.py

Consistent SQLite backups and configuration snapshots; never downgrade data.

Source: [`tools/watoom-code/backup.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/backup.py). Description basis: module docstring.

Declared CLI options: `--dest`, `--keep`, `--namespace`, `--root`, `--textfile-dir`.

## tools/watoom-code/backup_offhost.py

Off-host copy of verified WatooM-Code backups, pulled by the rig.

Source: [`tools/watoom-code/backup_offhost.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/backup_offhost.py). Description basis: module docstring.

Declared CLI options: `--dest`, `--export`, `--group`, `--keep`, `--receipts`, `--textfile-dir`.

## tools/watoom-code/bazzite_wait.py

Owner policy \(2026-11-07\): heavy work waits for Bazzite; the rig is allowed only after 10 minutes; never the homelab server.

Source: [`tools/watoom-code/bazzite_wait.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/bazzite_wait.py). Description basis: module docstring.

## tools/watoom-code/blender_bazzite.py

Operator-only headless Blender job on the Bazzite worker \(keeps Blender off the homelab server and its model\).

Source: [`tools/watoom-code/blender_bazzite.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/blender_bazzite.py). Description basis: module docstring.

Declared CLI options: `--blender-job`, `--evidence`, `--i-approve`, `--project`.

## tools/watoom-code/blender_job_spec.py

Declarative headless Blender job for a game project: which script, its arguments and limits; no paths outside the project.

Source: [`tools/watoom-code/blender_job_spec.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/blender_job_spec.py). Description basis: module docstring.

## tools/watoom-code/bounded_process.py

Bounded Linux operator commands with process-group cancellation.

Source: [`tools/watoom-code/bounded_process.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/bounded_process.py). Description basis: module docstring.

## tools/watoom-code/browser-acceptance.cjs

Source component: browser acceptance. Inspect the source before use.

Source: [`tools/watoom-code/browser-acceptance.cjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/browser-acceptance.cjs). Description basis: filename summary.

## tools/watoom-code/build.py

Build WatooM Code from maintained source and a pinned IaC toolchain. No deployment or network changes. All mutable build paths are explicit.

Source: [`tools/watoom-code/build.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/build.py). Description basis: module docstring.

Declared CLI options: `--buildah`, `--engine`, `--tag`.

## tools/watoom-code/capture_profiles.py

Operator-defined capture scenes and exact expected outputs; no caller paths.

Source: [`tools/watoom-code/capture_profiles.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/capture_profiles.py). Description basis: module docstring.

## tools/watoom-code/capture_spec.py

Project-neutral declarative capture contract; no caller shell or engine arguments.

Source: [`tools/watoom-code/capture_spec.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/capture_spec.py). Description basis: module docstring.

## tools/watoom-code/creative-candidate-acceptance.py

Aggregate real native creative candidate receipts; never deploy or fabricate a passing gate.

Source: [`tools/watoom-code/creative-candidate-acceptance.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/creative-candidate-acceptance.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/watoom-code/creative-candidate-rollback.py

Independently exercise immutable old/new rollback only on the owned creative candidate.

Source: [`tools/watoom-code/creative-candidate-rollback.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/creative-candidate-rollback.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/watoom-code/creative_release.py

Creative release hooks for the existing native-fenced promotion coordinator.

Source: [`tools/watoom-code/creative_release.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/creative_release.py). Description basis: module docstring.

Declared CLI options: `--blender-acceptance`, `--blender-toolkit-only`, `--evidence`, `--i-approve`, `--iac-root`, `--image`, `--rollback-blender-evidence`.

## tools/watoom-code/cutover.py

Reviewable, identity-fenced production cutover through Ansible; data never rolled back.

Source: [`tools/watoom-code/cutover.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/cutover.py). Description basis: module docstring.

Declared CLI options: `--acceptance`, `--candidate-sha256`, `--i-approve`, `--snapshot`.

## tools/watoom-code/deploy-platform.py

Deploy only the WatooM Code app from authoritative IaC; rollback on failed gates.

Source: [`tools/watoom-code/deploy-platform.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/deploy-platform.py). Description basis: module docstring.

Declared CLI options: `--administrative-access-closed`, `--asset-catalog`, `--bootstrap-evidence`, `--bootstrap-maintenance`, `--candidate-evidence`, `--engineering-tools`, `--evidence`, `--i-approve`, `--iac-root`, `--image`, `--leave-forwarding-stopped`, `--mesh-integration`, `--native-gui-fixture`, `--prompt-builder`, `--skills-collection`, `--toolkit-image`.

## tools/watoom-code/dev_release.py

Dev-only preparation through the maintained Ansible role and native idle guard.

Source: [`tools/watoom-code/dev_release.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/dev_release.py). Description basis: module docstring.

Declared CLI options: `--baseline`, `--dev-workspace-only`, `--evidence`, `--host`, `--i-approve`, `--iac-root`, `--prepare-only`.

## tools/watoom-code/dev_workspace/activation.py

Owned native activation, with independent systemd finalization and rollback.

Source: [`tools/watoom-code/dev_workspace/activation.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/dev_workspace/activation.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--host`, `--i-approve`, `--package-sha`, `--prepare`, `--recover`, `--recover-if-idle`, `--run`.

## tools/watoom-code/dev_workspace/index.js

Source component: index. Inspect the source before use.

Source: [`tools/watoom-code/dev_workspace/index.js`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/dev_workspace/index.js). Description basis: filename summary.

## tools/watoom-code/dev_workspace/isolation.test.mjs

Source component: isolation.test. Inspect the source before use.

Source: [`tools/watoom-code/dev_workspace/isolation.test.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/dev_workspace/isolation.test.mjs). Description basis: filename summary.

## tools/watoom-code/dev_workspace/prepare.py

Initialize only fresh dev objects after the two authenticated remote refs match.

Source: [`tools/watoom-code/dev_workspace/prepare.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/dev_workspace/prepare.py). Description basis: module docstring.

Declared CLI options: `--baseline`, `--host`, `--i-approve`, `--remote`.

## tools/watoom-code/dev_workspace/refresh.py

Operator-only fast-forward refresh; preserve model dev history and tool enablement.

Source: [`tools/watoom-code/dev_workspace/refresh.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/dev_workspace/refresh.py). Description basis: module docstring.

## tools/watoom-code/dev_workspace/runtime.py

Constrained development jobs; the SSH entry point accepts JSON, never a host shell.

Source: [`tools/watoom-code/dev_workspace/runtime.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/dev_workspace/runtime.py). Description basis: module docstring.

Declared CLI options: `--finalize`, `--git-transport`, `--receive-policy`, `--recover-all`, `--request`.

## tools/watoom-code/dev_workspace/test_activation.py

Test fixture/check: test activation. Inspect the source before use.

Source: [`tools/watoom-code/dev_workspace/test_activation.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/dev_workspace/test_activation.py). Description basis: filename summary.

## tools/watoom-code/dev_workspace/test_runtime.py

Test fixture/check: test runtime. Inspect the source before use.

Source: [`tools/watoom-code/dev_workspace/test_runtime.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/dev_workspace/test_runtime.py). Description basis: filename summary.

## tools/watoom-code/drive_model_session.py

Drive a WatooM-Code model session from the operator side: start or continue a session with a prompt file, approve its game-worker permission, wait for the turn to end, and say what happened \(tools used, worker jobs, stalled or not\).

Source: [`tools/watoom-code/drive_model_session.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/drive_model_session.py). Description basis: module docstring.

Declared CLI options: `--agent`, `--auto-resume`, `--max-min`, `--project`, `--prompt-file`, `--session`, `--title`, `--watch`.

## tools/watoom-code/dungeon-candidate-core.py

Exact-image owned candidate memory and admission race acceptance; no model calls.

Source: [`tools/watoom-code/dungeon-candidate-core.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/dungeon-candidate-core.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/watoom-code/dungeon-candidate-rollback.py

Exercise the production fences and digest validator on the owned isolated pair.

Source: [`tools/watoom-code/dungeon-candidate-rollback.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/dungeon-candidate-rollback.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--resume-old`.

## tools/watoom-code/dungeon-candidate-validation.py

Focused native application acceptance on the explicitly owned dungeon pair.

Source: [`tools/watoom-code/dungeon-candidate-validation.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/dungeon-candidate-validation.py). Description basis: module docstring.

Declared CLI options: `--case`, `--evidence`.

## tools/watoom-code/dungeon-candidate.py

Prepare an owned application/Toolkit pair with fresh session state and RO sources.

Source: [`tools/watoom-code/dungeon-candidate.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/dungeon-candidate.py). Description basis: module docstring.

Declared CLI options: `--activate`, `--candidate-suffix`, `--catalog`, `--evidence`, `--finish-activation`.

## tools/watoom-code/engineering/build.py

Rebuild only the engineering toolchain; retain exact verified application binaries.

Source: [`tools/watoom-code/engineering/build.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/engineering/build.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--layer-tag`, `--runtime-image`, `--tag`.

## tools/watoom-code/engineering/candidate.py

Isolated exact-image engineering acceptance and independently exercised rollback.

Source: [`tools/watoom-code/engineering/candidate.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/engineering/candidate.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--name`, `--resume`.

## tools/watoom-code/engineering/smoke.py

Bounded actual OCR/PDF, media, x86 decoding and DOS execution acceptance.

Source: [`tools/watoom-code/engineering/smoke.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/engineering/smoke.py). Description basis: module docstring.

## tools/watoom-code/forward.py

Loopback-only staging access, reconnecting across pod replacement.

Source: [`tools/watoom-code/forward.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/forward.py). Description basis: module docstring.

## tools/watoom-code/game_bazzite.py

Operator-only Godot import/regression/capture on the Bazzite worker \(keeps big game jobs off the homelab server\).

Source: [`tools/watoom-code/game_bazzite.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/game_bazzite.py). Description basis: module docstring.

Declared CLI options: `--capture-job`, `--evidence`, `--i-approve`, `--operation`, `--profile`, `--project`.

## tools/watoom-code/game_blender.py

Operator-side headless Blender job for a native game-worker request; the root dispatcher is the only caller.

Source: [`tools/watoom-code/game_blender.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/game_blender.py). Description basis: module docstring.

Declared CLI options: `--blender-job`, `--evidence`, `--i-approve`, `--project`.

## tools/watoom-code/game_capture.py

Operator-owned bounded software-render capture of the existing P6 scene.

Source: [`tools/watoom-code/game_capture.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/game_capture.py). Description basis: module docstring.

Declared CLI options: `--capture-job`, `--evidence`, `--i-approve`, `--profile`, `--project`.

## tools/watoom-code/game_godot_game.py

Operator-side typed watoom-godot-game job for a native game-worker request; the root dispatcher is the only caller.

Source: [`tools/watoom-code/game_godot_game.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/game_godot_game.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--godot-game-job`, `--i-approve`, `--project`.

## tools/watoom-code/game_import.py

Operator-only bounded import; never runs inside the application cgroup.

Source: [`tools/watoom-code/game_import.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/game_import.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--i-approve`, `--project`.

## tools/watoom-code/game_session_watchdog.py

Watchdog for game-project coordinator sessions that "just stop".

Source: [`tools/watoom-code/game_session_watchdog.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/game_session_watchdog.py). Description basis: module docstring.

Declared CLI options: `--dry-run`, `--report`, `--stale-after`, `--undispatched-after`.

## tools/watoom-code/game_terrain_export.py

Operator-side terrain/landscape-to-GLB export for a native game-worker request; the root dispatcher is the only caller. Runs an existing, project-staged .uproject \+ in-engine Python script \(terrain\_spec.py validates the declarative request\)

Source: [`tools/watoom-code/game_terrain_export.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/game_terrain_export.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--i-approve`, `--project`, `--terrain-job`.

## tools/watoom-code/game_unreal_export.py

Operator-side Unreal pack export for a native game-worker request; the root dispatcher is the only caller.

Source: [`tools/watoom-code/game_unreal_export.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/game_unreal_export.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--export-job`, `--i-approve`, `--project`.

## tools/watoom-code/game_validation.py

Operator-owned, isolated CPU Godot regression against a stable project snapshot.

Source: [`tools/watoom-code/game_validation.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/game_validation.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--finalize`, `--i-approve`, `--memory-gib`, `--project`, `--resume-prepared`.

## tools/watoom-code/game_worker_bridge.py

Validate native worker requests and dispatch fixed operator-owned helpers.

Source: [`tools/watoom-code/game_worker_bridge.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/game_worker_bridge.py). Description basis: module docstring.

## tools/watoom-code/godot_game_driver.py

Runs INSIDE the Bazzite container for the godot-game worker operation. Fixed behaviour, no inputs except /job/steps.json \(validated by godot\_game\_spec\).

Source: [`tools/watoom-code/godot_game_driver.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/godot_game_driver.py). Description basis: module docstring.

## tools/watoom-code/godot_game_spec.py

Typed watoom-godot-game job: a fixed list of skill commands run against a staged game project; no shell, no paths, no engine flags.

Source: [`tools/watoom-code/godot_game_spec.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/godot_game_spec.py). Description basis: module docstring.

## tools/watoom-code/grant_visual_recovery.py

Create one audited, exact-child recovery grant under an owned native release fence. This changes no session counters/receipts and never grants visual acceptance.

Source: [`tools/watoom-code/grant_visual_recovery.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/grant_visual_recovery.py). Description basis: module docstring.

## tools/watoom-code/image-results-browser.cjs

Source component: image results browser. Inspect the source before use.

Source: [`tools/watoom-code/image-results-browser.cjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/image-results-browser.cjs). Description basis: filename summary.

## tools/watoom-code/import-skill-collection.py

Merge retained discovery metadata into the existing native catalog. Never approves or executes.

Source: [`tools/watoom-code/import-skill-collection.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/import-skill-collection.py). Description basis: module docstring.

Declared CLI options: `--source`, `--target`.

## tools/watoom-code/lmb_provenance.py

Read-only metadata fingerprints, raw native input provenance and receipt identity. No engine invocation, request submission or historical receipt mutation.

Source: [`tools/watoom-code/lmb_provenance.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/lmb_provenance.py). Description basis: module docstring.

Declared CLI options: `--guard`, `--native-source`, `--output`, `--project`, `--receipt`, `--request`.

## tools/watoom-code/lmb_qualify.py

Controlled native LMB qualification only. Does not generate a landscape mesh.

Source: [`tools/watoom-code/lmb_qualify.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/lmb_qualify.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--i-approve`, `--project`.

## tools/watoom-code/maintenance_guard.py

Approved one-time bootstrap barrier on published Service and pod-to-pod ingress. Privileged host/kubectl access is an administrative bypass: operators must close port-forwards and refrain from opening them during the documented window. Exis

Source: [`tools/watoom-code/maintenance_guard.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/maintenance_guard.py). Description basis: module docstring.

## tools/watoom-code/memory_catalogue_release.py

Scoped approved release: native fence, SQLite backup, IaC apply and runtime identity.

Source: [`tools/watoom-code/memory_catalogue_release.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/memory_catalogue_release.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--i-approve`, `--iac-root`, `--manifest`.

## tools/watoom-code/memory_outbox.py

Operator reconciliation of stranded native AgentMemory outbox items.

Source: [`tools/watoom-code/memory_outbox.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/memory_outbox.py). Description basis: module docstring.

Declared CLI options: `--apply`, `--evidence`, `--i-approve`, `--sending-older-than-hours`.

## tools/watoom-code/mesh-candidate-acceptance.py

One real model turn exercises compiled native checkpoints with an owned CPU MCP fixture.

Source: [`tools/watoom-code/mesh-candidate-acceptance.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/mesh-candidate-acceptance.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/watoom-code/mesh_release.py

Narrow reviewed Mesh integration delta for the existing guarded release.

Source: [`tools/watoom-code/mesh_release.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/mesh_release.py). Description basis: module docstring.

## tools/watoom-code/operations/agentmemory/audit.py

Targeted read-only release capability and execution status audit. No secret output.

Source: [`tools/watoom-code/operations/agentmemory/audit.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/operations/agentmemory/audit.py). Description basis: module docstring.

## tools/watoom-code/orphan_claims.py

Exact cancellation reconciliation; never infer clearance from idle alone.

Source: [`tools/watoom-code/orphan_claims.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/orphan_claims.py). Description basis: module docstring.

## tools/watoom-code/overnight_watchdog.py

Overnight health watchdog for the watoom-code stack \(report-only by default\).

Source: [`tools/watoom-code/overnight_watchdog.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/overnight_watchdog.py). Description basis: module docstring.

Declared CLI options: `--report`, `--restart-crashed`.

## tools/watoom-code/platform-acceptance.py

Run isolated development acceptance inside the deployed app as its runtime UID.

Source: [`tools/watoom-code/platform-acceptance.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/platform-acceptance.py). Description basis: module docstring.

Declared CLI options: `--root`.

## tools/watoom-code/pose_preparation_contract.py

Fixed pose payload contract; no script paths or executable input.

Source: [`tools/watoom-code/pose_preparation_contract.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/pose_preparation_contract.py). Description basis: module docstring.

## tools/watoom-code/pose_preparation_worker.py

Fixed installed pose helper adapter; called only inside the capture cgroup.

Source: [`tools/watoom-code/pose_preparation_worker.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/pose_preparation_worker.py). Description basis: module docstring.

## tools/watoom-code/project_access.py

Restore explicit editable project paths without changing ownership or asset libraries.

Source: [`tools/watoom-code/project_access.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/project_access.py). Description basis: module docstring.

Declared CLI options: `--directory`, `--evidence`, `--i-approve`, `--project`, `--tree`.

## tools/watoom-code/project_captures.py

Expose project-local captures in the common viewer directory without duplicating files.

Source: [`tools/watoom-code/project_captures.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/project_captures.py). Description basis: module docstring.

Declared CLI options: `--project`.

## tools/watoom-code/prompt-builder-browser.cjs

Source component: prompt builder browser. Inspect the source before use.

Source: [`tools/watoom-code/prompt-builder-browser.cjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/prompt-builder-browser.cjs). Description basis: filename summary.

## tools/watoom-code/recover-idle-admission.py

Source component: recover idle admission. Inspect the source before use.

Source: [`tools/watoom-code/recover-idle-admission.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/recover-idle-admission.py). Description basis: filename summary.

Declared CLI options: `--evidence`, `--i-approve`.

## tools/watoom-code/recover-orphan-claim.py

Operator-authorized exact orphan-claim repair under native admission fencing.

Source: [`tools/watoom-code/recover-orphan-claim.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/recover-orphan-claim.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--expected-suspended`, `--i-approve`, `--session`.

## tools/watoom-code/recover-orphan-claims.py

Bounded multi-child extension of recover-orphan-claim.py; preserves history.

Source: [`tools/watoom-code/recover-orphan-claims.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/recover-orphan-claims.py). Description basis: module docstring.

Declared CLI options: `--claims`, `--evidence`, `--i-approve`.

## tools/watoom-code/recover-restarted-claims.py

Operator stop/reconciliation only; never resumes prompts or engine work.

Source: [`tools/watoom-code/recover-restarted-claims.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/recover-restarted-claims.py). Description basis: module docstring.

Declared CLI options: `--claims`, `--evidence`, `--i-approve`, `--root-session`.

## tools/watoom-code/release_guard.py

Release admission protocol shared by maintained deployment helpers.

Source: [`tools/watoom-code/release_guard.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/release_guard.py). Description basis: module docstring.

## tools/watoom-code/release_ledger.py

Append-only record of what was released: image digest, OCI source revision and IaC commit.

Source: [`tools/watoom-code/release_ledger.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/release_ledger.py). Description basis: module docstring.

## tools/watoom-code/render_routing_release.py

Narrow render-routing activation through the existing release coordinator.

Source: [`tools/watoom-code/render_routing_release.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/render_routing_release.py). Description basis: module docstring.

Declared CLI options: `--asset-capture-worker`, `--evidence`, `--i-approve`, `--iac-root`, `--render-routing-only`, `--update-owned-native`, `--update-shell-guard`.

## tools/watoom-code/repair_game_request.py

Operator-only same-identity repair from recorded native tool evidence; never submit a new job.

Source: [`tools/watoom-code/repair_game_request.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/repair_game_request.py). Description basis: module docstring.

Declared CLI options: `--database`, `--evidence`, `--project`, `--request-id`.

## tools/watoom-code/restarted_claims.py

Reconcile exact session claims from a proven terminated application process.

Source: [`tools/watoom-code/restarted_claims.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/restarted_claims.py). Description basis: module docstring.

## tools/watoom-code/restore-source.py

Restore exact maintained application commits onto the pinned public release, into a new checkout.

Source: [`tools/watoom-code/restore-source.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/restore-source.py). Description basis: module docstring.

Declared CLI options: `--destination`, `--metadata`.

## tools/watoom-code/rig/pull-homelab-backups.ps1

Source component: pull homelab backups. Inspect the source before use.

Source: [`tools/watoom-code/rig/pull-homelab-backups.ps1`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/rig/pull-homelab-backups.ps1). Description basis: filename summary.

## tools/watoom-code/rig_pose_contract.py

Pure schema for the fixed Shadowheart MHX adapter; no executable fields.

Source: [`tools/watoom-code/rig_pose_contract.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/rig_pose_contract.py). Description basis: module docstring.

## tools/watoom-code/self_learning/audit.py

Targeted read-only runtime audit; reports stay in the private run directory.

Source: [`tools/watoom-code/self_learning/audit.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/audit.py). Description basis: module docstring.

Declared CLI options: `--allow-absent-staging`, `--evidence`, `--namespace`.

## tools/watoom-code/self_learning/capture_planning_suite.py

Observed capture planning replays; never launches Blender or claims pixel quality.

Source: [`tools/watoom-code/self_learning/capture_planning_suite.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/capture_planning_suite.py). Description basis: module docstring.

Declared CLI options: `--baseline`, `--candidate`, `--endpoint`, `--model`, `--output`, `--reference`, `--resume`.

## tools/watoom-code/self_learning/contract_suite.py

Conservative replay contract for structural revisions. No domain benefit claim.

Source: [`tools/watoom-code/self_learning/contract_suite.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/contract_suite.py). Description basis: module docstring.

## tools/watoom-code/self_learning/corpus_validation.mjs

Source component: corpus validation. Inspect the source before use.

Source: [`tools/watoom-code/self_learning/corpus_validation.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/corpus_validation.mjs). Description basis: filename summary.

## tools/watoom-code/self_learning/deploy.py

Authorised cutover through existing native admission, maintenance and Ansible owners.

Source: [`tools/watoom-code/self_learning/deploy.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/deploy.py). Description basis: module docstring.

Declared CLI options: `--dry-run`, `--evidence`, `--i-approve`, `--resume`.

## tools/watoom-code/self_learning/deployment_model.py

Fail closed unless the explicitly reviewed validation model is already idle/ready.

Source: [`tools/watoom-code/self_learning/deployment_model.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/deployment_model.py). Description basis: module docstring.

## tools/watoom-code/self_learning/end_to_end.py

Source component: end to end. Inspect the source before use.

Source: [`tools/watoom-code/self_learning/end_to_end.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/end_to_end.py). Description basis: filename summary.

Declared CLI options: `--evidence`, `--namespace`.

## tools/watoom-code/self_learning/engine.mjs

Source component: engine. Inspect the source before use.

Source: [`tools/watoom-code/self_learning/engine.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/engine.mjs). Description basis: filename summary.

## tools/watoom-code/self_learning/engine.test.mjs

Source component: engine.test. Inspect the source before use.

Source: [`tools/watoom-code/self_learning/engine.test.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/engine.test.mjs). Description basis: filename summary.

## tools/watoom-code/self_learning/evaluate_existing.py

Run one protected registered CPU task suite against original and candidate data. Unknown Skills remain explicitly untested. Suites are operator-reviewed code; models cannot register, modify or execute evaluator programs.

Source: [`tools/watoom-code/self_learning/evaluate_existing.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/evaluate_existing.py). Description basis: module docstring.

## tools/watoom-code/self_learning/evaluate_fixture.py

Evaluate only the registered deterministic sort fixture; no arbitrary candidate execution.

Source: [`tools/watoom-code/self_learning/evaluate_fixture.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/evaluate_fixture.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--namespace`.

## tools/watoom-code/self_learning/existing_baseline.py

Read-only census and privacy-preserving historical usage baseline. No task execution.

Source: [`tools/watoom-code/self_learning/existing_baseline.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/existing_baseline.py). Description basis: module docstring.

Declared CLI options: `--database`, `--deployment`, `--directory`, `--evidence`, `--namespace`.

## tools/watoom-code/self_learning/expire_fixture.py

Expire only one owned staging fixture, never a later run or production.

Source: [`tools/watoom-code/self_learning/expire_fixture.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/expire_fixture.py). Description basis: module docstring.

Declared CLI options: `--input`.

## tools/watoom-code/self_learning/idle_stream_exercise.py

Actual native staging SSE \+ admission/ingress fences; independent recovery armed.

Source: [`tools/watoom-code/self_learning/idle_stream_exercise.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/idle_stream_exercise.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/watoom-code/self_learning/idle_streams.py

Allow only positively observed, read-only native SSE heartbeats through idle drain.

Source: [`tools/watoom-code/self_learning/idle_streams.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/idle_streams.py). Description basis: module docstring.

## tools/watoom-code/self_learning/index.mjs

Source component: index. Inspect the source before use.

Source: [`tools/watoom-code/self_learning/index.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/index.mjs). Description basis: filename summary.

## tools/watoom-code/self_learning/index.test.mjs

Source component: index.test. Inspect the source before use.

Source: [`tools/watoom-code/self_learning/index.test.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/index.test.mjs). Description basis: filename summary.

## tools/watoom-code/self_learning/live_smoke.py

One idle-gated safe request through the existing primary model router; no GPU lifecycle commands.

Source: [`tools/watoom-code/self_learning/live_smoke.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/live_smoke.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--namespace`.

## tools/watoom-code/self_learning/manage.py

Operator actions consumed by the existing native plugin; never edits its database.

Source: [`tools/watoom-code/self_learning/manage.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/manage.py). Description basis: module docstring.

Declared CLI options: `--action`, `--evidence`, `--id`, `--runtime`.

## tools/watoom-code/self_learning/manage_existing.py

Review native existing-Skill state or submit a root-owned independent evaluator report.

Source: [`tools/watoom-code/self_learning/manage_existing.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/manage_existing.py). Description basis: module docstring.

Declared CLI options: `--action`, `--evidence`, `--id`, `--report`, `--runtime`, `--scope-hash`.

## tools/watoom-code/self_learning/mcp_quiescence.py

Quiesce only inspected, idle Mesh stdio adapters through native MCP lifecycle APIs.

Source: [`tools/watoom-code/self_learning/mcp_quiescence.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/mcp_quiescence.py). Description basis: module docstring.

## tools/watoom-code/self_learning/memory_curator.py

Phases 3-4 of the learning loop: a deterministic, GPU-free memory curator \(docs/proposals/learning-loop-design.md\).

Source: [`tools/watoom-code/self_learning/memory_curator.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/memory_curator.py). Description basis: module docstring.

Declared CLI options: `--agent-email`, `--apply`, `--chat-db`, `--evidence-root`, `--export-recall`, `--godot-toolchain`, `--lesson-marker`, `--limit`, `--owner-email`, `--pattern-min-occurrences`, `--query`, `--receipts-dir`, `--repo`, `--since-days`, `--store`, `--txn`.

## tools/watoom-code/self_learning/memory_outage.py

Source component: memory outage. Inspect the source before use.

Source: [`tools/watoom-code/self_learning/memory_outage.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/memory_outage.py). Description basis: filename summary.

Declared CLI options: `--evidence`, `--namespace`.

## tools/watoom-code/self_learning/mock_provider.py

Deterministic CPU provider for native-hook acceptance; no inference.

Source: [`tools/watoom-code/self_learning/mock_provider.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/mock_provider.py). Description basis: module docstring.

## tools/watoom-code/self_learning/native_acceptance.py

Exercise the actual isolated WatooM runtime via its authenticated native API.

Source: [`tools/watoom-code/self_learning/native_acceptance.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/native_acceptance.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--namespace`, `--sessions`.

## tools/watoom-code/self_learning/native_controls.py

Source component: native controls. Inspect the source before use.

Source: [`tools/watoom-code/self_learning/native_controls.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/native_controls.py). Description basis: filename summary.

Declared CLI options: `--evidence`, `--namespace`.

## tools/watoom-code/self_learning/native_existing.py

Native discovery/load baseline for every existing Skill; no workflow execution.

Source: [`tools/watoom-code/self_learning/native_existing.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/native_existing.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--namespace`.

## tools/watoom-code/self_learning/native_overlay.py

Isolated revision-control exercise. Synthetic numbers are NOT performance evidence.

Source: [`tools/watoom-code/self_learning/native_overlay.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/native_overlay.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--namespace`.

## tools/watoom-code/self_learning/native_readiness.py

Wait for the native asynchronous filesystem Skill registry, then enforce coverage.

Source: [`tools/watoom-code/self_learning/native_readiness.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/native_readiness.py). Description basis: module docstring.

## tools/watoom-code/self_learning/optimisation.mjs

Source component: optimisation. Inspect the source before use.

Source: [`tools/watoom-code/self_learning/optimisation.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/optimisation.mjs). Description basis: filename summary.

## tools/watoom-code/self_learning/optimisation.test.mjs

Source component: optimisation.test. Inspect the source before use.

Source: [`tools/watoom-code/self_learning/optimisation.test.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/optimisation.test.mjs). Description basis: filename summary.

## tools/watoom-code/self_learning/optimisation_failure.py

Service failure handler; Codex disconnects do not stop this host service.

Source: [`tools/watoom-code/self_learning/optimisation_failure.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/optimisation_failure.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/watoom-code/self_learning/optimise.py

Apply only proven existing-Skill revisions at idle; never edit an active Skill file.

Source: [`tools/watoom-code/self_learning/optimise.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/optimise.py). Description basis: module docstring.

Declared CLI options: `--dry-run`, `--evidence`.

## tools/watoom-code/self_learning/prepare_cutover.py

Prepare a private, checksum-pinned cutover; never changes production.

Source: [`tools/watoom-code/self_learning/prepare_cutover.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/prepare_cutover.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--update-existing-package`, `--validation-deployment`, `--validation-model`.

## tools/watoom-code/self_learning/readiness_exercise.py

Native cold-location Skill readiness without model requests or production changes.

Source: [`tools/watoom-code/self_learning/readiness_exercise.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/readiness_exercise.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/watoom-code/self_learning/recover.py

One bounded independent recovery tick. Healthy services are never rolled back for agent loss.

Source: [`tools/watoom-code/self_learning/recover.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/recover.py). Description basis: module docstring.

Declared CLI options: `--state`.

## tools/watoom-code/self_learning/recovery_exercise.py

Deliberately fail only the isolated app; independent host recovery must restore it.

Source: [`tools/watoom-code/self_learning/recovery_exercise.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/recovery_exercise.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--namespace`.

## tools/watoom-code/self_learning/restore_probe.py

Isolated logical AgentMemory restore probe; no production writes.

Source: [`tools/watoom-code/self_learning/restore_probe.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/restore_probe.py). Description basis: module docstring.

## tools/watoom-code/self_learning/restore_staging_memory.py

Independent staging-only memory availability watchdog.

Source: [`tools/watoom-code/self_learning/restore_staging_memory.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/restore_staging_memory.py). Description basis: module docstring.

Declared CLI options: `--checkpoint`.

## tools/watoom-code/self_learning/role_validation.py

Exercise the actual production workflow prompt/guard in isolated staging.

Source: [`tools/watoom-code/self_learning/role_validation.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/role_validation.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--namespace`.

## tools/watoom-code/self_learning/rollback.py

Request supported restoration from the independently scheduled recovery controller.

Source: [`tools/watoom-code/self_learning/rollback.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/rollback.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--wait`.

## tools/watoom-code/self_learning/runner.py

Single resumable entry point. Production operations require explicit approval.

Source: [`tools/watoom-code/self_learning/runner.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/runner.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--namespace`, `--update-existing-package`.

## tools/watoom-code/self_learning/runtime_validation.py

Native closed-loop validation, usable in staging or an explicitly approved cutover.

Source: [`tools/watoom-code/self_learning/runtime_validation.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/runtime_validation.py). Description basis: module docstring.

Declared CLI options: `--approved-state`, `--deployment`, `--directory`.

## tools/watoom-code/self_learning/stage.py

Prepare isolated native learning manifests; apply through the dedicated Ansible playbook.

Source: [`tools/watoom-code/self_learning/stage.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/stage.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--namespace`.

## tools/watoom-code/self_learning/test_deployment_model.py

Test fixture/check: test deployment model. Inspect the source before use.

Source: [`tools/watoom-code/self_learning/test_deployment_model.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/test_deployment_model.py). Description basis: filename summary.

## tools/watoom-code/self_learning/test_evaluate_existing.py

Test fixture/check: test evaluate existing. Inspect the source before use.

Source: [`tools/watoom-code/self_learning/test_evaluate_existing.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/test_evaluate_existing.py). Description basis: filename summary.

## tools/watoom-code/self_learning/test_idle_streams.py

Test fixture/check: test idle streams. Inspect the source before use.

Source: [`tools/watoom-code/self_learning/test_idle_streams.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/test_idle_streams.py). Description basis: filename summary.

## tools/watoom-code/self_learning/test_mcp_quiescence.py

Test fixture/check: test mcp quiescence. Inspect the source before use.

Source: [`tools/watoom-code/self_learning/test_mcp_quiescence.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/test_mcp_quiescence.py). Description basis: filename summary.

## tools/watoom-code/self_learning/test_memory_curator.py

Test fixture/check: test memory curator. Inspect the source before use.

Source: [`tools/watoom-code/self_learning/test_memory_curator.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/test_memory_curator.py). Description basis: filename summary.

## tools/watoom-code/self_learning/test_native_readiness.py

Test fixture/check: test native readiness. Inspect the source before use.

Source: [`tools/watoom-code/self_learning/test_native_readiness.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/test_native_readiness.py). Description basis: filename summary.

## tools/watoom-code/self_learning/test_optimise.py

Test fixture/check: test optimise. Inspect the source before use.

Source: [`tools/watoom-code/self_learning/test_optimise.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/test_optimise.py). Description basis: filename summary.

## tools/watoom-code/self_learning/test_recover.py

Test fixture/check: test recover. Inspect the source before use.

Source: [`tools/watoom-code/self_learning/test_recover.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/test_recover.py). Description basis: filename summary.

## tools/watoom-code/self_learning/validate.py

Bounded, serial acceptance orchestration; preserves all evidence and honest test scope.

Source: [`tools/watoom-code/self_learning/validate.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/validate.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--namespace`, `--resume`.

## tools/watoom-code/self_learning/worker_verifier.mjs

Source component: worker verifier. Inspect the source before use.

Source: [`tools/watoom-code/self_learning/worker_verifier.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/worker_verifier.mjs). Description basis: filename summary.

## tools/watoom-code/self_learning/worker_verifier.test.mjs

Source component: worker verifier.test. Inspect the source before use.

Source: [`tools/watoom-code/self_learning/worker_verifier.test.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/self_learning/worker_verifier.test.mjs). Description basis: filename summary.

## tools/watoom-code/skills-browser.cjs

Source component: skills browser. Inspect the source before use.

Source: [`tools/watoom-code/skills-browser.cjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/skills-browser.cjs). Description basis: filename summary.

## tools/watoom-code/skills-candidate-acceptance.py

Aggregate existing evidence, then verify the exact fenced candidate and final GUI session.

Source: [`tools/watoom-code/skills-candidate-acceptance.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/skills-candidate-acceptance.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/watoom-code/skills-candidate-namespace.py

Move only the owned, idle candidate into the existing Kali-authorized test namespace.

Source: [`tools/watoom-code/skills-candidate-namespace.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/skills-candidate-namespace.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/watoom-code/skills-candidate-rollback.py

Exercise image rollback only on the identified idle, fenced candidate.

Source: [`tools/watoom-code/skills-candidate-rollback.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/skills-candidate-rollback.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--old-gui-only`.

## tools/watoom-code/skills-candidate-validation.py

Bounded native Skills acceptance using only owned candidate records.

Source: [`tools/watoom-code/skills-candidate-validation.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/skills-candidate-validation.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--phase`, `--real-session`.

## tools/watoom-code/skills-candidate.py

Prepare a separate Skills acceptance deployment; never copy live resumable session state.

Source: [`tools/watoom-code/skills-candidate.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/skills-candidate.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--prepare`.

## tools/watoom-code/skills_release.py

Skills hooks for the existing admission-fenced release coordinator. No second deploy path.

Source: [`tools/watoom-code/skills_release.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/skills_release.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--i-approve`, `--iac-root`, `--prompt-skills-only`, `--update-owned-native`.

## tools/watoom-code/sync_rig_projects.py

Keep the rig stage's project enrollment \(/etc/watoom-rig-async-stage.json\) in sync with the main game worker's project list \(/etc/watoom-game-worker.json\), so a project enrolled for the main Bazzite/local worker is automatically rig-eligibl

Source: [`tools/watoom-code/sync_rig_projects.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/sync_rig_projects.py). Description basis: module docstring.

## tools/watoom-code/terrain_spec.py

Project-neutral declarative terrain/landscape-to-GLB export contract; no caller shell or engine arguments.

Source: [`tools/watoom-code/terrain_spec.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/terrain_spec.py). Description basis: module docstring.

## tools/watoom-code/test-app-blender-guard.mjs

Test fixture/check: test app blender guard. Inspect the source before use.

Source: [`tools/watoom-code/test-app-blender-guard.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test-app-blender-guard.mjs). Description basis: filename summary.

## tools/watoom-code/test-asset-capture.mjs

Test fixture/check: test asset capture. Inspect the source before use.

Source: [`tools/watoom-code/test-asset-capture.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test-asset-capture.mjs). Description basis: filename summary.

## tools/watoom-code/test-capture-spec.mjs

Test fixture/check: test capture spec. Inspect the source before use.

Source: [`tools/watoom-code/test-capture-spec.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test-capture-spec.mjs). Description basis: filename summary.

## tools/watoom-code/test-coordinator-guard.mjs

Test fixture/check: test coordinator guard. Inspect the source before use.

Source: [`tools/watoom-code/test-coordinator-guard.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test-coordinator-guard.mjs). Description basis: filename summary.

## tools/watoom-code/test-critic-only-request.mjs

Test fixture/check: test critic only request. Inspect the source before use.

Source: [`tools/watoom-code/test-critic-only-request.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test-critic-only-request.mjs). Description basis: filename summary.

## tools/watoom-code/test-critic-recovery-grants.mjs

Test fixture/check: test critic recovery grants. Inspect the source before use.

Source: [`tools/watoom-code/test-critic-recovery-grants.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test-critic-recovery-grants.mjs). Description basis: filename summary.

## tools/watoom-code/test-game-worker.mjs

Test fixture/check: test game worker. Inspect the source before use.

Source: [`tools/watoom-code/test-game-worker.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test-game-worker.mjs). Description basis: filename summary.

## tools/watoom-code/test-godot-external-only.mjs

Test fixture/check: test godot external only. Inspect the source before use.

Source: [`tools/watoom-code/test-godot-external-only.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test-godot-external-only.mjs). Description basis: filename summary.

## tools/watoom-code/test-image-scope.mjs

Test fixture/check: test image scope. Inspect the source before use.

Source: [`tools/watoom-code/test-image-scope.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test-image-scope.mjs). Description basis: filename summary.

## tools/watoom-code/test-learned-lessons.mjs

Test fixture/check: test learned lessons. Inspect the source before use.

Source: [`tools/watoom-code/test-learned-lessons.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test-learned-lessons.mjs). Description basis: filename summary.

## tools/watoom-code/test-lmb-provenance.mjs

Test fixture/check: test lmb provenance. Inspect the source before use.

Source: [`tools/watoom-code/test-lmb-provenance.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test-lmb-provenance.mjs). Description basis: filename summary.

## tools/watoom-code/test-prompt-guard-consistency.mjs

Test fixture/check: test prompt guard consistency. Inspect the source before use.

Source: [`tools/watoom-code/test-prompt-guard-consistency.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test-prompt-guard-consistency.mjs). Description basis: filename summary.

## tools/watoom-code/test-read-access.mjs

Test fixture/check: test read access. Inspect the source before use.

Source: [`tools/watoom-code/test-read-access.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test-read-access.mjs). Description basis: filename summary.

## tools/watoom-code/test-read-shell-permission.mjs

Test fixture/check: test read shell permission. Inspect the source before use.

Source: [`tools/watoom-code/test-read-shell-permission.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test-read-shell-permission.mjs). Description basis: filename summary.

## tools/watoom-code/test-review-schema-consistency.mjs

Test fixture/check: test review schema consistency. Inspect the source before use.

Source: [`tools/watoom-code/test-review-schema-consistency.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test-review-schema-consistency.mjs). Description basis: filename summary.

## tools/watoom-code/test-searxng.mjs

Test fixture/check: test searxng. Inspect the source before use.

Source: [`tools/watoom-code/test-searxng.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test-searxng.mjs). Description basis: filename summary.

## tools/watoom-code/test-unreal-shell-guard.mjs

Test fixture/check: test unreal shell guard. Inspect the source before use.

Source: [`tools/watoom-code/test-unreal-shell-guard.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test-unreal-shell-guard.mjs). Description basis: filename summary.

## tools/watoom-code/test-visual-final-resume.mjs

Test fixture/check: test visual final resume. Inspect the source before use.

Source: [`tools/watoom-code/test-visual-final-resume.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test-visual-final-resume.mjs). Description basis: filename summary.

## tools/watoom-code/test-worker-request-integrity.mjs

Test fixture/check: test worker request integrity. Inspect the source before use.

Source: [`tools/watoom-code/test-worker-request-integrity.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test-worker-request-integrity.mjs). Description basis: filename summary.

## tools/watoom-code/test_animation_sampling.py

Test fixture/check: test animation sampling. Inspect the source before use.

Source: [`tools/watoom-code/test_animation_sampling.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test_animation_sampling.py). Description basis: filename summary.

## tools/watoom-code/test_asset_capture.py

Test fixture/check: test asset capture. Inspect the source before use.

Source: [`tools/watoom-code/test_asset_capture.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test_asset_capture.py). Description basis: filename summary.

## tools/watoom-code/test_asset_capture_bazzite.py

Test fixture/check: test asset capture bazzite. Inspect the source before use.

Source: [`tools/watoom-code/test_asset_capture_bazzite.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test_asset_capture_bazzite.py). Description basis: filename summary.

## tools/watoom-code/test_capture_integration.py

Operator-only integration acceptance against the fixed keyed rig fixture.

Source: [`tools/watoom-code/test_capture_integration.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test_capture_integration.py). Description basis: module docstring.

## tools/watoom-code/test_capture_pose_blender.py

Operator integration fixture. Run only inside an external4GiB Blender unit.

Source: [`tools/watoom-code/test_capture_pose_blender.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test_capture_pose_blender.py). Description basis: module docstring.

## tools/watoom-code/test_drive_model_session.py

Test fixture/check: test drive model session. Inspect the source before use.

Source: [`tools/watoom-code/test_drive_model_session.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test_drive_model_session.py). Description basis: filename summary.

## tools/watoom-code/test_game_godot_game.py

Test fixture/check: test game godot game. Inspect the source before use.

Source: [`tools/watoom-code/test_game_godot_game.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test_game_godot_game.py). Description basis: filename summary.

## tools/watoom-code/test_game_terrain_export.py

Test fixture/check: test game terrain export. Inspect the source before use.

Source: [`tools/watoom-code/test_game_terrain_export.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test_game_terrain_export.py). Description basis: filename summary.

## tools/watoom-code/test_game_validation_manifest.py

Test fixture/check: test game validation manifest. Inspect the source before use.

Source: [`tools/watoom-code/test_game_validation_manifest.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test_game_validation_manifest.py). Description basis: filename summary.

## tools/watoom-code/test_game_worker_routing.py

Test fixture/check: test game worker routing. Inspect the source before use.

Source: [`tools/watoom-code/test_game_worker_routing.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test_game_worker_routing.py). Description basis: filename summary.

## tools/watoom-code/test_godot_game_spec.py

Test fixture/check: test godot game spec. Inspect the source before use.

Source: [`tools/watoom-code/test_godot_game_spec.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test_godot_game_spec.py). Description basis: filename summary.

## tools/watoom-code/test_llm_router_context.py

The router's /v1/models application\_context follows each model's real llama-server context \(owner 2026-11-19\): --ctx-size or LLAMA\_ARG\_CTX\_SIZE from the Deployment scaled 100K per 128K, looked up through the public alias, 100000 when unknow

Source: [`tools/watoom-code/test_llm_router_context.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test_llm_router_context.py). Description basis: module docstring.

## tools/watoom-code/test_llm_router_performance.py

Tests the router's embedded reasoning-level performance aggregation without starting a server.

Source: [`tools/watoom-code/test_llm_router_performance.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test_llm_router_performance.py). Description basis: module docstring.

## tools/watoom-code/test_llm_router_switch_wait.py

The router's begin\_inference waits out an in-flight model switch instead of answering 503 \(no server started\).

Source: [`tools/watoom-code/test_llm_router_switch_wait.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test_llm_router_switch_wait.py). Description basis: module docstring.

## tools/watoom-code/test_operator_scripts_compile.py

Every operator-side worker script must at least compile: a SyntaxError in one only shows up as 'Helper did not produce result' for the model.

Source: [`tools/watoom-code/test_operator_scripts_compile.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test_operator_scripts_compile.py). Description basis: module docstring.

## tools/watoom-code/test_pose_preparation.py

Test fixture/check: test pose preparation. Inspect the source before use.

Source: [`tools/watoom-code/test_pose_preparation.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test_pose_preparation.py). Description basis: filename summary.

## tools/watoom-code/test_pose_worker_integration.py

Operator-only real-worker regression using an unconstrained synthetic FK fixture.

Source: [`tools/watoom-code/test_pose_worker_integration.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test_pose_worker_integration.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--plan`, `--prefix`, `--source`.

## tools/watoom-code/test_repair_game_request.py

Test fixture/check: test repair game request. Inspect the source before use.

Source: [`tools/watoom-code/test_repair_game_request.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test_repair_game_request.py). Description basis: filename summary.

## tools/watoom-code/test_rig_pose_contract.py

Test fixture/check: test rig pose contract. Inspect the source before use.

Source: [`tools/watoom-code/test_rig_pose_contract.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test_rig_pose_contract.py). Description basis: filename summary.

## tools/watoom-code/test_staging_path.py

Test fixture/check: test staging path. Inspect the source before use.

Source: [`tools/watoom-code/test_staging_path.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test_staging_path.py). Description basis: filename summary.

## tools/watoom-code/test_sync_rig_projects.py

Test fixture/check: test sync rig projects. Inspect the source before use.

Source: [`tools/watoom-code/test_sync_rig_projects.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test_sync_rig_projects.py). Description basis: filename summary.

## tools/watoom-code/test_terrain_spec.py

Test fixture/check: test terrain spec. Inspect the source before use.

Source: [`tools/watoom-code/test_terrain_spec.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test_terrain_spec.py). Description basis: filename summary.

## tools/watoom-code/test_toolkit_service_fence.py

Test fixture/check: test toolkit service fence. Inspect the source before use.

Source: [`tools/watoom-code/test_toolkit_service_fence.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test_toolkit_service_fence.py). Description basis: filename summary.

## tools/watoom-code/test_unenrolled_requests.py

Test fixture/check: test unenrolled requests. Inspect the source before use.

Source: [`tools/watoom-code/test_unenrolled_requests.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test_unenrolled_requests.py). Description basis: filename summary.

## tools/watoom-code/test_worker_status.py

Tests for worker\_status.py: fixture receipts and fakes only; nothing touches a real worker, the journal or the network.

Source: [`tools/watoom-code/test_worker_status.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/test_worker_status.py). Description basis: module docstring.

## tools/watoom-code/tests/bootstrap_isolated.py

Test fixture/check: bootstrap isolated. Inspect the source before use.

Source: [`tools/watoom-code/tests/bootstrap_isolated.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/bootstrap_isolated.py). Description basis: filename summary.

Declared CLI options: `--evidence`.

## tools/watoom-code/tests/test_agentmemory_transfer.py

Test fixture/check: test agentmemory transfer. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_agentmemory_transfer.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_agentmemory_transfer.py). Description basis: filename summary.

## tools/watoom-code/tests/test_backup.py

Test fixture/check: test backup. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_backup.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_backup.py). Description basis: filename summary.

## tools/watoom-code/tests/test_backup_offhost.py

Test fixture/check: test backup offhost. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_backup_offhost.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_backup_offhost.py). Description basis: filename summary.

## tools/watoom-code/tests/test_bazzite_wrappers_structure.py

Guards against a dedent slipping code out of a nested helper \(regression: NameError 'reason' in game\_bazzite.not\_started\).

Source: [`tools/watoom-code/tests/test_bazzite_wrappers_structure.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_bazzite_wrappers_structure.py). Description basis: module docstring.

## tools/watoom-code/tests/test_blender_job.py

Test fixture/check: test blender job. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_blender_job.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_blender_job.py). Description basis: filename summary.

## tools/watoom-code/tests/test_bounded_process.py

Test fixture/check: test bounded process. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_bounded_process.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_bounded_process.py). Description basis: filename summary.

## tools/watoom-code/tests/test_build_environment.py

Test fixture/check: test build environment. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_build_environment.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_build_environment.py). Description basis: filename summary.

## tools/watoom-code/tests/test_capture_profiles.py

Test fixture/check: test capture profiles. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_capture_profiles.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_capture_profiles.py). Description basis: filename summary.

## tools/watoom-code/tests/test_coordinator_hot_reload.py

Test fixture/check: test coordinator hot reload. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_coordinator_hot_reload.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_coordinator_hot_reload.py). Description basis: filename summary.

## tools/watoom-code/tests/test_creative_release.py

Test fixture/check: test creative release. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_creative_release.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_creative_release.py). Description basis: filename summary.

## tools/watoom-code/tests/test_game_session_watchdog.py

Test fixture/check: test game session watchdog. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_game_session_watchdog.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_game_session_watchdog.py). Description basis: filename summary.

## tools/watoom-code/tests/test_game_worker_bridge.py

Test fixture/check: test game worker bridge. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_game_worker_bridge.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_game_worker_bridge.py). Description basis: filename summary.

## tools/watoom-code/tests/test_image_prompt_wizard.py

Deterministic CPU-only acceptance of the shared image wizard; no image jobs.

Source: [`tools/watoom-code/tests/test_image_prompt_wizard.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_image_prompt_wizard.py). Description basis: module docstring.

## tools/watoom-code/tests/test_lmb_provenance.py

Test fixture/check: test lmb provenance. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_lmb_provenance.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_lmb_provenance.py). Description basis: filename summary.

## tools/watoom-code/tests/test_maintenance_recovery.py

Test fixture/check: test maintenance recovery. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_maintenance_recovery.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_maintenance_recovery.py). Description basis: filename summary.

## tools/watoom-code/tests/test_memory_outbox.py

Test fixture/check: test memory outbox. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_memory_outbox.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_memory_outbox.py). Description basis: filename summary.

## tools/watoom-code/tests/test_model_context.py

Test fixture/check: test model context. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_model_context.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_model_context.py). Description basis: filename summary.

## tools/watoom-code/tests/test_model_display_names.py

Test fixture/check: test model display names. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_model_display_names.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_model_display_names.py). Description basis: filename summary.

## tools/watoom-code/tests/test_native_lmb_receipts.py

Isolated native qualifier receipt tests; subprocesses are mocked, Unreal never runs.

Source: [`tools/watoom-code/tests/test_native_lmb_receipts.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_native_lmb_receipts.py). Description basis: module docstring.

## tools/watoom-code/tests/test_orphan_claims.py

Test fixture/check: test orphan claims. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_orphan_claims.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_orphan_claims.py). Description basis: filename summary.

## tools/watoom-code/tests/test_project_captures.py

Test fixture/check: test project captures. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_project_captures.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_project_captures.py). Description basis: filename summary.

## tools/watoom-code/tests/test_reasoning_variants.py

Test fixture/check: test reasoning variants. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_reasoning_variants.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_reasoning_variants.py). Description basis: filename summary.

## tools/watoom-code/tests/test_regression_failure_reason.py

Test fixture/check: test regression failure reason. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_regression_failure_reason.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_regression_failure_reason.py). Description basis: filename summary.

## tools/watoom-code/tests/test_release_guard.py

Test fixture/check: test release guard. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_release_guard.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_release_guard.py). Description basis: filename summary.

## tools/watoom-code/tests/test_release_ledger.py

Test fixture/check: test release ledger. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_release_ledger.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_release_ledger.py). Description basis: filename summary.

## tools/watoom-code/tests/test_restarted_claims.py

Test fixture/check: test restarted claims. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_restarted_claims.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_restarted_claims.py). Description basis: filename summary.

## tools/watoom-code/tests/test_router_migration.py

Test fixture/check: test router migration. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_router_migration.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_router_migration.py). Description basis: filename summary.

## tools/watoom-code/tests/test_skill_collection.py

Test fixture/check: test skill collection. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_skill_collection.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_skill_collection.py). Description basis: filename summary.

## tools/watoom-code/tests/test_swift_context.py

Test fixture/check: test swift context. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_swift_context.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_swift_context.py). Description basis: filename summary.

## tools/watoom-code/tests/test_unreal_export.py

Test fixture/check: test unreal export. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_unreal_export.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_unreal_export.py). Description basis: filename summary.

## tools/watoom-code/tests/test_verification_loop.py

Test fixture/check: test verification loop. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_verification_loop.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_verification_loop.py). Description basis: filename summary.

## tools/watoom-code/tests/test_verified_model_capabilities.py

Test fixture/check: test verified model capabilities. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_verified_model_capabilities.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_verified_model_capabilities.py). Description basis: filename summary.

## tools/watoom-code/tests/test_worker_directories.py

Test fixture/check: test worker directories. Inspect the source before use.

Source: [`tools/watoom-code/tests/test_worker_directories.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/tests/test_worker_directories.py). Description basis: filename summary.

## tools/watoom-code/toolkit-restart-acceptance.py

Crash only an owned isolated Toolkit controller; prove its independent Job stays fenced.

Source: [`tools/watoom-code/toolkit-restart-acceptance.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/toolkit-restart-acceptance.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--source-overlay`.

## tools/watoom-code/toolkit-service-fence-acceptance.py

Owned legacy-image HTTP/Service drain and exact restoration acceptance.

Source: [`tools/watoom-code/toolkit-service-fence-acceptance.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/toolkit-service-fence-acceptance.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/watoom-code/toolkit_release_fence.py

Legacy-Service bootstrap plus the maintained durable Toolkit admission fence.

Source: [`tools/watoom-code/toolkit_release_fence.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/toolkit_release_fence.py). Description basis: module docstring.

## tools/watoom-code/toolkit_service_fence.py

One-time bootstrap fence for the legacy Toolkit without durable admission.

Source: [`tools/watoom-code/toolkit_service_fence.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/toolkit_service_fence.py). Description basis: module docstring.

## tools/watoom-code/unreal_export_spec.py

Declarative Unreal pack export request: which purchased pack, folder and asset classes; no paths or engine arguments.

Source: [`tools/watoom-code/unreal_export_spec.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/unreal_export_spec.py). Description basis: module docstring.

## tools/watoom-code/validate-fenced-gui.py

Prepare one owned memory fixture, then validate the published GUI under admission fencing.

Source: [`tools/watoom-code/validate-fenced-gui.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/validate-fenced-gui.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--fixture`, `--prepare`.

## tools/watoom-code/validate-handoff.py

Bounded owned native handoff acceptance; never replays an existing journal.

Source: [`tools/watoom-code/validate-handoff.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/validate-handoff.py). Description basis: module docstring.

Declared CLI options: `--deployment`, `--evidence`, `--verify-existing`.

## tools/watoom-code/validate-live-memory.py

Bounded authenticated API/GUI smoke test in a newly owned Git project; no inference.

Source: [`tools/watoom-code/validate-live-memory.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/validate-live-memory.py). Description basis: module docstring.

Declared CLI options: `--deployment`, `--evidence`, `--namespace`, `--playwright-module`.

## tools/watoom-code/validate-prompt-builder.py

Validate the published prompt page without submitting work, under the existing native fence.

Source: [`tools/watoom-code/validate-prompt-builder.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/validate-prompt-builder.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/watoom-code/validate-skills-gui.py

Read-only authenticated public Skills GUI acceptance while native execution admission is fenced.

Source: [`tools/watoom-code/validate-skills-gui.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/validate-skills-gui.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/watoom-code/verification_loop.py

Phase 2 of the learning loop: harness-run verification graders for a changeset.

Source: [`tools/watoom-code/verification_loop.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/verification_loop.py). Description basis: module docstring.

Declared CLI options: `--evidence`, `--path`.

## tools/watoom-code/verify-iac.py

Read-only verification of maintained WatooM changes against deployed state. Never emits credentials, skill contents, Kubernetes secrets or configuration bodies.

Source: [`tools/watoom-code/verify-iac.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/verify-iac.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/watoom-code/worker_directories.py

Prepare only bounded Godot worker writable mounts; never remove caches.

Source: [`tools/watoom-code/worker_directories.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/worker_directories.py). Description basis: module docstring.

## tools/watoom-code/worker_status.py

Worker status snapshot for the command center \(Bazzite worker, RIG worker, server worker\).

Source: [`tools/watoom-code/worker_status.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/worker_status.py). Description basis: module docstring.

Declared CLI options: `--no-bazzite`, `--out`, `--prom`.

## tools/watoom-code/workflow-candidate-recovery.py

Owned candidate only: supported interruption, durable queued input, restart, resume, compaction.

Source: [`tools/watoom-code/workflow-candidate-recovery.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/workflow-candidate-recovery.py). Description basis: module docstring.

Declared CLI options: `--evidence`.

## tools/watoom-code/workspace-policy/capability_maintenance.py

Bounded read-only health refresh over existing native catalogue and learning stores. No model calls, engine jobs, source updates, package promotion or cleanup.

Source: [`tools/watoom-code/workspace-policy/capability_maintenance.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/workspace-policy/capability_maintenance.py). Description basis: module docstring.

Declared CLI options: `--iac-root`, `--output`.

## tools/watoom-code/workspace-policy/guard.mjs

Source component: guard. Inspect the source before use.

Source: [`tools/watoom-code/workspace-policy/guard.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/workspace-policy/guard.mjs). Description basis: filename summary.

## tools/watoom-code/workspace-policy/lesson_audit.py

Advisory principle/recipe review adapted from the installed audit-agents skill. Never rewrites source, promotes a recipe, removes evidence, or weakens acceptance.

Source: [`tools/watoom-code/workspace-policy/lesson_audit.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/workspace-policy/lesson_audit.py). Description basis: module docstring.

## tools/watoom-code/workspace-policy/provision.py

Idempotent host-side Homelab/LLM checkout and native policy installer. No reload, model call or session mutation.

Source: [`tools/watoom-code/workspace-policy/provision.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/workspace-policy/provision.py). Description basis: module docstring.

Declared CLI options: `--apply`, `--source`.

## tools/watoom-code/workspace-policy/register.py

Register/name the native project through supported APIs; no session creation or model call.

Source: [`tools/watoom-code/workspace-policy/register.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/workspace-policy/register.py). Description basis: module docstring.

Declared CLI options: `--iac-root`.

## tools/watoom-code/workspace-policy/test.mjs

Source component: test. Inspect the source before use.

Source: [`tools/watoom-code/workspace-policy/test.mjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/workspace-policy/test.mjs). Description basis: filename summary.

## tools/watoom-code/workspace-policy/test_health.py

Test fixture/check: test health. Inspect the source before use.

Source: [`tools/watoom-code/workspace-policy/test_health.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-code/workspace-policy/test_health.py). Description basis: filename summary.

## tools/watoom-toolkit/agent.py

WatooM Toolkit API: fixed jobs only. No arbitrary shell or package installs over HTTP.

Source: [`tools/watoom-toolkit/agent.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/agent.py). Description basis: module docstring.

## tools/watoom-toolkit/asset_catalog.py

Bounded metadata-only indexing of the existing read-only creative library.

Source: [`tools/watoom-toolkit/asset_catalog.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/asset_catalog.py). Description basis: module docstring.

## tools/watoom-toolkit/blender_3d.py

Trusted CPU Blender generator/inspection/export entry point. Artist source is preserved.

Source: [`tools/watoom-toolkit/blender_3d.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/blender_3d.py). Description basis: module docstring.

## tools/watoom-toolkit/creative.py

Creative operations reuse Toolkit jobs, publication, CPU workers and native scoped dispatch.

Source: [`tools/watoom-toolkit/creative.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/creative.py). Description basis: module docstring.

## tools/watoom-toolkit/creative_blender.py

Library-derived preparation reusing the existing Blender QA, six renders and export validator.

Source: [`tools/watoom-toolkit/creative_blender.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/creative_blender.py). Description basis: module docstring.

## tools/watoom-toolkit/creative_blender_common.py

Source component: creative blender common. Inspect the source before use.

Source: [`tools/watoom-toolkit/creative_blender_common.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/creative_blender_common.py). Description basis: filename summary.

## tools/watoom-toolkit/creative_character.py

Preserve an existing weighted character and derive only a missing compatible Run.

Source: [`tools/watoom-toolkit/creative_character.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/creative_character.py). Description basis: module docstring.

## tools/watoom-toolkit/creative_isolated_test.py

One owned bounded CPU worker exercises maintained creative code against read-only library sources.

Source: [`tools/watoom-toolkit/creative_isolated_test.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/creative_isolated_test.py). Description basis: module docstring.

Declared CLI options: `--additional-asset-id`, `--asset-id`, `--evidence`, `--operation`, `--parameters`, `--seed`.

## tools/watoom-toolkit/creative_material.py

Derive bounded PBR maps from an indexed existing image; no learned or baked claim.

Source: [`tools/watoom-toolkit/creative_material.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/creative_material.py). Description basis: module docstring.

## tools/watoom-toolkit/creative_verify.gd

Source component: creative verify. Inspect the source before use.

Source: [`tools/watoom-toolkit/creative_verify.gd`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/creative_verify.gd). Description basis: filename summary.

## tools/watoom-toolkit/creative_world.py

Seeded editable environment composition from indexed portable library props.

Source: [`tools/watoom-toolkit/creative_world.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/creative_world.py). Description basis: module docstring.

## tools/watoom-toolkit/dungeon_blender.py

Compose verified Vulkan-baked source modules using the native assembly transforms. This fixed CPU stage never evaluates downloaded Python or modifies source modules.

Source: [`tools/watoom-toolkit/dungeon_blender.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/dungeon_blender.py). Description basis: module docstring.

## tools/watoom-toolkit/dungeon_layout.py

Deterministic, bounded dungeon topology for the existing world pipeline. Coordinates are Unreal centimetres. Module placement/rendering are separate gates.

Source: [`tools/watoom-toolkit/dungeon_layout.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/dungeon_layout.py). Description basis: module docstring.

Declared CLI options: `--out`, `--seed`.

## tools/watoom-toolkit/dungeon_pipeline.py

Native dungeon preparation for the existing creative world operation. Verified adapter annotations live on existing Catalog records, not a second registry. This module does no model calls, engine launches, or source writes.

Source: [`tools/watoom-toolkit/dungeon_pipeline.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/dungeon_pipeline.py). Description basis: module docstring.

## tools/watoom-toolkit/dungeon_recipes.py

Pure bounded recipes from native inspection rows; these do not register or verify adapters.

Source: [`tools/watoom-toolkit/dungeon_recipes.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/dungeon_recipes.py). Description basis: module docstring.

## tools/watoom-toolkit/dungeon_unreal.py

Native dungeon assembly and real collision/navigation QA in an isolated editor project. Original pack namespaces must be staged or mounted read-only; this saves only GeneratedDungeon.

Source: [`tools/watoom-toolkit/dungeon_unreal.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/dungeon_unreal.py). Description basis: module docstring.

## tools/watoom-toolkit/dungeon_verify.gd

Source component: dungeon verify. Inspect the source before use.

Source: [`tools/watoom-toolkit/dungeon_verify.gd`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/dungeon_verify.gd). Description basis: filename summary.

## tools/watoom-toolkit/dungeon_worker.py

Fixed bounded CPU native-world worker; invoked only by the maintained Toolkit dispatch.

Source: [`tools/watoom-toolkit/dungeon_worker.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/dungeon_worker.py). Description basis: module docstring.

## tools/watoom-toolkit/engine_export.py

Trusted Blender 5.2 exporter for the existing isolated inspection worker.

Source: [`tools/watoom-toolkit/engine_export.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/engine_export.py). Description basis: module docstring.

## tools/watoom-toolkit/engine_playback_unreal.py

Reload saved assets in the real editor and prove component animation playback.

Source: [`tools/watoom-toolkit/engine_playback_unreal.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/engine_playback_unreal.py). Description basis: module docstring.

## tools/watoom-toolkit/engine_validate_worker.py

Existing Toolkit isolated inspection plus real Blender/Godot/Unreal acceptance.

Source: [`tools/watoom-toolkit/engine_validate_worker.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/engine_validate_worker.py). Description basis: module docstring.

## tools/watoom-toolkit/engine_verify.gd

Source component: engine verify. Inspect the source before use.

Source: [`tools/watoom-toolkit/engine_verify.gd`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/engine_verify.gd). Description basis: filename summary.

## tools/watoom-toolkit/engine_verify_unreal.py

Real installed UE import/reimport validator; isolated content only.

Source: [`tools/watoom-toolkit/engine_verify_unreal.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/engine_verify_unreal.py). Description basis: module docstring.

## tools/watoom-toolkit/fixed_layout.py

Bounded explicit board topology for the existing dungeon pipeline; no executable input.

Source: [`tools/watoom-toolkit/fixed_layout.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/fixed_layout.py). Description basis: module docstring.

## tools/watoom-toolkit/generator_deploy.py

WatooM generator deployment: audit -\> isolated build -\> image validation -\> stage -\> rollback. No production modifications. Audit is read-only. Apply requires --i-approve.

Source: [`tools/watoom-toolkit/generator_deploy.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/generator_deploy.py). Description basis: module docstring.

Declared CLI options: `--i-approve`.

## tools/watoom-toolkit/job_admission.py

Durable Toolkit admission on the existing state volume, including controller crashes.

Source: [`tools/watoom-toolkit/job_admission.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/job_admission.py). Description basis: module docstring.

## tools/watoom-toolkit/kube_worker.py

Short-lived fixed CPU jobs; controller has Jobs authority, workers have no API credential.

Source: [`tools/watoom-toolkit/kube_worker.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/kube_worker.py). Description basis: module docstring.

## tools/watoom-toolkit/publish_3d.py

Publish already-validated artifacts into a new immutable asset version directory.

Source: [`tools/watoom-toolkit/publish_3d.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/publish_3d.py). Description basis: module docstring.

## tools/watoom-toolkit/test_admission_http.py

Test fixture/check: test admission http. Inspect the source before use.

Source: [`tools/watoom-toolkit/test_admission_http.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/test_admission_http.py). Description basis: filename summary.

## tools/watoom-toolkit/test_asset_catalog.py

Test fixture/check: test asset catalog. Inspect the source before use.

Source: [`tools/watoom-toolkit/test_asset_catalog.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/test_asset_catalog.py). Description basis: filename summary.

## tools/watoom-toolkit/test_catalog_selected.py

Test fixture/check: test catalog selected. Inspect the source before use.

Source: [`tools/watoom-toolkit/test_catalog_selected.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/test_catalog_selected.py). Description basis: filename summary.

## tools/watoom-toolkit/test_creative.py

Test fixture/check: test creative. Inspect the source before use.

Source: [`tools/watoom-toolkit/test_creative.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/test_creative.py). Description basis: filename summary.

## tools/watoom-toolkit/test_dungeon_layout.py

Test fixture/check: test dungeon layout. Inspect the source before use.

Source: [`tools/watoom-toolkit/test_dungeon_layout.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/test_dungeon_layout.py). Description basis: filename summary.

## tools/watoom-toolkit/test_dungeon_pipeline.py

Test fixture/check: test dungeon pipeline. Inspect the source before use.

Source: [`tools/watoom-toolkit/test_dungeon_pipeline.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/test_dungeon_pipeline.py). Description basis: filename summary.

## tools/watoom-toolkit/test_dungeon_recipes.py

Test fixture/check: test dungeon recipes. Inspect the source before use.

Source: [`tools/watoom-toolkit/test_dungeon_recipes.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/test_dungeon_recipes.py). Description basis: filename summary.

## tools/watoom-toolkit/test_dungeon_worker_spec.py

Test fixture/check: test dungeon worker spec. Inspect the source before use.

Source: [`tools/watoom-toolkit/test_dungeon_worker_spec.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/test_dungeon_worker_spec.py). Description basis: filename summary.

## tools/watoom-toolkit/test_engine_validation.py

Test fixture/check: test engine validation. Inspect the source before use.

Source: [`tools/watoom-toolkit/test_engine_validation.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/test_engine_validation.py). Description basis: filename summary.

## tools/watoom-toolkit/test_fixed_layout.py

Test fixture/check: test fixed layout. Inspect the source before use.

Source: [`tools/watoom-toolkit/test_fixed_layout.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/test_fixed_layout.py). Description basis: filename summary.

## tools/watoom-toolkit/test_generator_deploy.py

Test fixture/check: test generator deploy. Inspect the source before use.

Source: [`tools/watoom-toolkit/test_generator_deploy.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/test_generator_deploy.py). Description basis: filename summary.

## tools/watoom-toolkit/test_job_admission.py

Test fixture/check: test job admission. Inspect the source before use.

Source: [`tools/watoom-toolkit/test_job_admission.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/test_job_admission.py). Description basis: filename summary.

## tools/watoom-toolkit/test_local_only.py

Test fixture/check: test local only. Inspect the source before use.

Source: [`tools/watoom-toolkit/test_local_only.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/test_local_only.py). Description basis: filename summary.

## tools/watoom-toolkit/test_m6_inspection.py

Published inspection must resolve only immutable, hash-verified local inputs.

Source: [`tools/watoom-toolkit/test_m6_inspection.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/test_m6_inspection.py). Description basis: module docstring.

## tools/watoom-toolkit/three_d.py

Typed fixed 3D Toolkit operations. No downloaded scripts or model runtimes are executed.

Source: [`tools/watoom-toolkit/three_d.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/watoom-toolkit/three_d.py). Description basis: module docstring.

## tools/writing-studio/tests/test_service.py

Offline tests for Writing Studio: fake LLM router and fake MOSS over real HTTP, real skill files from the repo.

Source: [`tools/writing-studio/tests/test_service.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/writing-studio/tests/test_service.py). Description basis: module docstring.

## tools/writing-studio/writing_studio_service.py

Writing Studio: creative writing and graphic-novel art, one page for the 25 creative-writing skills \(T-0099\).

Source: [`tools/writing-studio/writing_studio_service.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/tools/writing-studio/writing_studio_service.py). Description basis: module docstring.

Declared CLI options: `--default-model`, `--host`, `--moss-base`, `--output-dir`, `--port`, `--router-base`, `--skills-dir`.

