# Godot plan (GDScript, Godot 4.7.2)

One task = one row. Give a model **one phase at a time**. Agents are in `agents.md`. "MCP" means the `watoom-godot_*` tools
(Godot Editor over the restricted rig route; list the tool names with `discover_tools`; read the card with `wlk_symbol`
before the first use of a tool: product `godot-mcp-toolkit`). "Worker" means the native `watoom_game_worker` bridge
(`game_import`, `game_validation`, `game_capture`): heavy import, test and render run there, never in the app. Prefer a
`game-template-*` skill over an empty project (search `Godot game template`); if a template is used, keep **its** folder layout.

Project root: `/data/ai/projects/games/<project>`. Checkpoint every task in `.opencode/work/<task>/progress.md`.

## Phase 1 - Constraints and scaffold
| Task | Agent | Tool / route | Done when |
|---|---|---|---|
| G1.1 Write `PROJECT_SPECS.md` (Godot 4.7.2, GDScript only, 2D or 3D, CharacterBody, target desktop, strict typing, fps budget) from the Phase 0 brief | `watoom-game-designer` | `templates/project-docs.md` | File exists and answers every line; dimension chosen once |
| G1.2 Folder layout `scenes/ scripts/ assets/{models,textures,audio,fonts}/ resources/ autoload/ ui/` (or the template's) | `watoom-builder` | File tools for the folders, or start from `game-template-godot-3d-base-template` | Tree matches; nothing outside the project root |
| G1.3 `project.godot` with autoloads `GameManager`, `AudioManager`, `EventBus` (empty stubs) and an input map (`move_left/right/forward/back`, `jump`, `interact`) | `watoom-builder` | MCP `autoload_manage`, `input_map_action`, `input_map_event`, `script_write` | `input_map_list` and the autoload list show them |
| G1.4 Project loads clean | `watoom-reviewer` | Worker `game_import` (headless import); MCP `editor_get_console` | Zero errors, zero warnings-as-errors |

## Phase 2 - Design and architecture
| Task | Agent | Tool / route | Done when |
|---|---|---|---|
| G2.1 `GDD.md`: one-sentence core loop with win/lose, primary mechanic (max 2 verbs), camera, art style (3-5 words + hex palette), scope "vertical slice only" | `watoom-game-designer` | `templates/project-docs.md` | One page; every later task can cite a line of it |
| G2.2 `ARCHITECTURE.md` (<30 lines): each autoload with its public signals/methods; signals over polling | `watoom-systems-designer` | Read the finished GDD only | Every autoload listed; no cross-scene node paths |
| G2.3 Typed stubs for the autoloads | `watoom-developer` | MCP `script_write`, `script_check`, `lsp_project_diagnostics` | `script_check` clean; strict typing (`: float`, `: Texture2D`, `for x: T in`) |

## Phase 3 - Greybox and core prototype (primitives only; no art yet)
| Task | Agent | Tool / route | Done when |
|---|---|---|---|
| G3.1 `scenes/Main.tscn`: WorldEnvironment, DirectionalLight3D, floor, `Marker3D` spawn | `watoom-builder` | MCP `scene_create`, `scene_create_node`, `3d_setup_environment`, `3d_create_light`, `3d_create_primitive`; real terrain later via `watoom-terrain-map` | `scene_get_tree` shows the nodes; scene loads |
| G3.2 `scenes/Player.tscn`: CharacterBody3D, collider, mesh, SpringArm3D + Camera3D | `watoom-builder` | MCP `scene_create`, `scene_create_node`, `node_set_property`, `3d_create_camera` | Scene loads; collider shape set |
| G3.3 `scripts/PlayerController.gd`: WASD, jump, gravity via InputMap | `watoom-developer` | MCP `script_write`, `script_check`, `node_set_script`; pattern from the chosen template | `script_check` clean, <200 lines |
| G3.4 Instance Player in Main and run it | `watoom-reviewer` | MCP `scene_instantiate`, `game_start`, `input_simulate`, `runtime_get_node_state`, `debugger_get_log`, `game_stop`; Worker `game_validation` | The player moves and jumps; **zero** console errors |

## Phase 4 - Systems, one at a time (run and check after each)
| Task | Agent | Tool / route | Done when |
|---|---|---|---|
| G4.1 Interactable (Area3D + `interact` input) emitting an `EventBus` signal | `watoom-developer` | MCP `scene_create_node`, `signal_manage`, `script_write` | `input_simulate` triggers the signal; log shows it |
| G4.2 `ui/HUD.tscn` (health/score label, prompt, crosshair) bound to `GameManager` signals | `watoom-developer` | MCP `scene_create`, `control_set_layout`, `signal_manage`; `editor_screenshot` | Label updates on the signal; screenshot reviewed |
| G4.3 One enemy/hazard with a tiny state machine (Idle -> Chase/Patrol), <80 lines | `watoom-developer` (design the behaviour first with `watoom-game-designer`) | MCP `script_write`, `navigation_edit` if pathing; `runtime_get_node_state` | Enemy changes state when the player enters range; no errors |
| G4.4 2-3 placeholder sounds routed through `AudioManager` (jump, interact) | `watoom-developer` | MCP `audiobus_edit`, `audiobus_list`, `script_write`; generated sounds via `sound_generate` | Sounds fire on both events; bus layout listed |
| G4.5 After **each** G4.x: run the main scene, read the console | `watoom-reviewer` | MCP `game_start`, `debugger_get_log`, `editor_get_console`, `game_stop` | No new error or warning |

## Phase 5 - Real art (only from M2 onward)
| Task | Agent | Tool / route | Done when |
|---|---|---|---|
| G5.1 Replace graybox with owned or generated assets | `watoom-3d-modeller` (+ `watoom-integration-expert` for import) | Search `watoom-prompt-asset-search`; owned Fab -> GLB with `watoom-fab-owned-assets`; new meshes `watoom-prompt-mesh-generate` / `watoom-blender-asset-builder`; MCP `asset_import`, `scene_instantiate` | Assets import clean; scale/pivot/UV checked with `blender-asset-qa` |
| G5.2 Terrain layers and materials | `watoom-3d-modeller` | `watoom-terrain-map` (heightmap), `watoom-texture-layering` (`layer_masks.py`, `terrain_layered.gdshader`, `blender_layered_material.py`), `watoom-prompt-material` | `layer_report.json` sums to 255; shader compiles headless |
| G5.3 Lighting, glow/SSAO via WorldEnvironment; VFX | `watoom-3d-modeller` | MCP `3d_setup_environment`, `particles_create`; `watoom-prompt-effects`, `blender-time-of-day` | Capture reviewed by `watoom-reviewer` |
| G5.4 Performance pass | `watoom-3d-modeller` | `watoom-prompt-optimize`, `blender-game-optimization`; record triangles/draw calls before and after | Meets the fps budget from `PROJECT_SPECS.md` |

## Phase 6 - Verification
| Task | Agent | Tool / route | Done when |
|---|---|---|---|
| G6.1 Headless run and a render capture | `watoom-automation-expert` (script) then `watoom-reviewer` | Worker `game_validation` and `game_capture`; MCP `runtime_screenshot`; `watoom-engine-visual-diagnosis` if a review disagrees | Receipt + capture exist |
| G6.2 `TEST_LOG.md` checklist: movement, interaction, UI, no load errors, fps | `watoom-qa-tester` | Evidence from G6.1 | Every ticked box has evidence |
| G6.3 Break it, then play it cold | `watoom-adversarial-tester`, `watoom-blind-tester` | MCP `input_simulate`, `runtime_set_property` | Findings logged; fixes go back to `watoom-developer` |

Godot notes: GDScript is warnings-as-errors; do not weaken settings to get green. `execute_code` and `node_call_method` can
run arbitrary code in the editor: use a dedicated tool first. Heavy export runs on Bazzite (worker `--backend auto`), not the
homelab server.

## Imported-model materials and ground textures (lessons from zombie-animal-survival)

- `MeshInstance3D.material_override` replaces every surface material of an imported model with one material, so a character or building turns into one flat colour. Set per-surface materials (`set_surface_override_material`) or leave the imported materials alone; use `material_override` only for an intentionally uniform object.
- A terrain or arena ground with no albedo texture renders as a flat colour. Assign a tiled albedo (and normal) texture with `uv1_scale` set so it repeats, then check an actual render of the ground, not only that the node exists.
- Judge both from a rendered frame (vision-first review), never from the scene tree alone.
