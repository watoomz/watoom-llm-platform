# WatooM Code memory, catalogue and render handoff review

Date: 26 October 2026 (Australia/Brisbane)

## Live release

Approved source commit: 4f64b0e38ac22652907f48029beb12fae5f7a4c9

Running image: 127.0.0.1:5000/watoom-code@sha256:8a688bc3b2d53f512d01d546499be798b0bfc1180b7596eae98b76e7ff4bd91a

Application version: 0.0.0--202610252121

The native deployment guard was acquired after both live and durable execution-clearance checks. A standalone SQLite backup passed integrity verification before the additive migration. The guard is now released with zero leases. GPU controller generation remained 167, owner null, uncertainty false, primary qwen-ready. No router, firewall, DNS or host-network settings changed.

The first activation failed the catalogue completeness gate and rolled back automatically. The second activation passed with the identical candidate. The first discrepancy was not captured in enough detail to establish a root cause; discovery timing is a possibility, not a proven diagnosis. The maintained release helper now waits up to 30 seconds for the full inventory and retains incomplete observations before failing closed. Subsequent live API and browser checks consistently returned 131 skills including 28 pipelines.

## Implemented

- Append-only correction, supersession, consolidation and withdrawal, scoped by project/repository/agent. Originals remain auditable; conflicting retries and cross-scope targets are rejected. Native recall filters obsolete facts and resolves successor records.
- Mandatory native lifecycle capture, structured goals/milestones/decisions/safe stops, durable outbox retries and explicit outage/uncertainty behavior. Automatic lifecycle metadata does not copy raw tool input/output or transcripts.
- Authenticated memory status API and /memory dashboard: outbox counts, timestamps, retrieval latency/failures and recent receipts. Root-owned controller snapshots provide fresh read-only GPU ownership observations.
- Live /catalogue and skill index API, model-facing watoom_skill_search and task-specific relevance ranking. Short descriptions, pipeline types, dependencies, availability and manual-only restrictions are exposed. Strong matching instructions load only under existing permissions. New installed records enter through native discovery without a fixed routing allowlist.
- Writing, image and development pipeline metadata now supplies clearer descriptions, intent keywords and required supporting skills.

Live status: memory enabled and mandatory; 4,135 acknowledged records; pending/sending/uncertain all zero. Older records show unknown timestamps honestly. Backend acknowledgement is not a claim of power-loss durability. Retrieval counters start anew with the process.

## Verification

Affected schema, protocol, core, server and app typechecks passed. Native memory regression suite passed. Seven routing tests, 27 focused app tests, two authenticated API tests, 135 controller offline tests, four router tests and ten model-selection tests passed. Production app and immutable binary/image builds passed. Both isolated and live browser checks passed; actual screenshots were inspected.

The canonical repository-wide check did not pass: the reused dependency tree lacks @tsconfig/node22 in unrelated packages, and Turbo then exited with SIGSEGV. This remains a validation limitation, not a full-suite PASS.

Live search examples: graphic-novel writing selects watoom-prompt-writing and adaptation; Sims retargeting selects sims4-animation, blender-animation and capture workflows. Ranking uses weighted lexical matching with bounded instruction evidence; it does not guarantee perfect semantic selection.

## Workstation render handoff investigation

Machine RIG: Ryzen 9 3900X (12 cores/24 threads), approximately 32 GB RAM, RTX 2080 SUPER with 8,192 MiB VRAM, driver 617.42. F: has approximately 1.58 TB free. Blender was not found on PATH, in the standard installation directory or in the checked uninstall registry entries; an executable/version remains unverified. No sshd service was found by the service probe. Nothing was installed or exposed.

The existing capture dispatcher runs on the homelab and currently starts bounded CPU Cycles workers with 2 threads, 4 GiB RAM, no swap and a 900-second deadline. Its root-owned receipts attest to that Linux worker boundary. Those receipts cannot honestly be reused unchanged to attest to a Windows workstation run.

Recommended implementation: retain the existing native request identity and homelab coordinator, and add an opt-in workstation pull worker with narrowly scoped authentication. This avoids requiring an inbound workstation listener. Use declarative manifests, allowlisted operations and an isolated local job directory. Transfer the complete dependency set by content hash; preserve original sources. Claim each job with a lease/generation, heartbeat it and reconcile expired or disconnected work without automatic duplicate submission. Return output hashes, Blender/driver/device versions, limits and execution logs. The homelab verifies the worker identity and results before issuing a distinct workstation receipt. Finished rendering remains visual-review-pending until actual pixels/motion are reviewed.

Start with one bounded Blender still on CPU, then test CUDA/OptiX against the installed Blender build and 8 GiB VRAM. Measure realistic scenes before selecting GPU memory, system RAM, tile/frame, timeout and concurrency budgets. Large textures/scenes can exceed this GPU even when system RAM is available. Keep one job at a time initially; expose availability/busy/offline and chosen worker in the catalogue/status UI. A workstation disconnect must leave the existing job reconcilable.

This was an investigation only. No workstation worker, Blender installation, GPU render or network change was made.

## Durable artifacts

Authoritative IaC: /data/github/watoom-standardised-homelab/standardised_k3s_project

- Source bundle and release manifest: tools/watoom-code/source/watoom-code-memory-catalogue-20261026.bundle and memory-catalogue-20261026.json
- Scoped playbooks: ansible/playbooks/watoom-code-memory-observability.yml and watoom-code-memory-catalogue.yml
- Guarded release helper: tools/watoom-code/memory_catalogue_release.py
- Private activation evidence and database snapshots: /data/ai/projects/llm/watoom-code/memory-lifecycle-20261026/activation and activation-2

Unrelated dirty IaC changes were preserved and not committed. Application source is committed in its isolated worktree; the source bundle preserves it for reconstruction.
