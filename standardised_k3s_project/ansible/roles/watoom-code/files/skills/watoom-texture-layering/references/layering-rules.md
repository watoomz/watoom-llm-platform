# Layering rules (what a professional material stack does)

These are the rules the scripts encode. Cards in the `watoom-texture-layering` language-knowledge product quote
them; an agent that is unsure how to layer something should read those cards, not improvise.

## 1. Order is a contract (bottom to top)

1. **Base** (covers everything; the fallback). It must look acceptable on its own: if every mask failed you would
   still ship it.
2. **Large-scale material changes** (rock vs soil vs sand): driven by slope and height. These decide the read at a
   distance.
3. **Ecological / weathering layers** (moss, dirt, mud, snow, dust): driven by occlusion, curvature, concavity,
   height and noise. These tell the story of water, gravity and exposure.
4. **Wear and damage** (edge wear, scratches, chips): driven by edges (convex curvature) and vertex paint. Last
   because wear shows the layer *under* everything above it.
5. **Decals and hand-placed detail** (stains, markings): projected or UV-placed, never baked into a tiling base.
6. **Global macro variation + detail normal** over the finished result.

## 2. Masks: what drives what

| Effect | Mask source | Why |
|---|---|---|
| Rock on cliffs | slope (surface angle from up), 30-50 degree ramp | soil cannot rest on steep faces |
| Snow / frost | height, plus flat-facing (slope under ~40) | cold at altitude, settles on flat surfaces |
| Moss / dirt in crevices | ambient occlusion, concave curvature | water and debris collect in hollows |
| Sand / wet mud | low height band, concave + flat | waterlines and drainage |
| Edge wear | convex curvature / bevel difference | edges abrade first |
| Streaks | vertical noise stretched along gravity, masked by AO | run-off |

**Gentle real terrain:** thresholds written for mountains find almost nothing on rolling ground (measured on the Brisbane-area 4 km DEM: 95% of the ground under 13 degrees). Measure the slope percentiles first and place the dirt/rock ramps there (e.g. dirt 7-14, rock from 13), and set top-level `"smooth_m": 20` in the spec: open DEM data is quantised, and without smoothing the slope flickers per pixel and the layers speckle.

Never use a hard threshold: every mask is a smooth ramp with a **feather** (degrees or metres). Add **seeded noise**
to every natural boundary so it is not a straight line or a contour.

## 3. Blending maths

- **Weights sum to 1** per pixel. `layer_masks.py` guarantees 255 across the splat channels.
- **Height-blend** (not plain cross-fade): bias each layer's weight by its own height texture, so the layer with
  the taller surface wins at a boundary (pebbles through soil, grass through sand). Control crispness with a blend
  depth (0.05 crisp, 0.3 soft).
- **Sharpness** (`layer_masks.py`): weights raised to a power before normalising. 1 = muddy mix everywhere, 4 =
  default, 8 = crisp painted look. Too soft reads as blur; too hard reads as a sticker.
- **Normals blend by vector mix then renormalise**, never by averaging colours of normal maps.
- **Roughness and metallic blend per layer**, not just albedo: snow over rock must change gloss as well as colour.

## 4. Texture-space rules

- **Colour space**: albedo = sRGB; normal, roughness, AO, height, masks = Non-Color. A wrong colour space is the
  most common "looks washed out" bug.
- **Normals**: OpenGL (Y+) for Blender/Godot, DirectX (Y-) for Unreal; flip green when moving between them.
- **Albedo is not lit**: no baked shadows or highlights; keep within measured albedo ranges (see
  blender-pbr-materials/references/pbr-values.md). Snow is about 0.8-0.9, fresh soil 0.1-0.2, never pure 0 or 1.
- **AO only deepens crevices**: do not multiply full AO into albedo (the engine also applies AO); a 0-35 percent
  darkening is plenty.
- **Texel density**: pick one pixels-per-metre for the project and hold it; mix of densities on neighbouring
  objects is the first thing a reviewer notices. Typical 512-1024 px per metre for hero props, 128-256 for terrain
  tiles viewed from distance.
- **Tiling**: every tiling texture needs anti-tiling (a second rotated, differently scaled sample mixed in by a
  low-frequency noise) plus **macro variation** (large-scale tint and roughness wobble). Detail normals fade out
  with distance.
- **Steep terrain**: planar XZ mapping stretches on cliffs; use triplanar mapping there (cliff layers only).
  Tangent-space normal maps need UVs; under box/triplanar projection use a height/bump map instead, or the lighting
  is wrong.

## 4b. Terrain specifics

- 4-8 layers is plenty; more costs memory and shader time without a visible gain. Keep to the 8-layer, two-splat
  budget of `terrain_layered.gdshader` unless there is a reason.
- Use the same layer list for the mask spec, the splat channels and the texture-array slice order; one table, no
  drift. `layer_report.json` records it.
- Do not let two natural features share one mask (rock-and-snow): separate layers keep each tunable.
- Terrain3D: assign the same layers as texture assets, in the same order, and treat `control_hint.png` (base id,
  overlay id, blend 0-255) as the per-pixel intent. The packed Terrain3D control map is NOT written by this skill.

## 5. Shipping to an engine

The Blender material is procedural: it renders in Blender, but glTF/FBX do not carry the node graph. For an
engine, bake base colour, ORM (AO/rough/metal) and normal with `blender-texture-baking`, then apply the engine
material. For terrain, ship splat maps plus the layer texture arrays and use `terrain_layered.gdshader` (Godot)
or an equivalent landscape layer blend (Unreal).

## 6. Acceptance (visual PASS needs an image)

A layering change is not done until a rendered or captured image shows: (1) every layer visible somewhere it
should be, (2) no visible tiling at the intended view distance, (3) no straight mask boundaries, (4) cliff faces
not stretched, (5) nothing white-clipped or black-crushed. Describe what the image shows; do not infer from code.
