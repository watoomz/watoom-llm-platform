---
name: watoom-prompt-procedural-mesh
description: Create an efficient task prompt for generate a procedural asset on cpu, collecting pipeline-specific inputs before execution.
---
# Generate a procedural asset on CPU

Generate the specified asset description with the installed typed CPU procedural generator registry: avian, quadruped, human, tree, terrain, building or rock. Discover the actual generator ID, bounded parameters and output contract before using the native 3D route. Use only the requested supported generator; do not execute downloaded code or substitute LLaMA-Mesh inference. Validate scale, geometry and export, and inspect the produced views. If rigging/animation is provided, verify actual motion and engine import before acceptance.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "procedural-mesh",
  "title": "Generate a procedural asset on CPU",
  "category": "3D assets",
  "availability": "available",
  "keywords": [
    "procedural mesh",
    "cpu generator"
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
      "id": "seed",
      "label": "Seed and generator choice",
      "help": "A reproducible seed and supported builder/generator, or let the agent propose one.",
      "required": false,
      "default": "Use seed 1729 for reproducibility and choose only a verified installed generator appropriate to the request."
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
