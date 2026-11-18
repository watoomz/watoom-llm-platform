# Local chat model switching recovery — 2026-10-21

OpenCode correctly submitted `qwen35-defiant-fable-9b`; the router returned
503 because the exclusive GPU controller was in `recovery-required`.
Swift's reviewed 6144 MiB host prompt-cache change and restart annotation had
not been reconciled with the controller's deployment specification fingerprint.
The retained pre-tuning Deployment matched the old fingerprint exactly.
Only the primary fingerprint was updated after reviewing the full diff and
preserving a backup. The controller then reconciled through the existing
router API; ownership state, admission, scaling restrictions and RAM tuning
were preserved.

Real controller-mediated load checks include backend inference and model-ID
verification. Defiant, Ornith, Gemma, general Qwen, uncensored Qwen and Swift
passed. Tiel initially failed: only an incomplete `.gguf.part` file existed,
with no `active.gguf` link. The existing model-lab download command resumed it
and verified all 13,600,579,424 bytes against registry SHA-256
`a4d8ffc7f030466c67db289543871a8f9e6d5340241b300c09fbaf16642273ca`.
The existing atomic symlink helper selected that verified file without scaling.
A fresh Tiel attempt passed real inference in 141.5 seconds.

The first Tiel timeout and first primary-restore failure are retained. The
shared pinned server image had been garbage-collected during the idle interval,
and its cold pull left a startup pod terminating temporarily. The exact
platform image was fetched into the existing container runtime, and the pod
cleared naturally. No forced deletion, broad cleanup or service reinstall was
used. The failed missing-file startup pod had earlier been replaced only after
proving that its model server had never started.

These checks cover all seven configured concrete local chat models. The
`active-model` alias follows the loaded backend. Mesh and image checkpoints
retain dedicated geometry/image workflows. External providers were not
inference-tested by this local switching check. Model listing alone does not
prove an external credential, quota or model-specific capability.

Evidence: `/data/ai/helper-scripts/reports/model-availability-20261021/`.
See `local-load-results.json`, `tiel-download.log`, `tiel-install.json`,
`primary-recovery-run2.json`, `tiel-retry-and-restore.json`, and the final
verification receipt. User sessions were not resumed or changed by these tests.

Final verification: PASS. Swift restored with a nonempty `active-model` alias
response. Controller phase `qwen-ready`, generation 83, owner null,
uncertain false and active_requests zero. All seven concrete chat routes and
all nine native local catalog entries (including Mesh and active-model) were
present. No user session was resumed.

## Re-pinning after a reviewed primary Deployment change (2026-11-11)

A primary (`swift-qwen38-coder`) Deployment change that bypasses the controller
leaves the pinned `deployment_identity` digest stale, and the controller then
refuses every action including `recover` ("deployment identity or model
configuration changed"). After reviewing the diff, run
`ansible-playbook playbooks/gpu-controller.yml -e gpu_controller_repin_primary=true`
(wraps `scripts/gpu-controller-repin-primary.py`: UID must match, controller must
be qwen-ready/unowned/certain, only the primary digest changes, backup kept) and
mirror the new digest into `roles/llm-model-lab/files/gpu-controller.json`.
The role now restarts the controller whenever its config changes.
