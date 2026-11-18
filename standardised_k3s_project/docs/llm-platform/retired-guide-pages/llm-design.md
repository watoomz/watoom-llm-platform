---
title: Software Design Document
nav: LLM design
summary: Architecture, component responsibilities, ownership state, data flows and trust boundaries of the complete WatooM LLM platform.
---

## Design goals and context

The platform combines a native agent workspace with local inference and bounded specialist execution on one host. Its central constraint is safe sharing of one large GPU across interactive inference and explicitly admitted work. The architecture separates user-level planning from privileged infrastructure mutation, and software deployment from persistent application/model data.

The [requirements](llm-requirements.md) define acceptance; the [technical specification](llm-specification.md) defines the inspected deployment. This document explains implementation choices and failure behavior. Retained candidate deployments are not accepted services merely because they exist.

## System context

```text
Owner / browser / API client
        |
        +--> WatooM Code :4096 --> llm-router :8000 --> selected llama-server
        |         |                       |                    |
        |         |                 inference leases           +--> GPU
        |         |                       |
        |         |                 GPU controller (host)
        |         |                 durable state + journal
        |         |
        |         +--> AgentMemory --> BGE embedding service
        |         +--> SearXNG / native tools / reviewed MCP capabilities
        |         +--> Toolkit --> bounded CPU/engine worker Jobs
        |         +--> admitted image/Mesh/workstation jobs --> receipts
        |
        +--> Glance --> documentation / Model Manager
                                 |
                         privileged model broker
                                 |
                         controller enrollment
```

The browser reaches internal HTTPS services through the existing ingress/TLS arrangement. In-cluster inference uses the router service. A loopback registry supplies digest-pinned images. Models, application state, artifacts and engine installations retain separate storage roots.

## Component decomposition

| Component | Owns | Does not own |
|---|---|---|
| Native application | Sessions, inboxes, events, permissions, project bindings and model-visible tools | Kubernetes replicas, controller private socket, infrastructure credentials |
| Coordinator guard | Delegation budget, durable handoff identity, critique and image-evidence boundaries | General OS isolation or correctness of subjective visual judgments |
| AgentMemory | Memory persistence and configured recall | Application session database or controller ownership |
| Router | Model aliases, forwarding, request accounting and stream lifecycle | Independent scaling or recovery after controller refusal |
| GPU controller | Managed replicas, generation fencing, ownership, leases and identity checks | User prompts, project edits or application session semantics |
| Model Manager UI/worker | Metadata/settings/catalog/download coordination | Unrestricted root or GPU-write access |
| Model Manager broker | Narrow privileged enrollment/lifecycle operations | Executing arbitrary metadata/source text |
| Toolkit/dispatchers | Validated bounded jobs and durable result delivery | General cluster administration or silent GPU contention |
| IaC/release tooling | Desired configuration, immutable pins, verified promotion and rollback | Replacing user data as a side effect of reconciliation |

Boundaries are enforced by native permissions/plugins, container mounts/security contexts, namespace/RBAC controls, UNIX peer identity, controller journals and release guards. None alone establishes total isolation.

## Interactive request sequence

1. The user selects a project, agent and model. Native admission stores the input and schedules session execution.
2. The runtime loads configured tools/instructions and produces an inference request within the application context/output budget.
3. The router resolves the alias to a managed deployment and asks the controller about eligibility. Explicit model selection may request a controller-mediated switch; `active-model` follows the active backend.
4. Managed request accounting holds an inference lease through the request/stream lifetime. The backend evaluates the prompt and emits text/reasoning/tool-call fragments.
5. The application authorizes and executes permitted tools. A model-generated call is only a proposal until runtime validation and execution complete.
6. Continuations reuse the model slot/checkpoints where possible. The application records messages, outcomes and token/timing metadata.
7. The browser follows native events and reconciles persisted state on reconnect. Events are volatile; the inbox is durable.

A successful admission response is not an assistant answer. A selected/listed model is not necessarily loaded. An apparently idle GPU is not proof that a switch is safe.

## Exclusive GPU ownership

The production controller is the sole replica writer for its managed set. State contains phase, owner, monotonically increasing generation and uncertainty. Deployment identities bind UID to spec hash. Mutation intent and acknowledgement are journaled so an interrupted operation cannot be mistaken for clean idleness.

```text
qwen-ready / owner null
   | eligible acquisition: requests idle, slots idle, valid owner
   v
acquiring -> stopping-qwen -> starting specialist -> mesh-active / model-ready
   |                                                  |
   +------------------ restore / cancellation --------+
                             |
                          restoring
                             |
                 primary healthy + intent reconciliation
                             |
                 qwen-ready / owner null

Any uncertain mutation or failed restoration -> recovery-required
    -> liveness/identity-qualified reconciliation, never forced idle
```

This is the common sequence, not every production transition. Managed model switching can settle in `model-ready`; CPU parking and worker-specific states have separate rules. The private worker and router endpoints expose different actions. Production handlers authenticate root UNIX peer identity and bind owner actions to process/job/generation. An SDK example does not grant socket access.

Generations fence stale workers. Process identity protects against PID reuse. Spec hashes detect independent edits. A missing acknowledgement is uncertainty, not permission to activate under a new job ID. Recovery confirms liveness/termination and reconciles journaled writes before restoration.

## Release admission versus GPU admission

Native maintenance admission prevents application work crossing a release boundary. Durable checks cover active sessions, pending inputs/claims, specialist work and leases; actual slots establish inference idleness. GPU ownership prevents overlapping GPU phases. A campaign lock excludes another benchmark harness. These barriers are complementary.

The performance campaign has an explicitly authorized metadata-only exception for one historical parked inbox item. It is scoped to exact identity, age and idle conditions, not a default release policy or user bypass. Payloads are not required to prove it. Ordinary release helpers stay strict.

## Agents, skills and evidence

Native roles separate coordination, implementation, investigation, review and critique. The guard persists counters and child identity across restart/compaction. Reusing an outer Code Mode call ID does not reset nested execution accounting. Critic-only escalation is narrow, not arbitrary recursive delegation.

Skill availability supplies guidance, not installation, credentials, licenses or writes. Reviewed mounts/native location policy govern project scope. Some shell/worker operations remain unavailable until their sandbox is qualified. Tool guards do not constitute complete filesystem isolation.

Visual evidence binds an actually presented image hash/path to a verified vision model and structured receipt. Further processing can be blocked pending review. Receipts preserve provenance; honest visual judgment remains necessary. Private one-use recovery grants are operator-only and never public configuration.

## Storage and lifecycle

| Data | Writer | Persistence and recovery |
|---|---|---|
| Application SQLite/config/skills | Native app and owning configuration roles | Persistent application root, backups and scoped migrations |
| Memory backend | AgentMemory | Separately persisted; backend restore portability must be demonstrated |
| Model/projector/pipeline files | Model workflows | Immutable selections/hashes; shared files protected on removal |
| Controller state/journal/leases | Controller and approved operator protocol | Durable; never deleted to hide a failure |
| Worker input/results | Admitted worker/result broker | Hash snapshots, bounded artifacts and durable receipts/outbox |
| Benchmark evidence | Isolated harness | Hashes, lengths, identities and telemetry; private input separate |
| Documentation | Git source and renderer | Reproducible HTML/search/downloads in Glance |

Git and backups protect different data. Rebuild restores desired configuration, not sessions, weights, purchased assets or secrets. File presence is not a demonstrated restore.

## Cache and memory design

Distinct caches include application request prefixes, the backend active slot, recurrent checkpoints, host prompt-cache entries and the fork's disk tier. These differ from GPU KV precision and AgentMemory recall. A miss must identify its layer and evidence.

The primary has one inference slot. Agent/session switches can replace its prefix; hybrid state can require rollback to a usable checkpoint. Prefix changes, auxiliary calls and insufficient saved state have different signatures. The current 4 GiB setting was retained because two adopted-engine synthetic 60K states fit and restored efficiently; this is not a guarantee for every real history.

Older logs confirm evictions, but missing request IDs/trace events prevent attribution of every historical same-session miss. Temporal association is not causation. New cache/checkpoint settings require their own fenced trial, not production guesswork.

## Specialist and model lifecycle

Model Manager separates inspect, download/configure, register and actual generation acceptance. New settings create an immutable replacement identity rather than quietly rewriting an enrolled fingerprint. Removal requires a fresh confirmation and protects active/shared files. Quarantine is recoverable movement, not a claim of reclaimed space.

Mesh uses a stable request ID, worker ownership and restoration before downstream CPU processing completes. Toolkit jobs use contracts, time/resource limits and scoped outputs. Workstation rendering uses hash-snapshotted inputs and durable completion receipts. Reconnect reconciles the same job instead of submitting a duplicate.

## Failure and observability design

Expected failures include unavailable controller/backend, live-owner conflict, stale fingerprint, lost acknowledgement, cancellation, partial download, disk pressure, invalid tools and failed visual evidence. Each is surfaced rather than resolved by bypassing ownership or deleting data.

Correlation identities include request/model-call IDs where available, session/message IDs, worker request/job IDs, owner generation, deployment/pod UID, image digest and artifact hashes. Historical logs do not always contain all identities. Reports must minimize payload and credential disclosure.

This is a trusted-owner internal homelab, not a qualified internet-facing multi-tenant service. Internal routing and narrow broker/controller boundaries are explicit security assumptions.

## Design decisions

| Decision | Benefit | Cost or limit |
|---|---|---|
| One GPU writer | Prevents competing scale writers | Requires disciplined recovery/identity reconciliation |
| Local pinned inference | Reproducible local execution | Single-host capacity/hardware dependency |
| Native inbox and event model | Durable input and resumable sessions | Clients must distinguish admission from completion |
| Narrow specialist brokers | Scoped privileged contracts | Lifecycle/receipt coordination |
| Metadata/hash-only evidence | Review without exposing content | Some historical causes stay unobservable |
| Existing Markdown/Glance renderer | One reviewable documentation source | Schema/source exports need version maintenance |
| Owner-selected 300 W cap | Respects hardware preference | Highest measured 320 W throughput deliberately excluded |

Extension points are reviewed MCP/native plugins, managed models, qualified workers and versioned API exports. They must preserve ownership, project scope, credentials and user data. See [API documentation](llm-api.md) and [operations](llm-operations.md).
