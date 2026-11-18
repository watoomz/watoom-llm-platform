---
name: watoom-prompt-effects
description: Create an efficient task prompt for validate an unreal effect such as bloodfx, collecting pipeline-specific inputs before execution.
---
# Validate an Unreal effect such as BloodFX

Validate selected effect the specified effect asset in an isolated project using the accepted Unreal runtime and supported fenced rendering. Preserve the source. Prove actual animation at multiple times, visible motion and material/render fidelity with captures. Static load, timeline metadata and successful export are not playback evidence. If portable Godot output is requested, inspect an explicitly supported bake/conversion route and prove imported motion separately; GLTF static export does not convert GeometryCache or Niagara logic.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "effects",
  "title": "Validate an Unreal effect such as BloodFX",
  "category": "Validation",
  "availability": "validation required",
  "keywords": [
    "bloodfx",
    "niagara",
    "effect playback"
  ],
  "fields": [
    {
      "id": "source",
      "label": "Source asset, file or catalogue ID",
      "help": "Give the exact server path or catalogue ID; use none for a new asset.",
      "required": true
    },
    {
      "id": "version",
      "label": "Engine and platform",
      "help": "Target engine version and platform, for example Unreal 5.8.3 on Linux.",
      "required": true,
      "default": "Use the verified installed engine and Linux-compatible route. Inspect the actual version before execution."
    },
    {
      "id": "capture",
      "label": "Views or playback to prove",
      "help": "Camera views, lighting and animation times or interactions that must be visible.",
      "required": true,
      "default": "Two useful views, normally front or overhead plus perspective; include two distinct playback times when motion is required."
    }
  ]
}
```
