# Visual receipt path fix — 2026-10-21

The Magpie builder wrote its pixel review to the pipeline revision reports directory. The guard accepted only task-local .opencode paths, rejecting otherwise matching receipts and exhausting recovery. The model subsequently emitted tool-call XML as final text rather than a native call.

The maintained coordinator guard now accepts visual-review JSON files in the exact pending render revision sibling reports directory, with parent traversal rejected. Exact image path/hash, verified model, pixel basis, verdict and observations remain mandatory. A pending-review write schema exposes one accepted task-local path. When exhausted without tools, the final instruction explicitly requires JSON rather than tool-call XML.

The complete native guard regression suite passes, including revision isolation, traversal, mismatched hash and schema-path tests. The scoped IaC guard playbook deployed the immutable package; runtime activation and preservation of unrelated configuration were verified under the native deployment guard. A single-use operator recovery grant is bound to the existing parent, child and image hash. It permits an evidence recovery attempt, not acceptance without evidence. No job/session was started or resumed.

Evidence: /data/ai/helper-scripts/reports/visual-receipt-path-fix-20261021.

## Follow-up: front-view final response wrapper

The side-review recovery succeeded. A later front-view child returned a complete receipt prefixed by one prose sentence; strict whole-response JSON parsing rejected it. The native guard now extracts one bounded JSON object from a prose or Markdown wrapper, rejects ambiguous multiple objects, and applies the unchanged runtime image/hash/model/pixel-observation checks. XML tool calls remain invalid. Regression tests exercise actual child reconciliation with a wrapped receipt plus ambiguity, XML and size rejection. The scoped guard deployment was verified active before resuming the existing coordinator and exact pending front-view child. Evidence: /data/ai/helper-scripts/reports/visual-receipt-wrapper-fix-20261021.
