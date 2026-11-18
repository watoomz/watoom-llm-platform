---
name: watoom-landscape-mesh-builder
description: Assess and use the owned Landscape Mesh Builder UE Blueprint for heightmap-to-static-mesh terrain baking; not a Godot plugin or foliage/material repair tool.
---
# Landscape Mesh Builder
Owned Fab ID `48364dff3c874aa5b75903ba9d77bc5a`. Source `/data/ai/assets/fab/landscape-mesh-builder-48364dff` (Toolkit `/assets/fab/landscape-mesh-builder-48364dff`). Preserve purchased originals. Read current qualification/status at `/data/ai/assets/catalog/landscape-mesh-builder.json` before planning execution. The native project declares UE5.4 and GeometryScripting. Do not infer installed-runtime compatibility from version numbers; use real qualification evidence.

Use this tool as a candidate when the project needs heightmap-derived terrain mesh tiles, controlled geometry density or native Unreal terrain baking. It does not fix missing leaves, shader conversion, wrong colours or tree dependency omissions. For a Godot project, generate/bake in compatible Unreal then export compatible geometry/materials with the supported existing route; test import, collision, tile seams, scale, orientation and runtime performance. A UE Blueprint itself is not portable to Godot.

Publisher workflow: enable Geometry Script; supply a CPU-available heightmap and an actual static-mesh template with required collision/LOD settings; configure output directory/material; generate meshes, save them explicitly, then disable repeat generation. Inspect actual installed Blueprint properties/functions before choosing exact API names. Start with a tiny bounded sample; do not apply a4K heightmap or raise infinite-loop limits by default. Preserve source heightmap and dependency namespace.

Execution uses existing bounded native Unreal worker/operator controls; no new service, direct GPU borrowing, app-shell Unreal editor or guessed Toolkit conversion task. `tools/fab/qualify-landscape.py` qualifies native load/compile only. Neither its success nor Catalog indexing establishes mesh generation/export/visual acceptance. If the exact requested generation operation is not exposed, request an explicit bounded operator work package and report that integration gap; never claim the plugin is an enabled autonomous Toolkit operation.
