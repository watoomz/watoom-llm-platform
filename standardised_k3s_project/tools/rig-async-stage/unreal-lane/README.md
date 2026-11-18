# RIG Unreal lane (outbound-only, fixed operations)

Runs Unreal Editor jobs on the RIG (GPU, more memory) without any inbound connection to the RIG and without touching the guarded
Blender/Godot broker. The homelab (root) writes a job manifest into the transfer jail's `inputs/`; the RIG polls the same SFTP jail,
runs ONE fixed operation under a Windows Job Object and uploads results to `uploads/ue-<job>/` (`result.json` last = "complete").

* Operations are a fixed allow-list in `unreal_lane.OPS` (`probe`, and `metahuman-skin`: the GPU MetaHuman skin/DCC export, submitted with `rig_lane.py submit-skin PACK CHARACTER`; it runs the full editor with a real renderer because Epic's TextureGraph needs one). A manifest cannot carry code, paths or a command line; the
  in-engine script is a hash-pinned file shipped with the worker.
* Integrity: `inputs/` is root-written and read-only to the RIG; every file the RIG returns is checked (name, suffix, size, SHA-256) before
  the homelab copies it. The worker refuses to start if any shipped file or the pinned Unreal executables differ.
* A job that was running when the worker died is never replayed; it is reported as FAIL.
* Memory: set at install (`-MemoryGiB`, default 12), not by the manifest. Defers while the Blender/Godot workers report an active job (`-BusyJournals`)
  and honours the shared "Pause RIG jobs" control file.

## Install (once, and again after any Unreal/plugin update)
1. Homelab: `python3 tools/rig-async-stage/unreal-lane/build_lane.py /data/ai/artifacts/rig-lane-bundle-$(date +%Y%m%d)` and copy that folder to the RIG.
2. RIG (Unreal + the MetaHuman plugin installed and enabled): in PowerShell from the bundle folder
   `.\Install-UnrealWorker.ps1 -UnrealRoot 'C:\Program Files\Epic Games\UE_5.x' -MemoryGiB 12`   (12 is the default; the limit caps committed memory, so a MetaHuman job may need more - rerun the installer with a larger value)
   It verifies the bundle, pins this Unreal install (`unreal-runtime-provenance.json`), writes the config and starts scheduled task `WatooM-Unreal-Lane`.
3. Homelab: `sudo python3 ansible/roles/watoom-code/files/skills/watoom-metahuman/scripts/rig_lane.py submit probe`, then `status <job>` and `collect <job>`.

Adding an operation = a new entry in `OPS`, its pinned script, a rebuilt bundle and a reinstall (the provenance changes on purpose).

## Progress and result diagnostics

The worker best-effort uploads `uploads/ue-<job>/progress.json` when it enters `FETCHING`, `RUNNING` and `UPLOADING`. The file contains only the job id, phase, Unix timestamp and fixed operation name. A progress upload failure does not affect execution or completion; `result.json` remains the final completion marker and is still uploaded last. The lab reads progress as optional, so a missing file from an older installation remains a normal pending job.

Failure results keep their existing status and include `failure_stage` and `failure_code` for manifest rejection, staging failure, runner timeout/OOM/error and restart recovery. Updating `worker-source/unreal_worker.py` requires the owner to rebuild and reinstall the lane. `build_lane.py` regenerates `unreal-lane-provenance.json` from the changed worker source; no Unreal executable/runtime pin changes are needed. Do not edit pinned provenance by hand.
