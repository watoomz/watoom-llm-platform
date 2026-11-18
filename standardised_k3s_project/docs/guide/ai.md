---
title: AI inference platform
nav: AI platform
summary: Local LLM serving on one GPU — the router, the exclusive GPU controller, the managed model set, the Model Manager and the rules that keep inference safe.
---

## Architecture

```text
WatooM Code ─┐
Model Manager ┼──► llm-router.llama-cpp:8000/v1  (OpenAI-compatible)
Toolkit jobs ─┘        │  model request
                       ▼
          watoom-gpu-controller  (systemd, sole replica writer)
            · admission and inference leases
            · durable state + journal (generation, owner, phase)
            · deployment identity pinned by spec SHA-256
                       │  scale 0 ↔ 1, verified restore
                       ▼
          llama-cpp/<model> Deployments ──► GPU (20 GiB)
```

Only one large model fits in VRAM at a time. The router never scales anything: it asks the controller, which drains the current owner, switches the backend and records each step durably so an interrupted switch can be recovered rather than guessed.

## Primary model

| Setting | Value |
|---|---|
| Deployment / alias | `llama-cpp-swift-qwen38-coder` / `swift-qwen38-coder` (WatooM Code: `watoom/swift-qwen38-coder`) |
| Weights | `Swift-1.5-Qwen3.8-27B-Uncensored-Dynamic-MTP-UD-IQ4_XS.gguf` + `mmproj-BF16.gguf` (vision) |
| Runtime | llamAmpere v0.6.2 (sm86 fork of llama.cpp), local registry image pinned by digest; adopted 2026-11-02 (decode +15–38 %, prefill +18–20 % vs upstream b10666) |
| Context | 131,072 tokens, KV cache `turbo5`/`turbo4` (adopted 2026-11-03; KLD 0.003983 vs `q4_0` 0.007172 against a `q8_0` reference), flash attention on, `UBATCH=1024` |
| Placement | all layers on GPU; vision projector on CPU (`MMPROJ_OFFLOAD=false`) |
| Slots | 1 (`N_PARALLEL=1`), continuous batching |
| Speculative decoding | built-in MTP head (`--spec-type draft-mtp`, up to 5 draft tokens) |
| Prompt cache | 4 GiB host RAM (`CACHE_RAM=4096`); two measured synthetic 60K states fit; real prefix/checkpoint behavior still needs workload-specific evidence; RAM-evicted states spill to a 16 GiB disk tier on the `/app` SSD at `/app/ai/cache/llamampere/prompt-cache` (root-only, survives pod restarts; not the shared `/data` HDD, where each spill blocked the server for 17-65 s); spills are written by a background thread (`LLAMA_ARG_CACHE_DISK_ASYNC=1`, watoom llamAmpere build `943cbe3`, see `config/llm/llamampere/`), so the server never waits for disk I/O; `prompt_cache_disk_async_*` metrics count writes and drops |
| Sampling | temp 1.0, top-p 0.95, top-k 20; reasoning on, effort low |
| CUDA graphs | enabled (default) |
| GPU power cap | 300 W (`gpu_host_power_limit_watts`, `gpu_host` role) |
| Profile adopted | 2026-11-03 combined trial vs previous profile: fresh agent turn −16 %, continuation −20 %, decode +30–40 %, prefill +12–19 %, 90K retrieval/tool round-trip/30-min soak pass. Evidence `/data/ai/helper-scripts/reports/inference-perf-20261102-tune-combined-turbo-01`, rollback manifest in `.../inference-perf-20261103-adopt-combined-01/manifest-before.yml` |

WatooM Code budgets **100,000** tokens of context and **4,096** output tokens per request (`watoom_code_swift_context_tokens`). The difference from the backend's 131,072 is headroom, not waste.

## Managed models

All models are registered in `/data/ai/helper-scripts/config/gpu-controller.json`. Non-primary models sit at `0/0` until requested.

| Deployment | Router alias | Role |
|---|---|---|
| `llama-cpp-swift-qwen38-coder` | `swift-qwen38-coder` | Primary coding and agent model |
| `llama-cpp-tiel-coder-35b-a3b-mtp` | `tiel-coder-35b-a3b-mtp` | MoE coder; keeps an 8-layer CPU expert fallback at 128K |
| `llama-cpp-qwen38-uncensored-mtp` | `qwen38-uncensored-mtp-iq4-xs` | Vision-capable alternative |
| `llama-cpp-qwen38-atomic` | `qwen38-27b-ad-iq4-xs` | Alternative 27B build |
| `llama-cpp-qwen35-defiant-fable-9b` | `qwen35-defiant-fable-9b-q8` | Creative writing |
| `llama-cpp-ornith-15-9b` | `ornith-1.5-9b-q8` | Small general model |
| `llama-cpp-gemma-4-e4b` | `gemma-4-e4b-q8-k-p` | Small general model |
| `llama-cpp-llama-mesh` | `llama-mesh-q8` | LLaMA-Mesh 3D geometry specialist |

`bge-embeddings` runs independently (always on, small) for retrieval. Deployments named `*-candidate` or `llama-cpp-mm-*` are experiments or Model Manager installs and are not in rotation unless registered.

## Placement policy

Prefer full GPU residency for weights, MTP head and vision projector when the model, KV cache, compute buffers and a safety margin all fit. CPU expert offload is a documented capacity fallback, never a default. Never change quantisation, context or KV precision to claim residency. Validate any placement change through the controller with rollback before touching a running model.

## GPU controller

| Item | Location |
|---|---|
| Service | `watoom-gpu-controller.service` |
| Code | `tools/llm/watoom-gpu-controller` → `/data/ai/helper-scripts/gpu-controller` |
| Config | `/data/ai/helper-scripts/config/gpu-controller.json` |
| State | `/data/ai/helper-scripts/state/gpu-controller/state.json` + journal |
| Credentials | rotated by `watoom-gpu-controller-credentials.timer` |

Healthy idle state:

```json
{"phase": "qwen-ready", "owner": null, "uncertain": false}
```

The generation counter only increases; never hard-code it. A non-null owner means a model switch, Mesh job or operator task is in progress — let it finish.

> [!RULE]
> Never `kubectl scale` a model Deployment, reset controller state or bypass admission, even while debugging. Low GPU utilisation does not mean idle; an active coding session or busy inference slot blocks disruptive work.

### Re-pin after a reviewed primary Deployment change

The controller pins each model Deployment's UID and spec digest. If the primary (`swift-qwen38-coder`) Deployment is changed outside the controller, every action — including `recover` — fails with `Unsafe: deployment identity or model configuration changed`. After reviewing the diff, re-pin through the playbook (opt-in; it refuses unless the controller is `qwen-ready`, unowned and certain, the UID matches, and only the primary digest changes):

```bash
ansible-playbook ansible/playbooks/gpu-controller.yml -e gpu_controller_repin_primary=true
```

Then copy the new digest into `ansible/roles/llm-model-lab/files/gpu-controller.json` so a plain rerun does not revert it. A stuck `recovery-required` state whose owner is a live router process also needs that router restarted before `recover` is accepted.

Tools that need the GPU exclusively (for example `tools/llm/benchmark-cuda-graphs.py`) use the controller's operator protocol: wait for an idle app and idle slots, take ownership with a new generation, do the work, and always restore the primary through the controller.

## Router

`llm-router` (namespace `llama-cpp`, port 8000) exposes the OpenAI-compatible API. Read-only inspection:

```bash
kubectl -n llama-cpp port-forward svc/llm-router 18000:8000 &
curl -s localhost:18000/health
curl -s localhost:18000/v1/models | jq '.data[].id'
curl -s localhost:18000/models/status | jq
```

`POST /models/load` requests a model switch; it is not a discovery call.

## Model Manager

Glance → LLM Lab → Model Manager (`/model-manager/`). It installs models from Hugging Face by immutable revision:

1. Paste a Hugging Face URL, choose revision and variant, review exact download size and settings sources.
2. **Download & set up** fetches, verifies and registers the model with the controller.
3. GGUF language models default to 100,000 context, 4,096 output and `q4_0` KV unless the model documents a lower limit.
4. SDXL checkpoints and LoRAs are image backends; a LoRA needs an explicitly chosen compatible base.

Downloaded, configured, registered and tested are separate states. Removal unregisters and keeps files by default; confirmed removal quarantines only unshared files. The privileged half runs as `watoom-model-manager-broker.service`. The login password file is server-local and excluded from Git.

## LLaMA-Mesh

LLaMA-Mesh generates OBJ geometry from text. WatooM Code reaches it through its MCP pipeline: the controller lends the GPU to `llama-cpp-llama-mesh`, the job runs with a stable request ID, the primary is restored, then CPU-side asset preparation continues. Job records are kept under `/data/ai/llama-mesh/jobs`.

## Data

| Path | Contents |
|---|---|
| `/data/ai/models` | GGUF weights and projectors (excluded from Git) |
| `/data/ai/helper-scripts/reports` | Benchmarks and operator evidence |
| `/app/ai/builds/llama.cpp` | Local llama.cpp source and build output |


## Complete platform reference

See the [LLM API & reference](llm-api.md) for the current contracts, platform source map, operations and schemas, and the [LLM user guide](llm-user-guide.md) for day-to-day workflows. The qualified combined profile is described above.
