# Generic pose and render recipe v1

Recipe ID: `generic-pose-render-v1`.
Canonical folder: `/data/ai/archive/projects-20261029/pipelines/sims4-mod-studio-staging-20261024T082059Z/implementation/recipes/generic-pose-render-v1`.

Use for a user-described pose and still capture of an existing rigged asset. A coordinator/builder interprets the natural-language request, verifies the real rig, and submits concrete declarative edits to the existing external worker. This recipe itself neither launches Blender nor adds rigging capabilities.

## Request

Accept the source asset name/ID/path, requested pose in ordinary language, clothing/appearance to preserve, optional existing scene props, camera and output preferences. `intent-template.json` is a conversational planning form, not a worker manifest. Resolve the asset from existing selected-project evidence; ask only for essential missing details. If unspecified, preserve authored clothing/appearance, use a neutral studio view showing the pose, and begin with a low-cost still preview. Do not add props, change proportions, invent animation or overwrite originals implicitly.

Examples:
- Render the existing character standing, weight on the left leg, right hand on her hip, looking toward the camera. Keep the camp outfit.
- Seat the character on the existing chair, feet on the floor and hands resting on her knees; show a three-quarter view.
- Keep the existing body pose, turn the head toward the camera and preserve the authored portrait camera.
- Render the rigged robot with its right arm raised, full body, front view.
- Render two separate clothed poses, standing and seated, with matching lighting and separate PNGs.

Examples are goals, not guarantees that every source rig or the current adapter supports them. Seated poses, exact hand/foot contacts and gaze targets commonly require translation, IK or constraints; check those capabilities first.

## Reuse verified preparation

Use `asset-image-clip-capture` and its generic procedure. Reuse a matching hash-pinned prepared derivative, texture cache and dependency mapping when they preserve the requested asset; otherwise inventory only the selected source in an external worker. Validate current files/hashes, not only a historical success label. Asset-specific names and settings from Shadowheart are not universal rig mappings.

Use the deployed `watoom_asset_capture` native tool in selected project `/data/ai/projects/images`. It is not a shell executable and is absent for read-only roles. Workflow/builder may request; investigator/critic supplies read-only findings. Other projects require operator-approved IaC configuration. Supported input extensions are .blend/.glb/.gltf; the existing still test qualified a particular .blend, not every importer or rig. Blender5.2.1 LTS is pinned by the operator config.

## Inspect and resolve the pose

Submit a fresh `mode:"inspect"` manifest with canonical source and actual SHA-256 when current inventory is missing. Read its object names, armatures, actual pose-bone/control names, Actions, materials, images and visibility. The inventory alone does not prove a control responds correctly: use existing rig documentation or authorized bounded inspection to establish local axes, rest pose, constraints, IK/FK switches and animation/driver ownership. Never guess bone names or port rotations from another character.

Write a project-local pose plan containing the user's exact intent, selected rig/control names, supported concrete edits, camera/framing, required props/contacts and visual acceptance criteria. Map the requested anatomy to verified controls. Preserve outfit visibility and any observed clothing MASK modifiers. Verify that constraints, drivers, keyed animation or frame evaluation will not erase the edits. The tuned adapter evaluates the frame first, then applies explicit rotations and writes pose-evidence.json; overridden channels or changed controls with no evaluated deform-bone movement fail. Do not claim a requested pose is supported until its evaluated result is proven.

Current declarative edits are `pose:[{armature:<actual object name>,bone:<actual pose-bone name>,rotation_euler:[x,y,z]}]`, XYZ Euler rotations in radians, finite values within +/-pi, at most128 edits. Existing `action` with actual `armature` and a selected frame can reuse an authored pose only when it matches the request. No arbitrary scripts, free-text pose field, bone translation/scale, IK target positioning, IK/FK custom-property switching, constraint creation, prop creation or automatic rig retargeting is exposed by this adapter.

If the requested pose requires an unavailable control operation, return POSE_ADAPTER_BLOCKED with the exact missing operation and a bounded proposed extension. Retain the request and useful discovery. Do not run arbitrary Python in the app, invent a script-mode worker operation, remove constraints or silently render the default A-pose. Ask whether an observed existing Action/frame is acceptable only when it is a meaningful alternative. User authorization is needed for source/rig edits outside the requested derived pose.

## Create a concrete manifest and capture

Before submission, validate a schema1 manifest against `tools/watoom-code/asset_capture_contract.py`. Required fields: `schema`, `mode:"still"`, canonical `source`, actual `source_sha256`. Add only supported optional fields: `source_asset_id`, explicit `visibility.show/hide`, existing MASK `modifiers`, verified `pose` rotations or observed `action`/`armature`, chosen single `frames:[frame,frame]`, `camera`, `lighting`, `resolution`, `samples`, `output_format:"png"`.

Camera currently supports `view:front|three-quarter|side|back`, `framing:full`, `margin:1..2`, or `preserve:true` for an existing authored camera. A close portrait/custom camera is not an exposed new-camera framing mode: use a verified authored camera or report that preparation requirement. Lighting is studio or preserve. No arbitrary fields such as pose_prompt, script, command, target or translation may be sent to the native tool or manifest.

Start with512x768,16samples unless the source/request justifies another supported preview budget; preserve aspect ratio as appropriate. Contract bounds are64..2048pixels per side and1..64samples; allowed bounds do not prove the source fits4GiB or meets high-quality acceptance. The current worker caps subdivision1 and textures1k. Do not describe that as unrestricted final-quality rendering. Validate any later requested resolution/detail independently.

Save the concrete manifest at `.opencode/capture-jobs/<fresh-stable-job>/request.json`; request via `watoom_asset_capture` exactly `{action:"request",job:"<fresh-stable-job>"}`. The tool derives the selected project. Yield after QUEUED; wait for its completion notification or check `{action:"status",job:"<same-job>"}`. The dispatcher verifies the persisted native call, source revision and actual worker. Existing requests, RUNNING or uncertain work must be reconciled; never resubmit blindly. Use one separate job per output and per reviewed revision.

Execution uses the existing separate systemd worker: actual memory.max4294967296, zero swap,2CPU/2threads,900seconds, CPU Cycles, at least2GiB extra available headroom. Keep journal logging, automatic script execution disabled and --python-exit-code1. Do not launch heavy engines in the app, alter inference, relax guards or increase memory to make a pose work.

## Acceptance and adjustment

Require root-owned COMPLETED status, exit0, cgroup_limit_verified=true, source_unchanged=true, fresh correctly sized PNG and output hash. Inspect the actual pixels: requested body/head/limb arrangement, clothing coverage, natural joints, hand/foot contacts, balance, framing, textures and clipping. A successful render exit, changed image hash or historical portrait does not prove the new pose. When controls did not move the evaluated mesh, diagnose that exact rig dependency before another revision.

If an adjustment is needed, preserve the previous image and receipt, change only the diagnosed controls/camera, and use a new revision job after the prior job is terminal. Stop if the same unsupported operation or failure repeats; do not cycle through guesses. Save a per-asset pose recipe only after visual validation, with actual control mapping, source/dependency identities, settings and receipt.

Return the image and truthful pose/quality status. For multiple poses, validate each independently. This recipe authoring request does not execute a new render or modify the current job.

For the maintained execution details, read pose-controls.md and external-blender-worker.md in this skill. For video use video-capture.md.
