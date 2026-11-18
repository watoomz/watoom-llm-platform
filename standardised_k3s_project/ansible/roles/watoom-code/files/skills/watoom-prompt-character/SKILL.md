---
name: watoom-prompt-character
description: Create an efficient task prompt for prepare a character, collecting pipeline-specific inputs before execution.
---
# Prepare a character

Use character.prepare for indexed character the specified asset id and target the specified target engine. Inspect the installed requirements for skeleton/animations before running. Preserve hierarchy, scale, materials and existing clips. Validate actual Idle/Walk/Run motion where supplied, check two times per clip and review captures. Report missing rigging or animation rather than claiming it was created.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "character",
  "title": "Prepare a character",
  "category": "3D assets",
  "availability": "available",
  "keywords": [
    "character",
    "rig existing"
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
      "id": "clips",
      "label": "Rig and animation requirements",
      "help": "Required skeleton and clips, or static / preserve existing clips.",
      "required": false,
      "default": "Static unless the request needs animation. For existing animated sources preserve supplied clips and verify required motion."
    }
  ]
}
```
