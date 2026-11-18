# Sims 4 routing and follow-up questions
Read only the relevant row. These sibling skills are maintained in IaC. Load only a child listed as available in this session; otherwise report its deployment/assignment gap.

| What she wants | Execution skill | Ask only what is missing |
|---|---|---|
| See what is in a package, inspect or extract resources | [sims4-package-inspector](../../sims4-package-inspector/SKILL.md) | Which package? Inventory only or extract something specific? Raw or decoded can be selected by the coordinator after identifying resource support. |
| Make/change/repair furniture, objects or a general mesh | [sims4-asset-editor](../../sims4-asset-editor/SKILL.md) | Start from which asset or create something new? What should change/look like? Any reference or size requirement? |
| Clothing, hair, accessories or other CAS parts | [sims4-cas](../../sims4-cas/SKILL.md) | Which item? What change/new design? Which age/frame/part and required fit/morphs, only when relevant? |
| Change textures, colours, materials or UVs | [sims4-textures](../../sims4-textures/SKILL.md) | Which asset/image? Desired appearance or reference? Image output only or a game-ready texture replacement? |
| Make/edit a pose, work on a rig, animation or retarget motion | [sims4-animation](../../sims4-animation/SKILL.md) | Which rig/clip or new pose? Desired movement, pose or timing? Target Sims, Blender Action or Unreal? Resolve technical bone maps with the toolchain. |
| Still picture, preview, turntable or short video of an existing model | [sims4-render](../../sims4-render/SKILL.md) | Which model? Still image or video? Desired view/look and duration? Propose resolution/fps if she has no preference. |
| Change gameplay tuning or a script mod | [sims4-gameplay](../../sims4-gameplay/SKILL.md) | What should happen in game? Existing mod/source? Target game version/packs; script ABI is a technical discovery task. |
| Build/rebuild a .package from prepared resources | [sims4-package-builder](../../sims4-package-builder/SKILL.md) | Source/template or a new container? Which prepared changes belong in it? Intended game version/packs? |
| Check a mod or create a versioned candidate release | [sims4-release](../../sims4-release/SKILL.md) | Validate only or package a release? Which files/version and compatibility notes? Do not promise game-tested status without a real receipt. |
| Export a chosen asset/animation for Unreal | [sims4-unreal](../../sims4-unreal/SKILL.md) | Which asset/actions? Static or animated? Confirm Unreal 5.8.3 target and any scale/skeleton/material requirements. |

Combined examples:
- "Change this dress and put it back into a package": CAS, textures only if needed, package-builder, validation. Ask which dress and what changes first.
- "Make a picture of Shadowheart": render only. Resolve her supplied name through inventory; clarify still/video and view, not game patch or package keys.
- "Get the poses out of this package for Unreal": inspector, animation codec/retarget capability gate, optional Unreal. If TS4 clip decoding is unavailable, preserve extracted raw resources and report the blocker; raw clips are not Blender Actions.
- "I want a mod": clarify desired in-game behavior before selecting a module.

## Handoff record
Pass the user's goal, resolved source IDs/paths and hashes, requested output/changes, selected project, validated recipe evidence, runtime/worker contract, accepted defaults and remaining blockers. Keep the same coordinator job; canonical progress belongs to the coordinator. Follow the selected child's execution skill, not a prompt-writing contract. No capability, worker launch or deployment is implied by loading a skill.
