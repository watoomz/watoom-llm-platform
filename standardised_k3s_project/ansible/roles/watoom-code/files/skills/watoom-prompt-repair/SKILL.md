---
name: watoom-prompt-repair
description: Create an efficient task prompt for repair and export a mesh, collecting pipeline-specific inputs before execution.
---
# Repair and export a mesh

Repair the specified project mesh file using the installed mesh-repair/export route. Fix only confirmed geometry defects, preserve an original copy and record changes. Validate topology, normals, UVs, scale and exported geometry; compare actual before/after previews. Do not claim automatic rigging or animation.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "repair",
  "title": "Repair and export a mesh",
  "category": "3D assets",
  "availability": "available",
  "keywords": [
    "repair mesh",
    "fix normals",
    "non manifold"
  ],
  "fields": [
    {
      "id": "source",
      "label": "Source asset, file or catalogue ID",
      "help": "Give the exact server path or catalogue ID; use none for a new asset.",
      "required": true
    },
    {
      "id": "issue",
      "label": "Observed problem",
      "help": "Actual symptoms, errors or geometry defects and the expected result.",
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
