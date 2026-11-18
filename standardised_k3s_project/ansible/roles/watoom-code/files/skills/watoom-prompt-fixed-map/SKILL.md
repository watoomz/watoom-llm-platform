---
name: watoom-prompt-fixed-map
description: Create an efficient task prompt for recreate a supplied map, collecting pipeline-specific inputs before execution.
---
# Recreate a supplied map

Recreate the specified source map image as a small editable Unreal dungeon with the specified columns columns, the specified rows rows and the specified cell size cm cm cells. Derive walkable cells, blocked cells, internal wall edges and doors from actual pixel review; state uncertainties and validate bounds/connectivity. Discover whether fixed_layout is supported by the installed pipeline. Never submit a seeded world as an exact replica. If no supported fixed-layout/project assembly route exists, report the exact capability gap once. Use a fresh output for a changed plan; never delete identity guards. Deliver the editable project plus real overhead/perspective Unreal captures. No gameplay or additional systems.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "fixed-map",
  "title": "Recreate a supplied map",
  "category": "Worlds",
  "availability": "capability-gated",
  "keywords": [
    "recreate map",
    "source map",
    "fixed layout"
  ],
  "fields": [
    {
      "id": "source",
      "label": "Source asset, file or catalogue ID",
      "help": "Give the exact server path or catalogue ID; use none for a new asset.",
      "required": true
    },
    {
      "id": "layout",
      "label": "Layout and scale",
      "help": "Rooms, levels, dimensions or cell grid; distinguish a procedural layout from an exact source map.",
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
