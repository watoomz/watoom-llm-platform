---
name: vision-3d-inspector
description: Inspect images and generated 3D assets with deterministic geometry checks, six actual renders, controlled correction on copies, and verified GLB export.
---

Discover deployed generators with watoom_toolkit_generators. Use watoom_toolkit_generate3d for approved CPU providers; Meshy and GPU specialists require their separate configuration and authorization gates.

Use watoom_toolkit_inspect3d for a workspace-relative packed .blend or .glb. Review topology, normals, material/UV and skinning warnings. Inspect the actual published front/back/left/right/top/perspective PNGs with the native image-reading tool. Geometry checks do not establish visual recognition or animation quality.

Use watoom_toolkit_repair3d only for correction on a copy. Compare before-validation.json and validation.json. Originals are preserved. Required outputs include editable Blender, verified/reimported GLB, checksums, reproducible generation manifest and six CPU-rendered views.

Published assets are under /assets/generated/watoom-toolkit-3d/v1/<job-id>/ in OpenCode. Read manifest.json for provenance, actual clips, deformation checks and warnings. Avian's Blender native API subset is verified on 4.2.23; the full upstream add-on UI is not compatibility-certified. Quadruped wombat styling is a canine-derived approximation.

Do not report PASS from exit code alone. Require receipt.status PASS, verification PASS and valid artifact hashes. Query watoom_toolkit_jobs3d for uncertain outcomes; never blindly replay them. Do not bypass G3H/G3G or submit paid tasks without exact user authorization.
