---
name: watoom-prompt-unreal-godot
description: Create an efficient task prompt for unreal static assets to godot, collecting pipeline-specific inputs before execution.
---
# Unreal static assets to Godot

Convert selected Unreal asset/map the specified asset or map into static geometry for Godot. Preserve the authored /Game dependency namespaces, use the accepted native Unreal route to bake/finalise geometry, export via GLTFExporter to GLB, then import into Godot. Check finite geometry, scale, textures/materials, colliders and actual captures. Unreal Blueprints, plugin logic and GeometryCache effects do not automatically transfer through GLB.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "unreal-godot",
  "title": "Unreal static assets to Godot",
  "category": "Conversion",
  "availability": "available",
  "keywords": [
    "unreal to godot",
    "convert unreal"
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
      "id": "scope",
      "label": "Scope and acceptance",
      "help": "What must work, what is excluded, and the observable checks that define success.",
      "required": true,
      "default": "Implement the smallest useful version of the requested job. State the acceptance checks and keep unrelated systems unchanged."
    }
  ]
}
```
