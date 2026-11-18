---
name: watoom-prompt-kali
description: Create an efficient task prompt for authorised native kali tools, collecting pipeline-specific inputs before execution.
---
# Authorised native Kali tools

Perform an authorised security check of the specified explicit owned target limited to the specified scope and allowed tests. Discover the installed native Kali tool interface and execute through the configured route from WatooM Code. Do not invent shell flags or endpoints, broaden scope, change networking or expose credentials. Keep a concise command/result record and evidence-backed findings. Ask before any destructive action or action outside the stated scope.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "kali",
  "title": "Authorised native Kali tools",
  "category": "Security",
  "availability": "available",
  "keywords": [
    "security check",
    "kali",
    "penetration test"
  ],
  "fields": [
    {
      "id": "authorization",
      "label": "Authorised target and allowed tests",
      "help": "Exact owned/authorised targets, allowed tests and exclusions. This does not expand permission.",
      "required": true
    },
    {
      "id": "scope",
      "label": "Scope and acceptance",
      "help": "What must work, what is excluded, and the observable checks that define success.",
      "required": true,
      "default": "Read-only assessment within my explicitly authorised targets and allowed tests; report findings without exploitation or configuration changes."
    },
    {
      "id": "output",
      "label": "Deliverables",
      "help": "Required files, formats and evidence, or let the agent propose the smallest useful set.",
      "required": false,
      "default": "Preserved source, requested portable output, actual preview(s) and a concise report with validation and remaining limits."
    }
  ]
}
```
