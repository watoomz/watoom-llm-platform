# Production image handoff — 2026-10-21

The chat model coordinates image generation through the generation-only
`watoom-images` MCP adapter. Model Manager and its existing GPU broker run SDXL;
the GUI does not need torch or access to protected weights. All tool-capable chat
models can use the same adapter. Image checkpoints remain image backends.

## Usage in Prompt Builder and Glance
Select Images in Prompt Builder, describe the image and choose an installed model
or keep model discovery. Safe job defaults are 1024 square, 30 steps, guidance 7,
Euler and seed 0. Validated job overrides support dimensions up to 1024 per side
in multiples of eight, steps up to 50, guidance up to 20, seed and Euler/DPM.
Model-specific published settings can be supplied explicitly. Runtime precision,
base weights, paths, installation and deletion are outside this API.

The coordinator discovers installed identities/revisions with `list_image_models`
and submits once with `submit_image` and a stable request ID. It must then finish
its turn. The worker waits in `WAITING_NATIVE_IDLE` while native work or maintenance
is active. New jobs persist their originating native session. The chat automatically
reads the verified receipt and displays a downloadable image after chat-model restoration;
no follow-up prompt is needed. `image_job`, `image_result`, and Model Manager remain
available for diagnostics. No AI session is started or resumed automatically.
See [automatic result delivery](IMAGE_RESULT_DELIVERY_20261021.md).
Do not poll in a tool loop or resubmit with another ID after uncertainty.

The worker uses existing durable native admission and an exclusive GPU lease.
It generates, validates PNG integrity, releases inference, restores the previously
loaded chat model and verifies restoration before publishing success. Both Swift's
`qwen-ready` and alternate models' `model-ready` states are handled. Uncertain
restoration retains the native fence; interrupted generation is not replayed.
Repeated identical request IDs return the same job; conflicting input is refused.

## Artifacts and permissions
Root-controlled PNGs and receipts are published beneath
`/data/ai/watoom-code/generated/model-manager/<run>/`, visible as
`/generated/model-manager/<run>/`. Filenames are fixed, new-only and symlink-safe.
Receipts include actual settings, SHA256 and restoration evidence. Copy artifacts
through permitted tooling into the selected project before critic review. An output
path does not change native project permissions. Non-vision models must not claim
visual inspection. The API returns the actual PNG as MCP image content.

## IaC and deployment
The owning Model Manager role pins the immutable CPU image and versioned broker,
reuses the existing immutable SDXL runtime, mounts a private generation-only token,
and maintains the dedicated publication directory. The administrative password is
separate. Native config uses a private token-file reference, never a committed token.
`watoom-code-image-mcp.yml` updates only credentials and the owned MCP entry while
preserving user settings. The full application role maintains the same integration.

Deployment uses Recreate and a lifetime queue-consumer lock. A read-only IaC
preflight refuses active generation/download/removal. Operators must still fence
native admission and pause the manager queue before broker replacement, then verify
idle ownership and release their own fence. No networking changes are required.
Only Model Manager source was committed locally with explicit user approval; no push.
Other IaC/documentation edits remain in the working tree, preserving unrelated work.

## Validation
92 source tests pass, including idempotency, scoped authentication, native-idle
queuing, settings budgets/forwarding, concurrent consumer exclusion, PNG validation,
publication path safety and fail-closed restoration. All eight MCP template
combinations parse; migration preserves user settings and is idempotent. Both
Ansible playbooks pass syntax checks. The active-work preflight refuses a busy
catalog and accepts a quiescent one.

The live benign test passed Defiant → SDXL → Defiant. Its actual 1024-square,
30-step, guidance-7 PNG was SHA-verified and visually inspected as a usable wooden
park bench image. The app can read the PNG and receipt. An earlier two-step fixture
produced noise; production MCP jobs now use the existing SDXL quality baseline
instead of those installed test settings. Earlier rollout/restoration failures are
retained as evidence. This validates this image path, not every pipeline end to end.
Cold switches can take several minutes, especially after image garbage collection.

Final stable Swift restoration passed; native admission is open and the manager queue is empty. No AI session was created or resumed.
Evidence: `/data/ai/helper-scripts/reports/image-handoff-fix-20261021/`.
