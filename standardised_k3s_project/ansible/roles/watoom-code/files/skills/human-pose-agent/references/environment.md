# Installed environment and builder contract

Source: authoritative `ansible/roles/watoom-code/files/skills/human-pose-agent`. Live: `/data/ai/watoom-code/config/skills/human-pose-agent`; app: `/config/skills/human-pose-agent`.

## Execution boundary (verified deployment)

The request runner is a local subprocess runner, not a worker dispatcher. `pipeline.py` / `request_pipeline.py` launch Blender in the caller's cgroup. Python wrappers, `start_new_session`, selecting a builder agent, `--resume`, `--retry-failed` and `--engine-job` do not allocate memory or move execution to the capture worker. The application cgroup is 2GiB; the native capture worker is separate and bounded to 4GiB.

In the application shell, prepare metadata and use `--dry-run` only. Any non-dry-run invocation may start unfinished Blender stages. Execute those only through an explicitly verified external worker integration; this document does not provide such a launcher for custom stages. Never guess dispatcher options, nest subprocesses to evade the guard, or strip source assets to fit the app limit.

Exit `-9` means SIGKILL. Attribute it to OOM only with matching kernel/cgroup memory-event evidence; bone count and a missing report do not prove OOM. Preserve the failed attempt and report the missing route instead of retrying unchanged.

## Native fixed pose worker

The same native `watoom_asset_capture` tool now supports `pose-inspect` and `pose-prepare`. This dispatches a fixed installed helper inside the existing isolated 4GiB worker; it does not dispatch arbitrary builder stages. The unified runner's `human` mode remains unrelated MPFB generation.

Inspection manifest (replace source/hash with real values):
```json
{"schema":1,"mode":"pose-inspect","source":"/data/ai/assets/example.blend","source_sha256":"<64 lowercase hex characters>"}
```
Preparation uses the same source identity, `mode:"pose-prepare"`, plus `preparation:{"method":"auto","plan":<actual auto-plan JSON object>}`. For calibrated local channels use `method:"recipe"` and the recipe schema. For the fingerprinted Shadowheart control rig, use `method:"rig-adapter"`; read [its exact contract and review limits](shadowheart-mhx-adapter.md). Inline JSON only: no script, command, plan path or output path fields. Use the detailed inspection's exact rig names and measured targets. Recipe approval flags must reflect real calibration and human review.

Submit using native `watoom_asset_capture` with `action:"request",job:"<fresh stable job>"`; use `action:"status"` for that same job. The existing dispatcher verifies native tool provenance and source/manifest hashes, serializes execution and checks memory headroom. Worker limits remain 4GiB, no swap/network/GPU, two CPU threads, 900 seconds. Output is a fresh `.opencode/captures/<job>/` directory; no output overwrite or automatic retry.

`pose-inspect` produces `inspection.json` and a rebased `working-source.blend`. `pose-prepare` additionally writes `pose-plan.json`, `posed.blend`, `pose-validation.json`. The rig-adapter route returns `adapter-inventory.json` rather than the generic helper inspection schema. The root-owned result contains output hashes, helper hashes, `prepared_source`, pose status, source preservation and actual cgroup memory limit. Read that receipt, not just QUEUED or COMPLETED. Completion is preparation only: WARN/SAVED_UNVALIDATED_POSE remain review candidates. Do not claim images were rendered by a preparation job.

Native solver budgets: at most 8 targets, 180 iterations, 8 passes, 60000 collision faces per mesh and 100000 candidate pairs; at most 128 recipe bones. Constrained/locked generic recipe controls and pelvis auto translation remain rejected; only the fingerprinted rig-adapter route uses qualified constrained MHX controls and the unlocked hip controller. For unsupported controls request a qualified adapter rather than bypassing constraints.

## Fixed adapter internals (not app-shell commands)

The following arguments describe the maintained worker payload only. Native callers supply the declarative manifest above, never launch these commands themselves.

Stage `script`: `/config/skills/human-pose-agent/scripts/prepare_pose.py`. Stage `blend`: task-relative working source. Arguments: `--revision <absolute revision> --mode inspect --report inspection.json`. Inspect output: `inspection.json`.

For automatic posing use `--mode auto --report pose-inspection.json --plan auto-plan.json --output posed.blend --validation pose-validation.json`. Declare all three output files. Supply actual armature, role overrides and measured world-space targets following `sample_auto_plan.json`; template values are not calibrated. The recipe mode uses the same arguments with `--mode recipe` and its calibrated recipe schema.

Read the @@JSON@@ marker and the report status as well as exit status. A failed plan may produce diagnostic reports without a `.blend`; preserve them and use a corrected new revision. Existing outputs are never overwritten.

For capture use the prepared source path/hash in a fresh supported manifest under `/data/ai/projects/images/.opencode/capture-jobs/<job>/request.json`. Submit through native `watoom_asset_capture`; this name is not a shell executable. Verify root-owned receipts, actual4GiB limit, source hash and real PNG/MP4. No capture job is created by installation.
