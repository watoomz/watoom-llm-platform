---
name: sims4-release
description: Route a specified Sims 4 validator / release job to verified available skills and workers; normally selected by sims.
---
# Validator / Release

Reuse the sims handoff and ask only for essential missing information. Clarify validation-only versus candidate release and required version/compatibility notes.

Validate actual output/source hashes and receipts; require visual/game checks only for claims that need them. Release candidates remain unverified for unrun game checks. No automatic game install or public distribution.

Before execution, read the parent sims references/recipe-selection.md when reusing an existing asset or receipt. Verify current skill assignment, operation schema, source compatibility, worker readiness, output scope and resource limits. User intent/authorization, available agent tools, skill selection and worker capability are distinct. Coordinator owns progress; one execution-authorized builder handles a bounded edit, investigators clarify gaps read-only and reviewers inspect actual results read-only. Skill delegation does not create extra agents by itself.

Preserve originals and accepted checkpoints; use new versioned outputs. Reconcile uncertain native jobs instead of replaying. Report BLOCKED, unsupported and NOT_RUN precisely. A staged adapter or an authored PASS file is not a native receipt. Do not deploy, alter running services, bypass guards or launch heavy engines in the app shell.
