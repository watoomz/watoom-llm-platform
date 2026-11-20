## Making changes
- Make the smallest correct, reversible change that follows the project's existing conventions; reuse the established pattern or helper rather than adding a parallel one. Snapshot before risky changes and change one variable at a time when experimenting. Re-read a file after a failed edit.
- Test with the project's own build, lint and test commands, never a hand-rolled substitute. A failing suite is FAIL; an apply, rollout or exit 0 is not acceptance.
- Never replace an accepted or playable asset or an in-game character without review and owner approval.

## Engine and asset worker routes
Heavy work has fixed routes. Load the `watoom-worker-contracts` skill and read the matching reference before using any of them:
- `watoom_specialist_list` once, then `watoom_specialist_run` (specialistID `local-toolkit`, capability, stable job, typed payload) for asset search, index, inspect and optimize, world and dungeon composition, characters and materials.
- `watoom_game_worker` `{action:"request", operation, job}` for Godot regression, import and capture (also `capture-p7`, `poo-vfx-inspect`); the project comes from the session. QUEUED or WAITING_FOR_HEADROOM means waiting, not failure: keep the request_id, do independent work and reconcile the receipt when it arrives, and never duplicate the job or change its target meanwhile. FAILED needs an evidence-based repair, STALE_REQUEST/STALE_RESULT a new revision request, RECONCILIATION_REQUIRED an inspection of the existing job first. Use `watoom_rig_game_job` only when the status shows `rig_eligible: true`.
- `watoom_asset_capture` for renders or clips of an existing asset (`asset-image-clip-capture` skill).
- In the app shell, only a parse check: `godot --headless --check-only -s scripts/<edited>.gd` with the shell `workdir` set to the project root and nothing chained. It proves syntax, not behaviour.
- No Blender, Godot or Unreal launches from the app shell. If no worker route exists, checkpoint the exact command and ask the operator.
- Blender: load `watoom-blender-asset-builder` and only the relevant installed `blender-*` skills before writing custom scripts; record why if you still need custom code.
