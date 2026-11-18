# Generic retarget (watoom.retarget.v3): any source motion onto any humanoid or quadruped rig

Engine: `scripts/retarget_generic.py` (contract `scripts/retarget_contract.py`, skeleton profiles `scripts/source-rig-*-v1.json`).
It replaces neither the legacy `ts4-retarget` Shadowheart adapter nor its manifests; use it for every other rig.

## Sources
- `{"kind":"ts4","clip":ABS,"sha256":HEX,"skeleton":S,"start":T0,"end":T1}`: a decoded binary CLIP `.resource`.
  `skeleton` is one of `adult` (AF and AM share the rest pose), `child`, `toddler`, `infant`, `werewolf`, `mermaid`, `fairy`.
  Pick the skeleton that matches the clip's age/occult (`unknown_tracks` in the evidence rises sharply on the wrong one).
- `{"kind":"blender","file":ABS,"sha256":HEX,"action":NAME,"armature"?:NAME,"start"?:F0,"end"?:F1}`: an existing Action on an
  armature in a `.blend`, `.fbx`, `.glb` or `.gltf` (Mixamo, Unreal exports, Animalz/Rigify rigs, other retargets).
  glTF actions are named `<clip>_0` after import; Rigify sources are read from their ORG skeleton.

## Targets
`{"armature": NAME}` in the open `.blend`. `body` is `auto` (default), `humanoid` or `quadruped`.
- Humanoid joints are found by name: Rigify metarig, Mixamo, Unreal mannequin, Toolkit, generic `.L/.R`/`Left/Right`.
- Generated Rigify rigs are driven through their FK controls (IK/FK switches set to FK, recorded in `switches`) and
  checked on the ORG skeleton. Pivot-spine rigs report the hips-side spine bones in `coupled_semantics`.
- Quadrupeds are found by structure (four legs from ground contacts, spine between the leg roots, neck to the first
  branch, tail behind the pelvis) and paired along each chain. Only Blender/Unreal sources can drive quadrupeds;
  a humanoid TS4 clip cannot. Pass `mapping` `{target bone: source bone}` to override pairs.

## Options (defaults)
`mapping:"auto"`, `fingers:true`, `rest_alignment:"match-source"` (or `preserve-target`), `root_motion:"in-place"`
(`none`, `in-place` vertical only, `scaled`), `foot_contacts:"none"` (or `plant`: two-bone IK holds a foot where it
touched down while the source foot is grounded and still), `tolerance_degrees:1.0`, `export_glb:true`, `action`.
A v2 plan (`watoom.ts4.retarget.v2`) is accepted and upgraded to an adult TS4 source.

## Running
- Capture worker: `pose-prepare` with `preparation.method:"retarget"` and the v3 plan.
- Direct (where shell is allowed): `blender -b TARGET.blend --python /config/skills/sims4-animation/scripts/retarget_generic.py -- --plan plan.json --out NEW_DIR`
- Test any target/source pair: `scripts/test_retarget_generic_blender.py -- --target metarig|T.blend|T.fbx|T.glb --out NEW_DIR (--clip C.resource --skeleton adult | --source-file S.glb --source-action NAME) [--feet plant]`
- New TS4 skeleton profile from a Creator Tools rig: `scripts/snapshot_source_rig.py -- --rig X_Rig.blend --id ts4-x-v1 --out source-rig-x-v1.json`

## Evidence and review
`retarget-evidence.json`: mapping (with `control` when a control is keyed), per-joint rotation/direction error against the
request, `max_source_direction_mismatch_degrees` against the source bone, rest alignment, scale, facing yaw, planted
frames, coupled semantics, saved/reopened error and a GLB export check. `PREPARED_REVIEW_PENDING` is technical only: render
it with `/config/skills/blender-rendering/scripts/render_clip.py` (isolates the rig by default) and review the clip.
Known limits: no face, fingers on quadrupeds, props, contacts with seats/partners, clothing correction or TS4 clip events.
Large rest-alignment angles (different bone-axis conventions) can crease skin around shoulders; review those joints.
