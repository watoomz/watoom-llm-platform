# Image negative-prompt support — 2026-10-21

The native image tool accepts optional top-level `negative_prompt` (string, 0–4096 characters), separately from `prompt` and numeric `settings`. Omission preserves the old queue payload and request digest, so existing jobs and retries remain compatible. A changed negative prompt on an existing request ID is rejected as a conflicting retry.

The exact value is retained in the durable selection and forwarded through Worker, Operations and the root broker to SDXL's `negative_prompt` conditioning argument. Positive and negative text are never merged. The broker rejects negative-prompt parameters for chat/GGUF generation. Numeric worker budgets, exclusive GPU ownership, native admission, model restoration and result publication guards remain in place.

The maintained image skill tells coordinators to pass the separate negative block into `negative_prompt`. A stale schema must be reported before submission rather than silently dropping exclusions. Prompt building itself does not submit work or start a session.

Validation: all 99 Model Manager tests pass as root. Added HTTP/schema bounds, durable queue/idempotency/conflicting retry, worker-to-Operations forwarding, fake Diffusers conditioning and restoration-receipt tests. The immutable SDXL runner was inspected in a CPU-only, network-disabled container. No generation/session is started by this release validation.

Release evidence, deployment phase and live verification: `/data/ai/helper-scripts/reports/image-negative-prompt-20261021`. Both service and thin SDXL runner use source commit `e4ce76cec69a1d04d08735dcfb7933e97ece192d`; the existing pinned Torch/Diffusers runtime and model weights are reused. Deployment waits for the active job and restoration to finish, temporarily stops the idle CPU queue consumer, and uses existing identity-checked broker retirement/registration for the three stopped image workloads. It preserves model installation IDs, artifacts, settings and receipts. The unrelated output-directory relocation remains pending; this deployment keeps the existing live publication root.

Production verification passed: live CPU image and tool schema match the release; all three zero-replica worker deployments use the new runner and matching controller identities; model artifacts/settings/dependencies are unchanged; native guard and queue admission are open. The skill was installed and native locations reloaded. No image was generated to validate this deployment.
