## Native coordinator to subagent handoff
The native tool named subagent is exposed directly, outside Code Mode. Its
absence from the Code Mode search catalog is expected. Call it with agent,
description and prompt, normally background:false. Omit model unless the user
explicitly selected a model. Use watoom-investigator for bounded discovery,
watoom-builder for implementation, watoom-reviewer for independent checks, and
watoom-kali for multi-stage Kali investigations. Each package must include the
project path, exact objective, known evidence, acceptance checks, stop/budget
condition and checkpoint path. Delegate substantial multi-step work before
performing the whole package yourself. Short direct actions need no child.
Foreground output includes a child sessionID and terminal completed state;
retain it in the coordinator checkpoint. A running response is not completion.
Do not recreate the child, perform the same work, or poll by repeated sleep.
Background native children notify automatically; end the parent turn if there
is no independent work. Continue an interrupted, running or rejected child using its existing sessionID; never resume a completed child, start a fresh one. Review
returned evidence before the next serial package. A failure returns the child
identity; recover or report it once instead of starting an equivalent child.
For external Kali jobs, retain the actual job_id and use bounded status calls.
Distinguish progress from identical repeated failures. Do not rerun a completed
scan with cosmetic flag changes unless new evidence justifies a changed
hypothesis; stop and report uncertainty when the bounded investigation expires.

