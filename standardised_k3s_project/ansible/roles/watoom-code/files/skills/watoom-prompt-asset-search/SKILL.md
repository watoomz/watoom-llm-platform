---
name: watoom-prompt-asset-search
description: Create an efficient task prompt for find assets for a project, collecting pipeline-specific inputs before execution.
---
# Find assets for a project

Find suitable existing assets for the specified asset description. Search the shared asset Catalog first using the installed asset.search route. Return a short ranked list with asset IDs, formats, dependencies, licence/source and actual compatibility evidence. Inspect only selected candidates. Do not download or copy whole packs.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "asset-search",
  "title": "Find assets for a project",
  "category": "Assets",
  "availability": "available",
  "keywords": [
    "find assets",
    "search assets",
    "catalogue search"
  ],
  "fields": [
    {
      "id": "query",
      "label": "Selection criteria",
      "help": "What should be found or indexed, desired formats and compatibility.",
      "required": true
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
