# Generic scene capture

Use the native watoom_game_worker tool with action=request, operation=capture-scene
and a stable job name. First write .opencode/capture-jobs/<job>/request.json:

```json
{"schema":1,"scene":"scenes/capture.tscn","inputs":["scenes/capture.tscn","scripts/capture.gd"],"output_directory":".opencode/captures/review","images":["overview.png","detail.png"]}
```

Scene and inputs are project-relative regular files. Include the scene and its
capture helpers; no shell, arbitrary engine arguments or external paths. The
manifest and declared file contents are bound into the request revision. The
worker enforces its own 4GiB/600-second boundary, PNG validation, freshness, and
root-owned receipt. Legacy capture still means the three P6 asset-review views.
Never replace P6 to request another scene. The model owns valid scenes, cameras
and framing; pipeline completion does not imply visual acceptance.

Qualification used an unrelated minimal project and a real external rendered PNG;
native/Python revision parity and malformed/traversal cases are regression-tested.

## Diagnose capture failures without bypassing provenance

Read the actual worker receipt, producer diagnostics and worker implementation before asking the owner to waive a failure. The maintained capture worker currently computes freshness from output modification time relative to the run start; it does not require different PNG hashes between runs. Deterministic rerenders may be byte-identical. A valid PNG on disk can be a leftover: producer exit status, saved/expected counts, per-view execution and timestamp/source bindings still have to pass.

For missing first/last views, inspect counter initialization and advance order. A counter incremented before selecting the first view must initialize to -1 for zero-based indexing, or the initial selection must not preincrement. Verify the produced sequence is exactly 0 through N-1 and the saved count equals N; do not infer that six existing files were all rendered by the latest run.

Do not change job identities, introduce random camera jitter, delete retained output or mark a failed receipt PASS merely to clear freshness. Fix the producer/actual contract defect and submit one source-revised request using the existing stable job through the native worker, reconciling any uncertain/running work first. A terminal cached FAIL is not a newly executed retry. Keep technical capture success separate from actual pixel/visual acceptance.
