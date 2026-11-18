# Blender automation guidance review

Reviewed TerminalSkills sources at commit a021875c0f1bd906248e3784ce470faa65055201. This is a selective operational synthesis; existing MIT skill sources remain unchanged. The linked upstream skills declare Apache-2.0. No upstream scripts, installers or runtime claims are adopted wholesale.

## Choose the execution route

Existing-asset stills, pose previews and clips use asset-image-clip-capture and its native dispatcher. Its pinned Blender 5.2.1 workers use server CPU/4GiB or RIG OptiX/8GiB. Component policy is in worker-execution.md. Builder preparation now selects the same pinned Blender 5.2.1 binary after CPU qualification; the old 4.2.23 runtime remains available for rollback. Confirm the actual selected binary/version from existing environment evidence. A generic Blender API example does not expand the capture manifest, authorize app-shell execution or qualify a new runtime.

## Animation

[Animation source](https://github.com/TerminalSkills/skills/blob/a021875c0f1bd906248e3784ce470faa65055201/skills/blender-animation/SKILL.md)

For authoring, key object/bone channels on a working Action; preserve rotation mode and explicitly convert only when required. Inspect constraints, drivers and IK/FK controls before selecting channels. Frame evaluation precedes pose overrides. Keep source Actions and NLA state intact. Existing 4.2 adapters use their qualified legacy F-Curve path; newer layered Actions require slots/channelbags. Detect the actual API before editing curves. Never transplant newer slot helpers into the 4.2 runner. NLA layering, shape keys, drivers and retargeting are preparation capabilities only when the selected adapter supports them. They are not new capture manifest fields. Verify evaluated deformation and rendered motion rather than accepting changed channel values alone.

## Rendering

[Render source](https://github.com/TerminalSkills/skills/blob/a021875c0f1bd906248e3784ce470faa65055201/skills/blender-render-automation/SKILL.md)

Discover engine identifiers and optional properties from the selected Blender build. Retain CPU Cycles on current bounded routes; upstream OptiX/device selection is not local authorization. Reuse authored cameras, lighting and materials where suitable. Aim cameras using subject bounds and verify framing, clipping and exposure in a small preview. Request transparent PNG explicitly when needed. For video, budget frame count against measured time and memory; preserve recoverable frame outputs where the adapter supports them. On newer builds, inspect media_type before setting video format. Follow video-capture.md for the actual supported route, encoding and ffprobe/pixel checks. Do not clear an existing world/material graph as a generic setup step.

## Scripting and version changes

[Scripting source](https://github.com/TerminalSkills/skills/blob/a021875c0f1bd906248e3784ce470faa65055201/skills/blender-scripting/SKILL.md)

Use the existing runner and its failure reporting; raw operator launches must preserve nonzero Python failure status. Blender CLI argument order matters; script arguments follow --. Prefer data APIs for independent data edits; operators require a valid mode, active object and selection. Resolve nodes by type and inspect socket names. Use modern OBJ operators only on supporting builds. Batch edits save separate derivatives and release temporary meshes/bmesh resources. Do not run inherited install commands or pip-install bpy into the application. An upgrade needs side-by-side adapter, Action, export, pose, render and recovery checks before switching the pinned binary; retain the old runner and source assets for rollback.
