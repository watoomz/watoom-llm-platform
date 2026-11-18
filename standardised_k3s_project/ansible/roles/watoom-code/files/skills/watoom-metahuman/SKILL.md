---
name: watoom-metahuman
description: Convert owned MetaHuman (.mhpkg) packages for Unreal and Godot - inspect, install into an Unreal project, and export meshes, DNA and normal maps to a ready-to-import Godot folder using the Bazzite worker
---

# watoom-metahuman

Operator/root tool: `scripts/metahuman_pipeline.py` (needs the Bazzite worker and kubectl, like `watoom-fab-owned-assets/scripts/unreal-export`).
Packs are folders directly under `/data/ai/assets/fab/` holding one `.mhpkg` (a ZIP of Unreal assets plus `Manifest.json` files).

```
P=/data/ai/watoom-code/config/skills/watoom-metahuman/scripts/metahuman_pipeline.py
sudo python3 $P inspect <pack>                        # editable vs assembled, LODs, grooms, clothing, hash check
sudo python3 $P unpack <pack> [--force]               # <pack>/Content (verified Unreal Content tree) + metahuman-install.json
sudo python3 $P copy-to-project <pack> <UE project>   # copy into a project, enable MetaHumanCharacter/MetaHumanSDK/RigLogic
sudo python3 $P export-godot <pack> <Character> [--out DIR] [--texture-size 4096] [--skin-tone R,G,B] [--skin-dir DIR | --rig-skin]
sudo python3 $(dirname $P)/rig_lane.py submit-skin <pack> <Character>   # the GPU skin job on the rig (then: status / collect)
```

## To Unreal
A MetaHuman package is Unreal content, so "conversion" is installing it: `unpack` then `copy-to-project`, open the project in Unreal
5.6 or newer with the MetaHuman plugin, and open/assemble the character there (editable characters are `MetaHumanCharacter` assets).

## To Godot (`export-godot`)
Stage 1 runs on Bazzite (8 GiB job): `ue_metahuman.py` op `export_godot_inputs` under the full editor writes the head, body and full-body skeletal
meshes as GLB plus the head/body DNA. Two repairs run on the GLBs before Godot sees them: Unreal's empty unreferenced accessors are stripped (Godot would log import errors), and the head's **vertex normals are recomputed** (about 30 percent of the export's skin-triangle normals point against the mesh, which lit as dark and white blocks across the face while an unlit view looked fine). The scene uses the neck-cut `_Body.glb`, not `_FullBody.glb`: FullBody has its own head, which z-fights with the separate head mesh.
Skin textures come from one of two sources:
- **`--skin-dir DIR` / `--rig-skin` (recommended):** the rig's GPU `metahuman-skin` job (Epic's DCC export, 2048x2048 maps). Head and body base colour, normal
  (green-flipped for Godot) and SRMF (green channel read as roughness) become real materials, as do the eye, teeth and eyelash maps; the expression-driven maps (CM1-3, WM1-3)
  and masks are kept under `textures/reference/`. `--rig-skin` submits the job, waits up to 45 min and collects it.
- **Neither flag:** a flat `skin_tone` plus the package's stored 8K normal maps (green-flipped) - no GPU needed.

The scene builds a procedural looping idle on load (`IdleAnimation`: breathing, weight sway, head drift, relaxed arms; export vars `play_idle`, `idle_strength`, `arm_drop_degrees`). Motions are authored in character-space axes and converted per bone, so Unreal's bone axes do not matter; the head follows because it copies the body pose.

Output (default `/data/ai/artifacts/metahuman/<pack>/<Character>/godot/`, so pass a new `--out` when one exists): `meshes/*.glb`, `dna/*.dna`, `textures/`,
`<Name>.tscn`, `metahuman_setup.gd`, `manifest.json`. Copy it to `res://metahuman/<Name>/`. The head skeleton follows the body pose (shared bone names).

## Applying animations (`retarget_animation.gd`)
Written into every converted character folder. `godot --headless --path <project> -s res://metahuman/<Name>/retarget_animation.gd -- --source res://anims/x.fbx --character res://metahuman/<Name>/<Name>.tscn` converts every clip in an imported FBX/glTF onto the body skeleton (world-space rotation deltas, limbs re-aimed so an A-pose/T-pose mismatch does not offset them, hip travel scaled by height and dropped unless `--keep-root`) and saves `<Name>/animations/<file>.res`; the character script loads everything in that folder into its `IdleAnimation` player. `--inspect` lists a source's bones and clips. `--source-dir <res://folder>` retargets every FBX/glTF under a folder into one library (one `.res` per pack; clips keep their file names; files whose skeleton maps fewer than 8 bones, such as prop or arms-only rigs, are skipped and named in the log). Two solvers, chosen from the source's rest pose (`--solver delta|pose`): `delta` (rotation change from a neutral T/A rest) and `pose` (rebuilds bones from joint positions, for baked mocap whose rest is the first frame; roll about a limb is not recovered). Maps: `identity` (Unreal mannequin names), `mixamo` (Hips/Spine/Spine1/Spine2/LeftArm..., including the Spine1/Spine2/Chest and Leg/Shin variants and a Hips parent node); `auto` picks one. Verified on Motifect, Mocap.in and Sport/Gym clips. The owned animation packs are catalogued in `/data/ai/assets/catalog/animations.db` (`tools/fab/animation_catalog.py`; see docs/guide/animation-library.md).

## The rig skin job (`metahuman-skin`)
`rig_lane.py submit-skin <pack> <Character>` zips the character's verified Content and queues it for the rig's Unreal lane (see tools/rig-async-stage/unreal-lane).
Needs on the rig: Unreal 5.8.x with the **MetaHuman optional content installed** (texture synthesis data; without it the log says "skin editing will be disabled"),
a Job Object limit of about 20 GiB (12 GiB failed with "out of memory"/D3D12 E_OUTOFMEMORY), roughly 20 GB of free RAM and 20 GB of free disk on F:.
Verified: Base_Female on UE 5.8.4 / RTX 2080 SUPER, 532 s, 34 files.

## Known limits (do not hide these)
- Rendered and checked on Bazzite (software GL, Compatibility renderer): skin albedo, eyes, lashes and lips are correct after the normal repair. Roughness-from-SRMF-green and the normal green flip still follow Epic's conventions and are only eyeballed. `rig-godot-viewer` (tools/) opens any result on the rig's real GPU.
- Head surfaces are identified from their GEOMETRY (Unreal's glTF export loses the names): face skin, teeth, two eyes, eyelashes (an alpha cut-out) and the remaining thin shells (saliva, eye shell, eye edge, cartilage), which are made nearly transparent so they cannot cover the eyes. Godot only applies a role when the surface's vertex count still matches; an unrecognised mesh falls back to skinning the largest surface only. Eye/teeth normal maps are green-flipped like the skin ones; whether the eye atlas maps correctly onto the eyeball UVs has not been confirmed visually.
- Faces are animated by RigLogic from the `.dna`; Godot does not run RigLogic, so the face is a static neutral pose.
- Editable characters have no grooms/clothing; assembled packs (hair, clothing) are untested.
- Check the MetaHuman licence terms for the target engine before shipping.

## In-engine stages (`ue_metahuman.py`, selected by `export_pack.py --script ue_metahuman.py`)
Ops: `probe`, `docs`, `why`, `tex_info` (diagnostics), `export_dna`, `export_dcc`, `build`, `export_godot_inputs`. `request.json` carries
`{"op": ..., "asset": "/Game/EditableCharacters/<Name>/<MHC_Name>"}` via `--request-extra`. Use `--memory-gib 8 --reserve-gib 0` on Bazzite.
