# Native WatooM learning

Use `sudo python3 runner.py --evidence <private-existing-run>`; supported modes are `--dry-run`, `--stage-only`, `--i-approve`, `--resume`, `--status`, and `--rollback`. Default builds and validates staging. Approval is a separate human decision. A durable host service should run approved cutover; the independent systemd recovery timer never depends on Codex.

Learning uses native plugin KV, native Skill parsing/tools and the existing AgentMemory import/lookup API. Immutable candidates need three independent verified sessions and a protected evaluator attestation. No raw conversations or command output enter learning. No LLM or GPU is used by the curator.

Existing Skills: `existing_baseline.py` inventories the actual native registry and reads historical native counters without database writes. `corpus_validation.mjs` uses the installed parser on every original and structural candidate. These checks are explicitly structural; they do not establish representative workflow correctness. `manage_existing.py` reviews native state and submits independent baseline/comparison/regression receipts. Its root-only evaluator format is enforced in optimisation.mjs. All original representative cases and regression coverage must pass for both arms, with no safety, correctness or measured-cost regression and at least one measured task benefit. Byte reduction alone cannot pass. Unknown/unmeasured cases remain pending. DSPy/GEPA remains disabled.

Usage/failure/repeated-call fingerprints and independent verification receipts are tracked. Native token/cache/cost counters are shared loaded-session costs, not causal per-Skill costs; overlapping costs must not be summed. Historical zero price does not imply free inference. Corrections require a verifier receipt explicitly referencing recorded failures.

Automatic structural proposals preserve originals and fenced content. New revisions are never written over active files. Existing Skill selections are frozen at plugin startup and additionally require a configuration allowlist of exact revision IDs. Selecting a qualified revision requires a held native gate and zero active sessions; rollout must occur under the existing maintenance/deployment owner. Verified regression queues rollback to the preserved previous revision. Queued selection/rollback is not reported as an activated revision until an idle rollout and endpoint verification complete.

`manage.py --runtime staging|production` reviews and enables/disables/rolls back generated Skills using protected action files. `manage_existing.py` provides existing-Skill review and evaluation submission. No model-facing mutation or permission escalation is added.

Runtime proof, backups, test logs and secrets belong only in the private evidence directory. Read test-results.json and per-test logs for native versus contract test scope.

The guarded host optimisation timer runs only after a verified production release. Protected evaluator-registry.json entries pin reviewed CPU suite code by SHA. evaluate_existing.py runs each registered original/candidate suite as UID 1001 with read-only system paths, private network/devices and a bounded writable output directory. It requires at least three independent records for both arms, complete registered case coverage and correct measured medians. Generic instruction contracts are explicitly marked non-domain and can never qualify for production selection. Missing representative suites remain pending. Native overlay acceptance uses synthetic test data only and proves that the production controller rejects it.

Maintenance distinguishes active work from the inspected synchronous LLaMA-Mesh stdio adapters. Under an owned native admission gate, the controller records idle adapters and disconnects them with the native MCP lifecycle API. Active sessions, bridge sockets, changed adapter code or unknown processes abort the release. Both successful cutover and independent rollback restore recorded connections before releasing external access. A bounded 90-second drain window prevents the recovery controller’s own probes from being mistaken for application work; failed cutover bypasses that window.

The final transport check permits an established IPv4 client stream only after 20 seconds of positively observed native SSE heartbeat frames and the inspected empty `skill.updated` notification, with no client payload or other server payload. Admission leases, durable jobs and child processes must remain empty and the ingress fence must remain closed. Raw traffic is never retained. Unknown or changed connections still abort; no sockets are killed. idle_stream_exercise.py tests this against a real native staging event stream with independent recovery armed.

Native filesystem Skills register asynchronously after plugin setup. Final rollout and optimisation checks wait up to 45 seconds for every original Skill ID, failing closed on missing coverage or authentication errors. readiness_exercise.py verifies this against a fresh native staging location; TCP readiness alone is not accepted as Skill readiness.


Queue health distinguishes expected pending work from runtime faults. Generic
structural suites stay domain-pending; stale revisions are skipped without blocking
other candidates. Changed sources retire queued candidate/evaluated revisions while
preserving artifacts and history. Volatile builtin report diagnostics are not
whitespace-optimisation targets. Workers use journal transport with their existing
UID, memory, network/device isolation; inherited stdout file descriptors are absent.
Artifact publication uses unique temporary files and exclusive hard links, never
shared .tmp renames or overwriting an immutable revision.

capture_planning_suite.py collects real, independent model decisions for dispatcher
identity, 4GiB native routing, source/clothing preservation, verified pose controls,
frame/key/deformation checks, MP4 protocol, unsupported IK and uncertain-job dedup.
Three paired requests per arm use the same model/references, alternating arm order.
Observed total token counts are used once for the whole request bundle; noisy
latency and shared historical session costs are not improvement claims. The protected
offline evaluator judges those records, with exact source hashes and distinct
receipts. This is representative of capture planning only, never pixel/pose quality
or proof that an MP4 was rendered. New source hashes require fresh replay evidence;
the curator never starts GPU inference to fill missing evidence automatically.
Successful no-benefit evaluations are healthy rejections. Production selection still
requires independently verified, representative, materially beneficial results and
the existing idle rollout gates. Synthetic staging selection/rollback exercises
remain ineligible as production performance evidence.
