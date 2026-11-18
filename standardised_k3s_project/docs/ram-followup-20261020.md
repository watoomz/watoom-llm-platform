# Follow-up RAM diagnosis — 20 October 2026

VERIFIED: AgentMemory is not the main source. Six-hour production RSS 591.5–634.4 MiB; staging 87.9–105.1 MiB. Llama RSS 7442.7–12995.4 MiB over the same period.

Exact live build source (4e97ac86e) establishes that server_slot::prompt_save serializes target and MTP draft state into host std::vector buffers. server_prompt_cache::alloc additionally clones prompt checkpoints. Its 8192 MiB cap accounts for cached checkpoint copies, but current-slot checkpoint state remains outside that cache. Cache entries are bounded and evicted, not an unbounded append-only history. Source retained beside this report. This verifies the mechanism, not the precise number of live bytes owned by each object or absence of a leak.

Current smaps: {"anonymous_large_allocations_mib": 9850.7, "heap_rss_mib": 1015.3, "gguf_rss_mib": 113.3, "anonymous_total_mib": 11340.0}. Large anonymous mappings account for most resident memory; mapped GGUF residency is small. CPU vision projector remains enabled and CPU-resident. Do not infer host model weight residency from the GGUF file size.

Live native OpenCode had two running sessions and three execution leases. Legacy Kubernetes OpenCode and host-local OpenCode were idle, but neither supports the current atomic deployment guard. Scaling the legacy workload alone cannot safely create an inference maintenance window while native sessions run.

No workload/configuration/GPU changes were made. A 6144 MiB cache cap is recorded as a single-variable candidate, not a validated fix. It may reduce cross-session reuse; applying it without a representative replay would violate the requested performance constraint. Active work is the current blocker, not missing user authorisation. Existing audit runner health PASS must not be interpreted as controlled performance validation PASS.

Validation: read-only diagnosis PASS; runtime modification and controlled performance comparison BLOCKED. Rollback not needed. Existing snapshots: /data/ai/helper-scripts/audits/ram-20261020T035601.619178Z. Remaining risks: historical low host headroom, KV-position warnings, unverified exact allocator/checkpoint/cache byte split, slow leak not excluded.

Evidence: /data/ai/helper-scripts/audits/ram-deep-20261020T040131Z. Candidate and acceptance/rollback conditions: cache-experiment-plan.json.
