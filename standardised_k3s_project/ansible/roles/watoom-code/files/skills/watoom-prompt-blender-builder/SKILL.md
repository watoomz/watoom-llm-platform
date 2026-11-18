---
name: watoom-prompt-blender-builder
description: Create an efficient task prompt for build a blender game asset, collecting pipeline-specific inputs before execution.
---
# Build a Blender game asset

Author a new reference-driven Blender 4.2.23 asset using watoom-blender-asset-builder and selected installed EL4CTEO skills. Before geometry, propose a compact semantic part list and dimension/contact plan; assign materials to named parts, not fragile face heuristics. Start an empty scene. Use MODEL/MATERIALS/QA/EXPORT with automatic SOURCE_QA over the actual packed runtime source. Save runtime source/exports before adding preview floors. Run strict geometry/UV checks, actual Godot and Unreal import/playback when requested, and independently review multi-view renders. For animated assets prove source weights and motion plus imported playback. Never substitute a prepared fixture for the requested asset.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "blender-builder",
  "title": "Build a Blender game asset",
  "category": "3D assets",
  "availability": "available",
  "keywords": [
    "bench",
    "crate",
    "blender",
    "magpie",
    "new prop",
    "pavilion",
    "sculpt",
    "new asset"
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
      "id": "target",
      "label": "Target engine or output",
      "help": "For example Godot 4.7.2, Unreal 5.8.3, GLB, a report or a document.",
      "required": true,
      "default": "Godot 4.7.2, GLB plus preserved packed Blender source. Run the existing bounded native Godot/Unreal acceptance route for delivery."
    },
    {
      "id": "budget",
      "label": "Geometry and texture budget",
      "help": "Maximum triangles and texture resolution, or ask the builder to propose a budget.",
      "required": true,
      "default": "Static prop: under 2,000 triangles, textures at or below 1,024 px. Character/creature: under 50,000 triangles, textures at or below 2,048 px. Select the applicable budget and record it before modelling."
    },
    {
      "id": "style",
      "label": "Style and references",
      "help": "Art direction, palette and reference paths/URLs; say none if there are no references.",
      "required": false,
      "default": "Simple readable stylized game art with restrained materials. Use supplied references; otherwise state the visual assumptions."
    },
    {
      "id": "materials",
      "label": "Parts and materials",
      "help": "Describe functional parts, their counts and materials, or ask for a proposed construction plan.",
      "required": false,
      "default": "Propose the smallest functional part list with semantic names and a compact reusable PBR palette."
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
