# Explicit fixed-layout dungeon candidate

Status: isolated native worker acceptance passed. Production application/Toolkit activation is a separate gate; existing production contracts must not be assumed to accept this candidate yet.

This extends the existing world.compose dungeon mode, Catalog adapters, scoped jobs and artifact publication. It adds no registry, scheduler or arbitrary command-execution service. The ordinary seeded mode is unchanged.

Select a VERIFIED pack anchor from the existing Catalog, not a random Blueprint. For the bounded fixed board, use:
~~~json
{
  "task":"3d-creative",
  "operation":"world",
  "asset_id":"<verified anchor>",
  "timeout":840,
  "dungeon":{
    "style":"dungeon-builder",
    "fixed_layout":{
      "cols":3,"rows":3,"cell_cm":200,
      "rock_cells":[[2,2]],
      "wall_edges":[[[0,0],[1,0]]],
      "door_edges":[[[0,0],[1,0]]]
    }
  }
}
~~~
Give the native dispatcher a stable job string. Do not supply operation_id. Fixed layout cannot be mixed with procedural rooms/levels/grid parameters. Coordinates are zero-based column/row; rows increase along engine Y. The rectangular board dimensions are cols*cell_cm by rows*cell_cm. Blocked cells receive no floor. Outer/blocked boundaries get walls; explicit edges add internal walls, and door edges replace that edge's wall with a verified doorway. Disconnected authored regions are preserved rather than falsely certified globally reachable.

The same pinned adapters, staged dependency closure, LOD/material bakes, piece budget, native floor/wall/capsule/Recast checks, GLB/Godot checks and source-integrity checks apply. Dense Forge boards may exceed4096 pieces; start with a small Builder board. Never silently replace a rejected layout with a random dungeon.

The candidate adds overhead.png alongside the existing editable map and perspective.png. These two portable previews use the existing CPU Blender route with verified static material bakes. They are not proof of Unreal dynamic-light/shader parity. Actual Vulkan editor captures use the existing audited controller-owned render supervisor, only after idle native executions AND real inference slots are verified. Missing /dev/dri or /dev/kfd in an app container does not prove the NVIDIA host lacks a GPU. NullRHI can build and inspect a map but cannot establish engine pixel acceptance.

Changed plans must receive a fresh isolated project/job identity. Preserve previous map and identity evidence; never delete/edit an identity file to force a different plan into the same job. Publish only validated artifacts and place captures in the common owner viewing tree described in PROJECT_STORAGE.md.

Reproducible candidate source:
~~~sh
python3 tools/watoom-code/restore-source.py --metadata tools/watoom-code/source/fixed-layout-candidate.json --destination /data/ai/projects/development/watoom-fixed-layout-candidate
~~~
The normal production source.json/bundle and deployed image pins remain unchanged until guarded promotion.
