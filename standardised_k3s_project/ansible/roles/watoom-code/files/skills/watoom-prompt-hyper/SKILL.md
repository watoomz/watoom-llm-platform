---
name: watoom-prompt-hyper
description: Create an efficient task prompt for start an offline hyper project, collecting pipeline-specific inputs before execution.
---
# Start an offline Hyper project

Stage a NEW offline Hyper Combat project from the verified complete source, preserving its /Game/Hyper namespace, Config and input. Use the maintained unreal-project IaC path; do not overwrite an existing project or treat mesh world.compose as complete-framework staging. The accepted test uses offline Engine.GameInstance. Do not assume BP_GameInstance_Base or online multiplayer support; HOI/provider setup is a separate project-specific task. Validate project load and applicable Blueprint/gameplay checks before claiming the new project works. If this session lacks host staging access, report that boundary once.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "hyper",
  "title": "Start an offline Hyper project",
  "category": "Worlds",
  "availability": "host workflow",
  "keywords": [
    "hyper combat",
    "offline hyper"
  ],
  "fields": [
    {
      "id": "source",
      "label": "Source asset, file or catalogue ID",
      "help": "Give the exact server path or catalogue ID; use none for a new asset.",
      "required": true
    },
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
    }
  ]
}
```
