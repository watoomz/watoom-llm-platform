## Vision-first visual asset policy

### Visual evidence gate (mandatory for visual assets)
- For images, 3D asset renders, UI, textures, animation frames and visual quality decisions: **inspect actual pixels first** using an available, verified vision-capable model/tool. Check its availability and image accessibility once; do not infer vision support merely from the selected text-model name.
- Use approved artifact paths or a supported image attachment/reference. Never pass disallowed absolute paths or fabricate URLs. If images are inaccessible, report `VISUAL_REVIEW=BLOCKED` with the specific access limitation. Do not claim to have seen an image.
- Inspect front, side, back and three-quarter views when available; review animation by actual frames/playback, not just clip names. For Australian magpies check black/white nape and wing markings, beak, wings, tail, legs, silhouette and deformation.
- Only **after visual inspection**, cross-check `3d.inspect`, GLB/BLEND geometry, material, rig/animation metadata and hashes. Metadata or file presence is not visual quality evidence. Flag contradictions.
- Reuse prior assessments of identical image hashes and unchanged framing; recheck changed images, materials, models or animation. Avoid redundant calls and unbounded retries.
- If vision is unavailable, label `VISUAL_REVIEW=NOT TESTED`, record why, and block any visual-quality acceptance or in-game character replacement. Continue independent nonvisual checks safely.
- Native `3d.inspect` is a **technical** inspector, not a substitute for image vision. Discover the verified tool contract rather than probing invalid payloads.

**Role:** During visual asset iteration, inspect new render pixels with verified vision first, identify concrete visual defects, adjust the asset, and re-render only changed views. Report observed-versus-unverified details and artifact hashes.
