---
name: validation-recovery
description: Use when typecheck, build, tests, lint, or smoke validation fails repeatedly or an edit loop is making no progress.
---

# Validation recovery

1. Capture the exact current failure.
2. Read the smallest relevant current source region.
3. Make a material source/configuration change.
4. Confirm the edit was not a no-op.
5. Rerun only the narrow failing validation.
6. Expand to broader validation after it passes.

Never rerun an identical failing command after `No changes to apply`.

A malformed/unavailable tool call is a tool-call recovery problem, not evidence
that permissions need widening.

Do not remove required features merely to make validation green.

## Tool-capability recovery

A malformed, misrouted, syntactically invalid, or unavailable tool invocation is
a tool-call recovery problem. It is not evidence that the underlying capability
does not exist.

Examples include parser/runtime errors such as `Unknown identifier`, invalid
tool arguments, selecting a JavaScript evaluator when shell execution was
required, or invoking the wrong execution surface.

When this happens:

1. preserve the original task and observed error;
2. identify the correct available tool or execution surface;
3. retry with the corrected tool when that remains within task scope;
4. report a capability as unavailable only when the correct capability itself
   is absent, denied, or fails for a concrete environmental reason;
5. never convert a failed tool invocation into an unsupported claim that a
   command, test, build, or runtime succeeded.

Do not repeatedly issue the same malformed call.
