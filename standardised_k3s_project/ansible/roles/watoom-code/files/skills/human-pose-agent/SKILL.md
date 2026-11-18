---
name: human-pose-agent
description: Inspect humanoid Blender rigs and prepare new pose assets using calibrated local channels or bounded FK-chain IK. Use for rig-aware pose preparation before asset capture; constrained control rigs need a qualified adapter.
---

# Human pose preparation

Use the native `watoom_asset_capture` request/status lifecycle for the fixed installed helpers on the separate 4GiB CPU worker. Read [execution contract](references/environment.md) for manifests and outputs. No app-shell Blender or Python builder wrapper is involved.

| Requested operation | Manifest mode and output |
| --- | --- |
| Detailed humanoid rig inspection via `prepare_pose.py` | `pose-inspect`: `inspection.json` from human_pose_agent |
| Measured FK endpoint solving or calibrated local channels | `pose-prepare` with `preparation.method` `auto`, `recipe` or qualified `rig-adapter` and inline JSON `plan`: `posed.blend`, `pose-validation.json`, detailed inspection |
| General capture inventory | `inspect`: capture `inventory.json`, a different schema |
| Existing Action / supported XYZ rotations, still or clip | `still`, `turntable` or `animation` through asset-image-clip-capture |

Write a fresh `.opencode/capture-jobs/<job>/request.json` in `/data/ai/projects/images`, hash the exact `.blend`, then call the native tool with `{ "action":"request", "job":"<job>" }`. Keep that identity and read status/receipt; never replay uncertain work. Scripts, executable strings and helper paths are not accepted in manifests. The fixed adapter invokes installed `prepare_pose.py`, `human_pose_agent.py` and `auto_ik_validation.py` and records their hashes.

Preparation completion means a candidate exists, not an approved pose. `PREPARED_REVIEW_PENDING`, `WARN` and `SAVED_UNVALIDATED_POSE` require actual evaluated/visual review before delivery. Use the prepared source path and SHA from the root-owned receipt for a separate normal capture request. The worker preserves the original and rebases dependencies when making its working copy. Unsupported rig paths remain BLOCKED. If these modes are absent from the native tool, report an activation/version mismatch; do not fall back to the app-shell builder.

For a complex Shadowheart MHX rig, read [the fingerprinted rig adapter](references/shadowheart-mhx-adapter.md). `pose-inspect` now emits `adapter-inventory.json`. When compatible, `pose-prepare` accepts `preparation.method:"rig-adapter"` with its fixed semantic control/endpoint plan. This supports observed IK/FK switches, translated hand/foot targets, poles and hip control without disabling constraints. A seated numerical pass does not prove clothing fit; the reviewed deep seated sample failed garment acceptance.

Inspect first; select the exact armature and map actual bones, rest axes, constraints, locks and drivers. The 25 catalog entries are semantic task descriptions, not solved pose presets. Measure endpoint goals, support contacts and ground height for the asset. Supplied JSON files are examples, never ready-to-apply plans.

The automatic path handles only directly parented, unconstrained FK chains and explicit world-space targets. Constrained rigs, IK/FK switches, translated IK targets and unknown control paths require a qualified rig adapter. Pelvis translation is not enabled by the maintained wrapper pending keyed-animation qualification. Do not disable constraints to force a solve. Recipes require actual calibration and human review; never manufacture approval flags. Preserve clothing, skin masks, source Actions and source files.

Read the supplied [guide](references/AGENT_GUIDE.md) only for detailed schemas and solver mechanics. The maintained wrapper and current runtime acceptance take precedence over its packaging-time NOT TESTED statements. Eight synthetic regression groups passed on Blender5.2.1; real-character posing, multi-limb shared-parent solving, biomechanical stability, engine export and complex control rigs are not universally qualified. Read [acceptance scope](references/acceptance.json) before claiming support.

FAIL/BLOCKED forbids output acceptance. WARN or SAVED_UNVALIDATED_POSE is a review candidate, never an approved pose. Review actual evaluated deformation and front/side/three-quarter previews for anatomy, contacts, clipping and clothing. Numerical collision/balance checks are approximate and incomplete. Do not claim clean clothing intersections from a warning-free report alone.

Once preparation passes the task's review, capture the new `.blend` using `asset-image-clip-capture`, the existing native `watoom_asset_capture` request/status lifecycle and its separate4GiB CPU worker. Keep one stable capture identity; no arbitrary Python in a capture manifest. This preparation skill does not expand capture fields, worker limits or engine-export claims.
