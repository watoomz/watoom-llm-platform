---
name: context-budget
description: Explicit guidance for long local-model sessions when context/prefill cost is rising: narrow reads, avoid repeated outputs, use fresh child contexts selectively, and rely on native V2 compaction.
metadata:
  opencode/autoinvoke: false
---

# Local-model context budget

- Keep the builder's active context focused on the current implementation step.
- Do not repeatedly reread large unchanged files.
- Prefer grep/narrow reads over whole-file dumps.
- Use investigator/reviewer child contexts only when their fresh context is worth the new prefill.
- Never parallel-fan-out child agents on a single-slot backend.
- Preserve requirements, active errors, decisions, relevant file paths, and validation state across compaction.
- Native V2 checkpoint compaction is the primary history-management mechanism.
