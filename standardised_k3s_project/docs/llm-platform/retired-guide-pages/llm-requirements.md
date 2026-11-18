---
title: Software Requirements Specification
nav: LLM requirements
summary: Functional and quality requirements for the complete LLM platform, with verification criteria and source-level traceability.
---

## Purpose and interpretation

The platform enables an owner to perform local AI-assisted work while preserving project data, exclusive GPU ownership and reproducible infrastructure. This SRS defines obligations for the maintained platform, not an assertion that every future workflow is already qualified. “Shall” identifies an acceptance condition. “Current” identifies inspected implementation. “Not qualified” identifies a limit requiring evidence before use.

Priority P0 is safety/data integrity and is required for release. P1 is core usability/correctness. P2 is a supported enhancement whose absence must be visible. Scope and source authority are defined in the [documentation index](llm-documentation.md).

## Actors and use cases

| Actor | Objective | Authority |
|---|---|---|
| Owner/user | Submit a scoped project task; review results; approve consequential changes | Application permissions and explicit approvals |
| Coordinator | Plan, select capabilities, delegate, integrate and checkpoint | Native guard; no independent infrastructure administration |
| Builder/investigator/reviewer/critic | Complete the assigned package with evidence | Agent-specific read/write/delegation permissions |
| Operator | Maintain releases, models, GPU and backups | Explicit administrative workflow and owner direction |
| Integrator | Use native sessions or inference APIs | Authenticated/reachable endpoint; no privilege escalation through APIs |
| Specialist worker | Execute a bounded job and return durable receipts | Validated inputs, job identity, namespace/resource limits |

Primary use cases are project task execution, continuation of an existing session, model selection, image-backed review, specialist submission/status/result, model installation, release promotion and recovery from an uncertain operation. First use, cancellation, retries, worker death, a full disk and an unavailable GPU are required alternate paths.

## Functional requirements

| ID | Priority | Requirement | Acceptance evidence |
|---|---|---|---|
| FR-01 | P1 | Users shall create/select sessions bound to an explicit approved project location. | Native session create/list/read and location validation; unrelated project remains untouched |
| FR-02 | P1 | Submitted prompts shall be durably admitted; acknowledgement shall not be presented as completed work. | Inbox result and later session messages/status agree after reconnect |
| FR-03 | P1 | The UI shall expose installed agent/model/skill capabilities without treating discovery as installation or live qualification. | Native catalog, selected role and actual runtime capability agree |
| FR-04 | P0 | The coordinator shall preserve child identity and use permitted serial handoffs; restricted children shall not gain general delegation. | Coordinator-guard tests and native parent/child acceptance |
| FR-05 | P0 | Image-dependent claims shall use presented media and provenance-bound review receipts. | Model/path/hash receipt contract, two observations and matching presentation |
| FR-06 | P1 | WatooM Code shall reach the configured local inference model through the production router. | Streaming and tool-return checks through `/v1/chat/completions` |
| FR-07 | P0 | Only the GPU controller shall mutate managed model replicas. | Admission/RBAC controls and stale-generation rejection |
| FR-08 | P0 | A GPU switch shall require an eligible idle state, durable owner/generation and verified restoration. | Controller lifecycle tests and final idle state, without bypass or forced scaling |
| FR-09 | P0 | Uncertain transport/mutation outcomes shall retain recovery evidence and prevent independent activation. | Lost-acknowledgement and recovery regressions; no second resident managed model |
| FR-10 | P1 | Memory shall retain stored knowledge across app release and expose only the configured recall mode. | AgentMemory health; native memory validation; no state overwrite by seeding |
| FR-11 | P0 | Worker jobs shall use bounded resources, reviewed input scope and durable identities/receipts. | Contract validation, resource/deadline settings, duplicate request resolves to existing job |
| FR-12 | P0 | Downloaded models shall be selected by immutable revision/files and verified before enrollment. | Exact size/hash/selection; registered deployment starts at zero replicas |
| FR-13 | P0 | Removal shall require fresh identity-scoped confirmation and protect shared/protected/active data. | Manager remove-plan tests and quarantine receipt; no unshared-file guessing |
| FR-14 | P0 | Release tooling shall preserve user databases/configuration and roll back only its reviewed affected resources. | Before/after snapshots, independent-edit rejection, healthy restored application |
| FR-15 | P1 | Operators shall inspect request/owner/job/backup health without needing prompt content or credentials in reports. | Structured metadata, hash-only qualification evidence and freshness metrics |
| FR-16 | P0 | Application/catalog backup shall produce integrity and checksum evidence; restoration shall be tested separately. | Backup manifest, SQLite checks, off-host receipt and isolated restore evidence |
| FR-17 | P1 | API clients shall distinguish durable admission, volatile events and uncertain completion. | Client examples and reconnect/reconciliation behavior |
| FR-18 | P1 | Documentation shall be maintained in Git and served/searchable in Glance from the same source. | Renderer check, link validation and live served-page checks |

## Nonfunctional requirements

| ID | Priority | Requirement | Verification |
|---|---|---|---|
| NFR-01 | P0 | Application credentials, private skills, tokens and session contents shall not enter public documentation or Git artifacts. | Publication review; secret inputs remain server-local/vault-managed |
| NFR-02 | P0 | Owner activity shall block disruptive maintenance; low GPU utilization alone shall not authorize work. | Active sessions, durable claims/queues/leases and actual slots checked together |
| NFR-03 | P0 | An approved deployment specification change shall reconcile controller identity with the exact deployment UID/spec hash. | Reviewed diff, pinned source/live identity and healthy restart |
| NFR-04 | P0 | Performance adoption shall preserve the model, context, sampling and placement constraints unless an owner-approved candidate explicitly changes one. | Candidate schema, immutable image/model identities and isolated comparison |
| NFR-05 | P1 | Performance decisions shall use representative fresh/continuation work, repeated measurements and stable reference baselines. | Warm-up discard, five agent repetitions, reference/noise/drift rules |
| NFR-06 | P0 | The configured GPU power cap shall not exceed the owner-selected 300 W; sustained core temperature shall remain at or below 83°C in qualification. | Owning host role, live cap and telemetry; small instantaneous draw excursions are recorded |
| NFR-07 | P0 | The full candidate shall leave at least 512 MiB free VRAM at 100K context with an image. | Measured minimum during vision, not a static allocation estimate |
| NFR-08 | P0 | A final combined profile shall pass long-context retrieval, tool round-trip and a 30-minute mixed soak without CUDA/Xid/OOM/restart failures. | Candidate-specific gate artifacts and post-adoption router validation |
| NFR-09 | P0 | Workloads shall respect declared paths, retained assets and read-only shared inputs. | Mounts, source guards and write-scope regression tests |
| NFR-10 | P1 | Operational changes shall be reproducible through authoritative IaC and immutable image/source identities. | Clean rendered diff and idempotent approved reconciliation |
| NFR-11 | P1 | Error states shall be explicit and recoverable without deleting ownership/user data. | Typed conflict/unavailable errors, journals and guarded recovery |
| NFR-12 | P2 | Optional specialist capabilities shall fail visibly when unavailable, rather than silently substituting a different tool or paid service. | Capability discovery and negative-path tests |

There is no claimed high-availability or multi-user service-level agreement for this single-host system. Seven-day historical cache statistics are observations from earlier engine windows, not an SLO or a causal diagnosis of the adopted profile.

## Performance acceptance contract

Current campaign rules require at least three repetitions for ordinary suite points, one discarded fresh agent warm-up and five recorded agent repetitions by default. Synthetic decode filler is non-decisive; a final combined validation explicitly restores the full suite. A weighted fresh:continuation latency improvement must exceed the 1% noise floor. A baseline more than 3% from the median of at least five exact-identity windows is inconclusive and must not establish a winner.

Representative speed must improve both agent decode medians by at least 3% (2% for the CUDA-graphs candidate) or fresh-agent prefill by at least 5%; checked metrics must not regress more than 2%, except continuation TTFT uses an absolute increase of at most 250 ms. Continuation elapsed retains the 2% limit. Reprocessing must stay at or below 2,000 tokens; a combined continuation above 500 reopens checkpoint investigation.

Fixed-answer hashes must match for numerically equivalent candidates. For the explicitly approved turbo KV precision change, hashes remain reported but quality is deferred to KLD/top-1 against the same Q8 reference, then 90K retrieval and tool round-trip on the full combination. The applied quality threshold is turbo mean KLD no greater than Q4 and top-1 agreement no lower than Q4. No threshold is silently relaxed to make a candidate pass.

## Data and interface requirements

Durable records include application sessions/messages/inboxes, memory state, model catalog/jobs, worker receipts, controller state/journal and configuration/source identities. Payload access is distinct from metadata inspection. Documentation and diagnostic exports shall contain the minimum metadata necessary for reproducibility.

The native application API, OpenAI-compatible router, private controller RPC and manager API are separate contracts. Native session metadata is not an inference request. The router is not the application login endpoint. Access to the controller socket is not granted to the application or ordinary SDK clients.

## Traceability and release checks

| Requirement family | Implementation reference | Validation reference |
|---|---|---|
| FR-01/02/17 | Pinned native protocol schema and native session handlers | Native schema/handler tests; session/inbox readback |
| FR-04/05/09/NFR-09 | `ansible/roles/watoom-code/files/coordinator-guard/`; project guards | `tools/watoom-code/test-coordinator-guard.mjs`, visual receipt and read/write scope tests |
| FR-07/08/09/NFR-03 | `tools/llm/watoom-gpu-controller/` | Controller tests: identity, leases, lifecycle, recovery and lost acknowledgements |
| FR-12/13 | `tools/model-manager/` | Model selection/download/enrollment/removal tests and real generation acceptance |
| FR-14/16 | `tools/watoom-code/maintenance_guard.py`, `release_guard.py`, `backup.py` | Release guards, backup checks and isolated restore evidence |
| NFR-04 through 08 | `tools/llm/benchmark-engine.py`, `engine_qualification.py`, `combined_qualification.py` | Benchmark/qualification/cache/combined tests and candidate-specific live evidence |
| FR-18 | `docs/guide/llm-*.md`, existing guide renderer | Renderer drift/link checks and served HTML/assets |

A passing unit test is not a live GPU, native delegation, image-quality or restore acceptance. Requirements still needing runtime evidence must be recorded as not tested or blocked. Historical waivers apply only to the exact owner-approved scope; they are not general product behavior.

## Change management

A requirements change records owner intent, affected IDs, compatibility impact, exact acceptance evidence and rollback. Changes to safety gates, authentication, project writes, model precision or ownership policy need explicit review. Documentation authors shall preserve unresolved limits, including incomplete historical cache attribution, CPU vision-projector placement and unqualified experiments. See the [operations guide](llm-operations.md) for release execution.
