# WatooM Code production operations

Production baseline: **19 October 2026, Australia/Brisbane**. Legacy canary policy and Blender status updated **20 October 2026**. This retained document filename and its Glance compatibility anchor do not identify the old OpenCode V2 deployment as the current GUI.

## Entry point and stable configuration

Use https://watoom-code.internal.homelab.example. Current application resources retain namespace watoom-code and deployment watoom-code. Exact immutable application/Toolkit images, engine pins and acceptance limits are maintained in [production pipeline operations](WATOOM_UNREAL_DUNGEON.md).

WatooM Code Swift uses **100000 context / 4096 output**. The authoritative role default is watoom_code_swift_context_tokens: 100000. Swift backend capacity remains 131072 with q4_0/q4_0 KV; that larger capacity is not the application default. The template and preserved-state updater use the same IaC variable.

The production installation preserves 57 skills, seven agents, SearXNG, existing MCP connections and the established native specialist path. Ollama/Open WebUI are not part of the active GUI workflow.

## Legacy canary and Blender status

The legacy opencode/opencode-v2-canary is suspended at zero replicas; production remains watoom-code/watoom-code. Its IaC now defaults to stopped and disables legacy production promotion. Normal applies do not rebuild or start it. Existing persistent data and service selectors are retained.

See [Blender production status and legacy canary policy](BLENDER_PRODUCTION_STATUS.md) for the guarded shutdown, immutable candidate, real engine acceptance, five Fab acquisitions and remaining production gates. The Blender builder is not yet promoted. The magpie direction is funny and stylized, with occasional darker moments; visual acceptance remains separate from technical playback.

## Project work and coordinator handoff

Select the intended project before starting work. Keep generated files, logs, captures and task state within that project's own directory; use its .opencode/work and validation/capture areas. Shared source assets remain read-only. Do not scatter experiments into /data/ai/projects or copy an entire shared asset library into every project.

The coordinator owns canonical task state and validates returned child evidence. Do not redelegate an unresolved child or retry the same failed cycle without a changed hypothesis or new evidence. Use the existing critic escalation for repeated rejection, looping or excessive attempts.

Builder, investigator and reviewer may call only the critic through the established foreground child exception. The critic is read-only and cannot delegate further. Preserve existing depth, permission and handoff guards.

## Agent context routing

The 19 October context audit found an 8192/2048 discovery fallback. The current user-selected standard is **100000 context / 4096 output for every offered language model**, including active-model, with a lower published context limit applied when provided. All seven managed agents now inherit the session-selected model rather than pinning Swift. Critic, vision, permission and project-containment rules remain intact. q4_0/q4_0 is the proposed backend KV default; these application limits do not silently reconfigure existing backend deployments or certify unknown tool/vision capabilities. LLaMA-Mesh retains its separate specialist profile.

Vision receipt recovery preserves the image gate: a pending visual child may resume its same session to return matching JSON evidence even after parent error escalation. It cannot start another work child, bypass critic review, substitute OCR, or invent pixel observations. Runtime notes supply the exact image path/hash/model. Checkpoint writes receive a path-specific error rather than a misleading JSON error. Read-only agents return JSON as their final reply. Guard packages use content-addressed directories so configuration reload selects the new code while retaining session state.


Context limits belong to the resolved model, not a private per-agent setting. Choose explicit Swift for the 100K baseline; do not assume an active-model alias inherits Swift's configured budget. Deliberately selecting another model uses that model's limits. Existing sessions can retain their original model selection; refresh a session through supported controls after checkpointing when required.

## Vision and evidence

Inspect actual pixels when a task requires visual acceptance. A rejected vision receipt is a blocker to diagnose, not permission to bypass the gate through OCR, repeated receipt rewrites or invented model identity. Record the exact receipt-path/model-verification error and escalate through the existing critic route.

A successful tool call, metadata manifest, model download or Kubernetes rollout is not proof that a feature works. Keep PASS, FAIL, BLOCKED and NOT TESTED separate, including what was actually observed.

## Native creative and game workflows

Use existing watoom_specialist_list and watoom_specialist_run direct native functions for specialist discovery/execution; they are intentionally outside Code Mode. Follow [Unreal/dungeon instructions](WATOOM_UNREAL_DUNGEON.md) for seeded geometry, complete-project opt-in, shared catalog selection and accepted outputs.

world.compose is a geometry pipeline. Complete Hyper gameplay projects use the maintained unreal-project.yml opt-in path. Offline acceptance does not establish HOI/Steam/EOS multiplayer behavior. Preserve authored /Game namespaces and verify actual map, collision/navigation, rendered output and conversion where required.

## Production changes and recovery

Future defects belong in authoritative source and the normal IaC/build path, with affected regression checks and versioned artifacts. Prepare a concrete snapshot, validation and rollback before a guarded promotion. Preserve active jobs, actual inference and durable GPU ownership; never force a rollout, GPU swap or recovery over a live owner.

Do not use historical deployment commands or mutable image tags as a replacement for current pins. Model Manager integration was explicitly approved and deployed; preserve its separate inference and restoration acceptance gates.

## Historical reference

The [13 October frozen baseline](baselines/pre-new-agent-engine-20261013.md) preserves the old OpenCode V2 resource names, runtime configuration and qualification date. Its 102400/63488 client budgets and legacy agent/MCP observations are historical. Use current state for the production release.
