# AI directory layout

Host service state lives under `/app/ai/services`, build contexts and compiler output under `/app/ai/builds`, and everything large (models, projects, assets, caches, application data) under `/data/ai`.

## `/app/ai`

| Path | Holds |
|---|---|
| `/app/ai/services/opencode/home` | Mesh bridge home (`llm_mesh_bridge_home`), including `watoom-tools/watoom-llama-mesh.py` |
| `/app/ai/services/opencode/observability-vector` | WatooM Code observability pipeline state |
| `/app/ai/services/agentmemory` | AgentMemory service files |
| `/app/ai/services/kali/{mcp,workbench}` | Kali Workbench MCP and workbench state |
| `/app/ai/builds/llama.cpp` | llama.cpp source, builds and the sm86 image context |
| `/app/ai/builds/llamampere` | llamampere builds |
| `/app/ai/builds/kali-workbench`, `kali-control-image` | Kali image build contexts |

## `/data/ai`

| Path | Holds |
|---|---|
| `/data/ai/watoom-code` | WatooM Code application state and `config/` (opencode.json, agents, `watoom-tools/` versioned plugins) |
| `/data/ai/watoom-code-rig-jobs` | rig-jobs instance state |
| `/data/ai/projects` | project workspaces, grouped by space (see [project storage](PROJECT_STORAGE.md)) |
| `/data/ai/models` | model weights (`gguf/`), outside Git |
| `/data/ai/assets` | shared asset catalogue, Fab downloads, generated assets |
| `/data/ai/knowledge` | language-knowledge cards, manifests and vectors |
| `/data/ai/llama-mesh` | Mesh job records |
| `/data/ai/model-manager-stage`, `/data/ai/model-lab-state` | Model Manager and model-lab state |
| `/data/ai/writing-studio`, `/data/ai/creation-studio` | studio state |
| `/data/ai/tickets` | tickets board data |
| `/data/ai/helper-scripts` | installed helper scripts and controller state |
| `/data/ai/private`, `/data/ai/secrets` | private material, never in Git |
