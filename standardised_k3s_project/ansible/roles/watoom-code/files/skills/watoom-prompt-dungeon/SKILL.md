---
name: watoom-prompt-dungeon
description: Create an efficient task prompt for create a procedural dungeon, collecting pipeline-specific inputs before execution.
---
# Create a procedural dungeon

Create a small editable Unreal dungeon for the specified dungeon description, using the specified builder or forge or mixed, the specified room count rooms, the specified level count levels and seed the specified seed. Search the shared Catalog for a verified adapter, inspect the installed world.compose schema and submit one stable job ID. Reconcile the job before retrying. Require native floor/wall/capsule checks and Recast connectivity including stairs, editable-map reopening and actual textured previews. Procedural generation is not an exact source-map replica.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "dungeon",
  "title": "Create a procedural dungeon",
  "category": "Worlds",
  "availability": "available",
  "keywords": [
    "dungeon",
    "procedural world"
  ],
  "fields": [
    {
      "id": "layout",
      "label": "Layout and scale",
      "help": "Rooms, levels, dimensions or cell grid; distinguish a procedural layout from an exact source map.",
      "required": true
    },
    {
      "id": "seed",
      "label": "Seed and generator choice",
      "help": "A reproducible seed and supported builder/generator, or let the agent propose one.",
      "required": false,
      "default": "Use seed 1729 for reproducibility and choose only a verified installed generator appropriate to the request."
    },
    {
      "id": "version",
      "label": "Engine and platform",
      "help": "Target engine version and platform, for example Unreal 5.8.3 on Linux.",
      "required": true,
      "default": "Use the verified installed engine and Linux-compatible route. Inspect the actual version before execution."
    }
  ]
}
```
