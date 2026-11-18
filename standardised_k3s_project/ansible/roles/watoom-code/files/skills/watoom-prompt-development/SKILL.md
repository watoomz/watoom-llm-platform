---
name: watoom-prompt-development
description: Create an efficient task prompt for implement and test a change, collecting pipeline-specific inputs before execution.
---
# Implement and test a change

Implement the specified change in this project. Inspect existing source/tests and choose the smallest correct change. Follow installed role/handoff rules with exact agent/session pairs and no duplicate modifying children. Run meaningful affected tests, check actual behaviour and preserve unrelated changes. Keep durable infrastructure changes in authoritative IaC; report the commit, validation and remaining blockers.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "development",
  "title": "Implement and test a change",
  "category": "Development",
  "availability": "available",
  "keywords": [
    "software development",
    "Python",
    "TypeScript",
    "debug application",
    "fix application bug",
    "regression tests",
    "implement feature"
  ],
  "fields": [
    {
      "id": "change",
      "label": "Expected change and checks",
      "help": "Concrete before/after behaviour and relevant tests or acceptance criteria.",
      "required": true,
      "default": "Inspect the existing implementation, make the smallest correct change for my request and run meaningful affected checks."
    },
    {
      "id": "scope",
      "label": "Scope and acceptance",
      "help": "What must work, what is excluded, and the observable checks that define success.",
      "required": true,
      "default": "Implement the smallest useful version of the requested job. State the acceptance checks and keep unrelated systems unchanged."
    }
  ],
  "description": "Implement and debug software features with the installed development tools, source inspection and regression tests.",
  "requires": [
    "watoom-developer"
  ]
}
```
