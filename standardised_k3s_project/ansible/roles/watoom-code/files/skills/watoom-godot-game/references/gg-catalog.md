# gg-catalog: classify before you place (3D)

Plants, rocks and props are never dropped into a level because they look right in a file browser. Each one is a catalog family with a category and a habitat, it is inspected at eye level, and only then can the scatter use it. The catalog is `<project>/gg_catalog.json`.

## Commands

```bash
python3 scripts/gg_catalog.py init     --project /abs/path/game     # builds 8 default families from primitives in the style's own colours
python3 scripts/gg_catalog.py inspect  --project /abs/path/game --family pine    # exit 0 prints VERIFIED and stamps the date and file hash
python3 scripts/gg_catalog.py list     --project /abs/path/game
python3 scripts/gg_catalog.py validate --project /abs/path/game
python3 scripts/gg_catalog.py add      --project /abs/path/game --family fern --scene res://assets/fern.glb --category groundcover --above-sea 1 9999 --near-water 2 9999 --max-slope 0.5 --min-spacing 0.8
```
Exit 2 = refused (message says what to run first); exit 1 = a check failed, the reason is printed.

## Habitat values

`above_sea_m` is metres above `world.sea_level_m` as [low, high]. `near_water_m` is the distance to the nearest water cell, [low, high]. `null` or a large high value means no limit. `max_slope` is rise over run (0.5 = 27 degrees). Wet plants (reeds, marsh, aquatic) are placed by distance to water, never by height, because a creek lies at any height. Every other family (not rock, wet margin or aquatic) is also kept out of the creek itself and the sea. Family names are lower case letters, digits and underscores (max 32). `validate` enforces the category rules: wet families need a high limit on near_water_m of at most 40 m and no upper above_sea_m (aquatic: at most 4 m, it stands in the water); coast plants stay within 15 m of the sea; upland trees keep 4 m or more from the water; dry scrub keeps 10 m or more; only rock and aquatic may stand in the sea; rock and props have no wind.

## Onboarding procedure for an unknown pack

1. Look inside: `add` the family with your best category, then `inspect`. It reports triangles, materials, lights, skeletons and the real size.
2. Read every ERROR. It flags: no mesh, wrong scale (a centimetre export), lying down (Z-up), base not at y = 0 (would float or sink), missing material (renders white), black albedo with no texture, glowing emission, alpha 0 (invisible), and, from the renders, an asset that is mostly black or mostly white or not visible at all.
3. Fix the asset or the import, never the check. Run `inspect` again until it prints VERIFIED.
4. `inspect` renders the asset at eye level from the sunlit side and the shaded side on a neutral grey ground, with and without it; look at both PNGs it prints before trusting the result.
5. `verified` is bound to the category, the scene file, its `.import` file and every file the scene uses (textures, materials). Changing any of them, or editing the category, makes the family unverified again: scatter refuses until you `inspect` again. A failed `inspect` also clears the stamp.

## Scatter and audit

```bash
python3 scripts/gg_scatter.py plan --project /abs/path/game                 # counts per family from the category density; edit gg_scatter.json
python3 scripts/gg_scatter.py run  --project /abs/path/game --dry-run       # per family: placed, habitat share of the map, which rule removed most
python3 scripts/gg_scatter.py run  --project /abs/path/game                 # builds res://levels/<level>/scatter.tscn, then audits it
python3 scripts/gg_census.py audit --project /abs/path/game                 # audit alone, from the saved scene; also judges any MultiMesh you pass with `--scene`
```
`plan` will not overwrite an existing gg_scatter.json unless you pass `--force`. `run` refuses a family that is unverified, changed, a prop, or missing from the catalog, an exclude mask of a different size than the heights (both sizes are named), a terrain not built from the current heights, and a water analysis that did not pass (`gg_water.py analyse` exit 0 is required; `water build` is not). `run` exits 1 when any planned family places under 10% of its count: loosen the habitat, lower the count or remove it. Placement uses the rules at the exact position (the terrain mesh surface, not the nearest cell), keeps the minimum spacing, and is repeatable with the plan's `seed`. Optional per entry: `"on_layers": ["grass"]` and `"min_weight": 0.4` keep a family on a terrain layer.

## The audit: what it reads and what fails it

The audit loads the saved scene through the engine under a real renderer (a headless run keeps no MultiMesh transforms) and measures every instance: metres above the sea, slope, distance to water, and height off the terrain surface. It exits 1 when any family has more than 2% of instances breaking one rule, more than 1% standing more than 0.3 m off the ground, or any family in the level is not in the catalog. Tolerances: 5 cm on distances and bands, 0.01 on slope; one instance in the sea or in a creek (dry families) fails; the shares of all rules also add up to the 2%. Zero instances is a failure, and a MultiMesh without the `gg_family` tag or an UNVERIFIED family is a problem. The audit sees MultiMesh nodes only: hand-placed single instances are not counted. A passing `run` writes a stamp that records the scatter scene, catalog, water distance map and layer report; lighting includes the scatter only while all of them still match, and any audit that fails removes the stamp. A clean audit is a statement about this catalog; if the catalog is wrong the audit is only as right.

## Verified and not verified

Verified by running: eight default families inspect VERIFIED; eight deliberately broken assets (black, glowing, tiny, lying, no material, floating, invisible, white) each fail with the right message; scatter on an island with a creek audits clean; a tightened catalog makes the audit fail on the right rules and an unlisted family fails as unclassified. Not verified: glb packs and externally textured assets, the look of the merged MultiMesh in styles other than low-poly, wind (the data is kept but not rendered), cell sizes other than 4 m, 2D. The off-ground check compares with the heights file, not with the built terrain scene.
