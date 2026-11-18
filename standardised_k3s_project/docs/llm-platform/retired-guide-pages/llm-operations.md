---
title: System Documentation and Operations
nav: LLM operations
summary: Deployment ownership, safe inspection, releases, backups, recovery, monitoring and troubleshooting for the complete platform.
---

## Operator orientation

This guide is for an authorized operator on the existing host. It does not authorize deployment, model switching, stopping a session or restoring data. Read the [requirements](llm-requirements.md), [technical specification](llm-specification.md) and owner-approved change first.

The repository describes desired state; secrets, models, artifacts and user state live elsewhere. Preserve unrelated work and the Git index. Review explicit paths, never clean/reset a checkout. Application agents and operators retain their established publication roles.

## Safe daily inspection

These commands read status; they do not establish a maintenance window:

```bash
cd /data/github/watoom-standardised-homelab/standardised_k3s_project
git status --short
systemctl status watoom-gpu-controller --no-pager
cat /data/ai/helper-scripts/state/gpu-controller/state.json
kubectl -n llama-cpp get deploy,pods
kubectl -n watoom-code get deploy,pods
nvidia-smi --query-gpu=name,power.limit,temperature.gpu,memory.free --format=csv
free -h
df -h / /app /data
```

Healthy primary idle is `qwen-ready`, owner null, uncertainty false, primary ready. `model-ready` may be legitimate for an explicitly selected alternative. Generations increase: never hard-code one as authorization. A live owner/journaled uncertainty requires investigation before disruption.

Use the existing authenticated helper for native active-session/admission status. Do not export environment variables or DB payloads. Idle model slots do not prove absence of pending application work.

## Installation and reconciliation map

| Area | Existing route | Preconditions |
|---|---|---|
| Host power | `ansible/playbooks/gpu-host.yml` | Reviewed host change and current drop-in inventory |
| Controller/model lab | `gpu-controller.yml`, `llm-model-lab.yml` | Established activation gates and identities |
| Application | `watoom-code.yml` / owning release playbook | Exact vars, quiet fence, rollback snapshot |
| Skills/agents/guard | Owning `watoom-code-*`, `watoom-native-skills.yml` | Reviewed bytes and idle reload |
| Embeddings | `watoom-code-memory-embeddings.yml`, BGE playbook | Persistent memories retained; configured mode verified |
| Model Manager | `model-manager.yml` and manager cutover | Exact prepared source, administrative quiet and rollback |
| Documentation | Existing guide renderer/HostPath publication | Source/link/search/download and served-page checks |

Inspect each playbook's actual options before use. A generic rebuild is not a normal upgrade. Do not reinstall k3s/Docker or repeat retired controller initialization. Reconciliation must not overwrite user config or erase queues.

## Standard release procedure

1. Identify the owning source and exact changed fields. Capture source/image pins, deployment UID/spec identity and configuration snapshots privately.
2. Run affected tests/render/schema checks. Compiler/build success alone is not acceptance.
3. Confirm owner authorization and actual idle conditions: native sessions, durable inputs/claims/background work, leases, slots, controller and worker liveness.
4. Acquire established native/component/GPU fences. Do not create another replica writer or force a guard open.
5. Apply only reviewed source through its owner. Keep application, guard, Toolkit and model changes scoped.
6. Verify readiness and affected behavior through actual native/tool/image/router paths; health alone is insufficient.
7. Reconcile source/live controller fingerprint for approved backend spec changes and verify healthy restart.
8. Release admission only after success or verified restoration. Retain fences/evidence and report immediately when recovery fails.
9. Record result, rollback, evidence, limits and next action; publish reviewed paths through the owner's Git process.

Use `tools/llm/benchmark-engine.py` for tuning, not `kubectl set env` or primary scaling. It owns isolated pods through the existing controller protocol and restores power/primary in `finally`. Failed recovery retains the fence. Candidate JSON is allowlisted; image changes require immutable digests.

## Benchmark interpretation

Preflight needs a new evidence directory. Owner sessions win. A blocked preflight is not a candidate result: preserve it, retry at the authorized interval with fresh evidence. Only read-only admission transport probes have bounded retries. Answered busy/lease/session conditions remain enforced immediately.

Paired trials default to skipping synthetic decode. Full combined qualification explicitly uses `--skip-points none`. Correctness, 100K vision and agent safety points cannot be skipped. Five recorded agent repetitions follow warm-up by default. `suite-points.json` records deliberate omissions; unrecorded missing data fails.

The offline analyser applies reference/drift/noise rules. Baseline drift is inconclusive, not pass/fail. Turbo hash differences defer to quality. Review supplemental retrieval/tools/soak plus router checks with speed evidence: `SCREENING_PASS` never independently authorizes adoption.

The special `--cache-probe` verifies only exact disposable-container cgroups and actual saved-state/checkpoint bytes. It does not change global swappiness or production cgroups. Memory floors constrain the trial; a guessed “larger cache” is not an accepted fix.

## Model lifecycle

A user-selected/cataloged model is not necessarily loaded. One large managed model is resident at a time; switching waits for requests and controller eligibility. Discovery/status endpoints are distinct from mutation.

Model Manager separates inspection, download/configure/register and generation jobs. Review immutable revision, exact size, supported architecture/settings and dependencies. Do not execute downloaded repository code. Removal requires a fresh plan/confirmation; active/shared/protected files block unsafe removal. Quarantine does not imply reclaimed bytes.

Reconcile uncertain operations by existing request/job identity. Do not allocate a new ID after a timeout just to try again. Retain partial downloads and receipts.

## Monitoring and evidence

| Signal | Meaning | First action |
|---|---|---|
| Owner/phase/uncertainty | GPU ownership and reconciliation | Inspect owner identity, liveness, journal |
| Readiness/restarts | Process/service health | Inspect affected pod/events/logs |
| Leases/slots | Inference versus switch eligibility | Wait; do not kill unknown work |
| Temperature/memory/power | Capacity/operating condition | Compare exact profile and competing processes/displays |
| Native backlog/claims | Admitted/interrupted work | Reconcile existing native task/session |
| Backup timestamp/receipt | Local/off-host completion | Verify manifest/transfer receipt |
| DiskPressure/free bytes | Runtime/model/artifact storage | Inventory exact ownership before retention |
| TTFT/cache tokens | Prefill/reuse behavior | Correlate tasks/slots; association is not causation |

Use Loki/metrics/private evidence without pasting raw prompts, credentials or DBs. Record IDs, lengths, hashes and timings. Missing historical trace/correlation remains an explicit limitation.

## Backup and restore

The daily helper produces verified SQLite/config/deployment backup sets and keeps 14 runs. The current off-host workflow exports/pulls rotating sets and checks receipts. Inspect active configuration; older notes saying there is no off-host copy are historical.

```bash
systemctl list-timers watoom-code-backup.timer watoom-backup-offhost-check.timer --no-pager
ls -lt /data/backups/watoom-code | head -3
```

AgentMemory's non-SQLite engine archive is best-effort unless portable restore is demonstrated. Git is not a backup of sessions/models/assets. Other libraries/host state have separate protection limits in [recovery](recovery.md).

Restore procedure: select a verified manifest, review affected state, obtain a quiet approved window, snapshot current state, restore to an isolated location first, run DB/backend checks, then perform scoped restoration through its owner. Never downgrade a database simply to roll back an image. Verify sessions/inboxes, memory, project paths and native tools before resuming.

## Failure and recovery runbook

| Symptom | Boundary to inspect | Safe action |
|---|---|---|
| Router 503/no backend | Controller busy/unavailable or uncertain intent | Read status; wait or use documented liveness-qualified recovery |
| Fingerprint mismatch | Independent backend specification change | Match old snapshot, review full diff, reconcile approved fields only |
| Restoration failure | Worker/GPU/API uncertainty | Retain fence/state/journal; report and recover exact owner |
| Unauthorized/sign-in loop | Credential/origin/TLS path | Verify configured credential source without printing it |
| Input acknowledged/no reply | Native claim/queue/worker/inference wait | Inspect existing session; do not blindly resubmit |
| Child/vision gate blocks work | Guard contract | Continue exact child/critic/receipt path; never erase counters |
| Downloaded model unusable | Registration/settings/architecture | Inspect existing job/identity; download is not qualification |
| Malformed tool call | Model/template/schema mismatch | Retain safe schema/hash evidence and compare capabilities |
| TTFT spike after switch | Slot/prefix/checkpoint/cache | Measure processed/cached tokens before changing cache |
| RAM/swap/disk pressure | Workloads/caches/images/artifacts | Read host/cgroup evidence; no unscoped tuning/deletion |

Never edit state to clear uncertainty, delete leases, reset generation or force replicas. Do not restore historical wildcard RBAC/scaling writers. Probe failure is not proof that the owner is idle.

## Rebuild and dependency order

A rebuild needs the reviewed repository, vault recovery, existing storage mounts and actual user/model state. The broad infrastructure recovery order is network/storage, runtimes, secrets, ingress/monitoring, controller/model lab, application/memory/Toolkit, then specialist workers and acceptance. Follow [recovery](recovery.md) for owning playbooks; this document does not authorize foundation changes.

Verify every recovered layer before starting dependents. Recovered identity/journal state must correspond to the actual model resources. Old backups can contain retired integrations; restore reviewed affected fields rather than applying old manifests wholesale.

## Documentation and Git publication

Canonical docs are `docs/guide/llm-*.md` and references under `docs/llm-platform/`.

```bash
/data/ai/toolchains/docs-render/bin/python scripts/render-glance-guide.py
/data/ai/toolchains/docs-render/bin/python scripts/render-glance-guide.py --check
python3 scripts/verify-homelab-documentation.py
```

Glance mounts rendered guide files read-only from the canonical operator checkout. No inference restart is needed. Review source/generated diffs, publish explicit documentation paths, preserve unrelated work and verify served pages/search/downloads. Private release snapshots and model payloads are excluded.

Record source revision, owner scope, affected component, tests, identity, rollback, live verification and limits for maintenance. Revisit docs/schema exports after API, agent, model, worker or path changes. A documentation update does not authorize an application/model rollout.
