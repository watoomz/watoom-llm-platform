---
name: watoom-prompt-godot
description: Create an efficient task prompt for small native godot prototype, collecting pipeline-specific inputs before execution.
---
# Small native Godot prototype

Build a small Godot proof of concept for the specified idea in this project. Inspect existing code and installed Godot version first; reuse suitable indexed portable assets. Implement only the specified minimum scope. Run meaningful headless import/tests and actual visual checks. Keep generated output project-local and preserve unrelated gameplay. Deliver opening/running instructions, captures and honest remaining limitations.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "godot",
  "title": "Small native Godot prototype",
  "category": "Games",
  "availability": "available",
  "keywords": [
    "godot prototype",
    "game prototype"
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
      "id": "style",
      "label": "Style and references",
      "help": "Art direction, palette and reference paths/URLs; say none if there are no references.",
      "required": false,
      "default": "Simple readable stylized game art with restrained materials. Use supplied references; otherwise state the visual assumptions."
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
