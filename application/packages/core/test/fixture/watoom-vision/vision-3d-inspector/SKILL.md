---
name: vision-3d-inspector
description: Inspect images and 3D assets, record geometry defects, produce reproducible CPU multiview renders, and verify controlled corrections on copies.
metadata:
  opencode/autoinvoke: false
---
# Vision and 3D inspection

Use the existing OpenCode skill tool and permission checks. This skill is loaded on demand; reading it must never start Blender, Unreal, a model, a scan or a server.

Identify an authorized project input and a new output directory first. Record source revision and SHA256. Preserve original assets. Separate deterministic geometry findings, image metadata and visual-quality judgments.

For deterministic inspection use the included `scripts/inspect_asset.py` in the already installed Blender 4.2.23 native Python interface. Invoke Blender with `--background --factory-startup --disable-autoexec --threads 1 --python-exit-code 2`. Never run scripts embedded in imported assets. Current supported inputs are OBJ, GLB and PNG; BLEND and Unreal source assets require additional linked-resource and automation review.

The typed operations are `inspect`, `render`, and `correct-duplicate`. Each requires a verified input root, output root and fresh output subdirectory. Unsupported formats and inaccessible assets fail explicitly. Keep input files read-only, disable network and GPU device access, and enforce CPU, RAM, process, disk and whole-process-group time limits in the existing execution owner. Inspection precedes rendering. Do not use an unbounded shell command as a substitute for enforced resource controls.

Geometry reports include topology counts, duplicate/degenerate faces, non-manifold edges, inconsistent normals, disconnected components, signed volume, transforms, missing materials/textures and UV validity. Source OBJ preflight records duplicate face lines before Blender's importer can normalize them. This is not a claim of complete geometry or material correctness.

Render six fixed views on CPU only: front, rear, left, right, top and perspective. Preserve raw PNGs and their hashes. Metadata-normalized PNGs retain image-affecting chunks for exact repeatability; manifests identify both files, camera, light, color management, resolution, engine, samples, seed and Blender version. Visually inspect the images: valid topology and successful export do not establish acceptable appearance.

Controlled correction currently supports only duplicate OBJ face records without UV/material/normal metadata. Write a new copy, verify source duplicates decrease, reimport it, repeat geometry checks and confirm the original hash is unchanged. Refuse broader or uncertain aesthetic changes. Do not silently discard UVs, materials, normals or transforms.

Produce an evidence manifest containing immutable artifact references and truthful PASS/PARTIAL/BLOCKED/FAIL states. Only verified findings may enter the existing workflow/outbox AgentMemory event contract; secret contents, binary assets and claims of aesthetic success must not be captured automatically. AgentMemory acknowledgment remains observed, not proven power-loss durable.

Swift-Qwen image inference requires a separately approved workload. The configured projector is configuration evidence only. Never load another GPU model, modify routing, perform GPU handover or bypass the authoritative controller.
