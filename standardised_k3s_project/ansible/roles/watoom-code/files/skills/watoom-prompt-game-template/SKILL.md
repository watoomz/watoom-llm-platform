---
name: watoom-prompt-game-template
description: Create an efficient task prompt for game from a genre template, collecting pipeline-specific inputs before execution.
---
# Game from a genre template

Start a Godot game for the specified request from an installed, licence-checked genre template. Search the game template catalogue (platformer, metroidvania, deckbuilder, tower defense, RTS, top-down shooter, FPS/TPS, racing, souls-like, RPG, starter) and name the best match with its licence, pinned revision and declared Godot version; if none fits, say so rather than forcing one. Copy it into this project, never edit the library copy. Check it imports under the installed Godot, then implement only the specified request on top of it. Run headless import/tests and real captures. Keep attribution and licence files. Report what came from the template, what you changed and honest limitations.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "game-template",
  "title": "Game from a genre template",
  "category": "Games",
  "availability": "available",
  "keywords": [
    "game template",
    "genre template",
    "platformer template",
    "tower defense",
    "metroidvania",
    "deckbuilder",
    "rts",
    "racing template"
  ],
  "fields": [
    {
      "id": "idea",
      "label": "Game idea and genre",
      "help": "Name the genre and the core loop; the agent picks the closest installed template.",
      "required": true,
      "default": "A small game in the stated genre with one complete playable loop."
    },
    {
      "id": "scope",
      "label": "Scope and acceptance",
      "help": "What must work on top of the template and how it is checked.",
      "required": true,
      "default": "Reach one playable level or round using template systems; list acceptance checks and exclusions."
    },
    {
      "id": "output",
      "label": "Deliverables",
      "help": "Project path, run instructions and evidence.",
      "required": false,
      "default": "Project-local game, running instructions, captures and a report naming template, revision and licence."
    }
  ]
}
```
