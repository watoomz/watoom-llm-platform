# AI application directory layout

Current inventory and production recovery point: 13 October 2026. Historical procedures retain their qualification dates.

Service state lives under `/app/ai/services`; build contexts and compiler output live under `/app/ai/builds`. Model weights, project workspaces, generated assets and large caches remain under `/data/ai`.

| Previous path | Current path |
|---|---|
| `/app/opencode-agent-v2-canary` | `/app/ai/services/opencode` |
| `/app/open-webui` | `/app/ai/services/open-webui` |
| `/app/watoom-kali-mcp` | `/app/ai/services/kali/mcp` |
| `/app/watoom-kali-workbench` | `/app/ai/services/kali/workbench` |
| `/app/watoom-kali-console` | `/app/ai/services/kali/console` |
| `/app/watoom-kali-agent-gateway` | `/app/ai/services/kali/agent-gateway` |
| `/app/llama.cpp-src` | `/app/ai/builds/llama.cpp/source` |
| `/app/llama.cpp-builds` | `/app/ai/builds/llama.cpp/builds` |
| `/app/llama.cpp-image-sm86` | `/app/ai/builds/llama.cpp/image-sm86` |
| `/app/llamampere-builds` | `/app/ai/builds/llamampere` |
| `/app/pi-kali-agent-build` | `/app/ai/builds/pi-kali-agent` |
| `/app/watoom-kali-control-image` | `/app/ai/builds/kali-control-image` |

OpenCode V2 remains the production baseline. Kubernetes resource names and service endpoints are unchanged. There are no compatibility symlinks at old paths. Build-selection links internal to build directories are preserved.

Ollama is retired. Open WebUI chat uses llm-router; document embeddings use the local sentence-transformer. Historical Ollama manifest: `config/retired/ollama/ollama.yml`; model data is retained under `/data/ai/artifacts/ai-app-migration-20261004-190417/originals/ollama`.

Open WebUI retains the same named PVC, bound to `open-webui-data-ai-pv`; its host path is `/app/ai/services/open-webui/data`. The retired PV used Retain policy.

Recovery snapshots and rollback notes: `/data/ai/artifacts/ai-app-migration-20261004-190417`.
