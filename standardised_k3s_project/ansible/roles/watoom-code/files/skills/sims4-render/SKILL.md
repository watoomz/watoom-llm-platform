---
name: sims4-render
description: Route a specified Sims 4 blender render / turntable job to verified available skills and workers; normally selected by sims.
---
# Blender Render / Turntable

Reuse the sims handoff and ask only for essential missing information. Resolve the existing asset and still/clip/turntable request, requested view and optional timing.

Load asset-image-clip-capture. Follow its references/generic-capture.md; resolve textures, rig/pose and camera as needed. Existing recipes are optional shortcuts, not prerequisites. Load blender-rendering or blender-lighting-lookdev only for supported execution needs. Use a verified bounded capture worker. Do not select diffusion, character.prepare, fixed Godot scene capture or a full asset builder merely to preview an existing model.

Before execution, read the parent sims references/recipe-selection.md when reusing an existing asset or receipt. Verify current skill assignment, operation schema, source compatibility, worker readiness, output scope and resource limits. User intent/authorization, available agent tools, skill selection and worker capability are distinct. Coordinator owns progress; one execution-authorized builder handles a bounded edit, investigators clarify gaps read-only and reviewers inspect actual results read-only. Skill delegation does not create extra agents by itself.

Preserve originals and accepted checkpoints; use new versioned outputs. Reconcile uncertain native jobs instead of replaying. Report BLOCKED, unsupported and NOT_RUN precisely. A staged adapter or an authored PASS file is not a native receipt. Do not deploy, alter running services, bypass guards or launch heavy engines in the app shell.
