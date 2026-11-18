# Game plan — <GAME NAME>

> Copy to `<project>/.opencode/work/game-plan.md`. Fill the Design brief from the Phase 0
> interview, confirm it to the owner, then fill the milestones. Keep every task small:
> one acceptance check, a few files. Update "Status" and "Milestone reviews" as you go.

- **Project path:** `/data/ai/projects/games/<project>`
- **Engine:** <Godot 4.7.2 (native) | Unreal 5.8 (rig) | Three.js (Vite)>  ·  **Target:** <platform / fps budget>
- **Engine plan:** `references/engine-godot.md` | `engine-unreal.md` | `engine-threejs.md` (task tables name the agent and tool for each step; agents in `references/agents.md`)
- **Project docs:** PROJECT_SPECS.md, GDD.md, ARCHITECTURE.md, TEST_LOG.md from `templates/project-docs.md`
- **Owner:** <owner>  ·  **Started:** <YYYY-MM-DD>  ·  **Current milestone:** M0

## Design brief (from intake)

- **One-line concept:** <what the game is / what the player does>
- **Core loop:** <the 30s repeated loop>  ·  **Win/lose:** <condition>
- **Genre & references:** <genres; reference games/videos>
- **Perspective & controls:** <1st/3rd/top-down/iso; kbm/gamepad/touch>
- **Scope:** <prototype | vertical slice | full>  ·  **Scale:** <levels, enemy/char types, SP/MP>
- **Art style:** <stylised/realistic, palette, mood, lighting/time-of-day>
- **Assets to use (owned first):**
  - Characters: <owned Fab pack ids / MetaHuman packs / to-build>
  - Environment/props: <owned packs / to-build>
  - Audio/UI: <sources / defer>
  - To acquire or build from scratch: <list + why>
- **Characters:** <player + key NPCs/companions/enemies: look, abilities, anims needed>
- **Constraints & non-goals:** <deadlines; must-have vs later; what it is NOT>
- **Assumptions made (owner to confirm):** <explicit assumptions where info was missing>

## Milestones & tasks

Each task: `[ ] <id> — <task>` → **Agent:** <watoom-... role> → **Acceptance:** <one observable check> →
**Route:** <pipeline/skill/worker/tool intent> → **Status:** todo | doing | done | blocked. Take the ids, agents and
routes from the engine plan's task tables instead of inventing them.

### M0 — Foundation (scaffold runs)
- [ ] M0.1 — Instantiate game template / scaffold → Acceptance: project opens, headless import clean → Route: `Godot game template`
- [ ] M0.2 — Input map + main scene + camera + grey-box level → Acceptance: can move a primitive around → Route: `watoom-prompt-godot`

### M1 — Core loop (greybox, primitives only)
- [ ] M1.1 — Player controller + movement → Acceptance: <check> → Route: `watoom-prompt-godot`
- [ ] M1.2 — One core interaction → Acceptance: <check> → Route: `watoom-prompt-development`
- [ ] M1.3 — Win/lose condition → Acceptance: <check> → Route: `watoom-prompt-development`

### M2 — Vertical slice (one real chunk)
- [ ] M2.1 — Real player character → Acceptance: imports, animates, strict-typed → Route: `watoom-fab-owned-assets` / `watoom-prompt-character`
- [ ] M2.2 — One real level/environment → Acceptance: <check> → Route: `watoom-terrain-map` / `watoom-prompt-fixed-map`
- [ ] M2.3 — One enemy/companion → Acceptance: <check> → Route: `watoom-prompt-character`
- [ ] M2.4 — Basic audio + HUD → Acceptance: <check> → Route: `watoom-prompt-development`

### M3 — Content production (breadth)
- [ ] M3.x — <more levels/enemies/items, reusing M2 patterns> → Acceptance / Route …

### M4 — Polish & optimise
- [ ] M4.x — VFX / lighting / UI pass / perf budgets / bug fixes → Acceptance / Route: `watoom-prompt-effects`, `watoom-prompt-optimize`, `blender-game-optimization`

### M5 — Release
- [ ] M5.1 — Export build → Acceptance: build runs → Route: `watoom-prompt-godot` / export pipeline
- [ ] M5.2 — Run instructions + final captures + known limitations → Acceptance: documented

## Milestone reviews (Phase 3 gate — fill after each milestone)

### M<n> review — <date>
- **Functional:** <what passed; worker import/validation/capture receipts>
- **Visual critique:** <watoom-engine-visual-diagnosis findings + fixes>
- **Performance:** <before/after: tris, textures, fps, draw calls; biggest fix>
- **Asset QA:** <blender-asset-qa findings>
- **Code design:** <refactors applied; patterns reused>
- **Deferred:** <explicitly carried forward>
- **Learnings recorded:** <verified outcomes fed to memory/self-learning>

## Checkpoint / log
- <YYYY-MM-DD> — <evidence · changes · validation · blockers · next action>
