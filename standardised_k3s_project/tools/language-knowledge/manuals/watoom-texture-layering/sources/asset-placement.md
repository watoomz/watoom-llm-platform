# Classify an asset before you place it

A foliage family that is scattered without knowing what it is ends up in the wrong place: marsh plants on a dry hillside, bushes in the sea, village props in the forest, a plant that renders black. On the test game (2026-11-16) all of these happened, and the owner had to find them by eye. This page is the step to do first. The data lives in an asset catalog (`templates/asset_catalog.example.json`) and the live level is audited against it with `tools/rig-ue-mcp/ue_foliage_census.py`.

## 1. A family, not a type
`FT_SM_Tree_01 .. FT_SM_Tree_08` are variants of one family (`SM_Tree`); `FT_SM_GrassPatch_Var01..03` are one family. Classify and audit by family. `ue_foliage_census.py` groups them for you.

## 2. Give every family a category and a habitat BEFORE the first scatter
Write the catalog entry first: `category` (tree_upland, tree_riparian, shrub, groundcover, grass, flower, wet_margin, aquatic, dune_coast, dry_scrub, rock, prop), `above_sea_m` [low, high], `max_slope` (rise/run), `near_water_m` [min, max] (distance to a creek, lake or the sea edge; `[0, 0]` is in the water), `allow_in_sea`, and a note. **Distance to water is the axis for every water-bound family, not height above the sea**: creeks and lakes lie at any height (on the test game the land is 5 to 50 m above the sea), so a wet-margin plant gets a `near_water_m` maximum and no upper `above_sea_m` limit (`null`); `above_sea_m` is for the sea itself (dune and coast plants, nothing below the surface). Rules that held:
- **Wet-margin and aquatic plants belong at the water.** Sedges (Cyperus), marsh broad-leaf rosettes (Wildwood `SM_Plant`), reeds, lilies, papyrus, cattail: creek banks, lake edges and the shallows, within about two landscape pixels (16 m on the test game) of the water and low above THAT water's surface (0 to 3 m), whatever its height above the sea. They never go on dry upland. Measured on the test game (census 2026-11-16, 238k instances): `SM_Plant` median 21 m above the sea and mostly far from any water, Cyperus median 36 m above the sea and about 30 m from water, so most of both were misplaced. Floating or submerged plants stand in the water body itself, and only where it is deep enough.
- **Dune and coast plants** (Ammophila, sea grass) stand on the sand layer a few metres above the sea, wind-exposed, never inland.
- **Dry-scrub plants** (Agave, Cistus) stand on well-drained ground away from water.
- **Riparian trees** (alder, banana) stand close to water but on dry ground; **upland trees** keep back from the water line (about 8 m) and thin out on slopes.
- **The water gap.** Every family has a gap to the water: `near_water_m[0]` is the closest it may stand (0 for wet-margin and aquatic, about 1 to 3 m for riparian trees, grass and shrubs, about 8 m for upland trees, 20 m for dry scrub) and `near_water_m[1]` the farthest (`null` = no limit). The census measures the distance on the heights grid, so it cannot resolve less than one landscape pixel (about 8 m on the test game).
- **Rocks** can stand almost anywhere but are never floating.
- **Props** (houses, fences, barrels, carts) are placed once, inside a village footprint; they are never scattered by a recipe.
- **Nothing stands in the sea** unless its category says so. `ue_foliage_buried.py --in-sea` removes anything whose ground is below the sea surface, inland bowls and lake beds below sea level included; add `--edge-connected-sea` to touch only the real sea.
How to classify an unknown asset: the plant's Latin name or pack description (Cyperus, Typha, Nymphaea, Phragmites = water; Ammophila = dune; Agave, Cistus = dry; Alnus, Salix = riparian), the pack's own demo map, then look at it. When it is not clear, use the narrower habitat and say so in `notes`.

## 3. Look at one before you place thousands
Place ONE instance at eye level, photograph it with `tools/rig-ue-mcp/ue_viewport_shot.py` in sun and in shade, from the side and from above, and check: not black (two-sided material, normals, ground projection), not white or glowing, sensible scale next to a tree and the player, and wind that looks right. A plant whose wind makes it sway like water belongs at water. Set `verified` in the catalog to the date.

## 4. Scatter only with masks, then audit
- Drive habitat from data, not from a random fill: the heights (above sea, slope), the layer weights (sand, mud, grass), and the creek and sea masks. `unreal_scene_scatter.py` refuses a `.u8` mask whose size is not the heights size (it used to skip it silently, which left no creek or sea mask and put scenery in the water): regenerate the mask at the heights size.
- After every scatter run `ue_foliage_census.py --project profile.json --heights live_heights.png --water-mask creek_mask.u8 --catalog catalog.json`. It prints the families that are NOT in the catalog (classify them before they are used again) and every family that contradicts its entry (in the sea, above or below its height band, closer to or farther from water than its `near_water_m` band, steeper than its slope limit). Without `--water-mask` only the sea counts as water, so creek and lake plants all look far from water: pass the creek and lake mask (non-zero = water, heights size). Then run `ue_foliage_buried.py --in-sea`.
- Refresh the heights first (`ue_heights_fetch.py`) after any terrain edit, and `level.save` after the audit is clean.

## 5. Shadows from a plant you cannot see
A black shape on the ground that sways is the shadow of a plant: the plant's mesh may not draw (culled, or its material renders nothing from that side) while it still casts. Find the foliage instance near it (`foliage.get_instances` with transforms, nearest to the spot) before deleting anything, and remove only that instance with `foliage.remove_instances`.

## Record
Put every classification, every instance you removed and why, and the date in the ticket and in the catalog `notes`, so the next model starts from the decision and not from the symptom.
