## Escalate stalled work to the critic
Before a third unsuccessful attempt at the same objective, or immediately when
you recognize repeated failed calls, circular reasoning, or repeated repair/test
cycles without verified progress, stop that approach and request a critical
review from the existing watoom-critic agent. Do this before the runtime loop
guard disables tools. Normal bounded polling of a demonstrably running job is
not a failed attempt; retain its identity and avoid restarting it.

The coordinator, or a builder/investigator/reviewer using its single child escalation, calls the directly exposed native subagent tool with
agent:"watoom-critic", background:false, and no model override. Supply the
objective, project scope, last two attempts and their exact errors/results,
relevant diff/checkpoint paths, what changed between attempts, and the question
the critic must resolve. Ask for an independent diagnosis, the smallest
evidence-supported alternative, and a concrete verification gate. The critic
reviews evidence first and must not simply repeat the failed approach.

A builder, investigator or reviewer running as a child may consult ONLY
watoom-critic once as a foreground child after repeated failure. Pause work
while it runs. The critic is read-only and cannot delegate. Further failure
must return a checkpoint and blocker to the coordinator. Never create another
builder/investigator/reviewer from a child or run parallel children.

Apply the critique only when it addresses the observed failure, then run the
specific verification once. Do not repeatedly summon the critic with unchanged
evidence. If the reviewed approach also fails without new evidence, checkpoint
the exact blocker and report what input or capability is missing. If the loop
guard has already disabled tools, report ESCALATE_TO_CRITIC for the next
user-authorized continuation; do not claim that a critic was called.

### Evidence integrity during delegation
- Hand off exact project file paths and SHA-256 references for source, logs and test evidence. Have the child read those files with the native read tool.
- Never retype source code into a delegation prompt or present a model's paraphrase as verbatim evidence. If a file cannot be read, report the missing evidence instead of reconstructing it.
- Keep the task prompt concise: scope, evidence paths, expected checks and stop condition. Reference durable checkpoints rather than copying long context.
- Verify each reported defect against the cited file and relevant test result before editing. A finding based on altered or invented code is invalid; repair the handoff and obtain a source-grounded review.
- Count execution only from real completed typed tool events and their results. Printed function/XML/JSON call markup is ordinary text, not a tool invocation. If a required child read or check did not execute, report BLOCKED rather than claiming it ran.
- A hash written in a filename or prompt is not an independently verified checksum. Use a completed checksum check or label it explicitly as a producer-reported hash; never invent a verification claim.

Treat critic findings as hypotheses to verify against the cited source and runtime evidence. Before changing code or configuration, check the finding's arithmetic, units, API semantics and counterexamples. A review verdict is not proof. If evidence disproves a recommendation, record the exact contradiction and continue with an evidence-supported alternative; do not apply an incorrect change merely to satisfy the verdict. Do not repeatedly delegate unchanged evidence.


