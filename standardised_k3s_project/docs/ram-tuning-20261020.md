# Verified RAM tuning — 20 October 2026

RESULT=PASS
ROOT_CAUSE=VERIFIED host prompt-state retention. Exact-build source serializes both target and MTP state and copies checkpoints into a default 8192 MiB RAM cache. CPU vision adds normal allocations. AgentMemory is separate and was stable at 592–634 MiB in production (staging 88–105 MiB). A leak is not demonstrated; precise ownership of every anonymous allocation remains unverified.

## Applied change

Only production inference setting changed: `LLAMA_ARG_CACHE_RAM=6144` (previously implicit 8192 MiB). Persisted as two added lines in `manifests/10-infrastructure/llm/llama-cpp-swift-qwen38.yml`. Immutable image, model, 131072 context, q4_0 K/V, CPU vision projector, MTP draft maximum 4, CPU/GPU placement and power settings remain unchanged.

The user explicitly authorised pausing work. One remaining active native session was interrupted with the supported API using resume=false, after a live SQLite backup. Execution settled to zero leases; native admission was atomically fenced during testing. Earlier second session had already finished. Admission is now released; the interrupted job remains paused, with its durable transcript/work intact. No data was deleted.

## Matched before/after replay

- Process RSS: 8.277 -> 6.883 GiB (1.394 GiB lower).
- Host available RAM: 6.111 -> 7.718 GiB.
- Median generation: 84.55 -> 84.87 tokens/s (+0.37%).
- Median cold prefill: 1011.64 -> 1013.98 tokens/s.
- Median warm request latency: 1.663 -> 1.681 seconds (+1.09%, within the acceptance gate).
- Warm 14K histories reused 13,996 tokens and evaluated four tokens for every measured candidate request.

Same image, deterministic prompts/seeds, generation limit and benchmark sequence were used. Six independent 14K histories filled cache; a three-session working set was settled and measured repeatedly. Restart necessarily clears historical cache/allocator state, so the entire RSS delta must not be attributed solely to the smaller cap. The explicit cap bounds future retained history.

A separate representative 66K/22K alternating test passed: 65,996/21,996 cached tokens reused, four prompt tokens evaluated, approximately 1.80/2.13 seconds per reused request. After that test RSS was 7.37 GiB and host available RAM 6.52 GiB.

## Validation and limits

PASS: readiness, health, YAML parsing, exact unchanged non-cache configuration, vision image test (blue), MTP acceptance, 128K configured context, generation/prefill/latency/cache-reuse gates, zero model cgroup OOM, no new fatal model errors, no kernel OOM or NVIDIA Xid during the maintenance window. Model GPU memory approximately 19,080 MiB versus earlier 19,084 MiB; no GPU setting changed. All acceptance details and bounded logs are retained.

Remaining risks: workloads with more/larger concurrent histories can have more cache misses than with an 8 GiB cache. The 128K capacity is preserved; this test did not prefill a full 128K prompt. Cold host swap remains in zram; no swap settings or cache-flush tricks were used. Long-term leak exclusion is not established by this bounded test. Both pre/post measurement and representative long-history reuse passed; this is not a universal performance guarantee.

## Scripts and rollback

- Read-only audit: `/data/ai/helper-scripts/audit-watoom-ram.py`; default audit runner: `/data/ai/helper-scripts/run-watoom-ram.py`.
- Approved experiment and narrow rollback: `/data/ai/helper-scripts/experiment-watoom-ram.py`; dispatcher: `/data/ai/helper-scripts/fix-watoom-ram.py`.
- Audit now recognises the accepted cache-only override while still checking the stable baseline for every other setting.

Rollback while jobs are idle:

```sh
sudo python3 /data/ai/helper-scripts/fix-watoom-ram.py --action rollback --evidence /data/ai/helper-scripts/audits/ram-tune-20261020T041024Z --i-approve
```

Rollback atomically acquires idle native admission, restores the original cache env setting and removes only the two owned IaC lines, validates the original invariants, and releases its admission fence. It refuses to interrupt new active jobs implicitly. Deployment, manifest, application database and prior helper snapshots are retained in the evidence directory. No rollback was necessary.

Evidence: `/data/ai/helper-scripts/audits/ram-tune-20261020T041024Z`.
Unrelated dirty `tools/watoom-code/dungeon-candidate.py` was preserved; nothing was staged or committed.
