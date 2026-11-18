---
name: requesting-code-review
description: Use after finishing a task or feature, and before handing work to the operator, to review your own change against the request. You cannot dispatch a reviewer or run git; re-read every changed file as a fresh reviewer, grade issues by severity, fix the serious ones, and say what you could not check.
---

# Reviewing your own change before hand-over

Catch problems before they spread. You have no subagents and no shell, so you are the reviewer: read the work as someone who did not write it and has only the request and the files.

## Steps

1. **Collect the context**: the request or plan, and the list of files you created or changed (from your task notes). If an exact diff matters, hand the operator the read-only command (`operator-commands`, for example `git diff --stat` and `git diff`) and review their pasted output.
2. **Re-read each changed file in full**, not from memory.
3. **Check, in this order:**
   - **Requirements**: everything asked is present; deviations are deliberate and stated.
   - **Correctness**: logic, edge and empty inputs, error handling, anything silently ignored. Behaviour the spec is silent on is judged by what a reasonable user would expect.
   - **Safety**: secrets, permissions, protected branches, destructive operations, anything touching production or networking.
   - **Fit**: follows the project's existing patterns and tools; smallest change; no unrelated edits.
   - **Tests and docs**: tests check behaviour, not mocks; edge cases covered; docs updated where the change needs it. Note which tests you could not run.
4. **Write it down** in `progress.md`: strengths first and specific, then issues as Critical (bugs, security, data loss, broken function), Important (design, missing behaviour, test gaps) or Minor (style, polish), then anything you set aside as out of scope with the reason.
5. **Act**: fix Critical now, fix Important before moving on, note Minor. Re-check after fixing (`verification-before-completion`).
6. **Hand-over**: tell the operator what you reviewed, what you fixed, what remains, and what was not verified because you could not run it. For an independent second opinion, say so: the operator can run a separate review of the branch.

## Stop signs

Skipping review because it is simple; reviewing from memory; ignoring a Critical item; calling untested work reviewed.

Ported and condensed from obra/superpowers (MIT), see `superpowers-LICENSE`. The subagent reviewer template was not ported.
