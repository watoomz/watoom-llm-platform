---
description: Independently review the current WatooM workflow milestone
agent: watoom-workflow
model: watoom/active-model
subagent: false
---

Review the current matching workflow milestone for:

$ARGUMENTS

Use the persisted task/plan/progress state. Delegate one independent review to
`watoom-reviewer`, including native inspection of any current visual captures.
Persist the findings. Do not implement repairs unless the user separately asks
to continue/resume the workflow.
