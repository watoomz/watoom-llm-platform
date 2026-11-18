---
name: writing-plans
description: Use for a multi-step change before touching any files: turn the request or spec into a short plan with exact files, interfaces, ordered checkable steps and verification, then follow it. Skip for one-file edits.
---

# Writing plans

Write the plan for a careful engineer who has never seen this project. Exact paths, names and commands; no "add validation" without saying where and how.

## Where

Save it with your other task notes (for example `.opencode/work/<task>/plan.md`, beside `progress.md`) unless the operator names a place. Reread it before each step.

## Contents

1. **Goal**: one sentence. **Approach**: 2 or 3 sentences. **Constraints**: limits copied verbatim from the request (versions, naming, what must not change, protected branches).
2. **File map**: every file created or changed and its single responsibility. Follow the project's existing patterns; do not restructure unrelated code.
3. **Tasks**, each independently testable and small enough to review alone. Per task:
   - Files: create, modify (with line ranges when known), test.
   - Interfaces: what it uses from earlier tasks and what later tasks rely on, with exact names and types.
   - Steps, one action each with a checkable result: write the failing test, run it (expected failure), implement, run it (expected pass), checkpoint.
4. **Risks and review focus**: the inputs or conditions the request implies but the tests do not cover, most likely first, each with the test that pins it.
5. **Rollback**: how to undo the change if it goes wrong.

## Rules

- No placeholders ("TBD", "handle errors", "similar to Task 2"): write the real content.
- Smallest change that satisfies the request; leave unrelated files alone.
- Steps that need a command you cannot run are written as operator hand-offs with the full command and its revert (`operator-commands`).
- After writing, check the plan against the request line by line, and that names and signatures agree across tasks.
- Execute task by task, verifying each (`verification-before-completion`), updating `progress.md` as you go.

Ported and condensed from obra/superpowers (MIT), see `superpowers-LICENSE`.
