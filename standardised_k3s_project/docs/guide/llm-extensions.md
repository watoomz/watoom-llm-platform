---
title: Custom plugins, agents and integrations
nav: Custom extensions
summary: Where WatooM's custom application changes, native plugins, agents, skills, workers, memory and model integrations are implemented and deployed.
---

## What counts as an extension

The environment contains several different extension layers. A native application plugin, an agent instruction, a skill, an MCP adapter and a host dispatcher are different contracts with different privileges. Preserve their source and deployment owners together. The application snapshot includes upstream interfaces and dependencies; their presence is not a claim that WatooM authored them or enabled every plugin.

| Layer | Source | Deployment/configuration owner | Contract |
|---|---|---|---|
| Application and UI customisations | Separate pinned application checkout, distributed under `application/` | Application build and `watoom-code` role | Native sessions, project picker, tool/UI integration and API schema |
| Coordinator guard | `ansible/roles/watoom-code/files/coordinator-guard/` | Role `tasks/coordinator_guard.yml` | Native plugin hooks/storage; delegation budgets, child identity and receipts |
| Image scope | `ansible/roles/watoom-code/files/image-scope/` | Role image-scope tasks and enable helper | Native image tool scope and presentation/review constraints |
| Native agents | `ansible/roles/watoom-code/files/native/_src/` (shared modules + one core per role), rendered to `files/native/agents/` by `scripts/render-native-agents.py` | `watoom-code-parts.yml --tags agents` | Coordinator, 15 child roles, creative writer; worker procedures in the `watoom-worker-contracts` skill |
| Native skills | `ansible/roles/watoom-code/files/skills/` plus approved source registry in role defaults | `watoom-native-skills.yml` and role `native-skills` tasks | Discoverable instructions/resources; a skill document is not a service |
| Model/runtime capability mapping | `verified-model-capabilities.json`, `enable-verified-model-capabilities.py` and reasoning/context helpers in the role | Owning WatooM playbooks and production vars | Model IDs, provider routing, variants and verified context interfaces |
| Toolkit | `tools/watoom-toolkit/` | WatooM role and independent Toolkit release pins | Authenticated bounded job controller; worker isolation and artifact publication |
| GPU controller | `tools/llm/watoom-gpu-controller/` | `llm-model-lab` role, controller playbook | Sole GPU lifecycle writer, durable ownership, fencing and inference leases |
| Router and model adapters | `ansible/roles/llm-model-lab/files/` | Model-lab tasks and manifests | OpenAI-compatible inference front end and controller admission |
| Game/asset bridges | `tools/watoom-code/game_worker_bridge.py`, capture/spec modules and `tools/rig-async-stage/` | Dedicated worker playbooks | Exact parent/source/request identity, status and receipts |
| Blender/Fab/Unreal | `tools/blender-asset-builder/`, `tools/fab/`, `tools/unreal/` and owning skills | Blender/Fab/workstation roles and scoped helpers | Preserve purchased sources; export portable artifacts via bounded workers |
| Workstation execution | `tools/bazzite-render-worker/`, `tools/workstation-render-stage/` | Worker configuration and workstation playbook | Offload heavy work without parking production inference by default |
| Memory/learning | `tools/watoom-code/self_learning/`, memory helpers and role tasks | Dedicated memory and self-learning playbooks | Durable recall, guarded optimisation, explicit activation/rollback |
| Language knowledge | `tools/language-knowledge/`, role capability configuration | Owning flags and imported card sources | Source-derived language reference, separate from executable tools |
| Security/MCP integrations | `tools/kali/`, `pi-kali-agent`/gateway roles | Dedicated isolated security playbooks | Authorised security sessions; development agents do not inherit Kali powers |
| Glance observability | `config/glance/helper.py`, guide sources and renderers | Glance manifest/ConfigMaps and guide hostPath | Read-only view of APIs, controller, jobs and metrics |

## Native plugin lifecycle

1. Modify the maintained plugin package, not a live application-state copy. Keep its `package.json`, plugin entrypoint and configuration schema together.
2. Run the focused native guard/scope tests and inspect changed hook contracts against the pinned application source.
3. Preserve the prior immutable plugin/package identity and configuration snapshot.
4. Confirm native sessions and child executions are idle through the supported API and deployment guard. Do not interrupt sessions to reload instructions.
5. Apply only the owning role tasks through the established release mechanism.
6. Verify actual native hooks, refusal behaviour and durable state after reload. A copied file is not acceptance.

Coordinator guard uses the native application database/plugin storage rather than inventing a second registry. Its durable counters, exact child IDs and image evidence must survive compaction and restart. Private recovery grants are runtime authorisations and are excluded from Git; publishing the plugin implementation does not authorise publishing those grants.

## Skills and agent definitions

The role's approved skill catalogue is authoritative for installation. Some entries point outside this repository, including a deliberately private instruction source. The source inventory marks this exclusion rather than substituting a fabricated public body. The distribution manifest records missing external sources and their owners so a new installation cannot quietly assume they were bundled.

Native agents have structured front matter and explicit tool/model permissions. Keep model/tool IDs aligned with the live loader. Render existing definitions with `scripts/render-native-agents.py` where applicable; do not create a parallel agent registry. Coordinator-owned canonical work state stays under the project `.opencode/work/` tree.

## Workers and receipts

The native tool admits a request, the dispatcher reconciles it, the worker executes within bounds, and the coordinator consumes the resulting receipt. These are separate stages. The source fingerprint, operation, request/job identity and parent session must agree. A `RECONCILIATION_REQUIRED` result blocks replay until existing evidence is accounted for.

Keep application code, Toolkit code, role templates, service/timer installation and acceptance checks in the publication. Do not copy runtime jobs, private request bodies, session contents or acquired assets into a source repository. The [role reference](server-roles.md) lists deployed helper payloads; the [tools reference](server-tools.md) covers controllers, validators and release helpers.

## Upstream attribution and completeness

The application is based on OpenCode; retain its `LICENSE` and package notices. Preserve third-party notices for bundled dependencies, imported skills and engine/tool integrations. Do not apply a new root license to upstream or third-party code by implication. WatooM-authored code needs an explicit owner-selected license before a public open-source release.

The [publication guide](llm-publication.md) defines what is bundled, what remains an external prerequisite, how source pins are recorded and how the private distribution is checked. Source availability, production activation and clean-room installation qualification are separate claims.

## Registered native plugins

The following packages are selected by the inspected native configuration. Runtime
hash-suffixed directories are release copies; maintain the owning source below.

| Native plugin | Maintained source | Responsibility |
|---|---|---|
| `searxng-search` | `ansible/roles/watoom-code/files/native/plugins/searxng-search/` | Native web search through the configured local SearXNG service |
| `coordinator-guard` | `ansible/roles/watoom-code/files/coordinator-guard/` | Serial delegation, tool budgets, durable evidence and recovery boundaries |
| `self-learning` | `tools/watoom-code/self_learning/` | Native lesson/context integration and guarded learning lifecycle |
| `image-scope` | `ansible/roles/watoom-code/files/image-scope/` | Image operations constrained to approved project/output scope |
| `homelab-workspace` | `tools/watoom-code/workspace-policy/` | Project-scoped homelab capabilities and source/workspace policy |
| `language-knowledge` | `tools/language-knowledge/package/` | RAM-resident language/API reference cards and native lookup |

The separate `dev-workspace` package is optional configuration, not selected by
this inspected plugin list. Its source and role tasks remain in the distribution.
Skill and tool visibility depends on project/agent scope; being bundled does not
enable every integration or grant additional permissions.

## Current worker and knowledge integrations

- Blender and declarative asset capture use Bazzite workers. Requests wait when that worker is unavailable; RIG eligibility follows the maintained 10-minute wait policy. Do not park production inference as an implicit fallback.
- Asset capture has a derived Xvfb/Mesa EGL runtime, pinned Blender execution and common result/receipt validation. Worker exit/deadline classification distinguishes script failures from resource failures; the text "OOM" is not evidence of a memory kill.
- `watoom-metahuman` provides owned-package inspection, Unreal installation and Godot export helpers. The native skill and Unreal export scripts are source-owned; model/engine/asset licenses and static-face/skin/groom limits still apply.
- The outbound-only RIG Unreal lane accepts fixed `probe` and `metahuman-skin` operations, verifies shipped/runtime hashes, uses a Windows Job Object (12 GiB default), respects busy/pause journals, and refuses installer replacement during an active job. It is separate from the Blender/Godot broker.
- Language-knowledge includes inert reference triggers for recognised tool errors and uncertainty near API/CLI terms. Its package is selected independently of the main application image; preserve card/procedure data and verify the exact configured package after reload.

The application, Toolkit and AgentMemory image pins remain independent. The current worker/plugin changes do not imply that the application image was rebuilt. Source and runtime provenance are recorded in the private distribution's publication metadata; [Disaster recovery](disaster-recovery.md) includes external worker re-staging and journal reconciliation.

## What's new (2026-11-03 to 2026-11-07)

This interval adds source-backed API help, a Bazzite-first execution policy, an owned MetaHuman conversion path, and changes to the game-building and learning workflows. The sections below describe the user-visible behavior, operation, boundaries, and maintained source. The [WatooM Code guide](watoom-code.md) covers how to invoke these from a session; the [software design page](software-design.md) traces the trust and execution flows.

## Language knowledge and agent guidance

`watoom-language-knowledge` is a version-pinned, RAM-resident reference for the installed Godot and Blender APIs and command-line flags. Extractors build cards from installed/pinned interfaces and official reference material; cards include signatures, parameters, constraints, version/source and licence metadata. Search combines lexical matching with optional BGE embedding/vector results and reciprocal-rank fusion. If the embedding service or vector files are absent, lexical search remains available. Native tools are `wlk_search`, `wlk_symbol`, `wlk_command`, `wlk_get`, `wlk_status`, and `wlk_feedback`. Feedback is queued for operator validation; a card or feedback item is reference data, never executable permission.

The plugin also has two bounded, inert context triggers. A recognised Godot/Blender API or CLI error can append a matching reference entry to that tool result. When a reasoning block has an uncertainty phrase close to an API-looking name, the plugin may attach a short answer to the next model call as a trailing user-role data message. Doubts about importer behaviour (for example whether the FBX importer overwrites extracted textures) and option keys such as `fbx/embedded_image_handling` are answered from 81 import-option cards (`kind=import_option`), generated from the engine itself: option names and defaults come from the `.import` files Godot writes for generated sample assets, and value labels from the engine binary's own strings, so a card can say that the default is `1 = Extract Textures` and list the alternatives. That lookup stays silent unless a card clearly matches the file type and wording. The note does not alter the cached prompt prefix, is consumed once, and is limited/deduplicated per prompt. The plugin skips its own tools and does not turn suggestions into commands. Unit tests and a simulated plugin context exercise these hooks; live agent-session behavior has not yet been observed. Production card data covers Godot only; the full 124,278-card/vector build is not wired into production.

Use the agent's `wlk_*` tools before guessing a Godot/Blender API or CLI option. The explicit “wait, does X exist?” instruction asks the agent to check when uncertain. A displayed “Reference lookup” block is data, not an instruction. Source, extractors, admin/procedure tooling and tests are in `tools/language-knowledge/`; deployment is the `language_knowledge.yml` role task and its enable/card-path variables. The plugin is selected separately from the application image, so a main image pin does not identify its version.

## Bazzite-first heavy work and RIG eligibility

Rendering, captures, Blender, conversion and similar heavy work route to the Bazzite desktop worker first. Bazzite is reached over SSH and runs rootless Podman with a staged toolkit, no network, read-only root and dropped capabilities. The homelab does not run the local fallback by default: a local execution route would reserve GPU headroom and park the production model. `local_fallback` is an explicit opt-in (`watoom_game_worker_local_fallback`, default false).

When Bazzite is unavailable, a request stays `QUEUED` with `waiting_since` and `rig_eligible`. After 600 seconds, status allows the agent to submit the equivalent `watoom_rig_game_job`; the bridge itself cannot submit to the RIG, which accepts only model-submitted requests. The agent should continue useful work and follow the existing request ID rather than repeatedly resubmitting. The `bazzite_operations` setting controls which operations are eligible. Godot import/regression/capture, Blender and declarative asset capture use their Bazzite runners; asset capture polls Bazzite first. Godot requires 8 GiB free RAM; Blender and asset capture require the requested job size plus 2 GiB. Bazzite Blender and asset capture have passed small end-to-end jobs; Godot capture ran through worker startup to the game's own script error, not a successful game capture.

Godot's capture runtime is a separately built additive Xvfb/Mesa EGL image because the production toolkit lacks Xvfb, xauth and EGL. If that image is absent, preflight reports the missing capture image/tool. The systemd user unit must allow Podman's `newuidmap`: `PrivateDevices=yes` and `NoNewPrivileges=yes` caused intermittent helper failures and are omitted. SSH exit 255 is reported as unreachable; a bare string “OOM” is not treated as evidence of a memory kill; a deadline after a script error retains the script error as the cause. Source of routing and runners is in `tools/watoom-code/`, `tools/bazzite-render-worker/`, and the owned skill's `scripts/unreal-export/`; role defaults/rendering are under `ansible/roles/watoom-code/`.

Agent policy is assembled from `ansible/roles/watoom-code/files/native/_src/shared/69_language_knowledge_tools.md` and `70_bazzite_first_then_rig.md` by `scripts/render-native-agents.py`, then deployed through `ansible/playbooks/watoom-code-agents.yml`. The policy tells agents to check reference tools before guessing, keep working while jobs wait, and submit to the RIG only when status says eligible.

## MetaHuman package conversion

The `watoom-metahuman` skill handles an owned `.mhpkg` (a ZIP containing Unreal assets and manifests). `inspect` reports editable versus assembled content, LODs, grooms/clothing and hashes; `unpack` produces a verified Unreal `Content` tree; `copy-to-project` installs that content and enables the needed MetaHuman plugins in a UE project. `export-godot` runs two Unreal stages on Bazzite and emits head/body/full-body GLBs, DNA, textures, a Godot scene, setup script and manifest. The asset advisor now identifies `metahuman-pipeline` for MetaHuman packs.

The geometry stage uses the full Unreal Editor: the commandlet path asserts in Slate. Editable characters load headlessly once opened for edit; geometry export needs an 8 GiB job and the editor may crash at shutdown after a verified successful native result. The head skeleton follows the body through shared bone names. For skin maps, `export_dcc` can write DNA headlessly but Epic TextureGraph needs a GPU. The separate RIG `metahuman-skin` operation runs the full editor with a renderer and returns skin maps; without it, the pipeline uses a flat skin tone plus package normal maps. Godot applies the skin material to the largest head surface and body; the other head surfaces retain defaults, with their maps in `textures/reference/`. The normal green flip and roughness from SRMF green follow Epic conventions; textures have been imported and checked headlessly without import errors, but have not been visually rendered. Godot lacks RigLogic, so the face remains neutral/static. Editable characters have no grooms; assembled characters and male base are untested. Check the MetaHuman licence for use in another engine.

The Godot output is repaired before import: Unreal's empty accessors are stripped, and the head's vertex normals are recomputed because about 30% of the exported skin-triangle normals point against the mesh (it renders as dark and white blocks under lighting while an unlit view looks correct). The scene uses the neck-cut body mesh, because the full-body mesh carries its own head. Eyes, teeth and eyelashes get their own materials, identified from mesh geometry. The character plays a procedural 8-second looping idle (`IdleAnimation`, breathing, a slow weight sway, drifting head and neck, relaxed arms) built at load from the body skeleton; `play_idle`, `idle_strength` and `arm_drop_degrees` on the scene's script control it, and other animations can be added to the same skeleton. The face is a static neutral pose and does not blink, because Godot does not run RigLogic.

`tools/rig-godot-viewer/` opens any glTF, scene or converted folder on the RIG's GPU: drag it onto `Open-InGodot.bat`. It stages the folder where the scene's own `res://` paths expect it, imports it, and opens an orbit viewer (`1`-`4` switch shaded, unshaded, wireframe and normals views, which separates texture problems from lighting problems).

Maintained code is `ansible/roles/watoom-code/files/skills/watoom-metahuman/` (`scripts/metahuman_pipeline.py`, `scripts/rig_lane.py`, Godot setup and tests), with Unreal stages in `watoom-fab-owned-assets/scripts/unreal-export/ue_metahuman.py` and `export_pack.py`. The skill documents commands and output locations; it is for owned packs only.

## Outbound RIG Unreal lane

The Unreal lane is a separate outbound-only worker for the Windows RIG. The homelab writes a JSON manifest and package ZIP into an SFTP transfer jail; the scheduled worker polls, runs exactly one operation from `unreal_lane.OPS` (`probe` or `metahuman-skin`) under a Windows Job Object, and uploads artifacts with `result.json` last. Manifests carry no code or arbitrary paths. Shipped scripts and installed Unreal executables are hash-pinned; returned names, suffixes, size and SHA-256 are checked before homelab collection. A job interrupted by worker death is reported failed, never replayed. The lane defers while Blender/Godot workers are busy and obeys the shared pause control.

The operator installs/reinstalls the worker using `tools/rig-async-stage/unreal-lane/Install-UnrealWorker.ps1`; installation refuses replacement during a running job. `build_lane.py` builds the bundle. The model-facing skill helper submits `probe` or `metahuman-skin` and supports list/status/collect/cancel. UE 5.8.4 probe and one Base_Female skin job passed on an RTX 2080 SUPER; the skin job took 532 seconds with a 20 GiB Job Object limit and returned 34 files. MetaHuman optional content must be installed in the engine. A 12 GiB cap failed through commit exhaustion/D3D12 E_OUTOFMEMORY; about 20 GB free RAM and disk are advisable on the tested RIG. These are results for one rig and one editable character, not general compatibility. Source and detailed install steps are in `tools/rig-async-stage/unreal-lane/README.md`.

## Game authoring, templates, terrain, and asset discovery

`watoom-prompt-game-template` and `watoom-prompt-game-blueprint` turn a short request into a bounded project task; they prepare prompts rather than building the game themselves. The game-template catalogue contains licence-checked, pinned starter projects for supported genres. The agent searches for a matching template, reports its licence/revision/declared engine, copies it into the project (never edits the library copy), checks import, then implements the requested scope. If no template fits, it should say so. Prompt and skill sources are in `config/glance/pipeline-prompts.json` and `ansible/roles/watoom-code/files/skills/`; cataloguing/download/install helpers are in `tools/game-template-catalogue/`.

`watoom-terrain-map` generates a Godot terrain from a place name or latitude/longitude using open elevation DEM data. It writes a float EXR heightmap, preview, metadata, reusable mesh/collision script, rural material shader and ready scene. The agent uses `height_at()` for placement and the maintained landscape capture environment for review. DEM detail is limited by its source resolution; it does not add roads/buildings or satellite imagery, and a higher output grid interpolates rather than inventing detail. Source is `ansible/roles/watoom-code/files/skills/watoom-terrain-map/`; the prompt template is in the pipeline prompts.

The automatic Blender rig fitter classifies human, animal and bird subjects, fits a suitable rig, and validates the result through its staged passes; the asset catalogue advisor resolves an asset/query to a supported preparation pipeline, with format and rig preconditions. A candidate recommendation is not proof of compatibility or acceptance. Consult the selected skill's declared route and receipts. Implementations are maintained in the installed skills and `tools/fab/` (including `asset_advisor.py`); do not directly alter a purchased source pack.

The owned Fab workflow enriches catalogue entries with listing facts, offers a project-relevant advisor, and requires explicit owner approval for each exact download request. Requests bind asset, project and preparation plan; authenticated acquisition produces receipts and indexed source references. Unreal pack export is now a native game-worker operation: the request names a pack, `/Game` root and bounded class/include filters; worker output and receipt are copied to the project. Bazzite is preferred when staged and capable, with a pre-start-only local job fallback; a started export is not replayed. Downloaded plugins/code are not executed automatically, and a successful export does not prove Godot import, gameplay or visual correctness. Sources are `tools/fab/`, `watoom-fab-owned-assets/scripts/`, and `tools/watoom-code/game_unreal_export.py`; the owning skill has the request contract and limits.

## Asset archives (zip, tar, 7z, rar)

The native skill `watoom-asset-archive` (`ansible/roles/watoom-code/files/skills/watoom-asset-archive/`) gives models one safe way to look inside asset packs and extract only what a project needs. `asset_archive.py` offers `list`, `inspect`, `read`, `extract` and `status`; selection by glob, folder prefix and extension; `--strip` to drop wrapper folders; and `--dry-run` to preview. Output is one JSON document with `ok`, `errors` and `warnings`, so a corrupt, truncated, encrypted or unsafe archive is reported to the model rather than hidden.

* **Safety.** Absolute paths, `..`, symlinks and special files are never extracted. Case-only name clashes, over-long paths, decompression bombs and oversized selections are flagged. Every extracted file is checked against the archive's size and CRC, written to a temporary name first, and never overwrites a different existing file unless `--overwrite` is given. Destinations stay inside the chosen project and never inside `.git`, `.godot` or `.opencode`. A receipt is written to `<project>/.opencode/asset-extractions/`.
* **Where it runs.** zip and tar run inside the watoom-code pod. The pod has no `7z` or `unrar` (and the host's binaries need a newer glibc), so 7z and rar requests are left as files in `<project>/.opencode/archive-requests/` or the shared queue `/data/ai/projects/work/.archive-requests/`, and the host service `watoom-asset-archive` (user `opencode`, writes only under `/data/ai/projects`) answers them, normally within a few seconds. Install it with `ansible/playbooks/watoom-asset-archive.yml`; the skill itself is installed by `watoom-native-skills.yml`.
* **RAR support.** The distribution's `7z` cannot open RAR, so RAR uses RARLAB's `unrar` on the host.
* **Tests.** `python3 -m unittest test_asset_archive` in the skill's `scripts/` folder (27 tests, including real 7z archives, corruption and the request queue).

## Learning loop and verification

The learning work has distinct stages. A harness-side verification grader selects static checks by changed file type and owns the result; unsupported graders are reported as skips. Owner chat messages marked with `+` and verified engine/API failures can become lesson candidates; agents can see relevant engine error lessons. A deterministic nightly memory curator mines owner commits over agent-authored paths and may ingest existing verification evidence. It uses no LLM/GPU and writes a journalled sidecar SQLite store separate from AgentMemory. Its timer is off by default and can be disabled or rolled back by transaction. Learning proposals are not automatically activated code or skills. The existing detailed operation and rollback steps are in [WatooM Code](watoom-code.md); source is `tools/watoom-code/verification_loop.py`, `tools/watoom-code/self_learning/`, and the `self-learning` plugin/role tasks.

## Guard and worker-handoff corrections

Recent coordinator-guard fixes make child-session and worker evidence handling stricter: a completed child is not resumed as active work; a fresh package starts instead. A delegated result is accepted only when the corresponding request exists, and a visual-review handoff returns through the required receipt tool so the parent turn can continue. Image review keeps the original image bytes, and a guard rejection names the specific denied operation. These changes prevent stale child state or a claimed-but-missing worker request from being mistaken for completed work. The implementation and regression checks are in `ansible/roles/watoom-code/files/coordinator-guard/` and `tools/watoom-code/`.

## Application, inference, and observability changes

The custom application was ported to the pinned OpenCode v2.2.5 source and released as a separate immutable image; GUI-plugin, scroll-fix and file-download images also have their own pins. Follow `ansible/vars/watoom-code.yml` and the release owner rather than assuming a plugin change rebuilds the main application. GUI reasoning choices expose `xhigh`, `medium`, `low`, and `off` where supported. The configured Qwen model variants map to reasoning effort; `preserve_thinking=false` removes stale prior reasoning from subsequent context while the model still reasons on each turn. Chat-template tuning maps the model's medium/low modes to its supported template behavior; users should select a GUI level and need not supply backend flags.

The prompt cache has an SSD-backed disk tier under `/data` and writes through a background writer. It supplements memory cache; a long fresh prompt may still need prefill and model/prefix changes can invalidate reuse. Do not infer that every slow continuation is a cache fault. Source/configuration belongs to the LLM serving role and manifests, while the GUI variants are rendered by the WatooM Code role. Glance's command center adds read-only server and LLM serving panels; guide Markdown and helper sources render through existing Glance tooling. The panels observe health and do not acquire control of model or service lifecycles.

## Verification status

- Language-knowledge triggers: unit-tested (24 plugin tests) and exercised with a simulated plugin context; not yet observed on a live agent session.
- Bazzite Blender and asset capture: tested end to end with small jobs, including still and MP4 turntable capture. Godot capture reached the game's own script error after worker startup.
- MetaHuman: one editable Base_Female package was verified. Male base, assembled characters and other packs remain untested; Godot texture import was checked headlessly, not visually rendered.
- RIG lane: verified on the one UE 5.8.4 / RTX 2080 SUPER rig described above.
- Language-knowledge production data: the full Godot and Blender card set (about 124,000 cards, roughly 650 MiB resident) is loaded; vector search over it is not wired in production.
