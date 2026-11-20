# Engine routing and game validation

Current production verification (2026-10-21): the repaired Magpie regression is
**119 passed, zero failures and zero runtime errors** in an isolated 4 GiB worker,
with a 2,626,355,200-byte peak. A deliberate GDScript type error was separately
rejected with a nonzero exit. The app-readable receipt is
`/data/ai/projects/games/magpie-flight-godot-candidate/.opencode/validation/operator-godot/run5.json`.
This supersedes the initial failing diagnostic below. It validates runtime and
regression behavior; the ongoing asset job retains its own visual acceptance.

The OpenCode application has a shared 2 GiB control-plane budget. A local shell,
CPU-only option or timeout does not create a separate worker. Full Godot tests
and heavy engine validation must use a separate bounded worker. An exit 137 run
is interrupted; partial PASS lines do not establish a passing baseline.

## Installed Unreal and Toolkit

Production Unreal 5.8.3 is mounted in Toolkit at `/unreal-engine`; its executable
is `/unreal-engine/Engine/Binaries/Linux/UnrealEditor`. Host runtime:
`/data/ai/toolchains/unreal/5.8.3/runtime-74dc43e1a653`.
The `/data/ai/assets/unreal-engine` directory is not the engine workers use.
Absence of an editor in that tree or the app does not establish engine absence.

Read the installed `watoom-blender-asset-builder` skill and its request-workflow
reference. The maintained request runner preserves versioned source, stage hashes,
packed-source QA, images and recovery. Accepted source assets use native
`watoom_specialist_run`, `local-toolkit`, capability `3d.inspect`, task
`3d-inspect`, `parameters.engine_validation=1`, timeout 420, with the actual
workspace-relative request source path. Discover the current schema once.
This dedicated engine-validation worker has a separate 3 GiB allocation.

Engine validation and arbitrary owned-asset export are different operations.
Check the installed conversion helper/schema before declaring a conversion
unavailable. If the requested operation is unsupported, report the capability
gap separately from runtime availability; do not rebuild an owned asset merely
because the app cannot see Unreal. Historical helper-package PARTIAL reports
are not the current production status.

## Full-game regression

The Toolkit asset-validation operation is not a generic full-game test shell.
For the current Magpie baseline, a trusted operator can invoke the maintained
snapshot helper. Coding agents must request its receipt rather than use sudo or
fall back to full tests in the app:

```sh
sudo python3 tools/watoom-code/game_validation.py \
  --project /data/ai/projects/games/magpie-flight-godot-candidate \
  --evidence /data/ai/helper-scripts/reports/UNIQUE-GODOT-VALIDATION \
  --memory-gib 3 --i-approve
```

The helper verifies the pinned existing Godot 4.7.2 binary and takes a copied
project snapshot; it never runs tests against mutable live game files. A native
systemd worker drops to virtual worker UID/GID1009 using the existing setpriv
pattern, runs CPU-only with two cores, no GPU/network/swap and a 300-second
lifetime, and writes an independent exit receipt. Worker-writable snapshot/home
and cache are separate from root-owned control files. Memory defaults to 3 GiB;
4 GiB is available only when at least 6 GiB host RAM is available. Both choices
reserve at least 2 GiB for the host at admission. App/inference limits are unchanged.

Source hashes exclude `.godot`, `.opencode`, `.git` and the in-progress
`magpie-final` output directory. The copied source and live source must match at
admission; the receipt also reports whether live source changed during testing.
Only a real final test summary, zero failures, no runtime error lines and successful process exit yield
PASS. Keep failed evidence. `--resume-prepared` is permitted only after a setup
failure that produced no Godot log/receipt, with unchanged source/snapshot hashes.
Do not blindly retry a started test. The independent private receipt remains authoritative
if the operator session ends. The controller also publishes a concise app-readable
receipt under `<project>/.opencode/validation/operator-godot/<run>.json`, with
failed-test lines and runtime-error examples. Directory traversal refuses symlinks;
raw operator logs stay private. The worker sets an explicit non-root identity
environment in addition to dropping kernel UID/GID/capabilities.

## Instructions and access

Five managed roles and the candidate project's `AGENTS.md` carry the worker
routing contract. Child packages must repeat the exact worker/runtime/evidence
route. Native models, permissions and step limits are preserved. The current
project NO GIT directive outranks stale commit-based acceptance text.

The `project_layout.yml` task maintains only explicitly configured candidate
edit paths through `project_access.py`. Effective UID1001 ACL entries and masks
are checked directly; default ACLs must never be mistaken for effective access.
Candidate root, scripts/scenes/theme and generated-output parent are editable;
original shared asset-library files are outside this permission correction.
ACL snapshots provide exact rollback with `setfacl --restore=...`.

Current routing and ACL evidence is under
`/data/ai/helper-scripts/reports/current-job-routing-20261020` and
`/data/ai/helper-scripts/reports/current-job-permissions-20261020`.

## 2026-10-20 production verification

Live five-role routing blocks match IaC; Toolkit UnrealEditor is executable.
Coordinator acknowledged the correction and retracted its earlier unavailable
verdict. ACL reconciliation is idempotent (48 paths, zero further changes).
Ansible syntax/lint and rendered argument checks passed.

The external 3 GiB Magpie worker completed with exit 0 and a 2,790,006,784-byte
peak, beyond the previous 2 GiB app OOM point. Its summary reports 118/118,
but 1,543 runtime error lines make the validation FAIL, not a clean baseline.
Errors include RefCounted/Node type mismatches and missing methods. Preserve
this as a separate game/harness follow-up; engine routing is verified.
Receipt: `/data/ai/helper-scripts/reports/magpie-godot-3g-20261020-run2/result.json`.
Setup failures and the initial summary-only receipt are retained as evidence.

## Applied game corrections (2026-10-21)

The canonical candidate project now fixes startup data-only object parenting,
TargetSystem constructor use and the procedural sky material. Projectile hits
use the target system's integer pedestrian/animal states. Vehicle respawn now
restores alive/countdown/shake state; a focused test proved its previous failure
before the fix. Flight physics, score constants and original assets are preserved.

The runner starts after the SceneTree is ready, requires explicit test completion,
frees tracked/orphan fixtures after every test and flushes server resources.
Logic fixtures omit unrelated world geometry; separate production startup,
environment and owned-asset integration checks retain real scene acceptance.
Shared asset scenes are cached during the suite. Existing collision/callback,
velocity, airborne gravity and wrap assertions now exercise the current actual
interfaces. Cluster acceptance checks asset paths and transforms instead of a
stale total scene-child count. Pause tests check the actual tree flag too.

Changed game source: `scripts/main.gd`, `poo.gd`, `targets.gd`, `test_runner.gd`;
new test-only fixtures: `test_main_fixture.gd`, `test_visual_fixture.gd`.
The game project's NO GIT directive is preserved. Source backups, reviewed diff,
before/after hashes, negative controls and retained diagnostic receipts are under
`/data/ai/helper-scripts/reports/magpie-regression-fix-20261020/`.
Restore only the exact backed-up files after confirming current hashes still
match `after-hashes.json`; never overwrite newer asset/game work blindly.

## Asset-job input recovery (2026-10-21)

The active coordinator was briefly interrupted through its supported native API;
active-session inventory was empty before operator edits. A new revision
`/data/ai/projects/llm/pipelines/blender-asset-builder/magpie-v24-20261021` preserves
v23 and corrects the missing specification, stage argv, overlapping MODEL
input/output and wrong packed engine source. PoseBone sampling now matches the
maintained generator's `rig.matrix_world @ pb.matrix` contract. All scripts parse,
and the actual production app's pipeline dry-run returns PLANNED. No stage,
engine or visual acceptance is inferred from preflight. The coordinator resumed
with this exact revision and the readable regression receipt; asset execution
and visual acceptance remain owned by its serial builder job.
