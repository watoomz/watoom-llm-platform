---
name: watoom-prompt-blender-godot
description: Create an efficient task prompt for blender assets or animation to godot, collecting pipeline-specific inputs before execution.
---
# Blender assets or animation to Godot

Prepare the specified blend or mesh file for Godot using the installed Blender route. Export only required runtime meshes/armatures, preserve materials and bake evaluated animation where appropriate. Validate GLB structure and finite values, import into Godot and check collisions/scale. For animation, verify source motion and imported motion at two distinct times, then inspect real captures.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "blender-godot",
  "title": "Blender assets or animation to Godot",
  "category": "Conversion",
  "availability": "available",
  "keywords": [
    "blender to godot",
    "convert blend"
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
