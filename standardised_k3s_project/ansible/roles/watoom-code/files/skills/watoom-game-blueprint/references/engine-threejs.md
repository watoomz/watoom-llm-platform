# Three.js plan (Vite, vanilla JS or TypeScript)

One task = one row; give a model **one phase at a time**. Agents are in `agents.md`. Three.js is **not** one of the
engine pipelines (no engine MCP, no worker, no reference cards): everything runs as ordinary Node tooling in the project
folder `/data/ai/projects/games/<project>`. If the session has no shell, ask the operator for the specific command;
do not look for a bypass. Look up API facts with `watoom-researcher` (threejs.org documentation, the version pinned in
`package.json`); never write Three.js calls from memory when the version matters.

Tools on the lab (checked 2026-11-14): `node`, `npm`, `npx`, and `google-chrome`. The verification command below runs
WebGL2 headless with the software renderer and prints console messages:

```
google-chrome --headless=new --no-sandbox --disable-gpu --use-angle=swiftshader --enable-unsafe-swiftshader \
  --enable-logging=stderr --v=0 --virtual-time-budget=5000 --screenshot=out/shot.png http://localhost:4173/ 2>&1 | grep CONSOLE
```
Serve the build first (`npm run build && npx vite preview --port 4173 &`). Any `CONSOLE` line containing `Uncaught`,
`Error` or `Failed` is a failure. Software rendering proves "it draws and does not throw"; it does **not** prove 60 fps,
so record the number as "not measured on target hardware" unless you measured on a real GPU.

## Phase 1 - Bootstrap
| Task | Agent | Tool / route | Done when |
|---|---|---|---|
| T1.1 `PROJECT_SPECS.md` (Three.js exact version, vanilla JS or TS, input devices, target browsers, fps budget) | `watoom-game-designer` | `templates/project-docs.md` | One page |
| T1.2 Scaffold: `npm create vite@latest <name> -- --template vanilla` (or `vanilla-ts`), `npm install three@<exact version>`; commit `package-lock.json`; no `^`/`latest` | `watoom-builder` | shell; network to the npm registry | `npm run build` succeeds |
| T1.3 Layout `src/{main.js,game/{Game,Player,Input,World}.js,ui/,assets/,styles/}` | `watoom-builder` | file tools | Tree matches |
| T1.4 Renderer, scene, perspective camera, ambient + directional light, `requestAnimationFrame` loop, resize handler, one cube/plane | `watoom-developer` | file tools | Headless Chrome check shows the shape (look at `shot.png`) and prints no error |

## Phase 2 - Design
| Task | Agent | Tool / route | Done when |
|---|---|---|---|
| T2.1 `GDD.md` | `watoom-game-designer` | `templates/project-docs.md` | One page |
| T2.2 `ARCHITECTURE.md`: Game owns the loop and state, Player owns movement and camera, World owns geometry and colliders, Input is a pure keyboard/mouse abstraction | `watoom-systems-designer` | GDD only | Boundaries listed; no module reaches into another's internals |

## Phase 3 - Core prototype
| Task | Agent | Tool / route | Done when |
|---|---|---|---|
| T3.1 Ground plane and a few boxes in `World.js` (graybox) | `watoom-developer` | file tools | Visible in the capture |
| T3.2 `Player.js`: velocity-based controller (no physics library at first), WASD + Space, pointer-lock or orbit camera (choose one) | `watoom-developer` | file tools; a physics library (cannon-es, rapier) only if the GDD needs it, and added as a **pinned** dependency | Pure movement maths has unit tests (`vitest`, run in Node, no browser) |
| T3.3 Wire Input -> Player -> Game loop | `watoom-developer` | file tools | The movement tests pass; the headless run shows no error |
| T3.4 Playable check: drive keys through the page with a script (Chrome `--remote-debugging-port` and a small CDP/puppeteer-core script, or expose `window.__game` for tests) and read positions | `watoom-automation-expert` | shell; keep the script in `tests/` | Player position changes as expected after scripted input |

## Phase 4 - Systems (check the browser console after each)
| Task | Agent | Tool / route | Done when |
|---|---|---|---|
| T4.1 One interactable (raycaster from the camera) that changes colour | `watoom-developer` | file tools; `Raycaster` per the pinned docs | Scripted click toggles the state (read it back) |
| T4.2 DOM HUD in `ui/HUD.js` updated from `Game` | `watoom-developer` | file tools | HUD text matches state in the DOM dump (`--dump-dom`) |
| T4.3 One enemy/moving obstacle with plain vector maths, no pathfinding library | `watoom-developer` | file tools | Unit test on the steering function; moves in the run |
| T4.4 2-3 sounds (Web Audio or Howler) on jump and interaction | `watoom-developer` | file tools; audio files from owned assets or generated | Events call the audio layer (unit test with a stub); autoplay policy handled (start after first input) |
| T4.5 After each | `watoom-reviewer` | headless Chrome check | No new console error or warning |

## Phase 5 - Visuals
| Task | Agent | Tool / route | Done when |
|---|---|---|---|
| T5.1 Replace graybox with glTF | `watoom-3d-modeller` | Owned assets via `watoom-prompt-asset-search`; meshes via `watoom-blender-asset-builder` / `watoom-prompt-mesh-generate`; export GLB with `blender-export-pipelines`; load with `GLTFLoader` | Loads with no console error; scale/pivot ok (`blender-asset-qa`) |
| T5.2 `MeshStandardMaterial`, environment lighting (PMREM or a small HDR) | `watoom-3d-modeller` | file tools; textures from `/data/ai/assets/polyhaven` (diff, normal GL, rough; sRGB only on colour maps) | Capture reviewed |
| T5.3 Optional bloom or FXAA with `EffectComposer` | `watoom-developer` | file tools | Capture reviewed; cost noted |
| T5.4 Size and load budget | `watoom-3d-modeller` | `blender-game-optimization`, `watoom-prompt-optimize` (triangles, texture size, KTX2/Draco if needed) | Budget from `PROJECT_SPECS.md` met |

## Phase 6 - Verification and packaging
| Task | Agent | Tool / route | Done when |
|---|---|---|---|
| T6.1 Run in Chrome and Firefox (Firefox only if installed; otherwise state "not tested") | `watoom-qa-tester` | headless Chrome; Firefox if present | Both results, or an explicit gap |
| T6.2 `TEST_LOG.md` checklist: fps (with the "software renderer" caveat), movement, interaction, HUD, no console errors | `watoom-qa-tester` | evidence from T6.1 | Every box has evidence |
| T6.3 `npm run build`; serve `dist/` and load it | `watoom-automation-expert` | shell | `dist/` runs from a static server |
| T6.4 Break it, then play it cold | `watoom-adversarial-tester`, `watoom-blind-tester` | scripted input, held keys, window resize, tab blur | Findings logged; fixes go to `watoom-developer` |
