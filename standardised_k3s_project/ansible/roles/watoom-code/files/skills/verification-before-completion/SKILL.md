---
name: verification-before-completion
description: Use before saying work is done, fixed, passing or ready, and before handing a result to the operator. Requires evidence from a check you actually performed; if you cannot run the check, say it is unverified and hand the operator the command.
---

# Verification before completion

Core rule: **no completion claim without fresh evidence from this turn.** Confidence is not evidence.

## Gate (run it before every "done", "fixed", "passes", "ready")

1. **Name the check** that would prove the claim (test, validator, render, read-back of the changed file, diff).
2. **Do it now**, completely, not from memory of an earlier run. Read what you can read: re-open the file you changed, check the exact lines, run any validator tool you have.
3. **Read the whole result**: exit status, failure count, warnings.
4. **Match claim to evidence.** If the evidence does not support it, report the real state.
5. Only then state the claim, and say what you checked.

## You have no shell

When the proving check needs a command you cannot run (tests, flashing, deploy, service status), follow `operator-commands`: give the operator the full command and how to revert it, then report the work as **unverified until they return the output**. "Written, not yet run" is an honest status; "done" is not.

## Claim needs / does not count as

| Claim | Needs | Not enough |
| --- | --- | --- |
| Tests pass | the test output with 0 failures | an earlier run, "should pass" |
| Bug fixed | the original symptom no longer reproduces | the code changed |
| Build works | build output and exit status | the linter passing |
| Requirement met | a line-by-line check against the request | tests passing |
| Change is in place | the file re-read after the edit | the edit call succeeding |
| A helper/agent finished | you inspected its result files | its report saying success |

## Stop signs

"Should work", "probably", "seems to"; relief or celebration before checking; "just this once"; partial checks standing in for full ones; reporting success you inferred. Any of these means go back to step 1.

Ported and condensed from obra/superpowers (MIT), see `superpowers-LICENSE`.
