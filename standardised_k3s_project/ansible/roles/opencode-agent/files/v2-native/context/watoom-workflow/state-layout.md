# Workflow state layout

Project-local runtime state:

`.opencode/work/<task-slug>/`

Files:

- `task.md`
- `research.md`
- `plan.md`
- `progress.md`
- `review.md`
- `visual-review.md`
- `handoff.md`

`progress.md` is the authoritative resume point.

Every progress artifact should state:

- `Status: ACTIVE|BLOCKED|COMPLETE`
- current package;
- completed packages;
- actual validations;
- actual capture paths;
- blockers;
- exact next action.

Do not store secrets, credentials, tokens, dumps or unrelated logs in workflow
state.
