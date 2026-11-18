# Image scope fidelity — 2026-10-21

Metadata comparison confirmed the latest session requested three images but submitted one. Its queued positive and negative strings differed from the supplied labelled blocks. The requested model, pinned revision and sampling settings were unchanged. Prompt text and generated media were not reproduced in evidence.

Maintained and installed prompt-creator/image skills now distinguish serial GPU execution from complete same-turn batch submission. Added an optional Number of images field. Removed output-count wording from the per-image resolution default and replaced the imposed stylized-game-art default with a neutral requested-style policy. The explicit request wins over defaults. A missing output count still defaults to one.

Light positive-description clarity/grammar polish is allowed while retaining every requested subject, attribute, action, composition and supplied tag. Exact-text requests remain verbatim. The supplied negative block must pass unchanged, without additions or omissions. All N distinct requested outputs must be queued before ending the turn, with actual accepted count and exact receipt IDs reported; no invented preview/approval stop. Per-image variation is limited to requested differences. Native guards and GPU exclusivity remain in force.

Validation: 12 existing prompt-builder model tests pass; a neutral three-view bench fixture built through the real composePrompt implementation preserves description/tags, exact negatives and explicit count; the production browser acceptance passes across all 27 pipelines, verifies Number of images, copied prompt contents, clipboard, neutral defaults, mobile width and zero session/job submissions. Live skill-catalog markers and both installed skill files were verified under the native admission guard, which was released afterward. No session was resumed and no image generated.

Refresh an already open Prompt Builder and rebuild its copied prompt to receive these instructions. Previously copied prompts retain their old content. These checks validate form/instruction delivery and queue capability; they do not certify future model adherence or visual output quality.

Evidence: /data/ai/helper-scripts/reports/image-scope-fidelity-20261021.
