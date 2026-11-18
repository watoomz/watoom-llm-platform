# Image positive variation correction — 2026-10-21

The canonical-positive transport guard replaced three distinct model-proposed prompts with one shared base prompt. With a shared seed this removed the requested variation. Negative-prompt transport was correct.

The native image-scope plugin now preserves each submitted positive prompt by default and continues copying the reviewed negative block exactly. Prompt Builder exposes Positive prompt handling with light polish and requested per-image variations as its default. An explicit verbatim selection copies the common positive block when that behavior is intended.

The change is maintained in the scoped image-scope IaC role and image/creator skill sources. Production was updated through the scoped playbook under the native deployment guard while inference was idle. Configuration outside plugin selection was preserved. No generation or session was started or resumed.

Validation: 13 native transport tests pass; a neutral three-view bench fixture through the real MCP HTTP queue retains three distinct positives and exact negatives. Production plugin hash and connected image MCP were verified. The production browser form, defaults, prompt construction, clipboard and pipeline checks passed without submitting a job. This verifies transport and UI, not generated visual quality.

Evidence: `/data/ai/helper-scripts/reports/image-positive-variation-fix-20261021`.
