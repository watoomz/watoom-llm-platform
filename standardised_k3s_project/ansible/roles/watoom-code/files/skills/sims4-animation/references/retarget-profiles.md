# Extending TS4 retarget profiles

Use profile id ts4-af-shadowheart-mhx-v2-quin for the qualified Quin Shadowheart rig.
Its mapping animates hip, spine, chest and neckhead only. Limbs receive no dedicated animation; they retain rest local pose and may follow parent movement. Do not describe this as a full-body retarget. Review actual output.

New profiles require no Python allowlist change. Create a new unique lowercase/hyphen id and a matching <id>.json under /config/skills/human-pose-agent/references/adapters in the native application. Use a qualified rig fingerprint, never invent bone/rest/driver data. Include id, armature, bone_count, bones, switches and drivers in the existing rig-adapter format, plus a retarget object with exactly mapping (TS4 source bone name to fingerprinted target control) and scope (honest limitations). Current engine requires b__ROOT_bind__ -> hip and b__Head__ -> neckhead; only the existing TS4 adult-female source skeleton and MHX rotation engine are supported. Different skeletons/engines still require operator implementation.

Select the id in a fresh ts4-retarget plan. Existing clip hash, source roots, frame budget, rig fingerprint, constraint/driver preservation and visual-review requirements remain enforced. Profiles contain JSON data only; no script paths. Unknown ids, mismatched armatures and target controls absent from the fingerprint are rejected.

Repository profiles take precedence over runtime profiles. For durable reuse, persist the qualified JSON to ansible/roles/watoom-code/files/skills/human-pose-agent/references/adapters in the authoritative IaC repository; the existing pose-worker playbook installs that reference directory. Runtime additions are available to new worker processes immediately. Do not overwrite a qualified profile to change its meaning; use a new versioned id.

## Constraint-limited motion and failures

The retarget worker projects out-of-range rotations into existing full-influence LOCAL Limit Rotation constraints. It preserves constraints and drivers. Affected controls/frames, requested local angles, applied angles and remaining error are recorded in retarget-diagnostics.json; the root-owned worker receipt marks constraint_limited and includes a warning. This is an approximation and remains PREPARED_REVIEW_PENDING, never visual acceptance or exact source motion.

Unsupported/driven/partial constraints are not projected. Unresolved rotation errors still fail with a control, frame and residual error. Validation/decode/reopen failures also leave retarget-diagnostics.json. Inspect that report and the receipt before any fresh request; never replay a terminal request or disable rig limits to force success.
