---
title: Software design — cross-project integration
nav: Software design
summary: How the separate WatooM projects — homelab IaC, the LLM/agent platform, games, images and media — are wired into one system, with the real code at each seam.
---

## What this document is

The WatooM projects are developed separately — `homelab/` (this IaC repository), `llm/`
(WatooM Code, native agents and model serving), `games/`, `images/` and the media stack — but
they run on **one host, one GPU and one k3s cluster**, and they share a small set of spines that
make them a single system. This page documents those seams with the actual code at each one, so a
reviewer can trace a request from an agent turn through to a GPU, a rendered frame, a Prometheus
series or a published artifact. It complements the component-level pages ([Platform](platform.md),
[AI platform](ai.md), [WatooM Code](watoom-code.md), [Monitoring](monitoring.md)); here the subject
is the **integration**, not any one component.

Authority order is unchanged from the rest of the guide: live inspected state and acceptance
evidence first, then the owning IaC/source and immutable pins, then this document. Paths are relative
to `standardised_k3s_project/` unless noted.

## The shared substrate

```text
                         one Fedora host · GPU (20 GiB) · single-node k3s
   ┌──────────────┬───────────────┬───────────────┬──────────────┬───────────────┐
   │  homelab IaC │  LLM platform │     games     │    images    │     media     │
   │  (this repo) │ watoom-code + │  Godot/Unreal │  Blender +    │  *arr, Jelly- │
   │  ansible +   │ agents + llm- │  capture +    │  render +     │  fin, downloa-│
   │  manifests   │ router + GPU  │  review       │  owned assets │  ders         │
   └──────┬───────┴───────┬───────┴───────┬───────┴──────┬───────┴───────┬───────┘
          │               │               │              │               │
          │        ┌──────┴──────────────────────────────┴──────┐        │
          │        │  A. OpenCode agents + native workers        │        │
          │        │  B. coordinator-guard (evidence/receipts)   │        │
          │        │  C. llm-router + GPU-ownership controller   │        │
          │        └──────┬──────────────────────────────┬──────┘        │
          │               │                              │               │
   ┌──────┴───────────────┴──────────────────────────────┴───────────────┴──────┐
   │  D. Glance observability spine (helper-api ← Prometheus · Loki · dcgm · mktxp)│
   └──────────────────────────────────────────────────────────────────────────────┘
```

Five seams carry all the cross-project traffic: **(A)** agents dispatching bounded native workers,
**(B)** the coordinator guard that turns worker output into trusted evidence, **(C)** the inference
router and GPU-ownership controller that every model call shares, **(D)** the Glance observability
spine, and **(E)** the change-control spine (graders + the publishing split). The rest of this page
is one section per seam.

## A · Inference routing and GPU ownership


Every model call from every project — an agent coding turn, a game asset's pixel review, an image
caption — resolves through the **`watoom` OpenCode provider** to one service, `llm-router`
(`llm-router.llama-cpp.svc:8000`), which fronts many llama.cpp backends that cannot all be resident
on the single 20 GiB GPU at once. The router arbitrates with **leases**: a request for a model that
is not the current GPU owner triggers a switch, held for the duration of the call.

```python
# ansible/roles/llm-model-lab/files/gpu-controller-router.py  (production router)
canonical = MODEL_ALIASES.get(model_id, model_id)
lease = request_account.call('begin-inference',
                             deployment=MODELS[canonical]['deployment'],
                             allow_switch=allow_request_switch)['lease']
# ... proxy the OpenAI-compatible call to the owning llama-server ...
finally:
    if lease:
        try: request_account.call('end-inference', lease=lease)
        # Durable lease intentionally survives uncertain cancellation.
```

A model is usable for vision only when the OpenCode config marks it so; the capability is applied
after config render by a narrow, schema-checked step, never inferred from a model name:

```python
# ansible/roles/watoom-code/files/enable-verified-model-capabilities.py
models = document.get('providers', {}).get('watoom', {}).get('models', {})
# accepts only input in (['text'], ['text','image']) and output ['text']
models[name]['capabilities'] = capabilities   # e.g. input: ['text','image']
```

**Design consequence that bites in practice:** because the GPU is shared, a vision request can
return `model=null` *transiently* when a text coder owns the GPU at that instant — not a broken
route. The backend itself must have its multimodal projector loaded on the GPU
(`LLAMA_ARG_MMPROJ=/models/mmproj-BF16.gguf`, `LLAMA_ARG_MMPROJ_OFFLOAD=false` in
`manifests/10-infrastructure/llm/llama-cpp-swift-qwen38.yml`), which fits within the 20 GiB cap and
is the preferred full-residency placement. Operator reconciliation of a vision block is therefore a
*verification* of this path, not a config rewrite.

## B · The coordinator guard: worker output → trusted evidence

Games, images and any visual work converge on one rule: **a rendered frame is only accepted after a
verified, independent, pixel-only review** — geometry, filenames and author claims never establish
visual acceptance. The policy lives in the agent contract and the enforcement in the guard.

```text
watoom-builder ──capture-scene request──▶ native Godot/Unreal worker
     │                                          │ renders ground_close.png (+sha256)
     │   .opencode/worker-requests/<id>.json     ▼
     │   status: CAPTURED_VISUAL_REVIEW_PENDING
     ▼
coordinator-guard intercepts the next model turn that carries the image
     │   rewrites it into an ISOLATED pixel-only review (strict JSON schema)
     ▼
verified vision model (via seam A) ──▶ visual-review.json {verdict, observations, defects}
     │   validated against the pending image's exact sha256 + model identity
     ▼
reconcileCompletedVisualReview records it; a hard-stopped child needs a recoveryGrant nonce
```

The guard does not trust the agent to review its own work honestly; it **constructs** the review
turn so scene history is excluded and the model can only emit a schema-shaped receipt:

```javascript
// ansible/roles/watoom-code/files/coordinator-guard/index.js  (isolatedReviewBody)
const next = {...body, messages:[
  {role:"system", content:"Independent pixel-only visual inspection. "
     +"Task history and author claims are intentionally excluded."},
  {role:"user", content:[{type:"text", text:instruction}, image]}],
  temperature:0, parallel_tool_calls:false};
next.response_format = {type:"json_schema",
  json_schema:{name:"isolated_pixel_review", strict:true, schema}};  // from reviewSchema()
```

`reviewSchema()` pins `image_path`, `image_sha256` and `model` to the exact pending values and makes
PASS reachable only with a usable frame and zero defects — the guard **never rewrites a verdict** to
turn a rejection into a pass. When a child reviewer is hard-stopped, only an explicit, single-use
operator grant (bound to the parent/child session and the image hash) can release it:

```javascript
// recoveryGrant: a nonce-bound, one-time release for the exact blocked child
return (options?.visualRecoveryGrants || []).find(g =>
  g.parentSessionID===sessionID && g.childSessionID===state.child &&
  g.image_sha256===v.sha256 && /^[a-f0-9]{64}$/.test(g.nonce) &&
  !(state.consumedRecoveryGrants || []).includes(g.nonce));
```

Accepted images flow into the images project for curation via `archiveViewedImage(... root=
"/data/ai/projects/images/review")`, which is the seam from **games → images**.

## C · The observability spine

Glance is where every project becomes visible. The `helper-api` container composes read-only
telemetry from the cluster and serves both the guide's live cards and the
[command center](/command-center/). It talks to **Prometheus** (host, kube-state, dcgm GPU, mktxp
router) and **Loki** (firewall and security logs); nothing in the page path writes to the cluster. The command center's **Worker output** section shows Bazzite and RIG jobs, MOSS Image jobs (with the generated image) and LLaMA-Mesh jobs shown as Meshy (with the GLB model). Previews can be collapsed per job or hidden for all jobs with the Previews button; hidden previews are not loaded, and the choice is remembered in the browser. A performance panel reports the router's last 24 hours by reasoning level: requests, latency p50/p95, time to first output, errors and 503s (held in router memory, cleared when the router restarts; token rates show no data). A root timer (`watoom-worker-status`, `tools/watoom-code/worker_status.py`, installed by `playbooks/worker-status.yml`) reads the job receipts, the RIG transfer jail and SSH journal, asks Bazzite one status question over the existing worker access, and reads MOSS Studio's JSON sidecars and matching PNGs from `/data/ai/projects/images/moss-image/output/`. It writes one sanitised snapshot (project folder names and clipped failure reasons only) that the helper-api mounts read-only and serves as `/cc/workers`. Meshy is not an active local producer and has no local job record source; the local Toolkit excludes its paid provider route. The LLM performance by reasoning effort panel uses the router's in-memory rolling 24-hour request observations for request counts, HTTP errors/503s, end-to-end latency percentiles, and streaming first-event latency. Prompt and generation token rates remain “no data” because the current router response path has no reliable per-request token timing source; observations reset when the router restarts. The snapshot includes per-source collector health, Bazzite's last success/failure streak, RIG quiet time, and structured failure stage/code fields. A `RUNNING` receipt is labelled `stale_running` in the display after its prepared deadline (default 1800 seconds) plus 180 seconds when evidence is missing or its declared unit is not active; the collector does not change receipt status or replay work. The lab accepts old RIG workers, while updated Unreal-lane workers optionally upload `uploads/ue-<job>/progress.json` with `FETCHING`, `RUNNING` or `UPLOADING`. The collector also writes atomic host textfile metrics for worker health, busy state, 24-hour outcomes, stuck-job age/deadline and collector freshness. Four staged Prometheus alerts cover a stale snapshot, sustained Bazzite outage, a job beyond twice its deadline and a high failure ratio. These source rules are not active until the monitoring manifest is reviewed and applied. Each recent job also lists what it produced: capture and texture images appear as thumbnails that open a viewable copy, and GLB models get a **View 3D** tile that opens `/command-center/viewer.html` in a new tab (orbit, zoom, animation picker, dimensions, download). For this the collector re-encodes up to 8 images per job (a 360 px thumbnail and a 1600 px copy) and copies up to 3 GLBs of at most 40 MB under `worker-status/media/<job>/`; only the newest 30 jobs keep media, files are read only from allowed project, report and artifact folders without following symlinks, and the helper serves them read-only (`/cc/workers/media/...`, validated names, image/video/GLB types only). Other output files such as `.dna` are listed by name and size. The viewer is Google's model-viewer 4.4.0, vendored under `config/glance/command-center/vendor/` with its license and hash (no CDN); it shows self-contained GLB only, so FBX or Blender files are not previewed.

```python
# config/glance/helper.py — one source, many back ends, fail-soft
def cc_metrics():
    ...  # stats() + node_load1 + cc_gpu() + cc_wan()
def cc_gpu():   return {"util_pct": first_prom_value('max(DCGM_FI_DEV_GPU_UTIL)',0), ...}
def cc_wan():   return {"rx_bps": first_prom_value(
                   'sum(rate(mktxp_interface_rx_byte_total{name="wan-uplink"}[5m]))*8', 0), ...}
def cc_attacks():   # Loki: firewall drops -> offline GeoIP -> country counts for the world map
    data = loki_range('{job="router-firewall"}', limit=1500, hours=6)
```

Two delivery paths meet here and are worth distinguishing: the **guide** is served from a `hostPath`
onto the operator checkout, so a committed doc change is live without a redeploy; `glance.yml` and
`helper.py` are the **source of truth** rendered into configmaps by
`scripts/render-glance-configmaps.py` and need an apply + pod restart (configmaps do not hot-reload).
The command-center assets (and the vendored offline GeoIP table) ride their own `hostPath`, so page
iterations are live on commit after the first apply.

## D · The change-control spine

Across all projects, "it works" is a grader's verdict, not a model's claim, and *where* a validated
change lands depends on who made it.

```python
# tools/watoom-code/verification_loop.py — deterministic, read-only, never touches the cluster
def run(args, cwd=None):
    proc = subprocess.run(args, stdout=PIPE, stderr=STDOUT, timeout=TIMEOUT)
    return proc.returncode, proc.stdout.decode(...)   # the grader's exit code is the verdict
# graders: yamllint, ansible-lint, ansible-playbook --syntax-check, bash -n, py_compile, JSON parse
```

The **publishing split** is the integration contract between the autonomous agents and the owner:
WatooM-Code/OpenCode models commit to their agent branch and integrate only into `dev` after
validation — they never touch `main`. The owner's operator assistant publishes explicitly reviewed
paths to `main`. The project-space picker (`watoom-spaces.json`, rendered by the `watoom-code` role
from `watoom_code_project_spaces`) is what lets one agent GUI group work from every project directory
without any project leaking into another's scope.

## E · The asset build pipeline (images and games)

Heavy Blender/Unreal work is dispatched through the `watoom-fab-owned-assets` skill and its
`request_pipeline`, and the genuinely heavy exports are offloaded to the Bazzite workstation via the
skill's `remote.py` rather than run on the homelab host (which owns production inference). The output
is a published artifact with a hash, which re-enters seam B for visual review before anything is
accepted as a playable/usable asset — the same gate that games renders pass through. This keeps a
single acceptance standard across projects: **a hash in a filename is never a verified result.**

## Invariants that hold across every seam

| Invariant | Where it is enforced |
|---|---|
| One authoritative source per fact; docs never override live state | authority order, this guide; the [source map](llm-api.md) |
| The GPU has one owner at a time; vision weights stay resident when they fit | seam A, `gpu-controller-router.py`, llama.cpp manifests |
| Visual acceptance needs an independent, verified, pixel-only review | seam B, `coordinator-guard/index.js` |
| Evidence is never fabricated; a blocked child needs an explicit grant | seam B, `recoveryGrant`, `receiptMismatch` |
| Observability is read-only and fails soft, never 500s the page | seam C, `config/glance/helper.py` |
| Agents publish to `dev`; the operator publishes reviewed paths to `main` | seam D, `verification_loop.py`, branch policy |

## F · Source, automation and distribution

The platform has two source roots: the homelab IaC project and a separately pinned
WatooM-Code application checkout. Application/UI/native-plugin interface changes belong
to the latter; custom plugin payloads, agents, skills, host workers and installation
contracts are maintained in the owning IaC roles and tools. The [custom extensions
map](llm-extensions.md) traces these layers and their privilege/lifecycle boundaries.

| Stage | Input | Output and owner |
|---|---|---|
| Desired state | Playbooks, role defaults/tasks/templates, manifests and source config | Reviewed component change in the operator checkout |
| Installed runtime | Owning Ansible entrypoint plus independent image/source pins | Host helper copies, services/timers, configuration and workloads |
| Documentation | Maintained guide source plus tracked automation inventory | Glance HTML/search/downloads from the existing renderer |
| Distribution | Reviewed application source and filtered platform snapshot | Separate private GitHub repository without source history or runtime data |

The [server automation reference](server-catalogue.md) inventories all tracked scripts,
playbooks, roles and tools, with per-file hashes and purpose evidence. It is generated
by static source inspection, never by executing operational scripts. Defaults, task
includes and helper source remain authoritative; catalogue inclusion does not establish
live installation, current support or permission to execute a migration.

The [project guide](llm-project.md) documents requirements, configuration, installation
boundaries, smoke checks, development and recovery. [GitHub publication](llm-publication.md)
defines source provenance, private exclusions, upstream attribution and distribution
validation. Both application and platform source are required to reproduce custom
behaviour; a private image digest alone is not reproducible source. Model weights,
engine source, purchased assets, credentials, session state and recovery grants remain
external. Source publication does not change production ownership or activate a release.

## G · New creative and reference flows

The Nov 3–7 additions keep planning, reference, execution and acceptance separate:

```text
user request
  ├─ game-template / game-blueprint prompt ──▶ scoped project plan
  ├─ place or coordinates ──▶ open DEM ──▶ terrain skill ──▶ Godot scene + EXR
  ├─ uncertain API or engine error ──▶ language-knowledge lookup ──▶ inert source note
  └─ owned MetaHuman ──▶ inspect/verify package ──▶ Bazzite geometry export
                                                  └─▶ RIG GPU skin job (optional)
                                                       └─▶ Godot import + separate visual review

heavy worker request ──▶ Bazzite queue ──[unavailable 600s]──▶ agent may submit RIG job
                       └─ local server route disabled by default (would reserve GPU)
```

The language-knowledge plugin inserts bounded data from versioned cards; the note is not executable authority. Heavy jobs carry stable request identity and return receipts. The Bazzite bridge reports RIG eligibility but cannot itself submit a RIG job. The outbound Unreal lane accepts only the fixed `probe` and `metahuman-skin` operations, verifies inputs/outputs and does not share the guarded Blender/Godot broker. This design keeps code selection, worker admission and asset acceptance at separate trust boundaries. Maintained sources are `tools/language-knowledge/`, `tools/watoom-code/`, `tools/rig-async-stage/unreal-lane/`, and the installed skill sources described in [Custom extensions](llm-extensions.md).

The other new user-facing paths are project-local: game template selection copies a licensed pinned source without modifying the catalogue; the Fab advisor proposes a pipeline but per-asset approval still gates acquisition; native Unreal pack export produces a receipt but does not prove gameplay or visual correctness. The learning curator writes candidate lessons to its separate journalled store and remains opt-in. Glance's new command-center panels are read-only observations, not lifecycle controls.

## Environment disaster recovery

The [disaster recovery guide](disaster-recovery.md) defines the environment/project/service-state scope, private capture, off-host verification, isolated restoration and guarded replacement-host phases. Git alone is not a full backup; readiness remains blocked until the required recovery evidence exists. Media and purchased libraries may be reacquired, while private state and authored projects need independent protection.
