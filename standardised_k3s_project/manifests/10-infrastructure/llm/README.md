# Local LLM / AI manifests

WatooM Code -> `llm-router` (Python, controller-compatible) -> the llama.cpp backend the GPU controller has loaded -> GPU 20 GB. Exactly one backend runs at a time; the rest are 0/0. `bge-embeddings` runs alongside on CPU.

## Ownership

The GPU controller is the only writer of backend replicas; its deployment barriers and admission/RBAC safeguards stay in place. `llm-router.yml` and `llm-router-gpu-controller.yml` are the controller-compatible router. These manifests are applied by the GPU controller, model-lab, Mesh and WatooM Code playbooks, not by the broad `k3s_manifest_groups` registry, so a plain Kubernetes rebuild does not restore them.

## Selection and Mesh

The router model `active-model` follows the loaded backend. Named switches go through the controller (`POST /models/load`); never scale a backend directly or bypass a live or uncertain owner.

Mesh is registered in the router and as a WatooM Code MCP. `generate` with a stable `request_id` runs through the bridge and controller, restores the previous model, then prepares CPU assets. The Mesh backend has 8192 context and Q8/Q8 KV and is normally stopped.

See [AI platform](../../../docs/09_LLM_AI_PLATFORM.md) and [Mesh workflow](../../../docs/LLAMA_MESH_WORKFLOW.md).
