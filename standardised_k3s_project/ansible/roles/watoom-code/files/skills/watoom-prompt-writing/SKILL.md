---
name: watoom-prompt-writing
description: Create an efficient task prompt for creative writing, collecting pipeline-specific inputs before execution.
---
# Creative writing

Write the specified format about the specified premise, approximately the specified length, in the specified tone for the specified audience. Use the selectable creativewriter agent and relevant installed English writing/world-building skills. Preserve supplied canon, state only critical assumptions and produce the requested writing rather than a long plan. Save the draft and any continuity notes in this project.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "writing",
  "title": "Creative writing",
  "category": "Writing",
  "availability": "available",
  "keywords": [
    "creative writing",
    "write story",
    "graphic novel",
    "comic book",
    "manga",
    "webcomic",
    "write chapter",
    "write novel"
  ],
  "fields": [
    {
      "id": "writing",
      "label": "Format, length and audience",
      "help": "Document/story format, approximate length, tone, audience and existing canon.",
      "required": true,
      "default": "A concise first draft for a general adult audience in a clear natural tone; match any format, length or canon in my request."
    },
    {
      "id": "sources",
      "label": "Sources and constraints",
      "help": "Preferred primary sources, dates, exclusions or supplied documents.",
      "required": false,
      "default": "Use supplied sources first and authoritative primary references where needed; keep source collection bounded."
    }
  ],
  "description": "Co-write stories, chapters, comics and graphic novels, preserving canon and page-level illustration notes.",
  "requires": [
    "adaptation"
  ]
}
```
