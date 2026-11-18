---
name: watoom-prompt-game-blueprint
description: Create an efficient task prompt for full game from a design interview, collecting pipeline-specific inputs before execution.
---
# Full game from a design interview

Build the specified request end to end using the game-development blueprint. Run the design intake interview first, then write a milestone plan of small bounded tasks sized for the local models, routing each task to the matching WatooM pipeline, asset flow or genre template. After every milestone run the critique, performance and code-design gate before continuing. Keep output project-local, record checkpoints, and stop for owner input where the interview left a decision open.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "game-blueprint",
  "title": "Full game from a design interview",
  "category": "Games",
  "availability": "available",
  "keywords": [
    "build a game",
    "game blueprint",
    "milestone plan",
    "game design"
  ],
  "fields": [
    {
      "id": "game",
      "label": "Game concept",
      "help": "One or two sentences: genre, player fantasy and platform.",
      "required": true,
      "default": "A small complete game in the stated genre."
    },
    {
      "id": "scope",
      "label": "Scope and milestones",
      "help": "Target size, deadline and what is out of scope.",
      "required": true,
      "default": "Three small milestones ending in a playable build; exclusions listed."
    },
    {
      "id": "output",
      "label": "Deliverables",
      "help": "Plan file, builds and evidence.",
      "required": false,
      "default": "Milestone plan, playable build, captures and a gate report per milestone."
    }
  ]
}
```
