# Worker observability report (2026-11-08)

**Target report path blocked:** `/data/ai/artifacts/codex-briefs/worker-observability-20261108.report.md` is outside the writable workspace roots (`test -w` returned false). This progress copy is at `/tmp/worker-observability-20261108.report.md`; it must be copied to the requested path by an authorized operator.

## Item 1 — stale/abandoned jobs

Implemented display-only `STALE_RUNNING` classification in `tools/watoom-code/worker_status.py`. A running receipt is considered stale after `prepared.json`'s deadline (default 1800 seconds) plus 180 seconds when its prepared evidence is missing or its declared unit is absent from the live Bazzite unit list. The rule is a pure function and does not mutate receipts or statuses. Added fixtures/tests in `tools/watoom-code/test_worker_status.py` for active unit, missing unit, missing evidence and younger-than-threshold jobs.

Bridge reconciliation was not implemented: persisting a changed receipt is outside the display-only rule and requires careful read-safe ownership semantics. Proposed follow-up: a root-owned bridge maintenance pass may publish `RECONCILIATION_REQUIRED` with `failure_stage=run` and `failure_code=worker_error` for stale receipts, while preserving prior evidence and never replaying a job.

Tests: `PYTHONPATH=tools/watoom-code python3 -m unittest test_worker_status` — PASS, 23 tests, 0 failures (after correcting the fixture age to exceed the default deadline).

## Item 2 — structured failures

Added `failure_stage`/`failure_code` to bridge worker results and reconciliation failures in `tools/watoom-code/game_worker_bridge.py`, including timeout, OOM, SSH exit 255, source change, pull and script-error signals. Command argv exception strings become a short human reason. Bazzite wrappers now annotate Godot/Blender/asset-capture outcomes and NOT_STARTED stage failures; standalone Blender/Godot helpers and the Unreal lane include structured failure fields. `worker_status.py` exposes both fields on receipt and lane job records. Existing receipt fields and status values remain intact.

Files: `tools/watoom-code/game_worker_bridge.py`, `game_bazzite.py`, `blender_bazzite.py`, `asset_capture_bazzite.py`, `game_blender.py`, `game_validation.py`, `game_import.py`, `tests/test_game_worker_bridge.py`, `tools/rig-async-stage/unreal-lane/worker-source/unreal_worker.py`, `tools/rig-async-stage/unreal-lane/test_unreal_lane.py`, `worker_status.py`, `test_worker_status.py`.

Tests: `python3 -m unittest discover -s tools/watoom-code/tests -p 'test_game_worker_bridge.py'` — PASS, 11 tests, 0 failures. `python3 -m unittest discover -s tools/rig-async-stage/unreal-lane -p 'test_*.py'` — PASS, 20 tests, 0 failures. `PYTHONPATH=tools/watoom-code python3 -m unittest test_worker_status` — PASS, 28 tests, 0 failures.

Bazzite helper limitation: the owner-only `ansible/roles/watoom-code/files/skills/watoom-fab-owned-assets/scripts/unreal-export/bazzite.py` was not modified. Recommended follow-up there: expose a typed SSH failure/return code so callers can distinguish exit 255/unreachable, missing staged runtime, busy/OOM, and remote script failure without parsing exception reprs.

## Item 3 — reachability history

`worker_status.py` carries Bazzite `last_ok`, `consecutive_failures`, `first_failure`, and `failure_code` across snapshots; its health is `ok`, `degraded`, or `down`. RIG status includes `quiet_for_seconds` and the same health labels. The journal lookup now checks the last seven days so quiet duration remains useful after the former 30-minute query window.

Tests: included in `PYTHONPATH=tools/watoom-code python3 -m unittest test_worker_status` — PASS, 28 tests, 0 failures.

## Item 4 — collector self-observability

Snapshots include collector version, duration and `{ok,count,error}` for receipts, lane results, jail, journal and Bazzite probe. Invalid JSON receipts are counted and surfaced. Source failures fail soft; `main()` emits a fallback diagnostic snapshot on collector exceptions. JSON and metrics files use atomic replacement. Added an install task to ensure the existing node-exporter textfile directory exists.

Files: `tools/watoom-code/worker_status.py`, `tools/watoom-code/test_worker_status.py`, `ansible/playbooks/worker-status.yml`.

Tests: collector source-error and atomic-write coverage is included in the 28 passing worker-status tests above.

## Item 5 — metrics and alert rules

The repo already has node-exporter `--collector.textfile.directory=/host/var/lib/node_exporter/textfile` and `/var/lib/node_exporter/textfile` host conventions. The collector atomically writes `watoom-workers.prom` with worker up/busy, rolling 24-hour state counts, oldest-running time, per-running-job age/deadline, snapshot timestamp and consecutive failure metrics. Added staged alert rules to the existing `manifests/10-infrastructure/monitoring/monitoring.yml` ConfigMap for stale snapshots (>5m), Bazzite down (>10m), jobs >2x deadline, and >50% failures with at least four jobs in 24h. Rules are not applied.

Files: `tools/watoom-code/worker_status.py`, `tools/watoom-code/test_worker_status.py`, `ansible/playbooks/worker-status.yml`, `manifests/10-infrastructure/monitoring/monitoring.yml`.

Tests: metrics render and atomic-write checks are included in the 28 passing worker-status tests. The monitoring manifest parses with PyYAML (`yaml.safe_load_all`) — PASS. Alert rules have not been applied or live-validated.

## Item 6 — RIG phase visibility

Implemented an optional best-effort `uploads/ue-<job>/progress.json` upload from the Unreal lane at `FETCHING`, `RUNNING` and `UPLOADING`; it includes job, phase, timestamp and fixed operation. Upload errors are ignored and `result.json` remains last. The lab-side reader recognizes the three phases and uses it only when no result exists. Older workers remain compatible. No bundle was built, no hashes/provenance were touched, and no RIG connection/install occurred.

Files: `tools/rig-async-stage/unreal-lane/worker-source/unreal_worker.py`, `tools/rig-async-stage/unreal-lane/test_unreal_lane.py`, `tools/rig-async-stage/unreal-lane/README.md`, `tools/watoom-code/worker_status.py`, `tools/watoom-code/test_worker_status.py`.

Tests: `python3 -m unittest discover -s tools/rig-async-stage/unreal-lane -p 'test_*.py'` — PASS, 21 tests, 0 failures. Lab progress reader is covered by `PYTHONPATH=tools/watoom-code python3 -m unittest test_worker_status` — PASS, 28 tests, 0 failures.

Owner reinstall requirement: changed shipped source is exactly `tools/rig-async-stage/unreal-lane/worker-source/unreal_worker.py`. Before reinstall, Claude/owner must run the documented `build_lane.py`; that regenerates the bundle's `unreal-lane-provenance.json` hash entry for `unreal_worker.py`. No pinned Unreal runtime file/hash needs regeneration. The RIG must receive and install the rebuilt bundle with its scheduled task stopped under the lane's documented update procedure. I did not build or install it.

## Item 7 — docs

Updated the Workers panel section in `docs/guide/software-design.md`, the worker-status section in `tools/watoom-code/README.md`, worker bridge/collector docstrings, and the Unreal lane README with stale classification, structured fields, source diagnostics, metrics/alerts and phase progress/reinstall guidance.

Files: `docs/guide/software-design.md`, `tools/watoom-code/README.md`, `tools/watoom-code/worker_status.py`, `tools/watoom-code/game_worker_bridge.py`, `tools/rig-async-stage/unreal-lane/README.md`.

Tests: documentation-only, covered by the YAML parsing and test commands above; no Glance renderer or bundle builder was run.

## Deployment handoff for Claude

- Run/review `ansible/playbooks/worker-status.yml` to install the collector, enable its 30-second timer, ensure the textfile directory, and begin writing the snapshot and metrics. It deploys the collector source; no separate service restart is required after the timer is installed. The first timer invocation will produce the new fields and `.prom` file.
- The bridge/Bazzite wrappers are executed from the checked-out project paths. Review `ansible/playbooks/watoom-code-game-worker.yml` for the managed worker timer/service configuration; new code is consumed on its next poll. Do not interrupt an active job to activate it. No remote Bazzite unit restart is required by these source changes.
- Review/apply `manifests/10-infrastructure/monitoring/monitoring.yml` through the established manifest flow, then reload Prometheus configuration using its enabled lifecycle endpoint. Verify alert rules load and node-exporter exposes `watoom_workers.prom` metrics.
- RIG progress remains inactive until the owner rebuilds and reinstalls the Unreal lane. Regenerate only the lane `unreal-lane-provenance.json` generated bundle pin for `unreal_worker.py`; do not hand-edit pins.
- No deployment, restart, manifest apply, SSH, RIG access, Glance rendering, or bundle build was performed here.

## Risks / remaining constraints

- Exact report destination is not writable in this environment. This report is maintained at `/tmp/worker-observability-20261108.report.md`; copy it to `/data/ai/artifacts/codex-briefs/worker-observability-20261108.report.md` using an authorized operator.
- `bazzite.py` is owner-only and was not edited. Its callers now classify known return codes and wrapper signals, but a typed error from that helper would be more reliable than parsing its exception text.
- Full test suite blockers are documented below; no actual project or worker was touched. Alert rules were syntax-parsed as YAML but not live-loaded.

## Final validation

- `python3 -m unittest discover -s tools/watoom-code -p "test_*.py"` — FAIL, 83 run: 77 passed, 6 errors. Blockers: `test_capture_integration.py` references missing `/data/ai/projects/images/.opencode/capture-fixtures/pose-video-v2/source.blend`; `test_capture_pose_blender.py` requires Blender's unavailable `bpy`; four `test_repair_game_request.py` cases cannot create fixtures in protected `/data/ai/projects/games` (EACCES).
- `PYTHONPATH=tools/watoom-code python3 -m unittest test_worker_status` — PASS, 30 tests, 0 failures.
- `python3 -m unittest discover -s tools/watoom-code/tests -p 'test_game_worker_bridge.py'` — PASS, 11 tests, 0 failures.
- `python3 -m unittest discover -s tools/rig-async-stage/unreal-lane -p 'test_*.py'` — PASS, 21 tests, 0 failures.
- `python3 -m unittest discover -s tools/rig-async-stage -p 'test_*.py'` — PASS, 2 tests, 0 failures.
- `node --test tools/rig-async-stage/test-*.mjs` — FAIL, 5 test files: 2 passed, 3 could not start because their fixtures attempt to create directories under protected `/data/ai/projects/games` (EACCES).
- `python3 -m py_compile` on the nine changed Python modules — PASS; `node --check config/glance/command-center/cc.js` — PASS; PyYAML parsing of the monitoring manifest and its embedded alert rules — PASS. `git diff --check` on changed paths — PASS.

The required report destination `/data/ai/artifacts/codex-briefs/worker-observability-20261108.report.md` is outside the writable roots. I maintained the progress source at `/tmp/worker-observability-20261108.report.md` and copied a reviewable workspace artifact to `docs/reports/worker-observability-20261108.report.md`.

## Git status --short of this task's changes

```text
 M ansible/playbooks/worker-status.yml
 M config/glance/command-center/cc.js
 M docs/guide/software-design.md
 M manifests/10-infrastructure/monitoring/monitoring.yml
 M tools/rig-async-stage/unreal-lane/README.md
 M tools/rig-async-stage/unreal-lane/test_unreal_lane.py
 M tools/rig-async-stage/unreal-lane/worker-source/unreal_worker.py
 M tools/watoom-code/README.md
 M tools/watoom-code/asset_capture_bazzite.py
 M tools/watoom-code/blender_bazzite.py
 M tools/watoom-code/game_bazzite.py
 M tools/watoom-code/game_blender.py
 M tools/watoom-code/game_import.py
 M tools/watoom-code/game_validation.py
 M tools/watoom-code/game_worker_bridge.py
 M tools/watoom-code/test_worker_status.py
 M tools/watoom-code/tests/test_game_worker_bridge.py
 M tools/watoom-code/worker_status.py
?? docs/reports/worker-observability-20261108.report.md
```
