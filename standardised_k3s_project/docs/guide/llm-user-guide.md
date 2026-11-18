---
title: User Documentation
nav: LLM user guide
summary: Using projects, sessions, agents, models, memory, images and specialist jobs, with practical task examples and troubleshooting.
---

## What the platform provides

WatooM Code is the browser workspace for local AI-assisted coding, investigation, writing and reviewed asset workflows. It connects to local inference and installed tools. Glance is the entry point for service links, documentation, the Model Manager, job reference and pipeline prompts.

Use `https://watoom-code.internal.homelab.example` on the approved internal network and sign in with your existing credential. Open `https://glance.internal.homelab.example/guide/llm-api.html` for this documentation set. Do not share passwords or paste them into tasks. If an address is unreachable, check approved network access with the operator; do not alter DNS/firewall settings to work around it.

The platform can help execute work, but availability of a skill or model is not a guarantee that every operation is installed, authorized or live-qualified. Read the result and its evidence before using an output.

## First successful task

1. Open WatooM Code and choose the intended project/location. Check the full directory before asking for edits.
2. Start a session with `watoom-workflow` for a multi-step task. Use an existing session to continue the same work.
3. Keep the primary Swift model unless the task needs an explicitly supported alternative.
4. State the outcome, affected scope, constraints and how you will judge success.
5. Watch native status/tool/job activity. Respond to permission/form requests in the UI.
6. Review the final changes, tests and artifacts. Approval for a draft or experiment is separate from approval to deploy or publish.

Example:

```text
In this project, investigate why the save button fails after a refresh.
Inspect the implementation first. Preserve unrelated changes.
Fix the smallest proven cause, run the relevant checks, and report the files changed.
Do not deploy or push without my approval.
```

A message acknowledged or queued is not finished work. An active specialist can legitimately make the interface wait. Avoid submitting the same job again simply because no text has appeared yet.

## Projects and files

| Group | Typical work |
|---|---|
| `/data/ai/projects/games/<project>` | Game/engine projects |
| `/data/ai/projects/work/<project>` | Work projects |
| `/data/ai/projects/writing/<project>` | Writing and research |
| `/data/ai/projects/images/<project>` | Image/review projects |
| `/data/ai/projects/homelab/<project>` | Infrastructure source |
| `/data/ai/projects/llm/<project>` | Model/agent/pipeline tooling |

The same approved path is used inside the application. Shared assets and engine installations have different permissions; owning an asset does not authorize editing its original library copy. Ask for project-owned derivatives when appropriate. Do not move existing sessions or replace databases to change a project binding.

A good task names the project and output location. If an agent reports a blocked scope, review the path/authorization instead of asking it to bypass guards. Some shell/code operations remain unavailable until the relevant sandbox is qualified; a guard is not proof of complete filesystem isolation.

## Choosing an agent

| Agent | Use it for |
|---|---|
| `watoom-workflow` | Planning, coordination, task routing and integration |
| `watoom-builder` | Scoped implementation and build work |
| `watoom-investigator` | Diagnosis, source reading and evidence gathering |
| `watoom-reviewer` | Reviewing implementation, tests and evidence |
| `watoom-critic` | Independent critique through permitted escalation |
| `watoom-creative-writer` | Long-form creative work on the configured creative route |
| `watoom-kali` | Separately authorized security work in its own primary session |

The coordinator delegates bounded packages and retains canonical progress. Continue the existing child session when a child is still running. Development agents do not receive Kali tooling through ordinary delegation. A request to “ignore the guard” is not a valid repair.

Useful examples:

```text
Investigate the error, collect one targeted evidence round, and explain the proven cause before proposing a change.
```

```text
Review this diff for correctness and regression risk. Return actionable findings with file references; do not edit.
```

```text
Plan and implement this feature within the selected project. Keep existing user data and show how the acceptance criteria were checked.
```

## Models and response behavior

The normal primary alias is `watoom/swift-qwen38-coder` in the native application and `swift-qwen38-coder` in the router. The app budget is 100,000 context tokens and 4,096 output tokens; the backend capacity is 131,072. These are different limits, so a backend capability listing does not mean the app will use the whole capacity.

Only one large managed model is resident at a time. A model can be listed but unloaded; selection can wait for a controller-mediated switch after active work drains. Do not repeatedly click model loads or ask an agent to scale pods. The small embedding service is independently managed.

Current primary tuning uses turbo KV, fixed draft depth 5, CUDA graphs, ubatch 1024 and a 300 W configured cap. Threads, checkpoint defaults and 4 GiB prompt cache were retained. Users do not need to reproduce these flags in prompts. Do not change temperature/reasoning/precision just to imitate a benchmark number.

Long fresh requests spend time reading the prompt. Continuations often reuse cached state, but agent/session changes, prefix edits or checkpoint rollback can require re-prefill. A past cache finding does not prove every delay has the same cause. Report the session/time/action to the operator rather than guessing a cache fix.

## Continue, interrupt and recover work

Use the same session to continue the same objective. Give concise steering: the correction, constraint or next result you need. A status question does not need a duplicate task. If work must stop, use supported native interrupt/cancel controls and wait for task-owned jobs to settle.

After reconnecting, inspect durable messages/inbox/job state. Browser events can be missed while disconnected. A queued input may still be admitted; do not assume a failed connection means nothing happened. Report stuck activity with session/job ID and approximate time. Do not delete inboxes, clear controller state or kill unknown processes.

For consequential actions, state authorization explicitly: a trial is not production adoption; preparing a PR is not pushing/merging; finding an asset is not purchasing/downloading it; generating an image is not overwriting existing project assets.

## Skills, search and memory

The [job reference](/guide/job-reference.html) describes installed skills and example requests; [pipeline prompts](/guide/pipeline-prompts.html) provides reusable task formulations. Skill selection loads guidance. It does not install plugins, grant permissions, purchase assets or activate absent backends.

Web search uses the configured search service. Ask for sources when factual currency matters. AgentMemory is configured persistent recall; it is not the same as the model's active context, prompt cache or a backup. A remembered statement should still be checked against current source when it affects a change.

Do not put passwords, API tokens or private recovery grants into memory or a task. For facts that must persist, prefer maintained project documentation/checkpoints with the correct scope rather than relying solely on conversational recall.

## Images and visual evidence

Use the verified vision-capable model for image review. Name the source image/artifact and desired inspection. The runtime may require a receipt tied to the exact path/hash/model before further processing. Review is based on actual pixels, not a description or OCR substitute.

Example:

```text
Inspect the rendered image at the project capture path.
Report visible clipping, lighting and pose issues with concrete observations.
Preserve the source asset. Do not claim a visual pass from file existence alone.
```

Changing an image creates new evidence; an old receipt does not approve a different hash. A read-only reviewer can return the structured receipt without gaining write permission. A physical projector/display is distinct from the model's vision-projector component. Turning a display on may change GPU memory/load; tell the operator if it happens during a qualification run.

## Specialist jobs and assets

Toolkit/engine/image/Mesh workflows execute bounded jobs, often asynchronously. The application and worker can finish different stages at different times. Keep the existing request/job ID for status/recovery; uncertain submission is not permission to create a duplicate.

For Blender, Godot or Unreal work, specify the project, source asset, output format, constraints and engine validation needed. The owning workflow may require a reviewed task contract, read-only source libraries, hash snapshots and an artifact receipt. An export file alone is not proof of engine import or visible correctness.

For a game starting point, ask the coordinator to search the game-template catalogue for the genre and target engine, report the selected template's licence/revision, copy it into this project, and verify import before implementation. The game-template or game-blueprint prompt from Glance's Pipeline Prompts page prepares a scoped request; it does not itself launch a build. For terrain, provide a place name or coordinates and a project-local Godot output path. The terrain skill uses open elevation data and generates a scene and float heightmap; use its `height_at()` API to place objects rather than estimating ground height. See Games and [Custom extensions](llm-extensions.md#game-authoring-templates-terrain-and-asset-discovery).

For an owned Fab asset, ask for the advisor's supported pipeline and check format/version/dependency facts before requesting acquisition. Downloads require explicit owner approval for the exact asset and project. An Unreal pack export can be requested through the native game worker; follow its job ID and receipt, then separately verify import and appearance. For an owned MetaHuman `.mhpkg`, use the `watoom-metahuman` skill; it supports Unreal installation and a Godot export path, with a separate optional RIG GPU skin-map stage. Godot cannot animate MetaHuman faces through RigLogic, and the target-engine licence still needs owner review.

Examples:

```text
Create a project-owned derivative of this asset for Godot. Preserve the source,
validate scale/materials and import, and provide a rendered preview plus evidence.
```

```text
Render a preview from the existing rig and animation. Inspect the actual controls,
use the bounded capture workflow, and do not rebuild or overwrite the source.
```

Security work starts a separately authorized Kali session. Model installation and infrastructure changes use operator workflows; ordinary tool availability does not confer administrative access.

## Model Manager

Open Glance, then the existing LLM Lab/Model Manager link. Sign in with its separate operator-managed credential when authorized.

1. Inspect a supported repository/immutable revision and variant.
2. Review exact download size, settings, model limits and dependencies.
3. Choose an explicitly compatible installed base for LoRA/checkpoint cases that require it.
4. Approve download/setup only for the intended scope.
5. Wait for the existing job and distinguish downloaded, configured, registered and tested states.
6. Run an authorized generation acceptance before relying on a new model.

Do not install arbitrary remote code. An unsupported architecture cannot be fixed by changing a label. Removal defaults to preserving files and requires a fresh confirmation; confirmed unshared-file removal quarantines rather than silently purges. Do not repeat an interrupted install under a new identity without checking the first job.

## Permissions and approvals

Read each request's action, path and consequence. Grant only the needed scope. Sensitive operations include infrastructure deployment, model precision changes, deleting/moving shared data, installing remote software, purchases and external publication. Preserve project and owner constraints across follow-ups.

If a guard rejects something, ask for the actual reason and the supported recovery path. Do not ask the agent to erase durable evidence or invent credentials. When a tool is unavailable, an honest blocked result is preferable to a claimed success from an unrelated substitute.

## Understanding a final result

A useful completion report states what changed, where, how it was checked, artifact locations and unresolved limitations. Separate unit tests from real native/GPU/engine acceptance. Check whether the source was only prepared, committed, published or actually deployed. A successful rollout is not all acceptance gates.

After a recognised Godot/Blender error or nearby API uncertainty, a `Reference lookup` block may provide versioned card data. Treat it as reference, not a command to run; check the installed engine/API where the distinction matters. The trigger is unit-tested and simulated, but has not yet been observed on a live agent session.

For inference changes, expect measured representative latency/throughput, long-context/tool/vision checks, resource headroom, soak/error audit, clean restoration and router evidence. Current gains are measured on the stated workload and hardware, not a promise for every prompt.

## Troubleshooting

| Problem | User action |
|---|---|
| Sign-in fails | Verify the correct app and credential; ask operator to check auth/origin/TLS |
| Model says unavailable/busy | Wait for current work; report time/model/session; do not force switching |
| Input queued without a reply | Inspect existing activity/job; avoid duplicate submission |
| Continuation suddenly slow | Report session and preceding agent/model switch; let operator inspect token/cache metadata |
| Permission/scope blocked | Confirm the intended project/path and explicit authorization |
| Image review blocked | Supply the exact image and let verified review/receipt complete |
| Specialist still running | Follow the existing job ID and worker status |
| Files generated but result unclear | Ask for actual import/render/test evidence and limitations |
| Page or tool differs from docs | Report URL, action, source/version if known and sanitized error |

Never paste credentials or raw private chat/database exports into a support report. Session/job IDs, timestamps, model name, operation and sanitized error usually suffice.

## Further reading

See the [LLM API & reference](llm-api.md) for integration contracts, the platform source map, current runtime values and operations/administration.
