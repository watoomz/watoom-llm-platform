---
name: watoom-worker-contracts
description: Exact contracts for WatooM's execution routes - native specialist jobs (watoom_specialist_run payloads, asset.search/index, world.compose and dungeons, character/material/optimize, LLaMA-Mesh), the Godot game worker (regression, import, capture, capture-p7, poo-vfx-inspect, Bazzite/rig), Unreal runtime paths and map assembly, and asset selection/Fab acquisition/reference downloads. Load before submitting or judging any of these jobs.
---

# WatooM worker and specialist contracts

The agent prompts say WHEN to use a worker; this skill holds HOW. Read only the reference for the route you are about to use or judge:

| You are about to... | Read |
|---|---|
| call `watoom_specialist_list` / `watoom_specialist_run` (asset.search, asset.index, asset.inspect/optimize, world.compose incl. dungeons, character.prepare, material.derive), or generate with LLaMA-Mesh | `references/specialist-jobs.md` |
| request `watoom_game_worker` (regression, import, capture, capture-p7, poo-vfx-inspect), read a Godot receipt, write a test runner, or run a parse-only check | `references/game-worker.md` |
| inspect, convert or assemble anything in Unreal (runtime paths, `/unreal-engine`, Hyper, GLTF export, map assembly) | `references/unreal.md` |
| choose, acquire, download or accept assets (Fab library, formats, dependency closure, reference images, Blender skill choice) | `references/assets-and-downloads.md` |

Captures of an existing asset use the `asset-image-clip-capture` skill (`references/default-recipe.md`). Pipeline task prompts are built by the `watoom-prompt-*` skills.

Rules that apply to every route:
- Discover the live capability/schema once; registered is not tested. Never guess payload fields or probe with trial calls.
- One stable job identity from dispatch to reconciliation. A timeout, disconnect, QUEUED or RECONCILIATION_REQUIRED is an unknown outcome until the existing job is checked; never replay it under a new ID.
- Heavy engine, import, render and conversion work never runs in the 2 GiB app shell.
- A receipt validates only its own source manifest. Technical, visual and gameplay acceptance are separate gates.
