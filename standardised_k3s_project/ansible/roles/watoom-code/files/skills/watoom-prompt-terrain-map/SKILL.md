---
name: watoom-prompt-terrain-map
description: Create an efficient task prompt for real-world terrain to godot, collecting pipeline-specific inputs before execution.
---
# Real-world terrain to Godot

Turn the real-world location the specified request into a Godot terrain for the specified request. Follow the terrain-map pipeline: resolve the area and extent, fetch elevation data, build the heightmap and mesh, import into Godot and use height_at() for placement. State the data source, resolution, licence and vertical exaggeration. Verify the mesh is not inverted and take real captures. Keep output project-local and report limitations.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "terrain-map",
  "title": "Real-world terrain to Godot",
  "category": "Games",
  "availability": "capability-gated",
  "keywords": [
    "terrain",
    "heightmap",
    "real world map",
    "latitude longitude",
    "elevation"
  ],
  "fields": [
    {
      "id": "place",
      "label": "Place or coordinates",
      "help": "Place name or latitude/longitude plus extent in metres.",
      "required": true,
      "default": "State the location and a square extent that keeps the mesh a sensible size."
    },
    {
      "id": "scope",
      "label": "Use and acceptance",
      "help": "What the terrain is for and the checks that define success.",
      "required": true,
      "default": "Imported terrain with correct orientation, placed test object and captures."
    },
    {
      "id": "output",
      "label": "Deliverables",
      "help": "Files, resolution and evidence.",
      "required": false,
      "default": "Heightmap, mesh/scene, source and licence notes, captures and a report."
    }
  ]
}
```
