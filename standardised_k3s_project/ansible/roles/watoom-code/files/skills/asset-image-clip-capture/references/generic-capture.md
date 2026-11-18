# Generic capture decisions

The working Blender entrypoint is the native `watoom_asset_capture` tool. Start with the exact instructions in SKILL.md and external-blender-worker.md; do not rediscover workers or load every reference. This document covers conditional preparation, not extra execution interfaces.

## Source and preparation

Resolve the selected asset from current project/catalogue evidence. If there is a matching recipe/prepared source, verify its source/derivative/dependency hashes once and reuse it. Preserve originals and authored materials, textures, UVs, skinning and intended components. A task title or old success is not proof of source identity.

Without matching evidence, submit one external inspect job. Use its actual object/material/image/rig/Action metadata. Do not hide arbitrary untextured meshes or widgets by guessed prefixes; the worker hides verified bone custom shapes. Use explicit visibility edits for intended components. Resolve missing mandatory dependencies only from the selected source's declared roots and mappings. Missing textures fail rather than becoming fallback colours. Do not scan the library or silently substitute another asset.

The current declarative worker does not accept arbitrary texture rebinding/Python scripts. A supported prepared cache can be reused; new texture/material repair requires a separately verified preparation operation. Report that exact integration need once rather than trying app-shell Blender or guessed wrapper modes. Respect source/runtime/addon compatibility: Blender5.2.1 support does not qualify legacy4.2-only scripts or arbitrary plugins.

## Pose and camera

Preserve the authored pose unless asked to change it. For requested articulation read pose-controls.md: inventory real controls/rest axes/constraints, select only supported edits, verify evaluated deformation, and inspect a preview. IK/translation/custom-property/retargeting needs are precise adapter gaps. Do not accept a static A-pose as a requested seated pose or create a new rig implicitly.

The current camera supports full-subject fitted front/three-quarter/side/back or preservation of an existing authored camera. Bounds are evaluated after pose. Newly authored portrait crops/custom cameras are not exposed by this manifest. Use a verified authored camera or report the needed preparation capability. Keep lights authored when requested; otherwise neutral studio lighting is available. User-requested appearance/quality remains the acceptance target.

## Efficient preview and final output

One small preview through the same4GiB worker can expose wrong pose/visibility, missing textures, clipping and framing. Reuse it as the final only when it meets the user's requested quality. Fix a concrete defect in a fresh revision; do not repeat broad discovery. Keep current budget reductions explicit: texture1k, subdivision1, CPU2threads. Requested higher quality needs actual measurement/validation, not merely a schema-valid resolution.

For video read video-capture.md: distinguish authored animation from camera orbit, set frame range/FPS, estimate total runtime and validate actual encoded motion. New animation choreography is a separate preparation operation. Never generate a lookalike with diffusion to replace asset capture.

## Completion

Read the exact root-owned status and result; verify source unchanged, cgroup limit, exit code, actual outputs/hashes/settings and pose-evidence when used. Inspect pixels for the requested pose, complete components, materials, framing and clipping. Clips also require frame/FPS/duration/codec and actual temporal review. Keep technical execution separate from visual acceptance.

Retain requests, inventories, relevant pose plan/evidence, logs, output frames/video, receipts and visual review. The current worker retains a reproducible manifest/inventory and source dependency references; it does not save a prepared.blend. Do not claim an editable derivative exists unless an actual supported preparation step saved one. Return actual usable media paths, and save scoped recipes only after acceptance. Stop repeating the same unsupported operation or unchanged failure.
