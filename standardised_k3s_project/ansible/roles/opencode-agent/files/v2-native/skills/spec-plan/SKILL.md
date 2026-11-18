---
name: spec-plan
description: Explicit structured Context -> Spec -> Plan workflow for substantial features, migrations, refactors, or multi-step fixes before implementation.
metadata:
  opencode/autoinvoke: false
---

# Context -> Spec -> Plan

Use only when the task is substantial enough to justify planning overhead.

## Context
Record:
- current state;
- authoritative files;
- constraints;
- known failures;
- non-goals.

## Spec
Define:
- required outcome;
- acceptance criteria;
- safety boundaries;
- compatibility constraints.

## Plan
Create ordered, bounded tasks with validation after meaningful steps.

Track files may live under `.watoom/tracks/<slug>/`.

Planning never implies staging, committing, or pushing.
