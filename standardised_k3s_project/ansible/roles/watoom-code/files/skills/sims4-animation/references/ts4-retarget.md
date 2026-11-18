# TS4 adult-female reference to Shadowheart MHX v1

Exact native manifest (replace paths/hashes with verified user-selected inputs):

```json
{
  "schema": 1,
  "mode": "pose-prepare",
  "source": "/data/ai/projects/PROJECT/verified-clothed-source.blend",
  "source_sha256": "SOURCE_SHA256",
  "preparation": {
    "method": "ts4-retarget",
    "plan": {
      "schema": "watoom.ts4.retarget.v1",
      "profile": "ts4-af-shadowheart-mhx-v1",
      "armature": "Shadowheart",
      "clip": "/data/ai/projects/images/SELECTED.resource",
      "clip_sha256": "CLIP_SHA256",
      "start_tick": 0,
      "end_tick": 30,
      "root_motion": "in-place"
    }
  }
}
```

Both source files must be regular, canonical files under the configured capture source roots or images project. The input is decoded binary CLIP `.resource`/`.clip`, not the entire package, `.stored` compressed data, or JSON. Binary package extraction uses the installed Python CLI first. Select a named user-requested clip; do not choose arbitrary animations by file order. Supported ticks are 24/25/30/60Hz, 2..120 frames per preparation, with codec budgets unchanged. Root mode can be `scaled` for proportional displacement from the first selected tick; no absolute scene/partner alignment is implied.

Output `posed.blend` contains `TS4_Imported_Source_Action` and `TS4_Retarget_Shadowheart`. `retarget-evidence.json` reports source hash, profile/adapter hashes, unmapped tracks, mapped controls, control angle errors, per-frame matrices and saved/reopened errors. `PREPARED_REVIEW_PENDING` is technical preparation only. Capture the prepared source using ordinary still/animation manifests with `armature="Shadowheart"`, `action="TS4_Retarget_Shadowheart"`, and the returned frame range/FPS. Preserve camp shirt, pants, shoes and the pants body MASK modifier. Rendering is a separate request with its own visual review.

Mapping covers hips, spine/chest/head and bilateral arm/forearm/hand/thigh/shin/foot/toe FK rotations. Source hierarchy carries ancestor rotation into mapped global deltas. It does not import facial/finger motion to target controls, translate limb controls, fix contacts, handle partner choreography or correct garments. TS4 clip events stay opaque; they are not executed. Native requests cannot provide script paths or change the fixed bone map.
