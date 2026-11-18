# Shadowheart MHX control adapter v1

Use only `shadowheart-mhx-v1` after `pose-inspect` returns `adapter-inventory.json` with `compatible:true`. The registry checks 516 bones, 29 control/rest/lock/constraint signatures, and 20 actual IK/FK driver definitions. Renamed/restructured or modified rigs fail closed; matching a name alone is insufficient. The profile is `adapters/shadowheart-mhx-v1.json`. It qualifies the known 1k prepared Shadowheart rig and structurally matching derivatives, not every MHX rig or arbitrary original asset.

## Native request

Write a fresh capture job manifest and submit it through native `watoom_asset_capture` with `{action:"request",job:"<fresh-job>"}`. Keep the same job for status; do not invoke Blender or helper scripts in the app. The fixed worker remains CPU-only, two threads, 4GiB and 900 seconds.

```json
{
  "schema": 1,
  "mode": "pose-prepare",
  "source": "/absolute/verified/source.blend",
  "source_sha256": "<actual SHA256>",
  "preparation": {
    "method": "rig-adapter",
    "plan": {
      "schema": "watoom.rig_pose.v1",
      "adapter": "shadowheart-mhx-v1",
      "armature": "Shadowheart",
      "frame": 1,
      "targets": {"hand.L": [0.38, -0.20, 1.25]},
      "tolerance": 0.015
    }
  }
}
```

Coordinates above are one tested target for the known prepared source, not a universal pose. Read the current inventory's world endpoints before planning. For a moved/scaled rig measure world positions from that rig.

## Controls and mode selection

- `targets`: world-space anatomical endpoint positions for `hand.L`, `hand.R`, `foot.L`, `foot.R`. Feet mean evaluated ankle/foot bone head, not the offset IK handle origin. The adapter moves the real handle by measured endpoint error and verifies the result. A target selects IK on its limb. Declare both foot targets when feet must stay planted.
- `controls`: `hips` supports `world_position` and local `rotation_euler`; `elbow.L/R` and `knee.L/R` support world-position pole placement only. `head`, `spine`, `chest`, `hand_ik.L/R`, `foot_ik.L/R` support local rotations. FK controls are `upper_arm.fk.L/R`, `forearm.fk.L/R`, `thigh.fk.L/R`, `shin.fk.L/R`.
- `switches`: `arm.L/R` and `leg.L/R` accept `IK` or `FK`. FK controls require an explicit FK switch and cannot conflict with an endpoint target on that limb. Only the four observed MhaArmIk/MhaLegIk properties are keyed; no arbitrary property editing.
- Local Euler angles are radians in the observed control's native Euler order; quaternion-mode controls use XYZ Euler input converted to a quaternion. Use the inventory/profile to inspect order and authored limits. Locked channels, unknown controls and out-of-limit rotations are rejected. Constraints and drivers are preserved, never muted to force a result.

Hips are controlled through `hip`; the locked `pelvis` bone is not translated. Hip movement is qualified through this rig adapter only; it does not enable the generic auto helper's pelvis translation.

## Acceptance and limits

The adapter copies the working Action, evaluates the frame before edits, keys mapped controls/switches, verifies deform change and endpoints, saves a new source and reopens it to reverify channels, endpoints and preserved constraints/drivers. `pose-validation.json` records these checks, profile hash and rig fingerprint. `posed.blend` is a candidate; status remains `PREPARED_REVIEW_PENDING` / `SAVED_UNVALIDATED_POSE`. Root-owned receipts contain source/output/helper hashes and actual cgroup limit.

Real-rig tests covered hand IK with planted feet, lowered hips with bent knees and planted feet, and FK arm switching. Unreachable targets, authored joint-limit violations and a wrong rig fail closed. Rendered clothed hand/FK previews were reviewed. The deep seated test **failed garment visual acceptance**: camp pants show severe hip/thigh deformation/intersection artifacts. Do not reuse that seated candidate as an accepted recipe or mark it final. A scene chair/support, collision-free clothing fit, balance and natural wrist orientation are not certified by endpoint checks. Inspect front/side/three-quarter pixels; adjust the pose or delegate garment fitting to asset editing if needed. Preserve camp shirt, pants, shoes and the pants body mask in capture requests.

After preparation, use the returned `prepared_source` and exact output hash for a separate `still`, `turntable` or `animation` capture job. Single-frame rig posing is qualified here; authored motion and video need their own temporal/deformation review. No old app job is resumed by loading this skill.

Evidence: `/data/ai/helper-scripts/shadowheart-rig-adapter-20261025/`.
