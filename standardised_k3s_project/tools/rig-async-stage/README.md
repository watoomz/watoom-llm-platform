# RIG asynchronous jobs (isolated stage)

**Status 2026-11-07: running.** It was retired on 2026-10-29 (audit R20) and has since been re-enabled: the stage app is at 1
replica, `watoom-rig-async-stage.timer` is enabled and active (5 s ticks), and `/etc/watoom-rig-async-stage.json` enrols one
project for `import`, `regression`, `capture` and `capture-p7` (not `blender`). Routing policy (owner, 2026-11-07): heavy
work goes to Bazzite first; the rig is allowed only after Bazzite has been unavailable for 10 minutes (the game worker's
QUEUED status shows `rig_eligible`); never the homelab server.

This bundle is opt-in and uses namespace `watoom-code-rig-jobs`, a separate
application database, and only the enrolled qualification project. The original
Magpie application and its project files remain unchanged.

Models submit `watoom_rig_game_job` (import, regression, capture, capture-p7) or
`watoom_asset_capture` and immediately continue independent work. Keep stable job
identities. Wait only for dependent tasks. Do not poll repeatedly. Inputs are
frozen in hash-verified snapshots; original game files are never copied back.
Changed source revisions produce stale results rather than a false current PASS.
Godot import qualifies the Windows snapshot; it does not modify Linux import caches.
Specialized VFX/LMB operations retain the existing server worker.

Both RIG consumers share one durable execution slot. File data uses the existing
restricted SFTP channel with hash verification and transport-only retries. Process
crashes and uncertain leases require reconciliation; they are never blindly replayed.
Completion uses a durable per-application outbox and stable native synthetic input
IDs with delivery=queue, so active work is not interrupted or lost on a retry.

Local `Rig-Jobs.ps1` controls apply to staged Blender and Godot workers:
- Pause Now stops the child process tree at a checkpoint, releasing its GPU context.
- Finish Then Pause prevents new claims and allows the current job to finish.
- Resume explicitly restarts an interrupted bounded operation from frozen inputs;
  partial attempts are archived. This is not OS suspension or exact-frame continuation.
- Status shows the local requested mode and worker journal phases.

Boundary: pinned Blender5.2.1 and Godot4.7.2, Windows Job Object 8GiB, 900-second
operation deadline. Captures remain subject to actual pixel review. Fixture PASS
is not acceptance of the Magpie game's art, animation or gameplay.

Deployment must prove no active RIG claim before switching the existing worker
program. Retain the old source/config/task definition and queue DB. Never replay
historical manual jobs or delete ownership/lease files. Use the scoped stage config
and controlled deployment; do not apply the legacy full worker role over this bundle.

## Qualified deployment and updates

The installed application is isolated in `watoom-code-rig-jobs`; do not promote
its guard or writable project enrollment to the main application automatically.
`provision-app.py` creates this isolated application once and refuses replacement.

For an update: pause both desktop consumers, wait for terminal journals, stop
`watoom-rig-async-stage.timer`, and hold an immediate SQLite queue transaction
which rejects CLAIMED and RECONCILIATION_REQUIRED rows. Refresh and verify the
source manifest, then execute `install-runtime.py` under that held fence. It keeps
the previous source, queue backup and immutable versioned release. Copy the exact
worker-source payload to the RIG stage source directory while its two scheduled
tasks are stopped; compare every manifest hash. Start tasks paused, release the
fence, restart the timer, and restore the previous operator pause preference.
Never update a PAUSED attempt across runtime hashes or remove its lease.

Desktop shortcuts: Pause RIG jobs (Stage), Finish then pause RIG jobs (Stage),
Resume RIG jobs (Stage), and RIG job status (Stage). They share one control file
for Blender and Godot; paused queues remain durable.

Qualification on 2026-10-26: 29 Python tests, native guard tests, Windows process
tree pause verification, and three completed native jobs (Godot import, Godot
regression, Blender capture). The model wrote an independent checkpoint while
all three jobs were queued. Notifications use one stable native message per job.
