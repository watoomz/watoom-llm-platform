---
name: watoom-game-blueprint
description: Build a game end to end with the local models. Runs a design intake interview, writes a milestone plan of small bounded tasks sized for smaller models, routes each task to the real WatooM pipelines/assets, and runs a critique + performance + code-design gate after every milestone. Use at the start of any "make me a game / build this game" request and to drive it to completion.
metadata:
  opencode/autoinvoke: false
---

# WatooM game-development blueprint

This is the **orchestration blueprint** for building a game with the local models. It
does not implement every step itself: it runs the interview, produces the plan, and
routes each small task to an existing pipeline, asset flow, worker or specialist skill.
It is written so a **smaller model** can follow it one bounded step at a time.

**Operating rules (read first):**
- **Work in small tasks.** One task = one observable acceptance check, a few files, a
  short context window. Never hold the whole game in one prompt. Finish, validate, check
  point, then take the next task.
- **Discover, don't hardcode.** The pipeline/skill IDs below are *search intents*. Call
  the native `watoom_skill_search` with the intent keywords to get the current canonical
  ID, then load it with `skill`. A catalogue hit is not proof a route works — confirm its
  dependencies and execution environment first (see `godot` router rules).
- **Respect the guards.** Owned assets only (the Fab catalogue); visual review goes
  through the coordinator-guard receipt contract; model/GPU changes go through the GPU
  ownership controller; heavy builds/exports run on Bazzite, not the homelab server;
  GDScript is warnings-as-errors (strict typing). A technical PASS is **not** visual
  acceptance.
- **Checkpoint every task** under `.opencode/work/<task>/progress.md`: evidence, changes,
  validation, blockers, next action — before yielding.

---

## Phase 0 — Design intake interview (always first)

Before any code, interview the owner to fill the **design brief**. Ask in small batches
(3–5 questions), use the answers to ask sharper follow-ups, and stop when you can state
the core loop and the first milestone without guessing. If the owner says "you decide",
record an explicit assumption instead of leaving a blank.

Ask about, in roughly this order:

1. **Concept & fantasy.** One sentence: what is the game and what does the player do?
   What is the player's goal and what makes it fun?
2. **Genre & references.** Closest genres; 1–3 reference games or videos for *feel*.
3. **Core loop.** The 30-second loop the player repeats (e.g. explore → fight → loot →
   upgrade). What is the win/lose condition?
4. **Perspective & controls.** First/third person, top-down, isometric, 2D/2.5D/3D;
   keyboard+mouse, gamepad, touch.
5. **Engine & platform.** Default **Godot 4.7.2** (native pipeline); **Unreal 5.8** (rig, through the
   `watoom-ue` tools) if the owner needs it; **Three.js** for a browser game. This picks the engine plan in `references/`. Target platform(s) and any performance ceiling (e.g. 60 fps on the
   homelab GPU).
6. **Scope & scale.** Prototype / vertical slice / full game? Level count, world size,
   number of enemy/character types, singleplayer vs multiplayer.
7. **Art style.** Stylised vs realistic, palette, mood, lighting/time-of-day, references.
   This sets asset budgets and material direction.
8. **Assets to use.** Which assets? Check the **owned Fab catalogue** first
   (`/data/ai/assets/catalog/fab-owned.json` and `fab-pipeline-candidates.md`) — it
   includes MetaHuman packs surfaced via `epic-fab extras` (e.g. character packs). List
   specific owned packs for characters, environment, props, audio. Flag anything that
   must be acquired or built from scratch.
9. **Characters.** Player + key NPCs/companions/enemies: look, abilities, animations
   needed (idle/walk/run/attack). Note any owned character/MetaHuman source.
10. **Audio & UI.** Music/SFX direction, HUD elements, menus — defer to later milestones
    unless core.
11. **Constraints & non-goals.** Deadlines, must-haves vs "later", and explicitly what the
    game is **not**.

Write the answers into the plan's **Design brief** section (template below). Confirm the
brief back to the owner in one short summary before planning.

---

## Phase 1 — Plan: milestones → small tasks

Copy `templates/game-plan.md` into the project at `.opencode/work/game-plan.md` and fill
it. Decompose the game along the **standard game-dev flow**, mapping each stage to a
milestone. Within each milestone, break work into small tasks (above).

| Stage | Milestone goal | Typical small tasks |
|---|---|---|
| **M0 Foundation** | Project scaffold runs | pick/instantiate a game template; set up input map, main scene, camera, a grey-box test level; headless import passes |
| **M1 Core loop (greybox)** | The loop is playable with primitives | player controller + movement; one interaction; win/lose; placeholder shapes only |
| **M2 Vertical slice** | One real, representative chunk | real player character + 1 level + 1 enemy/companion, real art for that slice, basic audio/UI |
| **M3 Content production** | Breadth on the proven slice | more levels/enemies/items/assets, reusing the slice's patterns |
| **M4 Polish & optimise** | Looks and runs well | VFX, lighting/time-of-day, UI pass, performance budgets, bug fixes |
| **M5 Release** | Shippable build | export, run instructions, final captures, known-limitations list |

Keep M0–M1 on **primitives/placeholders** — prove the loop before spending on art. Only
pull real/owned assets from M2 onward.

---

## Phase 2 — Execute tasks via the real pipelines

For each task, pick the route by **intent** (confirm the canonical ID with
`watoom_skill_search`). Prefer an existing verified recipe over improvising.

**Scaffolding & gameplay (Godot)**
- Game scaffold / reusable foundation → search `Godot game template` (the
  `game-template-*` family: 3D base, FPS, horror-FPS, true-first-person-multiplayer,
  cobra-fps-feel-kit, kings-and-pigs; Unreal templates exist too).
- Small prototype / gameplay feature / bug fix → `watoom-prompt-godot`,
  `watoom-prompt-development`. The `godot` router skill selects the right child.

**World & levels**
- Real-world terrain from lat/long → `watoom-terrain-map` (open DEM → Godot terrain).
- Landscape/heightmesh → `watoom-landscape-mesh-builder`; fixed/handcrafted map →
  `watoom-prompt-fixed-map`; dungeon → `watoom-prompt-dungeon`; procedural mesh →
  `watoom-prompt-procedural-mesh`.

**Characters, assets & materials**
- Owned Fab UE asset → Godot GLB → `watoom-fab-owned-assets` (`export_pack.py`, runs on
  Bazzite via `--backend auto`). Reuse the companion pattern (CharacterBody3D follow,
  per-companion scene + collider, material assignment for external-texture GLBs).
- New mesh/character/material/effects → `watoom-prompt-mesh-generate`,
  `watoom-prompt-character`, `watoom-prompt-material`, `watoom-prompt-effects`,
  `watoom-blender-asset-builder`, `watoom-prompt-blender-godot`.
- Find/choose owned assets → `watoom-prompt-asset-search`, `watoom-prompt-asset-index`,
  `watoom-prompt-inspect`. Acquire an owned-but-undownloaded item → `watoom-prompt-fab-acquire`
  (operator-approved flow only; MetaHuman `.mhpkg` packs have no UE downloader route yet —
  treat as a flagged follow-up, not a blocker).

**Validation (every task, before calling it done)**
- Headless import/test and captures run through the native `watoom_game_worker` bridge
  (`game_import.py`, `game_validation.py`, `game_capture.py`) — heavy scene load/test/
  render never runs in the app. Builders *request* these operations under their contract.
- Godot strict check: typed GDScript, no warnings-as-errors failures (`for x: T in`,
  explicit `: float`/`: Texture2D` on `lerp()`/`load()`), scenes load clean.
- Visual check: one bounded structural/runtime check, then one fresh rendered review.
  Inspect the output; don't recolour to force a pass.

---

## Engine plans: the task-by-task version (use these for the actual work)

Phase 2 above chooses the route by intent. For the step-by-step build, take the plan for the engine and feed a model
**one phase at a time**. Every task row names the **agent**, the **tool or pipeline**, and a **done-when** check:

- Godot: `references/engine-godot.md` (the `watoom-godot_*` editor tools, worker captures, strict GDScript)
- Unreal: `references/engine-unreal.md` (the `watoom-ue` tools, the landscape/terrain converter, PIE checks)
- Unreal combat (weapons, guns, spells, pickups, combat animation, VFX, damage, multiplayer): skill `watoom-unreal-combat`
- Three.js: `references/engine-threejs.md` (Vite, Node tests, headless Chrome checks)
- Who does what, and the handoff contract: `references/agents.md`
- The four project documents: `templates/project-docs.md`

**Universal rules (every engine):**
1. One system at a time; never write two systems in one task.
2. After every coding or building task, the very next action is to run/play it and read the errors.
3. If an error appears, stop and fix it before creating anything new. After two failed attempts, call `watoom-critic`;
   for an engine/API fact you are unsure of, call `watoom-researcher` (or `watoom-investigator` for a project fact) with the exact question.
4. The simplest implementation that meets the done-when check; split any script or Blueprint over ~150-200 lines.
5. `watoom-reviewer` checks every builder package that changed files, scenes or assets before it is reported done.
6. Update `TEST_LOG.md` after each verification, with evidence; a technical pass is not visual acceptance.
7. Scope is sacred: one vertical slice. No menus, saves or extra levels unless added later as a new milestone.
8. Primitives and placeholders until the core loop is proven (M0-M1); real assets from M2.
9. Use only tools that are actually listed in the session; if a route is missing or disconnected, say so and stop.

---

## Phase 3 — Milestone critique / performance / code-design gate

**Run this after every milestone passes its functional checks, before starting the next.**
This is where the game is analysed and improved. Discover the current review/optimise
skills with `watoom_skill_search` (do not assume this list is complete):

1. **Visual & scene critique** — `watoom-engine-visual-diagnosis`: prove subject identity,
   completeness, material semantics, geometry/placement from real capture receipts. Use it
   whenever a review contradicts the intended scene. Feed rejections back as specific
   fixes, not blind recolouring.
2. **Performance pass** — `watoom-prompt-optimize` for asset budgets (triangles, texture
   resolution, record before/after) and `blender-game-optimization` for game-ready asset
   optimisation (LODs, draw calls, overdraw, collision cost). Check frame budget against
   the target set in the brief; identify the top offenders, fix the biggest first.
3. **Asset QA** — `blender-asset-qa` for imported/produced assets (scale, pivots, UVs,
   normals, material correctness).
4. **Code-design review** — review the milestone's code for correct design: single
   responsibility per node/script, signals over polling, no per-frame allocations,
   decoupled scenes, typed APIs, reuse of established patterns over parallel ones. Use the
   `godot` router to pull current best-practice guidance; apply the smallest correct
   refactor and re-validate. Do not expand scope under the banner of "cleanup".
5. **Record learnings** — feed only *verified, non-secret* outcomes (what improved, by how
   much, with evidence) into the existing memory / `self-learning` path. Unverified ideas
   stay candidates.

Write a short milestone review into the plan: what was checked, what changed, measured
before/after, and what is deferred. Only then open the next milestone.

---

## Honesty & stopping

Report technical PASS, visual acceptance, and deferred work separately. If a review keeps
rejecting the same symptom, change only a hypothesis backed by new evidence; after the
configured repair limit, checkpoint the exact missing proof and ask the owner — never
reset counters, spawn duplicate sessions, forge a receipt, or weaken a guard to get a
green count.

```skill-routing
{"kind": "router", "aliases": ["game blueprint", "build a game", "make a game", "game development plan", "game dev blueprint", "game lifecycle"], "requires": []}
```
