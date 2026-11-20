---
name: watoom-terrain-export
description: Stage an Unreal terrain/landscape-to-GLB export job (the .opencode/tmp/<dir> + .opencode/terrain-jobs/<job>/request.json pairing the terrain-export worker needs) and iterate on one without hand-authoring the .uproject file or re-deriving paths each time. Use before submitting a terrain-export worker request.
---

# watoom-terrain-export

The terrain-export worker (`terrain-export` operation) runs an already-staged `.uproject` + your own
in-engine Python script, unattended, on the Bazzite worker. It never stages the project for you and refuses
if the pairing of files is missing, in the wrong place, or malformed — this skill's one script does that
staging so you don't have to hand-construct it.

```bash
python3 scripts/terrain_stage.py init --project /data/ai/projects/games/<name> --job <job>
```

Writes `.opencode/tmp/<job>/Terrain.uproject` (PythonScriptPlugin + GLTFExporter, the same plugin
convention the Fab export pipeline uses) and a starter `.opencode/tmp/<job>/export.py`, plus the
`.opencode/terrain-jobs/<job>/request.json` that ties them together. **Edit `export.py` before submitting
the job** — the starter only has the output contract (write `/job/output/manifest.json` with `status`
`SUCCESS`/`PARTIAL`/`FAIL` and `output.produced`); you still write the actual landscape lookup/export for
your map. See `references/terrain-output-contract.md`.

To iterate (tweak the script, keep the same `.uproject`) without re-staging by hand — the worker refuses to
reuse a job name, so always submit under a fresh one:

```bash
python3 scripts/terrain_stage.py adopt --project /data/ai/projects/games/<name> --from-job <old> --new-job <new>
```

Copies `<old>`'s `.uproject` and script into a fresh `.opencode/tmp/<new>/` (not its prior `output/`) and
writes `<new>`'s request.json, inheriting `deadline_sec`/`memory_gib` unless you pass `--deadline-sec`/`--memory-gib`.

Both commands only touch files under the project directory you pass — they never run Unreal or reach the
Bazzite worker; submitting the job itself still goes through the normal native `terrain-export` worker request.
