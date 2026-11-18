# WatooM global rules

- Inspect current state before changing files.
- Use the smallest capability/tool surface that can complete the task.
- Work only inside the selected project unless explicitly authorized otherwise.
- Preserve dirty worktrees and unrelated changes.
- Never run broad destructive Git cleanup/reset/checkout/restore operations.
- Do not stage, commit, or push unless the user explicitly requests it.
- Do not use sudo or su from coding agents.
- Prefer project-local dependencies and existing project tooling.
- Load only the domain skill needed for the current task.
- Use fresh-context subagents only when investigation/review value exceeds prefill cost.
- Do not fan out parallel subagents on a single-slot local model.
- After a failed edit, reread current content before retrying.
- Do not rerun identical validation after a no-op edit.
- Preserve required behavior instead of deleting it to silence validation.
- Validate changed components before reporting success.
- Never claim a command/check succeeded unless it actually ran and passed.
- Prefer persistent IaC changes over live-only system changes.
- Keep final reports factual: changed, validated, remaining limitations.

<!-- WATOOM-RUNTIME-SKILL-CONTRACT-BEGIN -->

## Runtime and validation ownership

Language, framework and environment skills define how projects are discovered,
built, executed, tested and validated.

Permission policy grants capabilities; skills determine correct usage.

Agents with execution authority must not rely on a hard-coded global list of
interpreter or test commands when a relevant skill or project-local convention
exists.

For each supported environment, the relevant skill should define, where
applicable:

- how to detect that environment;
- authoritative runtime/interpreter/toolchain selection;
- existing environment or wrapper discovery;
- dependency-management conventions;
- compile/build commands;
- lint/static/type checks;
- unit/integration test discovery;
- runtime/smoke validation;
- graphical/headless validation;
- timeout/background-process handling;
- output/artifact verification;
- recovery when a validation tool invocation itself fails.

Project-specific instructions override generic defaults.

A validation result is evidence only when the command actually ran.

<!-- WATOOM-RUNTIME-SKILL-CONTRACT-END -->

## Local inference and handoff concurrency
Within a workflow, use serial foreground children and preserve existing session/job IDs. Never run two modifying children against the same project or canonical checkpoint. Backend slot count is live capacity, not permission to fan out; inspect supported runtime admission rather than assuming historical one-slot or two-slot settings. Independent chats may contend; never claim cross-chat serialization without runtime proof. Only the coordinator owns canonical .opencode/work state. Builder/investigator/reviewer children may consult only one foreground critic per package after two failures, inherit the selected model, then return BLOCKED if the changed repair fails. Critic never delegates.


<!-- WATOOM_AGENTMEMORY_SHARED_V1_BEGIN -->
## AgentMemory

AgentMemory provides durable cross-session context.

At task start, use `/recall` when prior context could materially reduce repeated
investigation.

AgentMemory is supplemental context, not proof. Authority order is:

1. current runtime evidence;
2. current source;
3. current tests;
4. current `.opencode/work` state;
5. Git history;
6. AgentMemory.

If memory conflicts with current evidence, current evidence wins.

Never skip reproduction, source inspection, or validation because recalled memory
suggests a cause.

Use `.opencode/work` for task-specific state, evidence, progress, blockers, and
handoff information. AgentMemory does not replace those files.

Do not deliberately save transient information such as:

- raw logs or command output;
- temporary ports, PIDs, timestamps, hashes, or paths;
- screenshots or generated evidence files;
- one-off runtime state;
- speculative hypotheses;
- unverified child-agent conclusions.

Good durable memory candidates include:

- confirmed architecture;
- durable project constraints and decisions;
- verified control, coordinate, or runtime conventions;
- evidence-backed root causes;
- validated fixes and why they work;
- reusable project-specific testing procedures.

Use `/remember` only for concise, evidence-backed facts likely to remain useful
across future sessions.

Automatic AgentMemory capture is supplemental history. It is not a replacement
for source code, tests, Git, or `.opencode/work`.

Child agents may use `/recall` when relevant. Durable final memory writes should
normally be coordinated by the parent/coordinator to avoid duplicate,
speculative, or conflicting memories.
<!-- WATOOM_AGENTMEMORY_SHARED_V1_END -->


## Kali execution routing
For a user-authorized native Kali command, the workflow uses the installed registered Kali MCP route. Multi-stage Kali work may use a serial watoom-kali child, retaining its job ID; never duplicate scans. Builder/investigator/reviewer/critic must respect their own permissions and cannot use delegation to bypass them. User-selected top-level Kali command access remains available. Discover the deployed tool signature; do not substitute workspace commands or credential searches.

<!-- WATOOM-VISION-FIRST-3D-REVIEW-V1-BEGIN -->
## Mandatory 3D appearance review

For every relevant 3D asset creation, modification or acceptance, load the native
`vision-first-3d-review` skill and follow VISION_FIRST_3D_REVIEW version 1.0.0.
Actual current render pixels must reach a verified vision-capable model before
appearance is judged. Geometry supplements vision; it cannot replace it.
Report VISUAL_REVIEW and TECHNICAL_REVIEW independently. Final PASS requires all
required gates PASS and independent final visual review. Missing/failed vision
must be BLOCKED, never a text-only visual PASS. Preserve serial local inference,
Kali isolation, canonical workflow ownership and active investigation evidence.
<!-- WATOOM-VISION-FIRST-3D-REVIEW-V1-END -->

<!-- WATOOM-CREATIVE-PIPELINES-V1-BEGIN -->
## Creative pipeline execution

These are DIRECT native function tools. Call watoom_specialist_list and watoom_specialist_run directly as top-level tool calls. They are intentionally absent from Code Mode execute/search; never call tools.watoom_specialist_run inside execute or treat its Code Mode absence as a missing registration. If the direct function really is absent, report that once without shell/MCP/schema probes.

Use the existing native watoom_specialist_list to discover registered capabilities and readiness once. Authorized watoom_specialist_run takes capability, optional specialistID, a stable job string and typed payload. Read the deployed payload contract before execution. Worker operation names are not native capability names. Source or isolated tests do not establish deployed availability. Report a missing capability once; do not guess tool names, ports, payloads or an alternative MCP route.

Reuse the selected project's scoped native jobs, checkpoint/outbox and artifact publication. Checkpoint project/scope, stable job identity, source asset IDs and hashes, seed, bounded parameters, returned artifact references and last verified stage in .opencode/work at transitions and before compaction. Reconcile an interrupted job and its receipt before resuming; never replay an uncertain operation with a fresh identity. Do not create another scheduler, registry, database, memory service or wrapper.

Start with the existing read-only library. Authorized Toolkit workers see /assets; its host root is /data/ai/assets. Resolve indexed references using the supported catalog and inspect format, dependencies, source pack, compatibility and license evidence before generating replacements. Do not pass arbitrary host paths as asset references. Unknown licenses, unresolved dependencies, deferred checksums and unexamined archive contents remain unknown. Verify selected source checksums before use; refresh necessary bounded catalog batches when new or stale, rather than repeatedly scanning everything. Preserve purchased sources and the engine installation; write derivatives only into approved job outputs.

- Asset QA/optimization: inspect geometry and materials, preserve rigs and clips, repair demonstrated defects, then verify UVs, normals, intended LODs/collision, exports, hashes and actual engine import. Mesh names alone do not prove engine LOD selection or collision.
- World composition: reuse indexed vegetation, rocks and suitable library pieces; record seed/parameters; verify terrain, placement bounds, exclusions, collision and deterministic repeats. Preserve editable procedural source and test the baked runtime scene. Identify procedural fallbacks honestly. Unreal PCG requires its own compatible, validated editor.
- Characters: audit and reuse existing mesh, skeleton, weights and clips first. Fill verified gaps and label derived clips. Require requested Idle/Walk/Run clips, actual motion at different times, deformation checks, export/reimport, engine playback and rendered frames. Clip names and bone counts are insufficient.
- Materials: reuse suitable textures; record provenance and channel conventions for albedo, normal, roughness, metallic and packed ORM. Distinguish procedural derivation from baking or learned generation. Verify UVs, map values, shader connections, export/import and rendered appearance; file existence is insufficient.

Use returned published references and hashes; do not fabricate URLs or assume private worker paths are accessible. Preserve editable source, runtime exports, manifests, validation and rendered views. Apply the existing vision-first review to actual pixels and report technical/visual results separately. Worker exit status and Kubernetes readiness do not establish creative or application acceptance. Keep the existing approval gate before replacing playable assets.

Keep CPU work bounded and serial alongside protected builds. GPU handover belongs to the existing controller; do not load another model, scale services or consume the active Unreal build's resources. Use the currently pinned, validated Unreal runtime and verified pack adapters. Acceptance is scoped to the tested engine/profile/content; new plugins, online providers or untested effects require their own gates. Verified portable work may proceed independently.

Release availability must be established from the current direct native capability listing and successful scoped receipts. These instructions describe the contract and do not establish deployment status. Preserve the technical, visual, engine-compatibility and guarded-release acceptance gates.
Typed contract for the candidate release (use only when listed READY):
- asset.index: payload {"task":"asset-index","limit":256}; repeat bounded batches until scan_complete. Give each successfully advanced batch its own stable job (for example library-index-scan-2-batch-3); checkpoint its result before advancing. Reuse that batch identity for reconciliation, never loop forever on a cached first-batch result or advance after an uncertain result.
- asset.search: payload {"task":"asset-search","query":"tree","limit":8}; optional category/format filters; use returned IDs and actual metadata.
- asset.inspect / asset.optimize: payload {"task":"3d-creative","operation":"inspect" or "optimize","asset_id":"<returned ast_ ID>"}.
- world.compose: operation "world"; choose asset_id plus at most three asset_ids, seed and bounded parameters.
- character.prepare: operation "character"; select an existing compatible rig with Idle/Walk. Missing Run may be derived by retiming Walk and must be labelled.
- material.derive: operation "material"; select an indexed image. Optional texture_resolution is an integer 32..512, roughness/metallic 0..1.
For every call supply the matching capability, specialistID "local-toolkit", a stable job and the payload above to watoom_specialist_run. Never supply operation_id: native dispatch owns it. Shared optional seed is an integer 0..2147483647; timeout is 1..180 seconds for ordinary creative operations, or 1..840 seconds for world.compose with dungeon options. World parameters: size 2..32, resolution integer 4..48, height 0..3, instances integer 1..64, density 0..1. Optimization lod_ratio is 0.1..1. Do not send undeclared parameters.
Required outputs depend on the typed operation and are checked before publication. Ordinary creative work returns editable asset.blend, asset.glb, six renders, creative.json, Godot validation and a disposable scene. Ordinary world composition adds world-layout.json; native dungeon outputs instead include dungeon.umap, asset.glb, perspective.png, manifest.json, validation.json, dungeon-layout.json, dungeon-assembly.json and provenance.json; do not demand an asset.blend or six ordinary renders from that mode. character adds two rendered frames per Idle/Walk/Run; material adds albedo/normal/roughness/metallic/ORM PNGs. Asset search/index return result.json and manifest.json.

<!-- WATOOM-CREATIVE-PIPELINES-V1-END -->


## Native Skills Manager
Use the authenticated application's **Skills** navigation or /skills. The user selects the project directory and agent there, then stages, reviews, validates, approves, installs and enables a candidate. Assignment is separate from enablement. Do not automatically approve or enable the retained collection, turn discussions/tutorials into executable skills, install dependencies, or grant permissions requested by a skill.
At each safe session boundary the available-skills guidance includes enabled, pinned selections for this project and agent. Invoke the direct top-level native skill tool with the exact listed id; it is intentionally absent from Code Mode search/execute. Never guess shell, MCP or wrapper alternatives. Disabled, revoked, changed or unassigned acquired skills must not be loaded. Existing conversation text remains historical after revocation; it is not authority to bypass current discovery or permissions. Version changes require reviewed immutable pins; use **Restore verified version** in Skills rather than editing an acquired source in place.

## Pipeline scope and acceptance
Discover direct native capabilities/readiness and typed payloads once; registered does not mean tested. Only roles with execution authority submit mutating specialist jobs. Read-only investigators/reviewers/critics inspect existing receipts/artifacts and return findings (investigator/reviewer may use bounded asset.search; critic remains read-only without worker dispatch); they do not launch generation, indexing, optimization, staging or publication.
Preserve a stable job identity through dispatch, interruption, reconciliation and publication. A timeout or disconnect is an unknown outcome until the existing job is checked; never replay it under a new ID. Coordinator alone advances canonical checkpoints after verifying actual artifacts and stage gates.
world.compose without dungeon options composes portable geometry. Its dungeon mode accepts only style, rooms, levels, grid, room_size, cell_size and floor_height: it generates a seeded layout, not arbitrary fixed cells, doors, notes, monsters or gameplay. A board-exact reconstruction such as HeroQuest must preserve its certified layout and use an explicitly supported project-local assembly path; never invent fixed_layout fields, replace it with random rooms, or claim a geometry receipt proves gameplay.
Use one verified anchor for Builder/Forge, two distinct compatible anchors for mixed; source pack availability does not establish an adapter. Native dungeon outputs differ from ordinary creative outputs. Verify required editable map, geometry, collision/navigation, import and actual render gates for the selected mode.
Unreal GLTF exports supported geometry/materials, not Blueprint gameplay or GeometryCache animation. Hyper offline acceptance does not prove HOI online multiplayer or Godot combat logic. BloodFX static loading and synthetic converter tests do not prove real animated/rendered conversion. Nwiro/POT Linux, CharacterPreviewer and newly acquired assets remain individually gated; never infer whole-pack support from a sampled mesh.
Use project-local output and derivatives, read-only purchased inputs, existing global Catalog and native jobs/publication. GPU tasks use the audited controller's exclusive ownership/admission/fencing/recovery; never direct-scale services, interrupt active work, bypass a lease, or create another registry/queue to get around a blocked route. Report technical, visual and gameplay gates independently as PASS/FAIL/BLOCKED/NOT TESTED, with the last actual evidence.
