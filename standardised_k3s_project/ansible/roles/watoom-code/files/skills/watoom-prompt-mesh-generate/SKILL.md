---
name: watoom-prompt-mesh-generate
description: Create an efficient task prompt for generate a prototype with llama-mesh, collecting pipeline-specific inputs before execution.
---
# Generate a prototype with LLaMA-Mesh

Generate one simple the specified object description prototype with the existing synchronous watoom-llama-mesh MCP generate tool. Discover its actual arguments and use one stable request ID. Let the existing GPU controller own switching/restoration; never direct-scale models. Validate output geometry, then use Blender cleanup, sensible scale/pivot and an actual preview. Keep raw, cleaned and game-ready stages distinct. This is a prototype; do not claim textures, rigging or production quality without evidence.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "mesh-generate",
  "title": "Generate a prototype with LLaMA-Mesh",
  "category": "3D assets",
  "availability": "available",
  "keywords": [
    "llama-mesh",
    "llama mesh"
  ],
  "fields": [
    {
      "id": "dimensions",
      "label": "Dimensions and units",
      "help": "Width \u00d7 depth \u00d7 height, with units. Add functional dimensions such as seat height or doorway clearance.",
      "required": true,
      "default": "Propose sensible real-world dimensions for this object and state them in the construction plan before modelling. Honour any measurements in my request."
    },
    {
      "id": "style",
      "label": "Style and references",
      "help": "Art direction, palette and reference paths/URLs; say none if there are no references.",
      "required": false,
      "default": "Simple readable stylized game art with restrained materials. Use supplied references; otherwise state the visual assumptions."
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
