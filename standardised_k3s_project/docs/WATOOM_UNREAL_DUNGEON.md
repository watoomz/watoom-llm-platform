# WatooM Code: Unreal and dungeon pipelines

WatooM Code is the GUI at https://watoom-code.internal.homelab.example.

## Production runtime

- Application: 127.0.0.1:5000/watoom-code@sha256:145b0a42622e9e7c1eb58f76970a79b6383fdc1bc45df44c95c7687c25a983bc; source 319c2e2751588103847b5b96d8ccdbb4206d6d57.
- WatooM Code Swift stable application context: **100,000 tokens**, output **4,096**; maintained by watoom_code_swift_context_tokens in IaC. Swift backend capacity remains 131,072 and is a separate setting.
- Toolkit: 127.0.0.1:5000/watoom-toolkit@sha256:3b2368f5c45c8ebced2644ac6f316ef499512de912afa4c6be85a3e37212ef39; runtime source b201f68e6cc95e251c7fe9dfed0ea000e5b792b7.
- Accepted engine: /data/ai/toolchains/unreal/5.8.3/runtime-74dc43e1a653; actual runtime **5.8.3-0+UE5**. Workers mount /unreal-engine read-only.
- Original dirty engine /data/ai/assets/unreal-engine, purchased assets and game worlds remain preserved.
- Engine acceptance covered editor libraries, C++ fixture compilation, commandlets, actual Vulkan rendering and the original Unreal → GLTFExporter → GLB → Godot route.
- Builder, Forge and mixed two-level maps passed floor/wall/capsule tests, complete Recast paths including stairs, static textured rendering, editable map reopening and actual Godot geometry/material/collider import.

Current-runtime crash-symbol recertification completed on 19 October 2026 (Australia/Brisbane): **2,122 changed matching-debug modules PASS**, **one CRT-only instrumentation stub N/A**, and **63 unchanged ELF build IDs preserved with their prior receipt scope**. Modules without matching debug sidecars are excluded; this is not universal line coverage. Baseline-proven stale symbol mappings were privately backed up before replacement, while independent existing real symbols were protected. The deployed editor ELF hash is unchanged; model inference and Enshrouded restoration passed. The earlier base had 2,186 matching-debug placeholder backfills. Host reboot acceptance remains **NOT TESTED**.

## Production maintenance and rebuild policy

This accepted application, Toolkit and published engine are the production baseline. Future issues must be fixed in authoritative repository source and the normal build/IaC path, with regression checks for the affected behavior. Publish versioned artifacts, validate through the existing guarded promotion and rollback process, and update the documented pins and evidence. Do not leave manual repairs, historical report paths, retained recovery overlays or temporary helper scripts as dependencies of the final build.

The normal engine build is ansible/playbooks/unreal-engine.yml; artifact publication is unreal-engine-publish.yml, and optional complete-project staging is unreal-project.yml. Preserve the accepted runtime and active jobs while preparing fixes. A documented source build path and syntax checks are not proof of a fresh clean rebuild; that acceptance remains NOT TESTED.

The [Model Manager](MODEL_MANAGER.md) is separately deployed; its inference acceptance gates do not change accepted Unreal/asset-pipeline results.

## Content-only source-map PoCs

For editable static map authoring, use the accepted PythonScriptPlugin/EditorScriptingUtilities path before considering a custom C++ commandlet. The maintained operator route is tools/unreal/grid_layout.py and grid-map-probe.py under the existing bounded accept-render.py GPU owner. It needs no C++ build or .NET installation. The published engine already bundles working Linux .NET10; absence from PATH is not evidence that the runtime is missing.

The repaired Quest1 geometry PoC passed real map save/reopen, 273 floor traces, 13 doorway capsule sweeps and pixel review of both Vulkan captures. It has 26x19 cells at200cm, with221 solid-rock cells; the previous494-walkable-cell trace contradicted the source legend. It is an editable blockout, not finished art or a certified replica. Recast and gameplay are NOT TESTED/out of this PoC's scope.

Open /data/ai/projects/games/heroquest-quest1-poc/UnrealProject/GenLevel.uproject and /Game/Levels/Quest1. Captures are indexed at /data/ai/captures/games/heroquest-quest1-poc/heroquest-quest1/. The seven live agent guides now describe the content-only route and prohibit speculative UBT patching for simple actor placement.

This operator acceptance does not promote the staged native fixed_layout application/Toolkit candidate. Qwen must still inspect the installed schema and distinguish an available native capability from host-only tools.

## Use the native pipeline

Choose the project in WatooM Code. Ask the coordinator to search the shared asset catalog for dungeon-builder or dungeon-forge, choose a verified adapter, and run seeded native world.compose. All seven maintained agents describe the exact route.

watoom_specialist_list and watoom_specialist_run are **direct native functions**, intentionally excluded from Code Mode. Do not repeatedly search Code Mode, simulate tool-call XML or substitute portable mesh inspection for an Unreal load.

A verified run-function example:

~~~json
{
  "specialistID": "local-toolkit",
  "capability": "world.compose",
  "job": "my-project-dungeon-001",
  "payload": {
    "task": "3d-creative",
    "operation": "world",
    "asset_id": "ast_19b6932244a653b79a9778f2",
    "seed": 42,
    "timeout": 840,
    "dungeon": {"style": "dungeon-builder", "rooms": 4, "levels": 2}
  }
}
~~~

Use a stable job ID to recover the **same** project/agent/payload; use a new ID for intentionally different work. Completed replay returns persisted outputs without another worker. Cancelled/uncertain operations need reconciliation, never silent replay. Cancel through supported session interruption rather than killing processes.

Outputs include editable .umap, textured .glb, preview .png, manifest, native validation, seeded layout, assembly and provenance. Inspect physical/path results and the actual preview before integration. Existing optimize, character and material pipelines remain available.

## Shared library and compatibility

All current/future worker templates mount /data/ai/assets as /assets read-only. Use the existing global catalog at /data/ai/watoom-code/toolkit-state/asset-catalog/catalog.json. Do not create another catalog or copy whole packs into every project. The completed FAB reconciliation contains **51,609 records**, preserves all **6,384 prior records** and both verified Builder/Forge adapters, and accounts for **45,292 receipt-backed supported files**. Another 52 source files have unsupported formats and are not presented as compatible pipeline inputs.

All **18 selected owned packs are downloaded and checksum-verified**. All 18 scoped probes finished: two full Builder/Forge acceptances, 15 sampled native/GLB/Godot geometry passes, and one Blood FX native GeometryCache load pass. Blood FX motion, rendered fidelity and portable effects conversion remain **NOT TESTED**; a separate bake is required. These probes do not certify whole-pack shaders or animation. Swift and Enshrouded were restored after capacity lending; actual inference recovery passed.

Downloads are separate from compatibility acceptance. Reconcile receipt-verified files in bounded batches. Unreal assets need correct content namespaces and dependency closures. Dynamic effects, Alembic and arbitrary downloaded packs are not certified by static Builder/Forge acceptance.

Server-only FAB acquisition uses existing /data/ai/bin/epic-fab and private server auth. Do not transfer credentials or download through the desktop. Maintained tools/fab/download-owned.py owns one flock and enforces memory/disk/time bounds. --continue-on-error preserves failures while independent owned packs continue; it never bypasses checksums. The JSON SHA1 byte-order repair is pinned in tools/fab/epic-fab-source.json with an offline regression test.

Read /data/ai/helper-scripts/reports/dungeon-fab-current.txt and /data/ai/helper-scripts/reports/remaining-acceptance-current.txt for current progress. Never start a duplicate queue.

## Session-safe release and recovery

Use tools/watoom-code/deploy-platform.py with immutable images, accepted candidate evidence, verified catalog and the owned GUI fixture. Exact source/default pins and a restorable bundle are maintained in tools/watoom-code/source/source.json.

Promotion checks immediate execution/durable claims and holds application admission, Toolkit Service drain and UID1009 durable ownership. A shell lease can block deployment even when /api/session/active looks empty. Kubernetes readiness alone is insufficient. The host helper enters the private state directory before dropping UID; do not loosen ancestor permissions.

Private release reports preserve prior image/configuration/catalog/database snapshots. Independent old/new real Blender jobs and injected digest-failure rollback passed. Production promotion checked authenticated public API/GUI, prior MCP connections and all seven agents before releasing admission. Never overwrite concurrent changes, bypass GPU ownership or terminate user sessions.

## Skills and private instructions

The current installation preserves 57 native skills and seven agents, including the selectable creative writer. Approved/enabled skills apply through project/agent assignments at the next safe step; current conversation context is not rewritten.

Owner-sensitive instructions are sourced from /data/ai/private/native-skills/reverse-engineer-feature using a server-side copy in the maintained native-skills role. Preserve this source in the operator's private backup. Its body is excluded from published Git trees and history and is not a documentation artifact.

## Evidence

Deployed acceptance: /data/ai/helper-scripts/reports/dungeon-integration-20261017T140618Z/final-report.json.

Engine: /data/ai/helper-scripts/reports/unreal-recovery-20261016T213935Z/final-acceptance.json.

Native API/GUI/cancel/restart/rollback receipts and exact candidate restoration snapshots remain under the dungeon evidence native-candidate directory. The accepted candidate is at zero replicas with guards held.

## Hyper Combat offline starter — accepted

All original18 and subsequent8 selected owned assets are downloaded and hash-verified. The existing global Catalog has60,714 records with previous entries and Builder/Forge adapters preserved. A later13-item account inventory is discovery only, not a download or compatibility claim.

Hyper Combat passed actual UE5.8.3 Blueprint compilation, keyboard input and movement (about24m), health100→90, Vulkan SM6 lit/textured unobscured captures and fresh editor restart. The unified Hyper+GLTF engine exported a real GLB accepted by Godot4.7.2. The published engine also passed a real commandlet/export with both historical build locations hidden in a private mount namespace.

Current runtime: /data/ai/toolchains/unreal/5.8.3/runtime-74dc43e1a653. Editor SHA256:74dc43e1a653fe3a46f68a1b3db6c3500d04d0f68a8878c9aa1b76b36a08fad3. Toolkit engine mount and hash pin were promoted behind native execution and durable Toolkit fences; an isolated candidate verified the new mount and exact previous-engine rollback first. Application and Toolkit image digests did not change. The former engine remains available for rollback.

Use ansible/playbooks/unreal-project.yml to opt in to a NEW content-only project. See ansible/roles/unreal-project/README.md. The editable starter /data/ai/projects/games/hyper-combat-offline preserves3,195 content files, the /Game/Hyper namespace, maps, input and configuration; UID1009 access and descriptor/input hashes passed. The staging role refuses existing destinations, symlinks, code/plugin starters and online profiles. world.compose remains a geometry pipeline; it does not install complete gameplay projects.

This acceptance is OFFLINE. The source's stale BP_GameInstance_Base reference is replaced only in the project copy with /Script/Engine.GameInstance. Online HOI/Steam/EOS needs separate GameInstance/provider configuration and host/join/travel acceptance. Keep default engine plugins enabled and genuine complete UBT target metadata; never patch BuildIds.

Normal clean-checkout source build: ansible/playbooks/unreal-engine.yml, pinned UE5.8.3 source and complete official targets. Syntax/profile checks passed; an actual fresh-checkout rebuild remains **NOT TESTED**. The current runtime is materialized accepted build output, not evidence of such a rebuild. Publication through unreal-engine-publish.yml creates a self-contained versioned runtime without Git metadata, DDC, saved files or historical recovery-marker dependencies. No recovery coordinator or retained overlay is required by the running engine.

Godot gameplay-logic conversion is deferred until a game needs it; GLB transfers geometry, not Blueprint combat behavior. BloodFX motion/render and portable effects remain **NOT TESTED**. Nwiro Integration Kit and POT Linux execution are unvalidated (their descriptors exclude Linux); no automatic MCP connection is installed. Companion Character Previewer still needs its own preview/input/render acceptance.
