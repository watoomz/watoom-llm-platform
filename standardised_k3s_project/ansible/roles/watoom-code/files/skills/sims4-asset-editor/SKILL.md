---
name: sims4-asset-editor
description: Route a specified Sims 4 asset creator / editor job to verified available skills and workers; normally selected by sims.
---
# Asset Creator / Editor

Reuse the sims handoff and ask only for essential missing information. Confirm creation versus editing, intended shape/style and existing source.

For supported Blender edits load the matching blender-* module. Use watoom-blender-asset-builder only for a full supported asset build; a request to render an existing model does not enter this path.

Before execution, read the parent sims references/recipe-selection.md when reusing an existing asset or receipt. Verify current skill assignment, operation schema, source compatibility, worker readiness, output scope and resource limits. User intent/authorization, available agent tools, skill selection and worker capability are distinct. Coordinator owns progress; one execution-authorized builder handles a bounded edit, investigators clarify gaps read-only and reviewers inspect actual results read-only. Skill delegation does not create extra agents by itself.

Preserve originals and accepted checkpoints; use new versioned outputs. Reconcile uncertain native jobs instead of replaying. Report BLOCKED, unsupported and NOT_RUN precisely. A staged adapter or an authored PASS file is not a native receipt. Do not deploy, alter running services, bypass guards or launch heavy engines in the app shell.
