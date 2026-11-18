# Consistent visual receipt generation and recovery

The v2 receipt format is unchanged. Structured JSON review generation now uses
three schema branches matching the existing semantic validator:

- PASS: usable=true, zero framing issues.
- FAIL/BLOCKED with usable=true: zero to six framing issues.
- FAIL/BLOCKED with usable=false: at least one framing issue.

All branches retain the exact image path/hash, verified provider-qualified model,
observation requirements, and inference restrictions. No reported verdict is
rewritten and no framing issue is silently dropped. Ordinary native write receipts
still undergo the same semantic/provenance checks. Interface labels can be visible
observations; genuine assessment obstructions must remain framing issues.

A receipt about a supplied reference image records only model-reported observations
of that frame; it does not accept a game, asset, render pipeline or art milestone.

If a corrected runtime needs to reconcile an existing blocked child, the generic
grant_visual_recovery.grant helper requires a held native idle release fence, the
reviewed immutable guard hash, an actual matching parent/child/project relationship,
verified image presentation, and an unchanged image hash. It creates an audited
one-use grant for that exact child and image. The existing native hook consumes it.
The helper never edits session counters, writes a model receipt, grants acceptance,
or creates/replays a job. Repeating a consumed grant is refused.

Validation: test-review-schema-consistency.mjs compares JSON Schema with the
existing semantic validator, including contradictory PASS and wrong-image cases;
test-coordinator-guard.mjs covers provenance and single-use exact-child recovery.
Deploy only the scoped guard through the maintained idle release procedure.
