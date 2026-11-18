# 4 GiB RAM-cache experiment — 20 October 2026

RESULT=FAIL for 4096 MiB; ROLLBACK=PASS to the verified 6144 MiB baseline.

## Verified cause

The pinned llama.cpp build b10666 / 4e97ac86e accounts target state, MTP draft state, and copied target/draft/speculative checkpoints inside the host prompt-cache budget. At 4096 MiB, saving the second real history evicted the required 3574.562 MiB saved state for the first real 66K history. Its next return reused zero tokens and recomputed all 66403 prompt tokens. This is a cache-capacity regression, not evidence of a weight-loading leak or an AgentMemory problem.

Cached GGUF residency is small and large anonymous allocations dominate. Fresh 6 GiB control RSS was 1.748 GiB before cache use (1.249 GiB anonymous). CPU vision remains enabled with its 0.864 GiB projector file; file size alone is not exact resident memory. The checkpoint-size function sums target, draft and speculative state bytes. The exact live split between individual checkpoint buffers and allocator-retained free memory is not exposed by the current logging/API; no speculative allocator or projector tuning was applied.

## Matched engine replay

Identical fresh starts, fixed image/model/seed/prompts/generation limits and unchanged non-cache configuration were used. Both 66K/22K alternating histories and cold/warm multi-session 14K replay passed at 4096 MiB.

| Metric | 6144 MiB | 4096 MiB |
|---|---:|---:|
| Replay process RSS | 7.090 GiB | 4.969 GiB |
| Median generation | 84.66 tok/s | 84.50 tok/s |
| Warm request latency | 1.694 s | 1.666 s |

The roughly 2.12 GiB replay saving is rejected because the real-workflow cache gate fails. It is not the final applied configuration.

## Real OpenCode histories

Transient generation used two retained real histories without adding messages or resuming their jobs. Their actual request lengths were 66403 and 42210 tokens, rather than the smaller 66K/22K synthetic fixture. At 6144 MiB, return switches reused 66399 and 42206 tokens, evaluating four tokens each. At 4096 MiB, the first 66K return switch reused zero and evaluated all 66403 tokens. Return latency changed from a 2.768 s control median to 132.839 s. The trial stopped at this mandatory failure and automatically restored 6144 MiB.

An initial transient probe under the native admission fence returned HTTP 500. It was not treated as a memory result: six GiB was restored, the native API was verified with admission released, and matched real controls were then collected. The maintained runner now includes real-session gates before persistence, with idle checks and no implicit session interruption.

## Recovery validation

PASS: exact 6144 MiB runtime and unchanged authoritative source; 131072 context; vision image test; MTP; readiness/health; GPU configuration; no new fatal model log errors, cgroup OOM, kernel OOM or NVIDIA Xid. The 6 GiB recovery replay again reused 66399 / 42206 tokens and passed the same latency and cache-reuse gates. Final warm process RSS was 7.079 GiB. GPU compute memory: 843488, 19084 MiB.

Both real session-history fingerprints remained unchanged. No OpenCode session was interrupted or resumed by this run. Admission is released and no temporary maintenance guard remains held. Production source is byte-for-byte equal to the saved 6 GiB manifest. No context/vision/MTP/CPU/GPU setting or unrelated workload was changed permanently.

## Applied settings and rollback

Applied: LLAMA_ARG_CACHE_RAM=6144; context=131072; q4_0 K/V; one slot; CPU vision; draft-MTP maximum 4; original image/build and GPU settings.

Rollback baseline/snapshots: `/data/ai/helper-scripts/audits/ram-4g-20261020T061715Z/real-session-trial`. Existing helper rollback remains idempotent and approval gated:

```sh
sudo python3 /data/ai/helper-scripts/fix-watoom-ram.py --action rollback --evidence /data/ai/helper-scripts/audits/ram-4g-20261020T061715Z/real-session-trial --i-approve
```

Existing audit, experiment, rollback and runner scripts were extended in place; no duplicate tooling was created. The runner tests real transient histories as well as synthetic histories before accepting future 4 GiB experiments. Other optimisation candidates were investigated read-only. No installations, network changes or user data deletion occurred. Unrelated dirty repository changes were preserved; nothing was staged or committed.

Evidence: `/data/ai/helper-scripts/audits/ram-4g-20261020T061715Z`. Exact results: final-summary.json; matched controls: baseline.json/candidate.json; real control: control-native-real.json; rejected real trial and verified recovery: real-session-trial/*.json.
