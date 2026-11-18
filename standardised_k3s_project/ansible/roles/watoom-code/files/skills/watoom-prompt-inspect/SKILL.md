---
name: watoom-prompt-inspect
description: Create an efficient task prompt for inspect a mesh, collecting pipeline-specific inputs before execution.
---
# Inspect a mesh

Inspect the indexed asset the specified asset id through the installed asset.inspect or mesh-inspection route. Report topology, finite bounds, scale, pivot, normals, UV/material slots and collision/rig information actually verified. Produce a project-local preview and inspect its pixels. Preserve the source.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "inspect",
  "title": "Inspect a mesh",
  "category": "3D assets",
  "availability": "available",
  "keywords": [
    "inspect mesh",
    "inspect asset"
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
    }
  ]
}
```
