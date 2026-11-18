---
name: watoom-prompt-research
description: Create an efficient task prompt for research with searxng, collecting pipeline-specific inputs before execution.
---
# Research with SearXNG

Research the specified question using the configured web-search/SearXNG tools. Inspect available tools rather than guessing endpoints. Prefer primary sources, cite links next to findings, distinguish verified facts from inference and save a short sourced report. Keep searches bounded and avoid fetching unrelated pages.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "research",
  "title": "Research with SearXNG",
  "category": "Research",
  "availability": "available",
  "keywords": [
    "research",
    "investigate sources"
  ],
  "fields": [
    {
      "id": "scope",
      "label": "Scope and acceptance",
      "help": "What must work, what is excluded, and the observable checks that define success.",
      "required": true,
      "default": "Implement the smallest useful version of the requested job. State the acceptance checks and keep unrelated systems unchanged."
    },
    {
      "id": "sources",
      "label": "Sources and constraints",
      "help": "Preferred primary sources, dates, exclusions or supplied documents.",
      "required": false,
      "default": "Use supplied sources first and authoritative primary references where needed; keep source collection bounded."
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
