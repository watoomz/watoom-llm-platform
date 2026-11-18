
## Heavy jobs wait for Bazzite; the rig comes second

Rendering, capture, Blender and conversion run on the Bazzite worker. If a `watoom_game_worker` request shows `QUEUED` with a reason about Bazzite being unavailable, keep working on independent tasks and do not resubmit: it retries on every poll. Only when the status shows `rig_eligible: true` (Bazzite unavailable for 10 minutes or more) and a direct `watoom_rig_game_job` tool is listed may you submit the equivalent rig job. Never ask for, or try to arrange, a run on the homelab server.
