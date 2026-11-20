# WatooM Code staging release

The application image reuses the successful musl CLI build, including its embedded browser UI. Its runtime source includes M4; the only subsequent application change removed test diagnostics. See the release evidence for hashes and the distinction between the build HEAD and committed M4 HEAD.

Deploy from `ansible/` with the existing inventory:

```sh
ANSIBLE_CONFIG=ansible.cfg ANSIBLE_ROLES_PATH=roles ansible-playbook -i inventories/homelab/hosts.yml playbooks/watoom-code.yml
```

The dedicated `watoom-code` role owns only namespace `watoom-code`. It seeds configuration once and never overwrites profile, reviewed skills or workflow databases. It reuses the five authoritative WatooM agent definitions. The native model selection is structured in their YAML front matter so the native loader can actually load them.

Application, AgentMemory and Toolkit have independent writable staging state under `/data/ai/watoom-code`. Purchased assets and Unreal engine mounts are read-only. Toolkit creates only bounded CPU Jobs in its own namespace; workers have no service account token or GPU resources. The application has no Kubernetes token and no controller socket. Live GPU ownership transitions are deliberately unavailable to model tools.

SELinux remains enforcing; the staging tree uses a persistent `container_file_t` label. Image storage remains in the existing isolated Buildah store under `/data`; registry data stays on `/app`.

The application exposes its native authenticated `/api/info` endpoint. Readiness checks it using the existing server credential in the pod; liveness/startup use the TCP listener. Browser assets are intentionally available before authentication so the sign-in view works.

Run `python3 tools/watoom-code/backup.py` (scheduled daily by `ansible/playbooks/watoom-code-backup.yml`) for a verified application/catalog SQLite backup (integrity_check, row counts, sha256 manifest, gzip), configuration archive and Deployment snapshot in `/data/backups/watoom-code`, keeping 14 runs and publishing `watoom_backup_last_success_timestamp_seconds` for the `WatoomBackupStale` alert. AgentMemory's own non-SQLite engine storage is archived best-effort from the live directory; this helper does not claim a portable backend-engine backup. Backups stay on the /data disk until an off-host target exists. Failed Ansible readiness restores previous Deployment specifications; database downgrades and destructive state restoration are excluded.

For localhost access run `python3 tools/watoom-code/forward.py` on the host. A local SSH command relay is used in this task because standard SSH TCP forwarding failed despite uncontested listeners. It binds only `127.0.0.1:14100` and leaves host networking unchanged.

## Production gate

`python3 tools/watoom-code/cutover.py prepare` captures the exact current production Deployment, replicas and UID, and writes a candidate manifest plus checksum under a private evidence directory. This performs no production mutation.

The production candidate is **not accepted** merely because staging works. Its existing configuration/MCP commands and mounts must be reviewed against the smaller CLI image and accepted before apply. `apply` requires `--i-approve`, the exact candidate checksum, the snapshot directory, and a separate production-candidate acceptance report. It deploys via the dedicated Ansible playbook and restores the captured Deployment on rollout failure. `rollback` also requires `--i-approve` and the snapshot directory. These scripts do not change inference replicas, GPU power, network settings or user databases.

The `watoom-code` role owns the production resources. The cutover playbook is an explicit one-release operation against that exact Deployment, not a second continuously reconciling role. Persist an approved production release into its existing defaults before routine production reconciliation resumes.

Optional profile components remain unavailable unless their actual runtime/adapter is installed. They are not silently enabled by catalog selection. Meshy is not in the local-only Toolkit source or image.


## Native coordinator and vision evidence guard

The maintained coordinator-guard package uses the supported native plugin interfaces. It reuses plugin storage in application.sqlite, tool transforms/hooks and session context hooks; it creates no database, MCP server or second tool registry. Its explicit configuration path is /config/watoom-tools/coordinator-guard, outside automatic plugin discovery.

For watoom-workflow, six actual direct tool executions require a completed foreground child before more work. Two execution failures require watoom-critic before another repair. A running child must be continued by its existing sessionID. Every nested Code Mode executor counts, even when its outer call ID is reused. Short tasks can complete within the budget. One checkpoint-only write remains possible at a handoff boundary; repeated skill loads, questions and checkpoint rewrites cannot keep that boundary open. Counters survive compaction, user steering, process restart and plugin reload. Other agents retain their own permissions; Kali is outside the coordinator budget.

An actual native image result establishes a pending SHA-256 review. The next model context must contain media and use an explicitly verified vision model before a matching JSON receipt can clear that gate. Further processing is limited until the receipt records its path, hash, model, pixel basis, verdict and at least two observations. A read-only child can return the JSON instead of gaining write permission; the parent checks its provenance against that child's persisted image presentation. Re-reading accepted unchanged hashes reuses the receipt. A new image cannot silently overwrite an unfinished review. This enforces evidence provenance, not the truth of artistic judgments: inspect actual renders and independently verify findings.

The current Swift alias has an actual image challenge and projector configuration recorded in vision-verification.json. Reverify when changing its model, projector or router mapping; do not add model IDs merely from advertised image capability. Ordinary coordinator system guidance stays stable for prompt-cache reuse.

Run focused tests using the existing Node/Bun runtime with tools/watoom-code/test-coordinator-guard.mjs. They cover direct/nested bypass, parallel reservation, restart persistence, cross-session scope, critic escalation, child identity, incomplete visual evidence, model verification and exact receipt matching. Native acceptance must also prove a real parent/child read and real image review; mocks alone are insufficient. Preserve source/config snapshots and actual typed tool-event receipts privately.

Deploy through the existing watoom-code role. enable-coordinator-guard.py changes only its plugin entry, preserves other settings and is idempotent. No image rebuild is required for this native package. Activate only at an idle boundary; supported session interrupt must settle task-owned work first. Roll back by restoring the exact prior configuration and agent instructions from private evidence at an idle boundary; do not erase SQLite guard state, user data or project files.

### Critic-only nested escalation
The maintained coordinator guard allows builder/investigator/reviewer to consult only watoom-critic once per child package, foreground and without model override. Native experimental.subagent_depth is 2 for this exception; the guard rejects all other child delegation, background/parallel children and delegation from the critic. Critic tools are read-only. Two guard rejections expose the exact mismatch and require escalation, including in a child; the caller pauses during the critic and further failure returns to the coordinator. Pixel receipts require the exact recorded absolute image path, image hash and presented model. Never delete receipts or use OCR to bypass pending pixel review. This is a native plugin/configuration update and needs no application image rebuild. Validate with test-coordinator-guard.mjs and real native nested-session acceptance.

A builder with a pending image retains the native write tool even after guard
rejections, but only a correctly scoped, matching visual-review receipt passes.
Other writes remain blocked. Read-only agents return their receipt as final JSON.
Coordinators receive the pending child identity and image hash; two invalid
completed evidence returns stop further delegation rather than looping.

Receipt schema errors identify the exact field: observations (not observed) is a required array with at least two strings of12 characters after trimming. Two invalid receipt writes require the existing critic-only escalation; after that critic, one further failed correction removes work tools and returns control to the coordinator. Matching honest evidence remains valid. Reload guard updates only after native executions are idle.

### Handoff recovery and ownership
The maintained coordinator guard counts real worker failures and fresh child rejections, preserves existing-child identity, and enforces one critic consultation per child package. Read-only investigators/reviewers/critics return pixel JSON as FINAL; they never write receipts. Canonical checkpoints belong to the coordinator.

An operator may provide a private plugin option visualRecoveryGrants array containing parentSessionID, childSessionID, image_sha256 and a random64-hex nonce. This is only valid for an already hard-stopped exact child with verified image presentation. It permits one evidence-only continuation, consumes the nonce durably and still validates all receipt fields. A failed recovery hard-stops again. Never commit session grants, hashes or private runtime configuration. Do not grant recovery automatically or clear durable session state.

Run node tools/watoom-code/test-coordinator-guard.mjs before selecting a new immutable guard package. Apply source through the normal coordinator_guard/native_agents role tasks, preserve configuration snapshots, acquire native admission and reload only while idle. Never interrupt a session to reload instructions.

Native execute.before delegation rejections are recorded durably before the error is returned. Two rejections trigger the existing critic/return boundary. A parent sessionID is never accepted as a child resume target; use the recorded child ID and agent rather than changing the agent to match the parent.

The guard narrows each request's model-visible subagent JSON schema to the permitted roles, serial execution and exact pending child. Read-only critics and already-consulted children do not see delegation. Runtime checks still enforce the same boundaries; schema shaping is guidance and must not replace validation. Command discovery must reuse a verified project invocation; arbitrary shell correctness cannot be guaranteed by the guard.

## overnight_watchdog.py — unattended health probe (report-only)

Safe, read-only classifier of the watoom-code stack for unattended/overnight
supervision. Prints a JSON snapshot and encodes the verdict in the exit code:

| exit | state | meaning |
|---|---|---|
| 0  | HEALTHY | stack up, recent progress |
| 10 | IDLE_REVIEW_GATE | parked on a vision review — needs a vision lease (via the GPU ownership controller) or a GUI parent-session resume |
| 20 | IDLE | quiet between jobs |
| 30 | HANG | a stateless service (router / opencode serve) is down |
| 40 | PROBE_ERROR | the watchdog could not read state |

```bash
python3 tools/watoom-code/overnight_watchdog.py --report /data/ai/artifacts/<run>
python3 tools/watoom-code/overnight_watchdog.py --restart-crashed   # bounce a crashed llm-router only
```

It deliberately **does not** run the fenced `recover-*.py` scripts, switch a GPU
model lease, or write a visual-review receipt — those stay operator-gated. A
supervisor (human, Claude Code, or a `codex exec` run) reads its verdict and
decides. Pair it with `codex exec` for autonomous diagnosis of a HANG.

## Blender on Bazzite

`blender_bazzite.py` runs the `blender` game-worker operation on the Bazzite worker (same request contract, limits, pinned
Blender build and receipts as `game_blender.py`; podman, no network, read-only root, only `.opencode/blender-out/<job>/` returns).
One-time staging: `sudo python3 tools/watoom-code/blender_bazzite.py stage`. If Bazzite cannot start a job the request stays
QUEUED and is retried; it never falls back to the homelab server unless `watoom_game_worker_local_fallback` is true.
Bazzite needs 8 GiB free RAM for Godot jobs (`MIN_FREE_GIB` in `game_bazzite.py`) and the job size plus 2 GiB for Blender.

## Asset capture on Bazzite

`asset_capture_bazzite.py` runs the declarative `watoom_asset_capture` jobs on Bazzite: the source's folder (plus any absolute
files the manifest or `.blend` name under the source roots) is mirrored at the same absolute paths, the unchanged Blender-side
script runs in podman with the exact 4 GiB cgroup, MP4 is encoded on the host (no ffmpeg in the image), and
`asset_capture.check_outputs()` validates the result like the server runner. The poll in `asset_capture_bridge.py` tries Bazzite
every cycle; if it cannot start the job the request is QUEUED (`waiting_since`, `rig_eligible`) and goes to the rig route only
after 10 minutes (`bazzite_wait.py`). It never runs on the homelab server.

## Worker status and failure metadata

`worker_status.py` is a read-only snapshot collector. It labels a RUNNING job `stale_running` for display when it exceeds the prepared deadline (default 1800 seconds) plus 180 seconds and either its prepared evidence is missing or its declared unit is not active. It does not edit receipts or replay jobs. Snapshots include per-source collector health, Bazzite reachability history, RIG quiet time, optional RIG phase progress, and `failure_stage`/`failure_code` fields while preserving existing status values.

The collector writes `/var/lib/node_exporter/textfile/watoom-workers.prom` atomically. The existing node-exporter textfile collector scrapes worker up/busy state, rolling 24-hour job counts, oldest-running age, deadline gauges, snapshot time and failure streaks. Install/update with `ansible/playbooks/worker-status.yml`; alert rules are staged in `manifests/10-infrastructure/monitoring/monitoring.yml` and are not applied by this source change.
