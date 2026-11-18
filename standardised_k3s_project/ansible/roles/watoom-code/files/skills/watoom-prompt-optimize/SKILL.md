---
name: watoom-prompt-optimize
description: Create an efficient task prompt for optimise an asset, collecting pipeline-specific inputs before execution.
---
# Optimise an asset

Prepare an optimised copy of indexed asset the specified asset id for the specified target engine, targeting the specified polygon budget triangles and the specified texture budget. Use asset.optimize after inspecting its installed schema. Preserve source materials/UVs and record before/after counts, bounds and visual differences. Import and validate the output before calling it game-ready.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "optimize",
  "title": "Optimise an asset",
  "category": "3D assets",
  "availability": "available",
  "keywords": [
    "optimise",
    "optimize",
    "reduce triangles"
  ],
  "fields": [
    {
      "id": "source",
      "label": "Source asset, file or catalogue ID",
      "help": "Give the exact server path or catalogue ID; use none for a new asset.",
      "required": true
    },
    {
      "id": "target",
      "label": "Target engine or output",
      "help": "For example Godot 4.7.2, Unreal 5.8.3, GLB, a report or a document.",
      "required": true,
      "default": "Godot 4.7.2, portable GLB and preserved source. Use Unreal validation when the selected route requires it or I request it."
    },
    {
      "id": "budget",
      "label": "Geometry and texture budget",
      "help": "Maximum triangles and texture resolution, or ask the builder to propose a budget.",
      "required": true,
      "default": "Use a conservative game-asset budget: static props under 2,000 triangles and textures at or below 1,024 px; propose a suitable explicit budget if the requested asset needs more."
    }
  ]
}
```
