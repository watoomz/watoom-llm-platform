---
name: workstation-render-stage
description: Offload supported asset inspection, pose preparation, stills, animation and MP4 captures to the admitted RIG worker through the native capture tool; verify receipts and review pixels.
metadata:
  opencode/autoinvoke: false
---

# Workstation capture worker

Use the same native watoom_asset_capture request/status tool documented in asset-image-clip-capture. Write a fresh declarative .opencode/capture-jobs/<job>/request.json in the selected authorized project, then submit once and retain its stable identity. The configured bridge routes new native jobs to the RIG; existing admitted jobs retain their route. Do not create another request for an existing or failed job.

All six original modes are supported: inspect, still, turntable, animation, pose-inspect, pose-prepare. Preparation uses fixed installed auto/recipe/qualified rig-adapter/ts4-retarget helpers. Use real observed rig names and fingerprinted profiles. The Quin TS4 subset animates torso/head with static limbs. PNG and MP4 are supported, including existing Action loops. glTF external buffers/textures and Blender linked libraries are snapshotted and remapped with verified hashes; originals stay unchanged. No arbitrary scripts or commands are admitted by this capture tool.

Pinned Blender 5.2.1, OptiX or explicit CPU, one slot, 8GiB Windows Job Object, four render threads, 900-second capture deadline. GPU VRAM is not hard-capped. Component pipelines separately enforce 300-second stages. Bulk transfer uses jailed SFTP with SHA-256 verification and resumable transfers; SSH control transports metadata only. The 2GiB app shell never runs Blender. Custom asset-building stages still require a separately admitted external execution route; capture capabilities do not imply arbitrary stage dispatch.

Require the matching root-owned native status and receipt, unchanged original source, pinned renderer/helper hashes, Windows memory_limit_verified=true and memory_limit_bytes=8589934592, and verified output hashes. CAPTURED_VISUAL_REVIEW_PENDING or PREPARED_REVIEW_PENDING requires actual pixel/pose review. QUEUED is not completion. Lost execution leases require reconciliation; never blindly replay. Paused jobs remain paused. The old manual inbox is operator qualification only.

```prompt-builder
{"version":1,"kind":"pipeline","id":"workstation-render-stage","title":"Workstation Blender capture (stage)","description":"Use the native capture tool for RIG inspection, pose preparation, stills and animation, then verify root receipts and review pixels.","category":"Validation","availability":"available","keywords":["workstation render","RIG Blender","Windows render offload","OptiX","retarget","MP4"],"requires":["asset-image-clip-capture"],"fields":[{"id":"asset","label":"Source asset","required":true},{"id":"capture","label":"Pose, view, frames and render budget","required":true}]}
```
