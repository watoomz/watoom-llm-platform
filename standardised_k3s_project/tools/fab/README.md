# Shared FAB library and Unreal framework operations

All maintained acquisition, inspection, Catalog and resource-loan code lives here. Private authentication, receipts, paid assets and runtime logs remain outside Git. No separate database, command registry or MCP service is introduced.

- Discover owned assets with existing /data/ai/bin/epic-fab list --json; save the full response privately. Never repeat auth or install another client.
- download-owned.py --evidence <fresh report> consumes server-download-selection.json, keeps mandatory hashes/partials and enforces bounded resource/time/disk limits. One owner per queue.
- inspect-game-framework.py --evidence <acquisition report> --asset-id <owned ID> requires a completed receipt; source inspection is not runtime acceptance.
- reconcile-catalog.py --evidence <fresh report> --acquisition-evidence <completed queue> uses the supported existing Toolkit Catalog. --verify-only reuses a completed scan snapshot and batches after a validator fix; never duplicates indexing. It imports the real Catalog FORMATS/EXCLUDE policy, preserves prior records/verified adapters and distinguishes unsupported/excluded files.
- accept-hyper-combat.py performs an isolated core Blueprint load/compile with explicit required plugins and source Content read-only.
- repair-hyper-engine.py builds only required plugin modules in a separate engine CoW overlay, then repeats core Blueprint compilation. The maintained build profile is ../unreal/profiles/hyper-combat.json. It never patches BuildIds, changes the accepted engine, or treats compilation as combat/play/render acceptance.
- lend-model-capacity.py --evidence <report> --completion-file <owned native-status.json> and lend-game-capacity.py use exact snapshots and automatic restoration. The model helper uses native active-execution checks plus actual slots and the existing fenced GPU operator protocol. Explicit --allow-loading-primary requires every unready primary pod to return the observed HTTP503 Loading model health contract directly; readiness or failed networking alone is insufficient. Game shutdown remains graceful, with a bounded600s verification window. Never bypass another owner's lock or kill a user session.
- Read fresh continuation/native-coordinator/hyper-capacity-coordinators evidence before starting anything. Do not duplicate coordinators, restore over a concurrent configuration change or rerun completed receipts.

Hyper's Unreal game instance, input, UI and gameplay logic require project-scoped integration; GLB only transports compatible assets. A Godot behavior port is deferred until a game needs it. POT/NWIRO code plugins are inspection-only unless separately accepted; downloading them does not authorize automatic execution or MCP registration.

After actual native/play/render acceptance, persist the candidate engine mapping, dependencies and job template through the authoritative Ansible role and immutable image/source pins. Do not promote an unvalidated candidate merely because its build finished.

### Cached target metadata finalization

After successful module-only build, UBT BuildMode.GatherOutputItems selects module outputs and omits target metadata. If actual loader logs still report mismatched BuildIds, use repair-hyper-engine.py --evidence <existing evidence> --resume --finalize-target. This completes the cached isolated project target including genuine UBT metadata, within existing resource/deadline bounds. No manual manifest edits or accepted-installation rebuild. Preserve overlay and verify actual runtime acceptance afterwards.

## BloodFX native motion and portable sprites

The source GeometryCache contract is separate from static GLTF. BloodFX source
assets remain read-only. The maintained CPU-only adapter samples original Unreal
geometry/materials into fixed-view 256px RGBA frames (12fps, at most96 frames per
effect), then builds namespaced Godot SpriteFrames for AnimatedSprite3D. This is
a camera-dependent sprite bake, not editable3D cache or shader translation.

Install requirements-bloodfx.txt in the chosen Python environment. The acceptance
runner requires an existing accepted Unreal runtime and the verified installed
Godot4.7.2 binary (SHA256 checked), and a project containing the native read-only
inspection receipt. Keep project outputs under /data/ai/projects.

Run accept-bloodfx.py with explicit --project, --engine, --content and --godot.
It owns one project lock, waits at most1hour for7GiB measured headroom, and is
intended for a5GiB hard/4GiB soft memory,2CPU systemd unit with a2GiB host reserve.
It forces the installed lavapipe Vulkan ICD; no GPU/model/game ownership changes.
Each editor render is bounded25minutes and Godot import/playback is bounded.
Original files are hashed before/after. Actual rendered temporal pixels and
Godot playback must pass; timeline metadata alone is insufficient.

A successful serial run stops at TECHNICAL_PASS_VISUAL_REVIEW_PENDING. Review
actual native/Godot captures before publishing derived assets through the existing
shared Catalog. Never index unvalidated frames or claim portable3D animation.
Source-only implementation and synthetic Godot smoke tests do not certify BloodFX.
