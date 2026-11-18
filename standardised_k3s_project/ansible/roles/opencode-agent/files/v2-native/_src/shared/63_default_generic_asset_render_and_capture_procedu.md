## Default generic asset render and capture procedure
Use asset-image-clip-capture for captures of an existing asset. In /data/ai/projects/images, the execution route is the native watoom_asset_capture tool, not a shell executable, arbitrary script runner, fixed Godot capture or full asset-building pipeline. Workflow/builder submits one declarative .opencode/capture-jobs/<fresh-job>/request.json then {action:"request",job:"<fresh-job>"}; yield after QUEUED and consume the root-owned completion receipt. Blender loading, rig inspection, posing and rendering run only in the separate4GiB CPU worker. Reuse matching verified preparation; read references/external-blender-worker.md for execution, references/pose-controls.md for requested articulation, or references/video-capture.md for video. Observe real rig controls; evaluate the chosen frame before explicit rotations, verify the deform result and inspect actual pixels. Preserve the asset and requested clothing. No guessed bone names or unsupported IK/translation/camera/script fields. CANCELLED jobs require a newly created job directory and ID; never delete/reassign records or retry the cancelled identity. Do not confuse a queue, a static pose or camera orbit with completed requested body motion. Ask only for missing creative/source information; report exact adapter gaps once.

Visual review requires exact image presentation through a configured verified
vision model. A successful PNG read alone does not establish pixel access.
If model=null or VISION_MODEL_REQUIRED is reported, preserve the completed capture
and existing child; report the missing routing capability. Never invent pixel
observations, manufacture a null-model receipt, or repeat the capture.
At a checkpoint boundary use write with verified complete content rather than
repeatedly editing oldString text that is no longer present.
<!-- END WATOOM DEFAULT CAPTURE RECIPE -->
