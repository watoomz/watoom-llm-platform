# LLM / AI Platform

WatooM Code is the production coding and creative application. Exact application, Toolkit and Unreal pins: [Unreal and dungeon operations](WATOOM_UNREAL_DUNGEON.md).

## Complete documentation set

The [LLM platform documentation](guide/llm-api.md) contains the Software Requirements Specification, Software Design Document, Technical Specification, System Documentation, API/SDK reference and user documentation. It is also searchable in Glance.

## Production architecture

~~~text
WatooM Code
  -> OpenAI-compatible llm-router
  -> controller-admitted managed llama.cpp backend
  -> GPU

WatooM Code web search -> existing SearXNG
Native specialist jobs -> existing Toolkit / GPU ownership protocol
~~~

WatooM Code is the GUI at https://watoom-code.internal.homelab.example. Glance is the dashboard and documentation entry point.

## Stable Swift application baseline

| Setting | Production baseline |
|---|---|
| WatooM Code Swift context | **100,000 tokens (100K)** |
| WatooM Code output limit | **4,096 tokens** |
| IaC default | watoom_code_swift_context_tokens: 100000 |
| Swift backend context capacity | 131,072 tokens; separate from the application budget |
| Matching backend KV key/value profile | turbo5 / turbo4, owner-qualified combined profile |
| Default model | watoom/swift-qwen38-coder |
| Router API (in cluster) | http://llm-router.llama-cpp.svc.cluster.local:8000/v1 |
| Router API (internal network, from 2026-11-18) | https://llm-router.internal.homelab.example/v1 (also plain http); model id `active-model` follows whatever the GPU controller has loaded |

The application configuration was verified through its authenticated API. The normal watoom-code role uses the same context variable in both the fresh configuration template and the idempotent preserved-state updater. Regression checks protect the 100K default, preserve the output limit and unrelated models, and reject values beyond the supported backend capacity.

A backend's larger advertised or configured context does not change the application's stable budget.

The external route (T-0054) is two Traefik IngressRoutes in `manifests/10-infrastructure/llm/llm-router.yml` plus a per-host Pi-hole `dns.hosts` record (live Pi-hole config, not in the repo). It is open like the other internal services: the router has no authentication of its own, and a caller naming another model can trigger a switch. An IP allowlist is not possible on this cluster because Traefik sees every client as 10.242.0.1 (k3s svclb); `externalTrafficPolicy: Local` did not change that (tested and rolled back 2026-11-17). Use token auth in front of the route if that risk matters.

## Model lifecycle and GPU ownership

The existing GPU controller is the sole GPU replica writer. Preserve exclusive ownership, deployment identity checks, durable generations, pending-intent fencing and verified restoration. Never directly scale model deployments or infer idle from low GPU utilization. An active coding job, real inference slot or uncertain owner blocks disruptive work.

Use router metadata endpoints /health, /models/status and /v1/models for read-only inspection through the existing authenticated/authorized path. POST /models/load requests a model switch and is not discovery. Inactive managed models are not automatically retired, configured successfully, or generation-tested.

Existing accepted geometry and game pipelines remain available. LLaMA-Mesh is a specialist, not the coding coordinator. The Unreal → GLTFExporter → GLB → Godot path remains accepted; GLB does not transfer Blueprint gameplay logic. See [pipeline operations](WATOOM_UNREAL_DUNGEON.md) for exact acceptance scope.

## Agents, skills and search

There are 17 agents. `watoom-workflow` is the coordinator: it routes each package to one of 15 child roles (investigator, researcher, game-designer, systems-designer, critic, developer, builder, 3d-modeller, automation-expert, integration-expert, qa-tester, adversarial-tester, blind-tester, reviewer, watoom-kali), applies verification tiers T0-T3 and runs the reviewer for T2/T3, user-facing and milestone work. `watoom-creative-writer` is a separate primary agent for writing. Children may consult the critic once per package and otherwise return to the coordinator; the coordinator guard enforces budgets, critic escalation and pixel-review receipts.

Every agent prompt is generated from `ansible/roles/watoom-code/files/native/_src` (eight shared modules plus a role core, ordered by `assembly.json`) by `scripts/render-native-agents.py`; `make check` fails if the generated files drift. Exact procedures for worker and specialist routes live in the `watoom-worker-contracts` skill, which agents load before using a route. Approved skills are listed in `watoom_code_native_skills` and installed by `playbooks/watoom-native-skills.yml`. Web search uses the local SearXNG through the native `websearch` tool; the versioned API reference (`wlk_*` tools) comes from `tools/language-knowledge`.

Owner-sensitive skill content remains server-private. Preserve its maintained private source without printing it or publishing its Git ancestry.

## Storage and desired-state owners

- Application state: /data/ai/watoom-code.
- Project work: /data/ai/projects, contained within each project's own directory.
- Model data: /data/ai/models; weights are excluded from Git.
- Shared assets: existing global Catalog and read-only worker library access.
- Application IaC: ansible/roles/watoom-code and its maintained playbooks.
- Router/controller: existing llm-model-lab role, scoped manifests and tools/llm/watoom-gpu-controller.

## Open work

The [Model Manager](MODEL_MANAGER.md) is deployed with fenced controller integration. GGUF generation passed; SDXL/LoRA validation remains separately tracked.

Fresh-checkout Unreal rebuild acceptance, online Hyper networking, BloodFX motion/portable effects and Nwiro/POT Linux execution retain their documented NOT TESTED/unvalidated scope. Godot combat-logic conversion is deferred.

## Tooling

- **Godot game worker:** the typed `godot-game` operation of `watoom_game_worker` is accepted end to end by the production model (see `NATIVE_GAME_WORKER.md`). The Bazzite iGPU has no DRI3 under Xvfb, so only `gl_compatibility` (llvmpipe) styles run there; Vulkan `forward_plus` styles need the server GPU and are out of scope for this worker (decided 2026-11-18, T-0047: keep the worker gl_compatibility-only rather than contend with model GPU leases).
- **ESP32 DIV v2 guide:** `tools/language-knowledge/manuals/esp32-div-v2-engineering/` (55 verified entries: pins, chips, firmware, SD and shared SPI, heap budget, debugging). The SD card mount now asks for 8 file slots and falls back to 4 (T-0045); PSRAM cannot be enabled because its pins are the display's.
- **Unreal tools (`tools/rig-ue-mcp/`):** `ue_stray_check.py` finds foliage and actors in the sky, under the sea or under the ground (a failed read now fails instead of reporting 0 stray; `--apply` writes a removed-instances receipt; stale `--heights` are detected); `unreal_lake_smooth.py` softens lake shorelines and validates its inputs. A full stray scan takes about 17 minutes on the current map.
- **Tickets board:** kanban at https://glance.internal.homelab.example/tickets/ for the owner, Sonnet, Sabre and the models; see [TICKETS_BOARD.md](TICKETS_BOARD.md).
- **Native skills install:** `watoom-native-skills.yml` copies the working tree, not a commit, and warns when an approved skill has uncommitted changes.

## Project spaces, verification and learning

The new-session picker groups projects as Games, Work, Writing, Images, Homelab and LLM & tooling, matching `/data/ai/projects/AGENTS.md`. New-project creation uses the chosen space root. `watoom_code_project_spaces` in `ansible/roles/watoom-code/defaults/main.yml` drives `<config-root>/watoom-spaces.json`, rendered by `tasks/coordinator_guard.yml` and served at `GET /api/config/spaces`; an absent file falls back to a flat list. Add a space in the defaults list, align its ID with a configured group, and re-apply the owning role through the approved release route. See the [picker guide](guide/watoom-code.md#new-session-project-picker).

Phase 2's `tools/watoom-code/verification_loop.py` runs read-only graders selected by changeset file type: Ansible lint/syntax, YAML parse, shell syntax, Python compilation and JSON parse. It emits overall/per-file/per-grader JSON and exit 0/1. Run it before the owner sees a change; the verdict is the harness's, never the agent's self-report. Unsupported types are skipped and need their existing checks, including the guide renderer for Markdown/HTML.

Phases 3–4's deterministic `tools/watoom-code/self_learning/memory_curator.py` uses no LLM/GPU. Owner fixes over agent-authored paths become procedural lessons; verification failures supplied through `--evidence-root` become episodic incidents. Only the journalled sidecar `<watoom_learning_root>/lessons.sqlite` is written, never AgentMemory. The nightly timer currently mines owner commits and is **off by default**, installed only with `watoom_learning_curator_enabled: true` via `tasks/self_learning_curator.yml` and `ansible/playbooks/watoom-code-self-learning-controller.yml`.

The three independent levers are: set the flag false and re-apply to remove the units; `touch <watoom_learning_root>/curator-disabled` to make the next run a no-op; or `memory_curator.py rollback --store <watoom_learning_root>/lessons.sqlite --txn <id>` to undo one night. Code, harness, coordinator guard and AgentMemory changes retain the existing idle gate and owner approval. See [operating instructions](guide/watoom-code.md#learning-loop) and the [design, sections 3 and 6](proposals/learning-loop-design.md).

## Unified Blender runner release

The helper lock `config/blender-unified-v3/release-lock.json` selects **v3.2-godot-path** and the `.../runtime/validation.json` receipt with the `godot` and `blender.checks` gate fields. `fix.py check` verifies integrity; `fix.py install --validation RECEIPT --i-approve` activates with rollback on failure; `fix.py rollback --snapshot SNAPSHOT_JSON --i-approve` restores the previous owned pointer. Activation is owner-gated through `ansible/playbooks/watoom-blender-unified-v3.yml -e unified_approved=true`. See [runner operations](WATOOM_BLENDER_UNIFIED_V3.md) and the game guide.
