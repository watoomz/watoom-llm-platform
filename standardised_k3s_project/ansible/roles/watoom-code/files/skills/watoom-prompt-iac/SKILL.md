---
name: watoom-prompt-iac
description: Create an efficient task prompt for maintain and activate an iac fix, collecting pipeline-specific inputs before execution.
---
# Maintain and activate an IaC fix

Fix the specified observed issue through the authoritative homelab IaC repository. Collect narrow read-only evidence first, preserve unrelated changes and prepare the exact change/snapshot/rollback. Validate affected source and activate within existing approval and ownership rules. Wait for active work to settle rather than forcing scaling or killing jobs. Verify live behaviour and persist the fix in the normal build path. No network/firewall/DNS/driver changes unless explicitly requested.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "iac",
  "title": "Maintain and activate an IaC fix",
  "category": "Development",
  "availability": "available",
  "keywords": [
    "iac",
    "kubernetes",
    "homelab fix"
  ],
  "fields": [
    {
      "id": "issue",
      "label": "Observed problem",
      "help": "Actual symptoms, errors or geometry defects and the expected result.",
      "required": true
    },
    {
      "id": "change",
      "label": "Expected change and checks",
      "help": "Concrete before/after behaviour and relevant tests or acceptance criteria.",
      "required": true,
      "default": "Inspect the existing implementation, make the smallest correct change for my request and run meaningful affected checks."
    }
  ]
}
```
