# Content-only grid map authoring

Static grid maps do not need a new C++ editor module, custom commandlet or UBT modification. Use a content-only .uproject with PythonScriptPlugin and EditorScriptingUtilities in the accepted runtime. Python creates editable actors and saves/reopens a real .umap.

grid_layout.py validates bounded complete cell grids, exact integer coordinates, wall symmetry, open door edges, actor budgets and layout identity. It emits floor, rock and deduplicated wall placements. grid-map-probe.py creates a fresh /Game/Levels/Quest1 map, checks actual floor/door collision after reopening, writes an actor manifest and captures real Vulkan overhead/perspective images. Source images and derived per-project layout JSON are not repository fixtures.

The existing accept-render.py --dungeon-export supervisor owns GPU admission, actual idle checks, bounded editor resources, readonly engine/source mounts and verified primary restoration. Prepare a fresh isolated project and dungeon-export-plan.json with the published editor checksum and SHA256 pins for every source/config/input file. Then invoke the supervisor using --evidence and --detach. Do not invoke the renderer outside its owner or rerun on a nonempty output map.

The editor launch is maintained by render-editor.py. It uses the accepted published engine, an owned Xvfb display and ExecutePythonScript; no dotnet installation is needed for this content-only route. The published runtime also already includes its Linux .NET10 in Engine/Binaries/ThirdParty/DotNet/10.0/linux-x64, independently of PATH.

A successful map/collision/capture receipt is not a pixel-review result or Recast/gameplay certification. Inspect both PNGs before publication. Source layout fidelity must be checked separately; total grid cells must not be confused with walkable floor cells, and shaded solid rock must not be treated as floor.

Native GUI availability is a separate gate: these operator tools do not add a fixed_layout field to a deployed WatooM Code contract. Agents must inspect installed capabilities and report a missing admission route rather than claiming source scripts are registered tools.
