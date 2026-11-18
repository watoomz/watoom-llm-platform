---
title: Technical Specification
nav: LLM specification
summary: Deployment, configuration, storage, interface and resource contracts for implementing and maintaining the complete LLM platform.
---

## Baseline and status

Verified 3 November 2026. This specification combines maintained source contracts and inspected live deployment facts. Runtime versions and fingerprints are changeable; owning IaC and live acceptance remain authoritative. It supplements the [design](llm-design.md) and [requirements](llm-requirements.md).

Production uses the owner-approved combined llamAmpere profile. Old b10666/Q4 baselines and retained canaries are historical references. Application, AgentMemory and Toolkit have separate immutable source/image pins. A different source revision is not a substitute for the production API contract.

## Deployment inventory

| Component | Namespace / host owner | Interface | Source or state |
|---|---|---|---|
| WatooM Code | `watoom-code/watoom-code` | HTTP 4096 behind HTTPS | Application root and `ansible/roles/watoom-code` |
| AgentMemory | `watoom-code/agentmemory` | MCP/service 3111 | Persistent memory, production vars/role |
| Toolkit | `watoom-code/watoom-toolkit` | HTTP 8879, `/healthz` | `tools/watoom-toolkit/agent.py` |
| Primary llama-server | `llama-cpp/llama-cpp-swift-qwen38-coder` | HTTP 8000 | Primary inference manifest |
| Python router | `llama-cpp/llm-router` | HTTP 8000, `/v1`, `/models` | Controller-aware router source/ConfigMap |
| BGE embeddings | `llama-cpp/bge-embeddings` | Service 8000 | Independent embedding deployment |
| GPU controller | `watoom-gpu-controller.service` | UNIX router/private sockets | Installed controller source/config/state |
| Model Manager | `glance/model-manager` | `/model-manager/` | Catalog and narrow host broker |
| Glance guide | `glance/glance` helper | `/guide/` | Rendered documentation HostPath |
| RIG/host workers | Dedicated stage namespace/systemd | Admitted job contracts | Inputs, queues, receipts/outbox |

The `stage` namespace name is retained although the accepted WatooM Code deployment there is the active user application. Zero-replica candidates are not active services. Inspect controller registration/readiness before selecting a model.

Browser entry points: `https://watoom-code.internal.homelab.example` and `https://glance.internal.homelab.example`. In-cluster inference base: `http://llm-router.llama-cpp.svc.cluster.local:8000/v1`. Workstations need an approved internal route/forwarding arrangement; cluster DNS is not assumed to resolve outside the cluster.

## Primary inference profile

| Field | Current value |
|---|---|
| Engine | llamAmpere v0.6.2, source `e9193f81423a613e19336834c0bb76dd94dd3191` |
| Image | `127.0.0.1:5000/watoom-llamampere@sha256:7c3043826d435ce79afe68c0f7a60acd91007935f7ecba57b1316e6fbf14df83` |
| Weight file | `Swift-1.5-Qwen3.8-27B-Uncensored-Dynamic-MTP-UD-IQ4_XS.gguf` |
| GGUF SHA-256 | `9341ee462261bde1dc357ca995704b6a6541852c74c11e89ec490418cdc0051b` |
| Vision | BF16 projector; CPU offload retained |
| Backend capacity | 131,072 context tokens |
| App budget | 100,000 context; 4,096 output tokens |
| Placement | All main-model layers on GPU; `--n-cpu-ffn 0` |
| KV | `turbo5` K / `turbo4` V; Flash Attention on |
| Slot/batching | One slot; continuous batching; batch 2048; ubatch 1024 |
| Speculation | `--spec-type draft-mtp --spec-draft-n-max 5` |
| Threads/checkpoints | 8 threads; checkpoint defaults 32 / minimum step 8192 |
| Prompt RAM cache | 4096 MiB |
| Sampling | Temp 1.0, top-p 0.95, top-k 20, min-p 0, repeat penalty 1.0 |
| Reasoning/graphs | Reasoning on, effort low; CUDA graphs enabled |
| Power | `gpu_host_power_limit_watts=300` in owning host role |

App budget and backend capacity are separate. Quantization, KV precision, projector, sampling, reasoning and speculation must not be silently substituted for comparisons. Request parameters can override defaults; a manifest does not prove every request uses identical sampling.

The sm86 build recipe is `tools/llm/llamampere-sm86.Containerfile`. It builds server and perplexity with linked backends. Dynamic backend loading was not a qualified runtime path for this image. A rebuild requires pinned source/base images, actual CUDA-device verification and an isolated engine test, not only compiler success.

## Hardware and resources

Inspected host: Fedora, existing single-node k3s/container environment, Ryzen 5 5500 (6 cores/12 threads), about 31 GiB RAM, GPU with about 20 GiB VRAM, sm86. This supersedes older hardware descriptions where inconsistent. Driver/kernel/clocks/free RAM must be rechecked operationally.

Primary requests are 500m CPU/5 GiB RAM; limits are 8 CPU/20 GiB RAM/one NVIDIA GPU. Requests are reservations, not measurements. BGE has its own resources and service; CPU requests or `-ngl` flags alone do not prove actual accelerator placement. Measure live device/process usage before budgeting shared capacity.

Qualification peak was 80°C against an 83°C limit; full 100K-plus-image minimum free VRAM was 1811 MiB. Those observations apply to the measured combination. Displays or other GPU processes can change headroom. The configured cap is 300 W; instantaneous power telemetry can briefly read slightly above a nominal cap.

## Configuration ownership and precedence

| Configuration | Owner | Rule |
|---|---|---|
| App/Toolkit/memory pins | `ansible/vars/watoom-code.yml` | Explicit pins required by role |
| App projects/skills/defaults | `ansible/roles/watoom-code/` | Production vars override defaults; narrow preserved-state updates |
| Primary launch env/args | Primary Kubernetes manifest | Inspect both explicit args and environment |
| Model identities/catalog | Controller source JSON and enrollment | UID/spec identity must match live deployment |
| GPU cap | `ansible/roles/gpu_host/` | Persistent reconciliation; audit unmanaged drop-ins |
| Manager setting proposal | Override, applicable recommendation, safe baseline | Exact inspected revision/variant; lower supported context enforced |
| Secrets/private skills | Vault/server-local private files | Never ordinary configuration or documentation exports |

Fresh initialization differs from upgrade. The app role seeds missing configuration while preserving user state; do not replace the whole config directory to refresh one setting. Production vars enable hybrid memory recall even where a role default is false. Generated API security arrays may omit deployed middleware; actual authentication still applies.

## Storage layout

| Path | Contract |
|---|---|
| `/data/ai/projects/<group>/<project>` | Approved writable project roots at matching container paths |
| `/data/ai/projects/images` | Image/review projects and generated output |
| `/data/ai/assets` | Shared inputs; reviewed read-only purchased/engine mounts |
| `/data/ai/models` | Model/projector/pipeline files, excluded from Git |
| `/data/ai/toolchains` | Qualified engine/runtime installs |
| `/data/ai/watoom-code/application.sqlite` | Persistent native database; privileged operator access |
| `/data/ai/watoom-code/config` | Persistent config/skills/plugins |
| `/data/ai/helper-scripts/state/gpu-controller` | Owner, leases, journal and recovery evidence |
| `/data/ai/helper-scripts/reports` | Qualification/release evidence |
| `/data/backups/watoom-code` | Verified rolling backup sets |
| `/data/github/watoom-standardised-homelab` | Canonical operator checkout and live guide source |

Mounts/guards are boundaries, not proof of complete isolation. Artifact roots have workflow-specific contracts. Restore targets must be verified before replacing data. User state and large models are not kept solely in application image layers.

## Interface contracts

Native app routes use `/api/*` and typed wrappers; they are neither old unprefixed session routes nor the router's inference API. The router provides discovery/status/load and an OpenAI-compatible forwarding surface. Compatibility naming does not manufacture unsupported backend features.

Controller clients use newline-delimited JSON over UNIX sockets; client frame limits are 65536 bytes. Actions carry job/generation/deployment/lease fields as defined by the production handler. Responses use `result` or `error`/`detail`. Production action/peer checks differ from the offline simulator.

Model Manager uses authenticated HTTP with same-origin and CSRF checks for mutation. Toolkit uses its own bearer-authenticated job interface. MCP tools are discovered from actual installed schemas; a skill name is not a universal SDK method. See [API documentation](llm-api.md).

## Qualification and compatibility

The adopted combination passed representative full-suite speed, Q8-reference KLD/top-1, 90K retrieval on the combined turbo profile, tool round-trip, 100K image headroom, a 30-minute mixed soak and post-adoption router checks. Fixed-answer hashes differ with KV precision and remain recorded; the owner exception is specific to that profile.

Measured fresh/continuation latency improved about 16%/20%, weighted 19.1%; agent decode about 40%/30%. Filler decode is not an agent-workload claim. Larger cache/thread/checkpoint alternatives did not establish adoption benefit. CPU vision placement remains intentional; future offload is a separate candidate.

Compatibility acceptance covers streaming fragments/tool IDs/arguments, reasoning, prefix reuse, context overflow, images, unavailable-controller behavior and native reconnect. An immutable digest establishes identity, not correctness by itself.

## Security and release invariants

The application must not acquire Kubernetes/controller credentials through examples or deployment drift. Brokers/controllers own their narrow mutation authority. Model metadata is parsed, not executed. Worker mounts, tokens, capabilities and resources stay at reviewed values.

A spec change requires identity reconciliation in a quiet fenced transaction. ConfigMap `subPath` mounts can need a controlled rollout; Glance guide HostPath updates do not. Documentation publishing does not authorize an inference/application rollout or a network, firewall, DNS or VLAN change.
