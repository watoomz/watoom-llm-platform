---
title: WatooM Code and pipelines
nav: WatooM Code
summary: The agent workspace — its components, agents and skills, how projects are scoped, the Toolkit that runs Blender, Unreal and Godot jobs, the background dispatchers and how releases are promoted.
---

## Components

| Component | Where | Purpose |
|---|---|---|
| WatooM Code app | `watoom-code/watoom-code` (4096) | Web UI and agent runtime at `https://watoom-code.internal.homelab.example` |
| AgentMemory | `watoom-code/agentmemory` (3111) | Long-term memory over MCP, embeddings from `bge-embeddings` |
| WatooM Toolkit | `watoom-code/watoom-toolkit` (8879) | Controller that launches bounded Blender, Unreal and Godot worker jobs |
| Coordinator guard | plugin in the app | Enforces routing, handoff, project scope and vision rules |
| RIG async stage | `watoom-code-rig-jobs/watoom-code` | Isolated stage that admits and dispatches background RIG game jobs |
| Host dispatchers | systemd timers | Bridge app requests to host-side workers (below) |

State lives in `/data/ai/watoom-code` (database, config, skills). Image, Toolkit and AgentMemory digests are pinned in `ansible/vars/watoom-code.yml`; the role fails closed without them.

## Agents

| Agent | Role |
|---|---|
| `watoom-workflow` | Coordinator: plans, routes and hands off; does not implement |
| `watoom-builder` | Implements changes and runs builds |
| `watoom-developer` | Implements application/game feature code to a spec; not infrastructure or 3D |
| `watoom-automation-expert` | Builds and maintains CI/CD pipelines, test harnesses and automation |
| `watoom-3d-modeller` | Creates and edits 3D assets; visual work needs pixel review before acceptance |
| `watoom-integration-expert` | Wires separate systems/services/APIs together; owns the integration glue |
| `watoom-investigator` | Read-heavy diagnosis and research |
| `watoom-reviewer` | Reviews changes and evidence |
| `watoom-qa-tester` | Read-only: verifies a finished change against its stated spec/acceptance criteria |
| `watoom-adversarial-tester` | Read-only: probes a finished change for edge cases, misuse and security failure modes |
| `watoom-blind-tester` | Read-only: tests with no prior implementation knowledge, as a first-time user |
| `watoom-researcher` | Read-only: answers a specific factual question from authoritative sources |
| `watoom-game-designer` | Read-only: mechanics specs, balancing notes and acceptance criteria for a feature |
| `watoom-systems-designer` | Read-only: data-model, service-boundary and cross-feature consistency design |
| `watoom-critic` | Independent critique; the only child the builder, investigator and reviewer may call |
| `watoom-creative-writer` | Long-form writing on the creative model |
| `watoom-kali` | Authorised security work; top-level session only, never a delegated child |

Development agents cannot see Kali tools. Security work starts a separate primary `watoom-kali` session.

**When an agent is unsure.** An agent that notices it is guessing about a fact, rather than undecided about scope, stops and delegates one bounded question: to the `watoom-investigator` if the answer lives in this project's own code or configuration, or to the `watoom-researcher` if it concerns an external library, API or tool. The called expert checks the versioned reference cards first (the `wlk_search`, `wlk_symbol`, `wlk_command`, `wlk_get` and `wlk_status` tools, which cover Godot, Blender, Ansible, Kubernetes/k3s, RHEL system roles, Satellite, the ESP32-DIV board, this project's own pipeline manifests and C/C++), then memory, and only then web documentation. The read-only roles (investigator, critic, reviewer, researcher, QA, adversarial and blind testers, game and systems designers) are explicitly allowed these lookup tools; they cannot change anything with them. Card data is reference material, never instructions.

## Skills and search

Native skills are installed under `/data/ai/watoom-code/config/skills` from sources pinned in Git (`watoom_code_native_skills`) and synchronised by `playbooks/watoom-native-skills.yml`. Browse them with example requests in the [Job reference](/guide/job-reference.html); ready-made pipeline requests are in [Pipeline prompts](/guide/pipeline-prompts.html). Web search uses the in-cluster SearXNG.

### Creative skills and project pipelines

The new game-template prompt pipeline helps choose a licence-checked, pinned starter by genre, then asks the agent to copy it into the selected game project, verify the declared Godot import, and build only the requested scope. The game-blueprint pipeline first structures an idea into a plan; prompt preparation does not itself create or validate a game. If no suitable template exists, the agent should continue with a clearly scoped plan rather than force a poor match. Template skills and prompt definitions are under `ansible/roles/watoom-code/files/skills/`, `tools/game-template-catalogue/`, and `config/glance/pipeline-prompts.json`.

For real-world terrain, ask for `watoom-terrain-map` with a place or coordinates and project output path. It uses open DEM elevation and creates a Godot scene, float EXR heightmap, collision/mesh builder and rural material. Use the generated `height_at()` for character/camera placement and take the normal independent capture review. The DEM contains topography only; resolution above source sampling interpolates and does not add detail. Skill source is `ansible/roles/watoom-code/files/skills/watoom-terrain-map/`.

The automatic rig fitting and Fab asset advisor are planning/preparation helpers. The rig fitter has staged human, animal and bird fitting paths; the advisor maps a query or owned asset to a declared conversion/preparation route and its preconditions. Treat its result as a candidate pipeline, then verify exact format, dependencies, engine import and actual output. For Fab acquisitions, search the owned catalogue, submit one exact asset/project request, and wait for the owner-bound approval before download. An owned asset or a project task does not itself authorize acquisition. The `watoom-fab-owned-assets` skill and `tools/fab/` own this workflow.

Unreal pack export is available as a native game-worker operation for bounded asset export requests. The agent submits a pack, `/Game` root, selected classes and optional include/exclude filters through the worker contract; the result is collected in the project with a receipt. The export can run on Bazzite by default and does not imply that the source pack was modified. Import, gameplay and visual acceptance remain separate checks.

The `watoom-metahuman` skill now provides owned `.mhpkg` inspection, verified Unreal installation, and an Unreal-to-Godot export path. It can produce meshes, DNA, textures, a Godot scene and setup script; GPU skin maps come from the separate RIG Unreal lane. Godot faces remain static because RigLogic is unavailable there. Read [Custom extensions](llm-extensions.md#metahuman-package-conversion) for exact limits, test status and source paths before using it.

## Project scope

Projects live at `/data/ai/projects/<group>/<project>`. Each group is mounted read-write at the same path inside the app; the rest of `/data/ai` is read-only.

| Group | For |
|---|---|
| `games` | Godot and Unreal game builds |
| `work` | Employer work |
| `writing` | Stories and documents |
| `images` | Image and render projects (`images/review`, `images/generated`) |
| `homelab` | Homelab infrastructure, including this repository |
| `llm` | Model, agent and pipeline tooling (`llm/pipelines/…`) |

### New-session project picker

The picker groups existing projects into **Games, Work, Writing, Images, Homelab, LLM & tooling**. Select a space when creating a project so it is placed under the matching `/data/ai/projects/<group>/` root. These six spaces map one-to-one to the directories in `/data/ai/projects/AGENTS.md`.

Grouping is config-driven: `watoom_code_project_spaces` in `ansible/roles/watoom-code/defaults/main.yml` is rendered by `tasks/coordinator_guard.yml` to `<config-root>/watoom-spaces.json` and exposed by `GET /api/config/spaces`. If that file is absent, the picker gracefully shows a flat project list.

To add a space, update the defaults list (ID, label and description), keep its ID aligned with a configured project group and `/data/ai/projects/AGENTS.md`, then re-apply the owning `watoom-code` role through the existing approved release route. The defaults list controls display order.

Shared inputs are in `/data/ai/assets`. Run evidence is kept with each job or under `/data/ai/helper-scripts/reports`; `/data/ai/artifacts` holds only ESP32 build output and Unreal pack exports.

## Toolkit and engines

| Engine | Version | Location |
|---|---|---|
| Blender | 5.2.3 (in the Toolkit image) | `/data/ai/toolchains/blender/5.2.3` on the host |
| Unreal Engine | 5.8.3 | `/data/ai/toolchains/unreal/5.8.3` |
| Godot | 4.7.2 | `/data/ai/toolchains/godot/4.7.2` |

The Toolkit image (`tools/watoom-toolkit/Containerfile.3d`) carries Blender and the worker code. Jobs run as separate pods with fixed CPU, memory and time limits, read inputs by hash and write outputs plus a receipt. `3d.inspect` performs export/re-import, Godot import, Unreal import and LOD checks.

### Godot Editor MCP

`watoom-code` can inspect and drive the Godot Editor that is open on the rig through the `watoom-godot` MCP server. The agent pod runs `ssh` to a restricted account (`godotmcp`) on the rig at `10.99.1.44:2223`. That account can only run one launcher, `C:\watoom\rig-godot-mcp\run-godot-mcp.cmd`, which starts a policy wrapper in front of the NPGameDev `godot-mcp-server`; the bridge then talks to the editor plugin over loopback on the rig. The policy gate lives on the rig, so the pod cannot loosen it.

As of 2026-11-13 the rig policy names every tool in the toolkit's reference (115 names), including the write tools and `execute_code`; the owner opened it. The rig's `godot-mcp-policy.reviewed.json` is the reviewed list and `C:\ProgramData\watoom\godot-mcp-policy.json` is the live copy, re-read on every request. To close one tool, add its name to `deny_names` (deny wins). A tool added by a later toolkit update stays blocked until its name is added. Agents are told to prefer read-only tools, keep write tools to what the task needs, and use `execute_code`/`node_call_method` only when no dedicated tool does the job. The `godot-mcp-toolkit` and `watoom-godot-route` language-knowledge cards describe each tool, its access label and the route policy; experts read them when an agent is unsure how to use a tool. The Godot Editor must be open on the rig with the `godot_mcp_toolkit` plugin enabled; if it is closed the tool list is empty. The server entry is merged into the existing configuration by `watoom_code_godot_mcp_enabled` through `playbooks/watoom-code-godot-mcp.yml`, followed by a restart of the `watoom-code` pod. To switch it off, set the variable to `false`, re-run that playbook (it removes the entry) and restart the pod, or disable the `godotmcp` account on the rig. Rig-side setup, the verified Windows OpenSSH behaviour and the extra steps for opening further tools are in `tools/rig-godot-mcp/README.md`.

### Unreal Editor MCP (not yet enabled)

The same route exists for Unreal through db-lyon/ue-mcp (`watoom-ue`, pinned 1.4.14, micro context strategy: one gateway tool, about 240 tokens). The lab side (SSH playbook, config entry, policy wrapper, converter, cards) is built and tested; it stays off (`watoom_code_ue_mcp_enabled: false`) until the rig side is installed from `tools/rig-ue-mcp/README.md`: the plugin in the project, a restricted `uemcp` account on port 2224, a router exception and the policy file. Nothing has run against the rig's Unreal 5.8 editor yet. The rig policy allows every ue-mcp category and denies nothing (all 3,714 actions, opened by the owner on 2026-11-14), so the model is told to prefer dedicated actions over the Python and console escape hatches and to read before it changes. A category added by a later release stays blocked until the policy is regenerated. The language-knowledge product `ue-mcp` has one card per action (3,714) with its effect and whether the route allows it. The texture-layering skill's `unreal_landscape_export.py` prepares the 16-bit heightmap and uint8 layer-weight tiles that `landscape.import_heightmap` and `landscape.set_layer_weight_region` take.

### Building a game end to end

The `watoom-game-blueprint` skill now carries a task-by-task plan for each engine: `references/engine-godot.md`, `engine-unreal.md` and `engine-threejs.md`. Every task row names the agent that does it (game designer, systems designer, developer, builder, 3D modeller, integration expert, automation expert, reviewer, the three testers), the tool or pipeline to use (the Godot and Unreal editor tools, the terrain and texture-layering scripts, the worker bridge, headless Chrome for Three.js) and a done-when check. `references/agents.md` says which agent to call for what, and `templates/project-docs.md` gives the four short documents (specs, GDD, architecture, test log) every task cites. The Unreal and Three.js plans are new and untested end to end; the Unreal plan assumes Blueprint-only because the rig has no C++ toolchain.

### Texture layering

The `watoom-texture-layering` skill covers layered texturing for terrain and props. `scripts/layer_masks.py` turns a terrain heightmap and a layer spec (slope, height, curvature and noise rules) into splat weight maps that sum to exactly 255 per pixel; `scripts/blender_layered_material.py` builds a stacked PBR material in Blender (slope, height, noise, vertex-colour, AO and edge masks, macro variation, detail normal); `templates/terrain_layered.gdshader` draws up to eight layers in Godot with height-blend, triplanar cliffs and anti-tiling. The mask maths, the Blender build and render, and the shader compile are covered by unit tests on the lab; the shader's rendered look on a GPU and Terrain3D control-map import still need the rig. The `watoom-texture-layering` cards state the layering rules, and experts read them when an agent is unsure how to layer a material.

Unreal validation starts from a pinned asset-registry seed beside the engine (`asset-registry-seed-<engine-sha>`). Each job verifies its SHA-256 before use and falls back to a cold scan if it is missing or altered, so it changes speed only, never results.

## Background dispatchers

| Timer | Interval | Does |
|---|---|---|
| `watoom-game-worker` | 30 s after idle | Runs admitted, bounded Godot validation jobs |
| `watoom-rig-async-stage` | 5 s after idle | Admits RIG game jobs, reconciles the broker queue, delivers completions through a durable outbox |
| `watoom-workstation-render-stage-scan` | polling | Admits render requests from the workstation inbox |
| `watoom-fab-approvals` | 1 min | Processes owner-approved Fab asset acquisitions |
| `watoom-image-review` | 1 min | Copies project captures into `images/review` |
| `watoom-capability-health` | 1 h | Refreshes the native catalogue and learning health (no inference) |
| `watoom-change-requests` | 30 s after idle | Validates model change requests and publishes the diff for operator approval; never applies anything |

The render broker queue is `/data/ai/helper-scripts/state/workstation-render-stage/queue.sqlite`. The in-cluster stage worker claims `godot` jobs; the Windows workstation worker claims `blender` render jobs. Inputs are snapshotted by hash at admission through the `watoom-workstation-inputs.socket` service, so later edits to a source file never change a queued job.

## Host change requests

Models cannot edit host-owned files such as the ESP32 worker contract, which live in the read-only canonical checkout. When a failure is caused by one, the model files a change request that an operator approves. Check for a named option first: ESP32 builds that exceed the default 128 files / 4 MiB source budget add `"source_profile":"large"` (up to 1024 files / 16 MiB) to the build manifest, with no request needed.

| Step | Who | What happens |
|---|---|---|
| File | Model, in any project | Writes `.opencode/change-requests/<id>.json` (`schema`, `id`, `file`, `old`, `new`, `reason`) in its project root. `old` must match the target exactly once; at most 40 changed lines; one fresh id per request |
| Scan | `watoom-change-requests` timer | Checks the request against the allowlist and publishes `<id>.status.json`: `PENDING_APPROVAL` with the exact diff, or `REJECTED` with the reason |
| Decide | Operator, on the host | `change_request.py list`, `show <id>`, then `approve <id>` or `reject <id>` (add `--project NAME` if two projects share an id) |
| Decide in Glance | Operator, in the browser | Open **Change requests** under *Observe and search* (`/command-center/change-requests.html`). It shows each pending diff with the reason and **Approve and apply** / **Reject** buttons. Enter the operator PIN (root-only file `/root/.watoom-change-request-pin`) so models and other LAN clients cannot approve; five wrong PINs lock it for five minutes. The decision is queued and the host scanner applies it within about a minute, only if the request is still the version you reviewed |
| Apply | `approve` | Re-checks the request and target are unchanged, applies the edit, runs the fixed checks from the policy, then commits and pushes only that file. A failed check restores the file |

To create or rotate the PIN run `scripts/set-change-approval-pin.sh` as root. It stores the PIN and its salted hash in the encrypted vault (`CHANGE_REQUEST_PIN`, `GLANCE_CHANGE_APPROVAL_PIN_HASH`), writes the root-only file, applies only the `glance-change-approval` Secret and restarts Glance. The cluster never holds the PIN itself. [Where secrets live](security.md)

```bash
python3 tools/change-requests/change_request.py list
python3 tools/change-requests/change_request.py show <id>
python3 tools/change-requests/change_request.py approve <id>
```

> [!RULE]
> The policy `tools/change-requests/policy.json` is the only authority. Only allowlisted files are accepted (currently the ESP32 `contract.py`, `runner.py`, `worker.py` and operations doc), the checks are fixed argv lists a request cannot choose, a target with uncommitted changes is refused, and models cannot approve their own requests or run host commands. Queues are found in every `/data/ai/projects/<group>/<project>/.opencode/change-requests` whose path contains no symlinks. Every action is appended to `/data/ai/helper-scripts/reports/change-requests/audit.jsonl`. Adding a file or project scope means editing the policy and reviewing its check.

## Learning loop

Phase 2 uses `tools/watoom-code/verification_loop.py`, a harness-run, read-only grader orchestrator. It selects graders by file type: `ansible-lint` and `ansible-playbook --syntax-check` for Ansible, YAML parse, `bash -n`, `py_compile` and JSON parse (plus `yamllint` when the repository pins a configuration). The JSON verdict includes overall, per-file and per-grader results; exit status is 0 or 1. **The verdict belongs to the harness, never the agent's self-report.** Run it over the changeset before presenting work to the owner; fix failures and re-run.

From `standardised_k3s_project/`, for example:

```bash
python3 tools/watoom-code/verification_loop.py --path docs/guide/watoom-code.md --path config/glance/guide/assets/search-index.json --evidence /path/to/task-evidence
```

Paths are relative to that project root; repeat `--path` for every changed file. Unsupported file types and missing graders are reported as `SKIP`, not proof of correctness. Markdown and HTML still require the existing guide renderer and documentation link checks.

Phases 3–4 use `tools/watoom-code/self_learning/memory_curator.py`: a deterministic nightly curator with **no LLM/GPU**. It mines the owner's commits over agent-authored paths into procedural lessons and can ingest verification failures from an evidence root as episodic incidents. Its journalled writes go only to the sidecar `<watoom_learning_root>/lessons.sqlite`, separate from AgentMemory. The shipped timer mines owner commits; evidence ingestion requires supplying `--evidence-root` to the curator.

The curator is **off by default**. `ansible/roles/watoom-code/tasks/self_learning_curator.yml`, wired into `ansible/playbooks/watoom-code-self-learning-controller.yml`, installs the nightly timer only when `watoom_learning_curator_enabled: true`.

Other learning inputs are owner chat lessons marked with `+` and verified engine/API error lessons shown to agents. These feed the guarded lesson path; they do not silently patch source or override the current API reference. Phase 2's verification grader chooses static checks by file type and emits a harness-owned JSON verdict. A `SKIP` means that grader could not check that file, not that it passed. The critic also has a source-verification instruction for API/library fixes. Sources include `tools/watoom-code/verification_loop.py`, `tools/watoom-code/self_learning/`, `ansible/roles/watoom-code/files/skills/self-learning/`, and the shared agent instructions.

Three independent stop/rollback levers are available:

1. Set `watoom_learning_curator_enabled: false` and re-apply the controller playbook to stop the timer and remove its service/timer units.
2. Run `touch <watoom_learning_root>/curator-disabled`; the next curate/apply run is a no-op (`DISABLED`). Substitute the configured root before running.
3. Undo one night's journalled transaction using its printed transaction ID:

```bash
python3 tools/watoom-code/self_learning/memory_curator.py rollback --store /configured/learning/root/lessons.sqlite --txn TRANSACTION_ID
```

Replace the store path and transaction ID with the configured values. Sidecar lessons can auto-apply; nothing durable in code, the harness, coordinator guard or AgentMemory changes without the existing idle gate and owner approval. The full design and decisions are in `docs/proposals/learning-loop-design.md`, sections 3 and 6.

## Releases

Production changes to the app, guard, skills or Toolkit are promoted through fenced routes that wait for an idle app and GPU, apply, verify and roll back on failure:

| Change | Route |
|---|---|
| App, agents, guard, skills | the owning `playbooks/watoom-code-*.yml`, run under the release fence |
| Toolkit image | `tools/watoom-code/deploy-platform.py --blender-toolkit-only` with an exact-image acceptance bundle (fixtures, review and engine hashes) |
| Model placement | GPU controller with rollback (see [AI platform](ai.md)) |

After a Toolkit promotion, the app's location bindings are reloaded while idle. A one-off repair must never become a hidden dependency: fix source, add a regression check, release through the route above.

The application source port, GUI plugin, scroll fix and file-download feature are tracked as separate immutable image pins. Reasoning-level GUI controls (`xhigh`, `medium`, `low`, `off`) are supplied through the model capability/variant configuration. For the Qwen model, `preserve_thinking=false` drops stale prior reasoning from context while allowing fresh reasoning each turn. The exact supported variants and chat-template settings are source-controlled; avoid copying backend flags into user prompts. The prompt-cache disk tier is owned by the LLM serving configuration and uses `/data`; cache reuse is an optimization, not a guarantee for a new or changed prompt prefix.

## Backups

`watoom-code-backup.timer` runs daily at 03:30. It takes a verified copy of the SQLite database, configuration and AgentMemory, keeping 14 copies in `/data/backups/watoom-code`. It then exports a rotating off-host set that the workstation pulls. `watoom-backup-offhost-check.timer` checks the pull receipts hourly.

## Complete platform manuals

Use the [LLM user guide](llm-user-guide.md) for end-to-end workflows and the [LLM API & reference](llm-api.md) for integration contracts, the platform source map, operations, maintenance and recovery.

## Project and source reference

See the [LLM project guide](llm-project.md) for requirements, configuration, deployment,
development and troubleshooting; [custom extensions](llm-extensions.md) for plugins,
agents, skills and worker integrations; and the [server automation reference](server-catalogue.md)
for every tracked script, playbook, role and tool. [GitHub publication](llm-publication.md)
covers the separate private distribution and source provenance.
