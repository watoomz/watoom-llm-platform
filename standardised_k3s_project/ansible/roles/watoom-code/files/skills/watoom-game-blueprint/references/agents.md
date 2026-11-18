# Which agent does which game task

Use this with the engine plans (`engine-godot.md`, `engine-unreal.md`, `engine-threejs.md`). The coordinator
(`watoom-workflow`) delegates **one bounded package at a time** and keeps the checkpoint; children return their scoped
result and do not route among each other. Names below are the real agent ids.

| Agent | Use it for in a game | Never use it for |
|---|---|---|
| `watoom-workflow` | Run the plan: pick the next task, hand off, keep `.opencode/work/<task>/progress.md`, decide scope. | Writing the code itself. |
| `watoom-game-designer` | GDD, core loop, mechanics spec, balance numbers, acceptance criteria for a feature. **Before** a builder when *what to build* is unsettled. | Implementation. |
| `watoom-systems-designer` | ARCHITECTURE (singletons, signals/dispatchers, data model, service boundaries), consistency across features. | Scene/asset work. |
| `watoom-developer` | Gameplay code to a spec: controllers, interactions, enemy state machines, HUD logic. | Infrastructure, 3D content. |
| `watoom-builder` | A bounded change that must be built and validated: scaffold a project, wire a template, apply a spec'd scene/level build through the engine tools. | Open-ended design. |
| `watoom-3d-modeller` | Meshes, rigs, materials, UVs, LODs, export; pixel review of visual work. | Gameplay logic. |
| `watoom-integration-expert` | Joining things that already work alone: engine MCP route + project, asset pack -> engine import, terrain pipeline -> landscape. | Building the parts. |
| `watoom-automation-expert` | Headless validation scripts, test harnesses, build scripts, capture scripts. | Running an existing check (just run it). |
| `watoom-investigator` | A fact that lives in this project or host (where is the asset, what does this scene reference, what failed in this log). Read-only. | Implementing. |
| `watoom-researcher` | A fact about an external engine/library/API (Godot class, Unreal action, Three.js API, version differences). The "expert" to call when unsure: it checks the reference cards (`wlk_*`), then memory, then current docs. | Project-local facts (that is the investigator). |
| `watoom-critic` | After two failed attempts, or before a risky plan: is the diagnosis/next action sound? Returns PROCEED / REVISE / BLOCKED. | Editing, delegating. |
| `watoom-reviewer` | After **every builder package that changed files/scenes/assets**: independent check against the acceptance criteria, looking at actual output (captures), not just reports. | Replacing the tester trio. |
| `watoom-qa-tester` | Phase 6: the finished slice against its own GDD/acceptance criteria. | Fixing. |
| `watoom-adversarial-tester` | Phase 6: try to break it (edge inputs, out-of-bounds, spam, bad state). | Happy-path checks. |
| `watoom-blind-tester` | Phase 6: play it as a first-time user with no knowledge of the implementation. | Anything needing the code. |
| `watoom-creative-writer` | Dialogue, item text, lore, only when the GDD asks for narrative. | Mechanics. |

`watoom-kali` is a security agent and has no role in game building.

## Handoff contract (every delegation)
State: the bounded task id and change, evidence already known, the exact missing fact or decision, allowed actions
(which tools/routes), the expected output, and the stop condition. Reuse a valid receipt instead of re-investigating.

## Stuck? Call the expert, do not debate
Two failed attempts at the same cause, or any "does this API/action really work like that" doubt -> stop and delegate the
exact question: `watoom-investigator` if the answer is in this project, `watoom-researcher` if it is an engine/library
fact. The specialist looks up the cards first (`wlk_symbol` / `wlk_search`; products `godot`, `godot-mcp-toolkit`,
`ue-mcp`, `watoom-godot-route`, `watoom-ue-route`, `watoom-texture-layering`), then memory, then current documentation.
There are no reference cards for Three.js: use the documentation at threejs.org through `watoom-researcher`.
