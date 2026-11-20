# Terrain export output contract

`game_terrain_export.py` (the operator) only trusts one file your script writes: `/job/output/manifest.json`.
Nothing printed to stdout/stderr is read for the pass/fail decision — only the log is kept for your own
debugging (`native.log`, pulled back alongside `output/`).

The operator's receipt is PASS only when **all** of:

- the container exited 0
- `output/` was pulled back successfully
- `manifest.json` parses and `manifest["status"]` is `"SUCCESS"` or `"PARTIAL"`
- `manifest["output"]["produced"]` is truthy
- the staged project tree is unchanged outside `Saved/`, `Intermediate/`, `DerivedDataCache/`, `output/`, `.git/`
  (your script may write anywhere under `output/`, but must not touch the rest of the staged copy)

Minimal shape (what the starter script in `init` already writes on failure, and what a full run should
write on success):

```json
{
  "status": "SUCCESS",
  "output": {"produced": true, "files": ["terrain.glb"]},
  "failure_reason": null
}
```

`status`/`output.produced` are the only fields the operator reads; anything else in `manifest.json` is
yours (file list, vertex counts, whatever helps you verify the export afterward).

## A real, working export pattern (for assets, not landscape specifically)

`ue_export_assets.py` (the Fab-pack export worker, same unattended `-ExecutePythonScript` style) already
exports `StaticMesh`/`SkeletalMesh` assets to glTF/FBX successfully in this engine version:

```python
import unreal
def gltf_options():
    o = unreal.GLTFExportOptions()
    for key, value in [('bake_material_inputs', getattr(unreal.GLTFMaterialBakeMode, 'DISABLED', None)),
                        ('export_vertex_skin_weights', True), ('export_mesh_quantization', False)]:
        if value is None: continue
        try: o.set_editor_property(key, value)
        except Exception: pass
    return o

ok = unreal.GLTFExporter.export_to_gltf(asset, str(target_path), gltf_options(), set())
```

A `Landscape` actor is not a loadable asset the same way (it's a level actor, not a package you
`unreal.load_asset()` by path) — this part is **not yet proven working in this codebase**. The documented
starting points to try, in order, and verify against this engine's actual Python API before trusting the
result:

1. `unreal.EditorLevelLibrary.get_all_level_actors()` filtered to `unreal.Landscape`/`unreal.LandscapeProxy`
   instances, then `unreal.AssetExportTask` against the proxy if it exposes one (some engine versions
   expose landscape-to-static-mesh export via the Landscape editor utilities, not a bare `AssetExportTask`).
2. If no direct export path exists, converting the Landscape to a static mesh first (editor utility /
   Blueprint-callable function) and exporting *that* with the same `AssetExportTask`/`GLTFExporter` pattern
   shown above.

Whichever you use, read the result back (triangle/vertex count, bounding box) and put it in `manifest.json`
so a PASS actually means something — the operator cannot see inside your script's logic, only your receipt.
