---
name: watoom-prompt-captures
description: Create an efficient task prompt for capture an existing unreal or godot project, collecting pipeline-specific inputs before execution.
---
# Capture an existing Unreal or Godot project

Capture the existing the specified engine project/map the specified project or map without rebuilding its content. Discover the supported capture route and use legitimate GPU ownership/admission. Container /dev/dri absence does not establish that the host lacks NVIDIA hardware. Produce a useful overhead and perspective capture after shader/texture loading and UI repaint. Review actual pixels for framing, lighting, missing assets and dialogs. Nonblack PNG statistics are not visual acceptance.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "captures",
  "title": "Capture an existing Unreal or Godot project",
  "category": "Validation",
  "availability": "available",
  "keywords": [
    "capture project",
    "screenshot project"
  ],
  "fields": [
    {
      "id": "project",
      "label": "Existing project or map",
      "help": "Exact server project/map path; use new if staging a fresh project.",
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
