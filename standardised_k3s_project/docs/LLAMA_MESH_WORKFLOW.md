# LLaMA-Mesh to Unreal prototype workflow

This page covers both the offline OBJ workflow and the deployed G3H production MCP pipeline. Installation of these source files does not load models, restart services or submit inference. It reuses the existing router/backend environment and installed Blender. It never installs packages.

## While another job is running

Do not invoke generation or switch the GUI model. The offline commands can validate previously exported output without contacting any model. Wait until your job finishes before real inference. Offline commands have no scheduler; production jobs use the durable host pipeline and controller-mediated recovery.

## Save an existing response (offline)

Run on the homelab host from `/data/github/watoom-standardised-homelab/standardised_k3s_project`:

```bash
scripts/llama-mesh validate /path/to/exported-response.txt
scripts/llama-mesh ingest /path/to/exported-response.txt --name arena-pillar --prepare
```

Input may be plain OBJ, one OBJ Markdown block, or complete non-streaming OpenAI-compatible response JSON. JSON completions must have finish_reason=stop; truncated completions are rejected. Plain text cannot prove generation finished: inspect the source and resulting mesh. OBJ geometry validation checks coordinates, face indices, duplicate and zero-area faces, and reports open/non-manifold edges. It does not prove the object looks correct or detect all self-intersections.

Each successful ingestion creates a fresh run under `/data/ai/assets/generated/llama-mesh/`. Existing runs are never overwritten. Input provenance, warnings and geometry counts are recorded. Raw/plain imports do not claim a verified generating model.

## Prepare an existing run (offline)

```bash
scripts/llama-mesh prepare /data/ai/assets/generated/llama-mesh/YOUR_RUN --size-cm 100
```

The CPU-only Blender process uses one thread, disables visible CUDA devices, has a 180-second timeout, and uses factory settings. It welds extremely close vertices, recalculates normals, triangulates, creates starting UVs and a neutral material. It scales the largest dimension to size_cm and places the pivot at the XY centre and bottom Z. It creates preview.blend, unreal.fbx, blender-report.json and blender.log. It does not generate textures, collision geometry, rigs, animation or .uasset files. Prepared outputs are not overwritten; ingest into a fresh run to retry or choose another size. Preserve logs for failures.

## Production generation after G3H

Use the connected OpenCode watoom-llama-mesh MCP namespace and its synchronous
generate tool. Supply one stable request_id; retry an uncertain request with
the same ID. The host bridge and exclusive GPU controller perform model
switching, memory-release barriers, durable recovery and Qwen restoration.

Do not use the legacy GUI/model-manager activation path or direct-backend
scripts/llama-mesh generate on a controller-managed host. These legacy commands
now refuse before mutation. Offline validate, ingest and prepare remain
available, and the production pipeline reuses this parser.

The verified 12 October G3H acceptance is recorded in
tools/llm/watoom-gpu-controller/README.md. Its synchronous generation returned
a validated cube and restored Qwen. That evidence supersedes this workflow's
earlier generation limitations; it does not establish general asset quality.

## Import into Unreal

Open the Content Browser, choose Import and select unreal.fbx. Import as a Static Mesh with uniform scale 1. Enable Generate Missing Collision if appropriate for this prototype, then inspect the mesh in Static Mesh Editor. Check centimetre scale, orientation, pivot, material, UVs, normals and collision before placing it in a level. Unreal performs the .uasset conversion during import. For weapons or characters, attaching the prop or creating skeleton/rig/animations requires separate work.

## Validation and limits

VERIFIED: offline parser tests and a synthetic cube exported through installed Blender. FBX re-import into a clean Blender scene confirms a 100 cm cube measures 1 metre. No model inference was used by these tests. Workflow-created test assets are under the same canonical asset root and clearly marked synthetic_test in manifest.json. Test fixtures, logs and validation reports remain in the workflow artifact directory.

UNVERIFIED: general model generation quality, output completion rates and import into your Unreal project. Those require an idle test window. The installed Blender reports a colour-management configuration warning but successfully completes the geometry export/re-import; no system Blender configuration was changed.

## Current production ownership and recovery

Verified 13 October 2026. Maintained bridge/adapter/pipeline source is under `ansible/roles/llm-model-lab/files`; runtime helpers are under `/data/ai/helper-scripts`. GPU-controller source and tests are `tools/llm/watoom-gpu-controller`.

Weights: `/data/ai/models/gguf/llama-mesh/LLaMA-Mesh-Q8_0.gguf`. Production job records: `/data/ai/llama-mesh/jobs`. Production generated assets: `/data/ai/assets/generated/opencode-mesh`; preserve `raw/`, `cleaned/` and `game-ready/` stages. Offline ingestion retains its separate `generated/llama-mesh` root.

Services: `watoom-gpu-controller.service` and `watoom-opencode-mesh-bridge.service` are active. `watoom-gpu-controller-credentials.timer` rotates credentials. `watoom-llama-mesh-recovery.service` is a successful oneshot and is normally inactive after completion.

Do not reset ownership, replay storage cutover, delete durable state/receipts, force replicas, or invoke historical competing writers. Preserve `/data/ai/helper-scripts/state/qwen-runtime-baseline.json` and current controller state/journals. Read controller/worker state first; follow [baseline recovery](baselines/pre-new-agent-engine-20261013.md).

The accepted G3H cube proves the bounded production path, not general character quality, rigging, textures or Unreal import. Validate each generated asset structurally and visually before game integration.
