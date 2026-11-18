---
description: Resume a WatooM workflow from its project-local progress artifact
agent: watoom-workflow
model: watoom/active-model
subagent: false
---

Resume the matching WatooM workflow from `.opencode/work/`.

Requested task or slug:

$ARGUMENTS

Read the existing task/progress/research/plan/review artifacts first. Continue
from the exact recorded next action. Do not restart completed phases.
