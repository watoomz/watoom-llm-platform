# gg-assets: pick an owned model, bring it into the project, check it

Do not read `asset-index.md` (970 lines) to choose a model: it is for the owner and wastes your whole context. Use the model index instead.

## Commands (run `find` and `use` in your own session; the worker container has no asset library)

```bash
python3 scripts/gg_assets.py find  --query "dragon" [--ext glb] [--animated] [--max-mb 30] [--max 8]    # ranked, one line each
python3 scripts/gg_assets.py use   --asset ID --project /abs/path/game --slot dragon [--replace]         # copies to assets/library/dragon.glb, records it in assets/library/ASSETS.md
python3 scripts/gg_assets.py check --project /abs/path/game --slot dragon                               # engine inspection; also allowed as a worker step
```
Exit codes: 0 ok, 1 the check found an error, 2 refused (the message names the reason).

## What the index is

`tools/fab/build_model_index.py` (operator) writes `/data/ai/assets/catalog/model-index.json`: every `.glb`, `.gltf` and `.fbx` in the owned packs under `/data/ai/assets/fab` and the loose files in `humble_assets`, with, for each `.glb`, what the file really holds (meshes, skins, animation names). A pack that is only an Unreal `.uasset` pack, or a zip, is NOT in it: it needs the conversion route of the `watoom-fab-owned-assets` skill first (`asset_advisor.py advise`, then the native unreal-export job). Files under `glb/converted/` are the output of that conversion pipeline. Re-run the builder after a download or conversion.

## Rules

- Prefer `.glb` (textures inside). A `.fbx` is copied without its textures and may render white; `use` prints a warning.
- A file over 30 MB is refused unless `--allow-large`: every worker job syncs the whole project to the Bazzite worker, so keep large files out of scratch copies (use a smaller model or a decimated copy).
- Only files named in the index are copied, only from under the asset library. Nothing is downloaded, converted or bought here.
- `check` uses the same verdicts as `gg_catalog.py inspect` for a prop-sized model (0.3 to 30 m): no mesh, a wrong scale, black or invisible or glowing materials are errors; triangles and lights are warnings. The "origin must be on the ground" rule is dropped because it only matters for scatter. Fix the model or pick another; never edit the check.
- Put the model behind a `SubViewportContainer` + `SubViewport` and let `gg_ui.py shot --min-model-views N` prove it really draws; credit each slot from `assets/library/ASSETS.md` in your report.
