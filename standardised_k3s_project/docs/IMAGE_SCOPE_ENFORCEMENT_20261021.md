> Superseded positive handling: the original canonical-positive copy collapsed per-image variations. See IMAGE_POSITIVE_VARIATIONS_20261021.md. Production now preserves per-image positives by default; reviewed negatives remain exact.

# Native image prompt transport enforcement — 2026-10-21

The latest session queued all three images, but its tool inputs omitted negative_prompt and rewrote the positive block. Additional skill instructions did not reliably prevent this model behavior. Two jobs completed; one queued invalid job was cancelled through Store.cancel, preserving its record. No replacement or resumed job was submitted.

A versioned native plugin now uses the supported execute.before hook to read the original reviewed Positive prompt and Negative prompt blocks from the native root user session. It copies those exact blocks into submit_image arguments before MCP execution, restoring omitted negatives and replacing assistant paraphrases. Child calls resolve their native parent chain. Exact continuation can recover a retained earlier reviewed block. Ordinary unstructured image calls retain their existing interface. Incomplete, ambiguous or oversized labelled scopes fail before submission; there is no silent truncation.

Existing request IDs, model revisions, sampling settings, coordinator guards, permissions, native admission, GPU ownership, restoration and result delivery remain unchanged. The plugin does not create calls or start inference. Existing same-turn batch submission rules remain in force; the observed latest batch already contained the requested three jobs.

Accepted native tool receipts include scope_transport/image_scope proof with source session/message, requested count, character counts and SHA-256 hashes. The execute.after hook appends that proof only to a confirmed successful job receipt; it does not certify generation or visual fidelity. New audit entries contain hashes/lengths, not prompt text. This lets the coordinator report what transport actually queued rather than claiming that omitted model arguments were dropped.

Draft polishing remains possible before final review/copy. Once labelled blocks are submitted, execution-time rewriting is disabled by this transport. This guarantees prompt transport for the supported reviewed-block workflow; it does not guarantee a diffusion model's visual interpretation.

IaC: image_scope.yml installs a source-hashed package and enable-image-scope.py merges only its plugin entry. The scoped watoom-code-image-scope.yml playbook deploys it without rolling out unrelated pending infrastructure changes. The normal role and seed template retain the integration. Location reload activates all loaded locations; plugin.list confirms watoom.image-scope active with the exact source hash.

Validation: 11 native scope/receipt tests pass. A neutral integration test deliberately supplies rewritten positives and omits negatives, then traverses the actual MCP HTTP implementation into a temporary SQLite queue; all three jobs contain the exact reviewed blocks and no worker/GPU runs. Config merge preservation/idempotency, rejected package path, YAML and enabled/disabled template checks pass. Native plugin activation and an open admission guard are verified. No production inference, new AI session or automatic resume was used for validation.

Evidence: /data/ai/helper-scripts/reports/image-scope-enforcement-20261021.
