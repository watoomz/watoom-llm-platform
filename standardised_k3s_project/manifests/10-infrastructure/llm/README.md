# Local LLM / AI manifests

Verified 13 October 2026: Open WebUI/OpenCode/Pi -> controller-compatible Python llm-router -> selected llama.cpp backend -> GPU 20 GB. Swift is normally ready: `Swift-Qwen3.8-27B-IQ4_XS.gguf`, context 131072, Q4/Q4 KV, Flash Attention, one slot, draft-MTP max 4, 250 W. Other ten GPU backends are normally zero. Ollama is retired.

## Ownership

G3H controller is the sole GPU replica writer. All eleven deployment barriers and admission/RBAC safeguards remain required. Both `llm-router.yml` and `llm-router-gpu-controller.yml` preserve the controller-compatible implementation. Model-lab must not reinstall the legacy router.

Specialised LLM sources remain outside broad `k3s_manifest_groups`. Existing GPU-controller, model-lab, Mesh integration/recovery and OpenCode playbooks own reconciliation; a broad Kubernetes rebuild alone is insufficient. Preserve reviewed activation gates, ownership state and receipts.

## Selection and Mesh

Router/Open WebUI default `active-model` follows the loaded backend. Named transitions go through the controller; there is no direct scaling fallback or global chat queue. Never bypass a live/uncertain owner or use legacy activation commands.

Mesh is registered in the router and OpenCode MCP. Production uses `generate` with a stable `request_id` through the bridge/controller pipeline, restores Qwen, then prepares CPU assets. The normally stopped backend has 8192 context and Q8/Q8 KV. Existing G3H acceptance proves a bounded validated cube and restoration, not general asset quality or Unreal import.

See [AI platform](../../../docs/09_LLM_AI_PLATFORM.md), [Mesh workflow](../../../docs/LLAMA_MESH_WORKFLOW.md), current snapshot and [protected baseline](../../../docs/baselines/pre-new-agent-engine-20261013.md).
