# G3H production integration

The controller is the sole GPU replica writer. Existing admission and acknowledged
storage barriers must remain installed. Do not repeat ownership initialization or
run retired cutover scripts on an activated system.

OpenCode V2 uses the existing ConfigMap selected by OPENCODE_CONFIG. Its subPath
mount requires a canary rollout after registration changes. Mesh is registered
under mcp.servers with codemode enabled and timeout.execution=3600000 ms.
The stdlib Python MCP adapter preserves asynchronous operations and provides
bounded synchronous generate with a required stable request_id. The pipeline
restores Qwen before CPU cleanup and successful job completion. Request-ID
receipts prevent a second job; never allocate a new ID after an uncertain outcome.

The authoritative bridge/adapter source is ansible/roles/llm-model-lab/files.
The OpenCode reconciliation role installs those files and refreshes registration
without replacing other agents, providers or credentials. The generic canary
helper copy also includes the same adapter. The bridge depends on the controller.
Model-lab application requires the existing reviewed activation gates and does
not reinstall the legacy router.

Production defect fixed: Runtime's cutover-proof iteration must use
deployment_identity, preserving the injected process-identity callable. The
production-proof regression covers worker identity acquisition.

## Verified acceptance, 12 October 2026

Request: G3H-prod-d40ec0e462894f3e
Job: 20261012T120132Z-04c4b829
Evidence: /data/ai/archive/projects-20261029/pipelines/mesh-switch-coordination/g3h-unattended-runs/production-20261012T120112Z
Artifact: /data/ai/assets/generated/opencode-mesh/g3h-cube-fab2c4760ae1420b97e4ea4e2293f519/game-ready/asset.glb

OpenCode searched the Mesh namespace, invoked generate once, received validated
assets, then answered QWEN_POST_G3H_OK through restored Qwen. Controller audit
records QWEN_STOPPED, MESH_READY, ASSET_SAVED, MESH_STOPPED, QWEN_READY and
OWNERSHIP_RELEASED. The activation path checks released GPU memory before any
GPU model is started. Final owner is null, phase qwen-ready, uncertain false.
One receipt maps to one completed job; duplicate submit returned the same job.
OBJ has 8 vertices and 12 faces; GLB is 1468 bytes, one scene/mesh and 24 exported
vertices. Structural/topology/finite-value checks passed. This is generated
prototype geometry without authored UVs or textures.

102 offline tests passed, including recovery, fencing, rollback conflict,
durable state, MCP and production proof coverage. Two current live server
dry-run controls denied unauthorized deployment and scale mutations. Existing
33 admission controls and all 11 acknowledged storage barriers remain preserved.
The narrow Mesh Ansible playbook deployed successfully.

## Recovery and rollback

Keep /data/ai/archive/projects-20261029/pipelines/mesh-switch-coordination/g3h-snapshots/20261012T070337Z
and its verified repository.bundle. It includes router, pipeline, service,
configuration and agent backups. Preserve current durable state and cutover proofs.

Read controller status and worker liveness before taking recovery action.
Never manually edit durable ownership, force replicas, or bypass admission.
The installed watoom-llama-mesh-recovery.service runs controller-mediated
recover-queue. It resumed no jobs and recovered no orphan owners on the final
idle verification. Existing g3h_ops recovery/rollback functions refuse live or
uncertain owners, fence ended-owner mutations and gate config restoration on
real primary inference. Use a restoration record matching the configuration
being changed; missing records or independently edited fields fail closed.

A source/config rollback must preserve controller ownership enforcement and
the narrow router permissions. Do not apply historical router RBAC or scaling
writers from a backup. Restore only reviewed affected fields after Qwen is
safely ready and Mesh ownership has been relinquished.

NOT TESTED live: forced GPU crash, host reset, disruptive rollback. Their offline
recovery contracts pass; no disruptive failure was induced during acceptance.


## Model picker switching and deployment fingerprints

The OpenCode chat picker stores the model for the next submitted turn. The
router uses that explicit model ID to request a controller-mediated GPU switch;
models are loaded one at a time. A listed model is not necessarily loaded.
Image checkpoints and the Mesh geometry worker use their dedicated workflows.

Any approved deployment specification change (including RAM-cache environment
variables or a rollout restart annotation) must also reconcile that deployment's
`deployment_identity` fingerprint in the durable controller configuration.
Otherwise the controller correctly refuses mutation and can enter
`recovery-required`, causing model requests to return HTTP 503.
Do not disable identity verification, remove ownership state, or force scaling.

Before accepting a new fingerprint, verify the deployment UID is unchanged,
match the old fingerprint to a retained Deployment snapshot, and review the
complete old/new specification diff excluding replicas. Preserve a configuration
backup and accept only the reviewed change. Restart the controller to load its
configuration, then let the same authenticated router owner reconcile through
`POST /models/load` with the primary model. A different or live worker owner
requires the existing liveness-gated recovery procedure. Check controller status,
zero uncertainty, backend inference and catalog consistency afterward.

On 2026-10-21 the retained RAM-tuning baseline matched the old Swift fingerprint.
The reviewed changes were the 6144 MiB host prompt-cache setting in the server
and init container, plus the restart annotation. Only the primary fingerprint
was refreshed; the RAM tuning and other deployment identities were preserved.
Evidence and bounded model-load results are retained at
`/data/ai/helper-scripts/reports/model-availability-20261021/`.

## Slow model loads (2026-11-19)

The models load from the spinning `/data` disk. A 27B gguf took 220-320 s in early November and 360-450 s+ by
mid-November (slower reads, swap full, a 614-extent uncensored file). Three limits must stay above the real load time:

- each model Deployment's `startupProbe` (10 s x 60-90; liveness alone killed pods mid-load and the switch went to
  `recovery-required`),
- `startup_timeout` in `gpu-controller.json` (1200 s; it covers init + load),
- the client: watoom-code `providers.watoom.settings.headerTimeout/timeout` (`enable-router-discovery.py`).

The primary's init container hashes its gguf once and records size/inode/mtime/ctime in
`/data/ai/models/verified/<model>/`; it re-hashes only when the file changes (before, every start re-read 15 GB).
Any change to a pinned Deployment's spec needs `scripts/gpu-controller-repin-primary.py --name <deploy> [--recovery] --apply`
afterwards, and the role copy `ansible/roles/llm-model-lab/files/gpu-controller.json` kept equal to the live config.
The router waits (`SWITCH_WAIT_SECONDS`, 900) for an in-flight switch instead of answering 503 to requests that cannot switch.

## Adding a model after the cutover (2026-11-19)

Do not add a hand-written model Deployment to `gpu-controller.json`. The controller refuses to start when a
`deployment_identity` entry has no acknowledged record in `cutover-proof.json` (`cutover identity proof does not match
deployment`) and only `llama-cpp-mm-*` deployments may enrol through the managed ledger. On 2026-11-19 two hand-written
entries (a Qwen3.8 OpenCode LoRA and the GLB 3D Coder) crash-looped the controller for ~2 min until the previous config
was restored. The cutover proof is a security barrier: never edit it to make an entry pass.

Add new models through Model Manager (`tools/model-manager`): it creates the replicas-0 Deployment, enrols it through
the controller's lifecycle API and publishes the router catalog. It covers GGUF models, GGUF LoRA adapters on an
installed GGUF base (`--lora`) and MTP speculation proven from the GGUF header (T-0086).
