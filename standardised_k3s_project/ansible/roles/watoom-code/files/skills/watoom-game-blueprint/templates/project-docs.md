# Project documents (copy into the project root and fill)

Four short files. They are the contract every later task cites; keep each under one page.

## PROJECT_SPECS.md
- **Engine and version:** <Godot 4.7.2 | Unreal 5.8 | Three.js X.Y.Z (exact)>
- **Language / authoring:** <GDScript only, strict typing | Blueprint-only (C++ later) | JS or TS>
- **Dimension and perspective:** <2D | 3D>, <camera>
- **Physics / movement base:** <CharacterBody3D | Character | own velocity controller>
- **Target:** <platform, input devices, fps budget (say where it is measured)>
- **Project path:** /data/ai/projects/games/<project>   ·   **Checkpoints:** .opencode/work/<task>/progress.md
- **Owned-asset policy:** owned assets only; anything else is acquired through the operator-approved flow.

## GDD.md
- **Core loop (one sentence, with the win and lose condition):**
- **Primary mechanic (at most two verbs):**
- **Camera:**
- **Art style (3-5 words) and palette (hex):**
- **Scope:** Playable vertical slice only. No campaign, menus, save system or extra levels unless added later as a new phase.

## ARCHITECTURE.md  (under 30 lines)
- Each singleton/system, its public signals/events/methods, and who may call it.
- Communication rule: signals/dispatchers/events over polling; no node-path or module reach-through.
- Data: where tunable numbers live (resources / data assets / a config module), not inline.

## TEST_LOG.md
| Check | Evidence (capture path, log line, test name) | Result |
|---|---|---|
| Movement responds | | |
| Interaction works | | |
| UI/HUD updates | | |
| Enemy/AI does not error | | |
| No errors on load | | |
| Frame rate (target hardware, or "not measured") | | |
Only tick a row when the evidence column is filled. A technical pass and visual acceptance are separate rows.
