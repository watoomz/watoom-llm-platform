# LMB fingerprints and native provenance

The coordinator fingerprint is `metadata-manifest-sha256-json-utf8-size-mtimeNs-cache-mount-v1`.
It covers the selected Godot project, including for `lmb-qualify`. It does not cover the external Unreal project.
It hashes UTF-8 bytes of JavaScript `JSON.stringify(rows)` with SHA-256, producing lowercase hex.
Each regular file contributes `[relative_posix_path, decimal_size_string, decimal_mtime_ns_string]`.
Traversal uses `readdir` recursively, then sorts the final rows by `Buffer.compare(Buffer.from(path))`.
Directories named `.godot`, `.opencode`, `.git`, and `magpie-final` are excluded at every depth;
regular files ending in `.import` are excluded. Symlinks are rejected, including links bearing excluded names.
The four explicit P6/P7 `.gd`/`.tscn` capture sources under `.opencode/validation` are included once when present.
Their parent directories must resolve canonically. Missing capture files are allowed. Traversal has a 20,000-row limit;
the historical limit precedes explicit capture rows and the sentinel, which remain unchanged.
The sentinel `[".watoom-worker-contract","cache-mount-v1","0"]` is always included. If a real file has that name,
both rows are retained in stable order, preserving the established algorithm. No filenames are Unicode-normalized.
Python parity requires `ensure_ascii=False`, compact separators, UTF-8 path byte ordering and integer `st_mtime_ns`;
default `json.dumps` spacing/escaping does not reproduce this digest. The audit executes the actual JS function.
A metadata digest cannot establish raw-content integrity: contents can change while size and mtime are preserved.

`gameSourceManifest` exposes the exact sorted rows; `gameSourceFingerprint` hashes them without changing normal-source identities.
The source patch also rejects indirect capture parents and rejects an explicitly mismatched job in new public status files.
Legacy status files without job remain readable. Existing identity checks still bind request/project/operation/fingerprint.
Requests are selected by project, operation, job and (on submission) fingerprint. Status selection uses the original job
without requiring its historical fingerprint to equal current source. The newest request for that job is selected;
older request/status files are retained and can be read directly. Request IDs retain the historical context hash
`[project,operation,source_fingerprint,session_id,message_id,call_id]`. Native call IDs must be unique; retries with a
stable job reuse the existing request even with a new call ID. Different jobs use distinct native tool calls.

Run the new read-only verifier with explicit trusted inputs:

```sh
python3 tools/watoom-code/lmb_provenance.py \
  --project /data/ai/projects/games/magpie-flight-godot-candidate \
  --guard /data/ai/watoom-code/config/watoom-tools/coordinator-guard-<verified-hash>/index.js \
  --native-source /data/ai/assets/fab/landscape-mesh-builder-48364dff \
  --request /data/ai/projects/games/magpie-flight-godot-candidate/.opencode/worker-requests/<request-id>.json \
  --receipt /data/ai/helper-scripts/reports/game-worker/<request-id>/result.json \
  --output /data/ai/helper-scripts/reports/<new-private-report>/verification.json
```

It exclusively creates a mode-0600 report. It does not submit work, run an engine or alter existing evidence.
Historical receipt fields that are missing produce warnings; any present identity mismatch fails. Empty/tampered
native manifests or missing/changed/added current native inputs fail. The supplied module is trusted executable JS;
verify its source hash before using it. Compare root-owned status and native-call evidence separately for old receipts.
Legacy result files may be group-writable; their root ownership alone is insufficient to establish immutable provenance.

The reviewed `lmb_provenance.patch` updates the directly executed native helpers only during approved fenced activation.
It is intentionally pending: writing those helper files in place would activate them on the next systemd dispatch.
The patch preserves the existing launch routes, memory limit and native compile-only acceptance scope.
The qualifier requires the real Blueprint, records all declared purchased-pack files and compares raw hashes before/after.
If purchased source changes, it writes an explicit failed receipt. The wrapper carries the native manifest forward.
The bridge binds the result to its admitted request and publishes a root-owned, mode-0644 enriched receipt.
The receipt records execution start time and its own location. There is no automatic engine rerun.

New receipt fields and meanings:

| Field | Meaning |
|---|---|
| `request_id`, `job`, `operation`, `project` | Admitted coordinator request identity; `job` is the coordinator job, not the Kubernetes job name |
| `source_fingerprint` | Coordinator Godot project metadata digest |
| `source_fingerprint_algorithm` | Explicit algorithm above; not a raw-content claim |
| `native_input_files` | Sorted declared purchased-pack inventory: canonical/relative paths, type, size, exact mtime_ns, UTC time and per-file raw SHA-256 |
| `native_input_sha256` | SHA-256 of compact UTF-8 JSON of sorted `[relative_path, raw_sha256]` pairs; metadata is excluded |
| `native_input_algorithm` | `raw-sha256-path-manifest-v1` |
| `native_provenance_scope` | Purchased-pack scope; no claim to trace every file opened or hash all engine/plugin dependencies |
| `source_unchanged` | External purchased pack raw hashes match before/after native qualification; not the Godot metadata check |
| `live_source_still_matches_snapshot` | Existing wrapper compatibility field; bridge independently recomputes Godot metadata before delivery |
| `cgroup_memory_max`, `cgroup_limit_verified` | Value read inside native container and whether it equals 4,294,967,296 bytes |
| `native_status` | Actual native compile result; generated terrain/export/visual acceptance remains outside scope |
| `executed_at` | Dispatcher UTC timestamp immediately before invoking the bounded helper |
| `receipt_path` | Exact enriched wrapper `result.json` path |

External provenance inventories cover the declared source pack, not a complete process file-open trace.
The worker derives a descriptor with PythonScriptPlugin enabled, copies Config, mounts purchased Content read-only,
scans `/Game/LandscapeMeshBuilder` and explicitly loads/compiles `/Game/LandscapeMeshBuilder/Blueprints/BP_LandscapeMeshBuilder`.
Its engine and plugin dependencies are outside the coordinator digest and native pack digest.
The audit separately records the actual generated descriptor, probe, job, copied Config, engine executable/version,
host scripts and inherited job template. Neither this audit nor static tests constitute fresh native acceptance.

Deployment requires the existing native admission fence, idle sessions/leases, durable pending-work clearance,
worker lock, protected snapshots, immutable image/hash validation and scoped automatic rollback.
Use the timestamped audit's reviewed deployment script; its `--i-approve` and administrative-access gate are mandatory.
It never changes inference, GPU, network, or unrelated deployments. It never stages pre-existing dirty changes.
A failed rollback retains the owner fence for recovery rather than reopening admission into an uncertain state.
Runtime tool invocation and fresh native receipts remain explicitly untested until separately authorized.
