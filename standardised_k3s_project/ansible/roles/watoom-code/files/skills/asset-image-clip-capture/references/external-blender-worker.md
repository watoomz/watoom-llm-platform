# Declarative external Blender capture

The native tool derives the selected project and reads `.opencode/capture-jobs/<job>/request.json`. It accepts no executable code or tool paths. Only workflow/builder roles may submit. Initially enabled project: `/data/ai/projects/images`; other projects require operator IaC approval.

Manifest schema 1 requires `mode` (`inspect`, `still`, `turntable`, `animation`, `pose-inspect`, `pose-prepare`), absolute canonical `source` (.blend/.glb/.gltf) and exact `source_sha256`. Sources must be within the configured roots or selected project. Begin with inspect to obtain real object, image, rig and Action names. Inventory does not render the default model state.

Optional fields: `visibility:{show:[exact names],hide:[exact names]}`, `camera:{view:"front"|"three-quarter"|"side"|"back",framing:"full",margin:1.15,preserve:false}`, `lighting:"studio"|"preserve"`, `resolution:[768,1024]`, `samples:24`, `frames:[1,1]`, `fps:24`, `output_format:"png"|"mp4"`, `action`, `armature`, `pose:[{armature,bone,rotation_euler:[x,y,z]}]`, `source_asset_id`. Pose angles are radians. Use only observed names and authorized changes. MP4 requires multiple-frame mode and installed configured encoder. No arbitrary scripts, expressions or shell commands.

Limits: pinned Blender5.2.1; the server profile uses actual systemd MemoryMax4GiB, zero swap,2CPU,900seconds with 2GiB extra headroom and CPU Cycles. The RIG profile uses an actual 8GiB Windows Job Object, four render threads and 900seconds with OptiX or explicit CPU. No inference parking or shared inference GPU use. SFTP transfers immutable hashed inputs and returned artifacts; restricted SSH carries control metadata only. Preview subdivisions capped1 and texture limit1k for budget; record reduced detail. Resolution64..2048,1..64samples, at most120frames and128Mi framepixels. Longer/high-detail captures require a separate explicitly qualified budget. Failed OOM evidence is retained.

Still/turntable and existing Blender Actions are implemented. Sims package extraction is separate. Fixed pose preparation supports auto, recipe, qualified rig-adapter and ts4-retarget plans, including installed fingerprinted profiles such as ts4-af-shadowheart-mhx-v2-quin. Its subset mapping animates torso/head with static limbs; do not promise full-body retargeting. Missing external textures fail rather than silently rendering replacements. Motion bounds currently sample first/middle/last; review all motion for clipping. Inspect reported image dependencies before render; use a derived texture cache for large assets and preserve originals.

Status files are root-owned `.opencode/asset-capture-requests/<id>.status.json`. The host verifies the original completed native tool call before executing. It never blindly replays RUNNING requests after restart. Read referenced root-owned `result.json`; require successful capture/preparation status, source_unchanged=true and actual output hashes. Server receipts require cgroup_memory_max4294967296 and cgroup_limit_verified=true. RIG receipts require platform=Windows, memory_limit_bytes8589934592 and memory_limit_verified=true, with pinned renderer/helper hashes checked by the root bridge. Never invent Linux cgroup fields for Windows. Output is `.opencode/captures/<job>/`. CAPTURED_VISUAL_REVIEW_PENDING is not visual acceptance; inspect the real PNG or clip before claiming success.

Existing clothing body masks can be explicitly toggled with `modifiers:[{object:"observed body mesh",name:"observed mask modifier",enabled:true}]`. Only MASK modifiers are allowed. The inventory lists exact modifier names; do not infer them. Their visibility drivers are muted only in memory for this derived capture.

## Dispatcher identity and use

Application agent: prepare the manifest, then use the native request/status calls
above. The dispatcher is not a tool or a shell executable to invoke manually.

Host operator/IaC paths:

- Timer `watoom-game-worker.timer`: checks after boot and every30seconds after an
  inactive dispatcher run. Service `watoom-game-worker.service` runs the shared
  dispatcher; its768MiB cgroup is orchestration only.
- Entry point `/data/github/watoom-standardised-homelab/standardised_k3s_project/tools/watoom-code/game_worker_bridge.py`
  imports `asset_capture_bridge.dispatch` from adjacent `asset_capture_bridge.py`.
- Configuration `/etc/watoom-asset-capture.json` pins project/source roots,
  Blender path/hash and encoder. No per-request executable selection is accepted.
- After checking the native admission proof, the bridge calls adjacent
  `asset_capture.py --project <project> --job <job> --evidence <private-root-dir>
  --i-approve --expected-manifest-sha256 <sha>` once. That operator CLI creates
  the separate4GiB capture worker. Agents do not imitate this invocation.

For a stalled queue, an authorized operator checks
`systemctl status watoom-game-worker.timer watoom-game-worker.service --no-pager`
and `journalctl -u watoom-game-worker.service -n40 --no-pager`, then the matching
flat `.opencode/asset-capture-requests/<request_id>.status.json` and its referenced
root receipt. No `<request_id>/status.json` directory exists. QUEUED may wait for
the timer/headroom; RUNNING/uncertain evidence must be reconciled before retrying.
Do not start a second dispatcher, clear request records or replay a job manually.
Maintain changes through `ansible/roles/watoom-code/tasks/game_worker.yml` and
`asset_capture_worker.yml` in the authoritative repository.

With workstation_enabled, new native requests retain the same admission identity and are pulled by the RIG. Existing admitted host requests stay on their original route. An interrupted queued request cancels before claim; already executing work finalizes without resuming interrupted sessions. Uncertain claims require operator reconciliation, never automatic re-render. The manual staging inbox is retained for operator qualification; normal model jobs use the same native tool, not a second spool.
