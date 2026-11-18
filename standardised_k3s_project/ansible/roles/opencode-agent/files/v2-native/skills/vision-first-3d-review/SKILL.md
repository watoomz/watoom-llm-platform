---
name: vision-first-3d-review
description: Mandatory VISION_FIRST_3D_REVIEW for creation, modification and acceptance of visible 3D assets, rigs, poses and animation in Blender, Godot and portable or engine asset workflows.
---

# VISION_FIRST_3D_REVIEW

Policy version: 1.0.0. Applies across WatooM projects to characters, creatures,
vehicles, props, environments, imported/generated/procedural meshes, rigging and
animation, GLB/GLTF/FBX/OBJ and engine workflows whenever appearance matters.

## Required execution

1. Identify the current source asset, design requirements and supplied references.
   Load the relevant Blender/Godot/engine skill for rendering and structural tests.
2. Render the actual current output after meaningful visual changes. Record source
   and image SHA256, source revision, render command, view, dimensions, framing,
   lighting and pose in project-local validation evidence. Never overwrite an
   active investigation or reuse stale captures for changed source.
3. Submit actual image bytes with native image read on a verified image-capable
   model route. A filename, metadata, OCR, scene graph or text report is not image
   input. Verify the tool response contains image content and the inference
   transport preserves that content. Record image hash, model identity and
   transport evidence reference; never log credentials or base64 image payloads.
   If that path cannot be verified, VISUAL_REVIEW=BLOCKED. Never fall back silently
   to text. Existing vision evidence is a baseline, not proof of a new review.
4. Compare every relevant view with requirements and actual reference images.
   Identify visible defects, repair, re-render and repeat. Use consistent framing
   and lighting for before/after evidence. Batch images within verified context
   limits; do not start concurrent local inference or alter model/GPU ownership.
5. Obtain independent final review from watoom-reviewer after the modifying child
   has finished. Preserve existing serial delegation and checkpoint ownership.
6. Run separate structural checks with appropriate Blender/mesh/engine tooling.
   Vision cannot certify topology, normals, UV validity, weights, pivots, units,
   GLB integrity, collisions or import correctness. Geometry cannot certify looks.

## Views

Characters/creatures: front, side, rear, three-quarter, relevant action pose and
actual game-camera view. Flying assets also require folded and extended wings,
mid-flap or glide, flight three-quarter, wing/body intersections, tail and legs.
Other assets use relevant inspection views; document why any required view is
inapplicable. Inspect current images rather than inferred geometry.

## Evidence and verdict

For each defect report image path/hash, camera view, component/region, visible
problem, severity, evidence, correction, occurrence in other views and whether a
previous repair regressed. 'Looks good' is insufficient. Use an existing project
weighted rubric where applicable; never invent perfect scores.

Report independently: VISUAL_REVIEW and TECHNICAL_REVIEW, each PASS, FAIL, BLOCKED
or NOT_TESTED. Record required checks and evidence references for each. Visual
PASS requires genuine pixel analysis and independent final review. Technical PASS
requires appropriate structural validation. Final PASS requires every required
gate PASS. A known required defect makes final FAIL; otherwise an unavailable
required check makes BLOCKED; unperformed checks are NOT_TESTED and cannot PASS.
A structurally valid but visibly defective asset must FAIL visual acceptance.

## Failure and recovery

Unavailable endpoint, unsupported image content, missing/current-source captures,
unknown transport provenance or missing independent reviewer blocks visual
acceptance. Technical-only work may continue with explicit BLOCKED visual status.
The investigator reproduces one consolidated render/input/transport/model failure
with bounded evidence. Never restart inference, reroute models or interrupt active
work to satisfy this policy. Never infer projector compatibility from a configured
path alone; use verified matching artifact and behavioral evidence.

## Ownership and permanence

This native skill and mandatory agent/global references are installed by the
existing Ansible opencode-agent native skill/agent copy tasks. No new daemon,
proxy, wrapper, dependency or inference hot-path layer is required. Changes must
be staged in isolated IaC and deployed only after active OpenCode/vision work is
safely complete. Verify installed global rules, all four agent contracts, skill
discovery and an actual pixel challenge after deployment; copying files is not
proof of activation. Preserve Kali isolation and all existing execution rules.
