---
name: watoom-prompt-material
description: Create an efficient task prompt for derive a material, collecting pipeline-specific inputs before execution.
---
# Derive a material

Use material.derive for indexed source the specified asset id to prepare the specified material description for the specified target engine. Inspect supported fields and output maps first. Verify map roles, colour spaces, dimensions and material assignment, then inspect an actual rendered surface. Do not invent missing PBR channels or claim shader fidelity from texture files alone.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "material",
  "title": "Derive a material",
  "category": "3D assets",
  "availability": "available",
  "keywords": [
    "material",
    "pbr texture"
  ],
  "fields": [
    {
      "id": "source",
      "label": "Source asset, file or catalogue ID",
      "help": "Give the exact server path or catalogue ID; use none for a new asset.",
      "required": true
    },
    {
      "id": "materials",
      "label": "Parts and materials",
      "help": "Describe functional parts, their counts and materials, or ask for a proposed construction plan.",
      "required": false,
      "default": "Propose the smallest functional part list with semantic names and a compact reusable PBR palette."
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
