---
name: asset-image-clip-capture
description: Render stills, pose previews, turntables and authored animation clips from existing 3D assets. Resolve actual rig controls and run the verified bounded capture worker; preserve the source. Use for asset render/capture requests, not diffusion generation or new asset building.
---

# Asset image and clip capture

Render the user's existing asset and requested pose/view. Preserve source files,
appearance and clothing; reuse matching verified preparation. Discover technical
controls yourself. Read only the relevant inventory and references.

## Execute through the native capture dispatcher

In `/data/ai/projects/images`, workflow and builder use **native
`watoom_asset_capture`**. It is neither a shell executable nor a Godot profile.
The existing **`watoom-game-worker.timer` → `watoom-game-worker.service`** dispatches
both game and Blender requests. The dispatcher is already installed; agents do not
start it or search for another queue. It routes new requests to the admitted **8GiB RIG Windows worker** when enabled, or the separate **4GiB server CPU worker**; its own 768MiB service limit is not the render limit.

Read [external-blender-worker.md](references/external-blender-worker.md) for the
exact dispatcher files, operator diagnostics, manifest schema and receipt paths.

1. Resolve source/hash and verified cache. Inspect with a separate native job only
   when the needed object, material, rig or Action inventory is missing. Recipes
   are optional; reviewers/investigators inspect evidence, one builder executes.
2. Read [pose-controls.md](references/pose-controls.md) for posing and
   [video-capture.md](references/video-capture.md) for clips. Use actual controls,
   evaluate the frame before overrides, key a working Action copy, and verify
   evaluated deformation and post-render channels. An A-pose does not pass a
   requested gesture or seated pose.
3. Create `.opencode/capture-jobs/<fresh-job>/request.json` completely **before**
   calling `{action:"request",job:"<fresh-job>"}`. Record its request ID.
4. Yield after QUEUED. The dispatcher notifies the coordinator. If status is
   needed, call `{action:"status",job:"<same-job>"}`; do not repeatedly submit.
5. Match the root-owned terminal status and receipt: successful status, verified worker boundary (server 4GiB cgroup or RIG 8GiB Windows Job Object),
   unchanged source and fresh valid output hashes. Review real pixels/motion
   against requested pose, clothing, framing and quality. Technical completion
   and visual acceptance are separate; return the actual media.

## Recovery and supported scope

### Project admission preflight

The coordinator AND executing builder must be registered in the native images
project (`session.location.directory` exactly `/data/ai/projects/images`). This
is session metadata, not shell cwd, source location or manifest location. A
session started in a pipeline staging directory is not an images session even
when it can write image-project files. Check only project metadata for this
preflight; task messages and personal data are unnecessary.

`ASSET_CAPTURE_PROJECT_DENIED` occurs before request registration, manifest
validation or dispatcher processing. Stop after one denial. Do not copy sources,
retry request/status, change ownership, widen the allowlist or invent a different
dispatcher to solve it. Explain the session-project mismatch. For an authorized
neutral or clothed task, ask the operator/user to start it in the images project;
retain the existing task and request history. The guard remains fail-closed.


QUEUED/RUNNING or uncertain execution: reconcile the same identity, never replay.
WAITING_FOR_HEADROOM: wait without evicting inference. RECONCILIATION_REQUIRED:
retain evidence and request operator reconciliation. For a diagnosed, authorized
retry after CANCELLED/FAILED/STALE_REQUEST, prepare a new directory and job ID;
never delete, overwrite or reassign historical request/status records.

Within render manifests, only observed XYZ rotation controls, existing Actions and MASK modifier toggles
are supported. Bone translation/scale, IK target placement, rig-property switches,
retargeting and arbitrary Python are unavailable. Camera supports full-body
front/three-quarter/side/back or a preserved authored camera. Custom crops need
supported preparation. Report a missing operation once rather than guessing.

The workers use pinned Blender5.2.1 and a 900-second capture deadline: server CPU Cycles/2threads/4GiB/zero swap, or RIG OptiX (explicit CPU available)/4threads/8GiB Windows Job Object
and2GiB extra available headroom. Preview caps are subdivision1/textures1k;
Shadowheart512x768/16samples is validated. Other quality budgets require evidence.
Preserve clothing visibility and body masks; never claim unlimited poses/quality.

For a write failure report the exact path/UID/mode once; operator/IaC owns repair.
Parents: capture-jobs1001:1001/0755, captures1001:1009/2775; worker1001:1001.
Never recursively change ownership or launch Blender in the app shell. If the
native tool is absent, report the current role/project instead of probing wrappers.

Use [generic-capture.md](references/generic-capture.md) only for needed preparation.
Optional shortcuts: [clothed recipe](references/shadowheart-clothed-preview.md),
[tested rig controls](references/shadowheart-rig.md),
[semantic pose requests](references/generic-pose-render.md). Save a per-asset recipe
only after acceptance. Skill names do not create worker capabilities.

## Request form

The following prompt-builder supplies task inputs; it does not itself launch a render.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "asset-image-clip-capture",
  "title": "Asset image or animation clip",
  "category": "Validation",
  "availability": "available",
  "keywords": ["asset_image_clip_capture", "asset preview", "asset screenshot", "animation clip", "turntable"],
  "fields": [
    {"id":"project","label":"Existing project","help":"Selected canonical project path.","required":true},
    {"id":"asset","label":"Asset or scene","help":"Exact source asset and object, collection, node or scene selector.","required":true},
    {"id":"output","label":"Image, animation clip, or turntable","help":"Use the actual asset; describe a still, requested pose, turntable, existing clip or newly requested motion.","required":true,"default":"One still image, useful three-quarter view."},
    {"id":"capture","label":"View and timing","help":"Desired view, pose or motion, duration and output quality; technical preparation is discovered from the asset.","required":true,"default":"Verify pose and materials with a small preview first, then validate requested quality. For clips, use the actual action duration and budget the frame count against the worker timeout."}
  ]
}
```

## Rig-aware pose preparation

For detailed humanoid inspection, calibrated quaternion channels or FK endpoint goals, use [human-pose-agent](../human-pose-agent/SKILL.md). Submit fixed `pose-inspect` or `pose-prepare` manifests through the SAME native `watoom_asset_capture` request/status tool and admitted external worker. `pose-inspect` emits human-pose `inspection.json`; normal `inspect` emits capture `inventory.json`. `pose-prepare` accepts only declarative auto/recipe plans, never script paths or commands, and returns a new `.blend` plus validation and hashes. Review pose/anatomy/clothing before accepting it, then use its exact path/hash for a separate still/clip request. WARN and PREPARED_REVIEW_PENDING are candidates, not visual PASS. Do not invoke the app-shell builder runner for preparation; arbitrary builder stages still have no verified dispatcher. Constrained rigs still require a qualified adapter.

For Shadowheart MHX, use the fingerprinted `human-pose-agent` rig-adapter route when `adapter-inventory.json` matches. It supports the observed IK/FK switches, real hand/foot targets, poles and hip control. Read its contract before authoring a plan; deep hip bends can fail garment review despite exact endpoint checks.
