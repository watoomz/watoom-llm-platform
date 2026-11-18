# WatooM — Human Asset Posing Agent v2

## Purpose

Inspect an unknown Blender character, identify what it can actually articulate, then pose it with grounded reference, anatomical constraints and explicit validation. **Do not automatically assume Mixamo, Rigify or any other rig format.** The script is an inspector and calibrated-channel executor, not a universal inverse-kinematics solver.

## Execution

In Blender's CLI (substitute actual executable and asset path):

```bash
blender -b /absolute/path/character.blend --python /absolute/path/human_pose_agent.py -- --report /absolute/path/new-inspection.json
```

The inspector creates a new report (never overwrites an existing report), describing: all objects; skinned meshes and vertex groups; shape keys; armatures; full bone hierarchy/rest coordinates; rotation modes and locks; IK/other constraints; animation action; guessed semantic bone roles; missing/ambiguous roles; and 25 pose task descriptions. Import `.fbx`/`.glb`/`.gltf` to an isolated `.blend` copy first using version-supported Blender tools. Never overwrite a source game asset.

## Agent policy and decision tree

1. **Discover**: inspect report; identify human armature and bound meshes; if none, mark **BLOCKED: NOT_RIGGED**, and offer a separately approved rigging step. Do not pose a static mesh by pretending vertex groups are bones. In multi-character scenes select by exact armature name.
2. **Classify rig**: deform skeleton vs control rig; IK targets and pole controls; constraints/drivers; custom props/IK-FK switches; active actions; bone scale and armature world transforms. Map roles using geometry and hierarchy, *not solely names*. Distinguish missing fingers/toes, facial controls, weapon bones, props and clothing.
3. **Calibrate**: establish asset forward/up, ground, foot sole offset, rest stance, bend-plane for both knees/elbows, axis orientation of controls, and locked channels. Test a small controlled bend on a throwaway copy (with snapshot) and verify world-space result, then revert. A rig with unknown channels is **NEEDS_CALIBRATION**, not ready to pose.
4. **Choose** task from `pose_catalog`; model action as **contacts → pelvis → torso → planted/swing limbs → hands → head → secondary asymmetry**. For animation, create separate contact, anticipation, passing, flight/peak, impact and settle keys as appropriate. Do not substitute a static key for a complete locomotion cycle.
5. **Solve** desired end-effectors and body balance using *actual* geometry. Static: centre of mass projection over foot/knee/seat polygon; dynamic: plausible fall/recovery direction. Contact feet/objects without penetrations or sliding. Sit on real chair height, not arbitrary Z=0. Choose an IK solver appropriate to the actual rig; do not invent a Blender API flag.
6. **Express** only verified local bone/control channels as quaternion `[w,x,y,z]` and optional local translation. Apply with supplied executor only when `calibration_verified` and `human_reviewed` are true. These flags are assertions provided by the agent/reviewer, **not proof that calibration has occurred**. Never forge them. For complex constrained rigs a separate rig-aware solver may be necessary.
7. **Validate** evaluated joint locations, bone lengths, limb bend direction, foot contact, clipping, weight balance, finger grips, silhouette and torso twist from front, side and three-quarter views. Compare with actual human references and original asset. Any automated assessment should report uncertainty; if not testable, mark **NOT TESTED**.
8. **Deliver** new `.blend`, independent pose report/JSON and screenshots/renders, never overwrite the source. Export FBX/GLB to a separate destination only after verifying engine-specific rest pose, root transform, units, keyframes and export support. Report file paths and explicit results.

## Pose quality rules

- **Human weight**: hips/pelvis carry mass; shoulders and head compensate. Quiet idle is slightly asymmetric, not a rigid T-pose.
- **Legs**: flex hips/knees/ankles coherently; no backward knees, fixed ground feet that slide or locked knees on landing. Direction of knees follows feet unless intentionally twisting within anatomical range.
- **Arms**: shoulder blade movement contributes to high reaching; wrists follow grip, forearm follows upper arm; a punching elbow must not snap hyperextended.
- **Spine**: use distributed thoracic/lumbar bends; avoid sharp hinge at one vertebra. Head balances naturally atop neck.
- **Movement**: walk arms swing opposite legs, stance foot bears weight; run adds forward drive and flight; jumps require load/takeoff/flight/landing; lifting requires actual object hand contacts and load-aware stance.
- **Anatomical angle numbers** are not universal control-rotation values: rig rest orientation, bone roll, age, body type, footwear, collision and style can change correct targets. Derive them from the character and reference, not a global X/Y/Z formula.
- **Hands**: if fingers exist, wrap around props with thumb opposition and varied finger flexion. If not, adapt silhouette without pretending digit articulation exists.
- **Physics**: a nice-looking pose is not proof of balance or contact. Check against actual environment meshes and centre of mass estimates where available.

## Example calibrated recipe schema

`sample_recipe_DO_NOT_APPLY.json` is intentionally unapproved. Replace bone names only after confirming actual names, calibrate local channels, complete human review, then set true gates. The example identity quaternion should never be mistaken for a target pose.

```bash
blender -b /absolute/path/character.blend --python /absolute/path/human_pose_agent.py -- --report /absolute/path/pose-run-report.json --recipe /absolute/path/calibrated-recipe.json --output /absolute/path/character-posed.blend
```

## Reference observation set

Use examples as *qualitative observations*, not rig transform truth:

- Walking / running / jumping sequence: https://www.rawpixel.com/search/white%20portrait%20people
- Gait and lower-limb tasks / stairs / hop / sit transitions: https://www.frontiersin.org/journals/bioengineering-and-biotechnology/articles/10.3389/fbioe.2021.793746/full
- Crouching / kneeling / floor poses: https://faestock.com/products/crouching-poses-stock-model-reference-pack
- Leap and landing phases: https://www.animebooks.com/sobopovo2mop.html
- Blender API armature vs pose data: https://docs.blender.org/api/main/info_gotchas_armatures_and_bones.html

These sources are for pose study only; do not copy or redistribute reference images into game assets without license review. The script ships no copyrighted pose images or generated motion captures.

## Status and limits

- **VERIFIED**: Python 3 syntax compiles; preset catalog includes 25 task descriptions; the script source writes a structured JSON inspection and can keyframe supplied local quaternion channels.
- **NOT TESTED**: no Blender runtime or user's character assets available in this execution environment, so rig discovery, Blender compatibility and visual quality have not been runtime verified.
- **BLOCKED**: automatic generic rig solving without calibration; actual game-engine export validation; collision and quality scoring without an asset/environment-specific evaluator.

## Automatic IK and clipping/balance verification (v2)

`auto_ik_validation.py` adds **bounded CCD IK** for unconstrained FK arm/leg chains, and automated geometry checks. Supply measured world-space endpoint goals in `sample_auto_plan.json` (replace sample values and armature name). Targets and pole positions are **not** inferred from a pose name: the agent must choose them from asset measurements, reference poses and scene contacts.

```bash
blender -b /absolute/path/character.blend --python /absolute/path/human_pose_agent.py -- --report /absolute/path/fresh-inspection.json --auto-plan /absolute/path/actual-auto-plan.json --output /absolute/path/new-posed.blend --validation-report /absolute/path/fresh-validation.json
```

**Capabilities**

- Inspect available humanoid chains; check hierarchy, constraints, rotation locks and reachability.
- Solve hand/foot endpoints via bounded cyclic-coordinate-descent IK with damped steps and best-iterate restore.
- Steer the elbow/knee bend using optional world-space `pole`.
- Measure final endpoint residual.
- Evaluate approximate anatomical centre-of-mass from bone landmarks and support-point hull/line.
- Verify endpoints against explicitly measured `ground_z`.
- Test ground-marker penetration.
- Flag limb capsule overlap candidates.
- Use evaluated skinned-mesh triangle BVHs to test intersections with other character mesh objects and other visible scene meshes.
- Explicitly labeled statuses: `PASS`, `WARN`, `FAIL`, `BLOCKED` or `NOT TESTED`.
- A failed IK or collision/balance check prevents saving an output pose. `WARN` produces a new pose for review, not an approved game animation.

**Coverage constraints**

- IK operates on directly parented, unconstrained three-bone chains with discovered roles or explicit role overrides.
- It does **not** override existing Rigify/Mixamo control constraints, detect all anatomy or enforce unknown joint angle limits.
- It does not automatically select targets, place pelvis, animate locomotion, solve physics or generate foot sole markers.
- The automatic balance test is a coarse, role-weighted approximation based on Z-up world XY support points (not an anatomy/physics-certified COM).
- Environment mesh checks require the actual environment geometry in the `.blend`.
- Ground at Z=0 is **not assumed**; put measured height in the plan.
- BVH triangle intersections can identify surface crossings but cannot detect self-intersection *inside the same combined mesh* or completely enclosed meshes.
- Apparel can legitimately overlap skin and needs an exclusion/interpretation policy. Any omitted mesh is reported (budget 60k faces/object by default), not silently called safe.

**Acceptance**

An output saved as `WARN` needs asset-specific visual/rig review before use. `PASS` means only that implemented numerical tests passed, not that the pose is aesthetically correct or biomechanically safe. No existing `.blend` or report is overwritten. Run on an isolated character copy first.

**Verification level**

Python syntax checked locally, but Blender execution and real character validation are **NOT TESTED** in the packaging environment. Do not claim the solver works on your character until its generated status report and preview are reviewed.

## Changelog (v2 improvements)

- CCD solver now writes local quaternions via a stable world→local conversion instead of mutating `pb.matrix` directly.
- Damped per-joint steps + best-iterate restore reduce oscillation and drift.
- Location keyframes are inserted only when a bone actually translates (most pure FK chains stay at rest location).
- Import path for the validation module is made robust to script directory.
- Slightly expanded bone-name aliases (common Mixamo / Rigify variants).
- Guide title and acceptance language aligned with v2 behaviour.

## v3 safety additions (2026-10-25)

- The supplied improved-v2 archive is preserved. This version adjusts bones by pose matrices to account for Blender edit-bone rest axes instead of using parent-only quaternion multiplication.
- `targets.<role>.orientation_world_quat`: optional `[w,x,y,z]` world orientation for the hand/foot bone. The final orientation is verified in radians.
- `settings.joint_limits`: optional role -> local `x/y/z` angular ranges in radians, **requiring asset-specific calibration**. Omitted limits trigger a warning, not a claim that the pose is anatomically correct.
- `settings.full_body_passes`: 1–30 CCD multi-limb solving sweeps (default 5). This is not physics-based inverse dynamics.
- `pelvis_world_position`: optional pelvis world-space location, currently supported only for a parentless, unlocked, unconstrained pelvis.
- Same-mesh triangle BVH candidates are detected, excluding pairs that share mesh vertices. Results are WARNING candidates, not proven penetration. Fully enclosed meshes and some tight contact cases remain outside coverage.
- Balance remains an approximate static 2D COM/support test. Genuine balance needs measured foot support polygons, a gravity model and an actual physics simulation.
- **Required before unattended use:** execute `REGRESSION_TEST_PLAN.md` on actual Blender runtime and target game assets. Static compilation alone is not runtime proof.
