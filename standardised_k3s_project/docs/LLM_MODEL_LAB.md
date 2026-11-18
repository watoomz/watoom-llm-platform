# Local LLM model lab

Verified deployment inventory: 13 October 2026.

Model metadata is `config/llm/model-lab/models.json`; model weights remain under `/data/ai/models/gguf` and outside Git. The deployed default is `active-model`, following the loaded Swift backend. Candidate metadata does not establish live qualification or registration. Use existing `scripts/llm-models` commands after inspecting their help; activation/deployment is a mutation. On the controller-managed host, legacy activation commands refuse; use the existing controller-compatible paths and never bypass a live or uncertain owner. Pi uses `llm-router-local`, with typed policy/MCP/LOTCE execution separate from model selection.

See [AI platform](09_LLM_AI_PLATFORM.md), live inventory and [storage layout](AI_DIRECTORY_LAYOUT.md).
