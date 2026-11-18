---
description: Run a persistent sequential WatooM research → plan → build → review workflow
agent: watoom-workflow
model: watoom/active-model
subagent: false
---

Run this assignment through the WatooM persistent workflow:

$ARGUMENTS

Work sequentially. Persist compact state under `.opencode/work/`. Do not commit,
stage, push, reset, clean, checkout or restore Git state.
