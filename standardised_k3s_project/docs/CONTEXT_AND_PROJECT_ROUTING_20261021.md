# Chat context and project routing corrections — 2026-10-21

## Context mismatch
OpenCode advertised a 100,000-token allowance for local chat models while six
backends allocated only 63,488 tokens. Builder requests of 63,845, 65,371 and
78,337 tokens were rejected. This was a runtime/catalog mismatch, not a GPU
restart or missing model.

All seven installed GGUF files were inspected directly. Gemma declares 131,072
training context; the Qwen-based files declare 262,144. The six non-Swift chat
deployments now request 131,072 tokens with one slot, matching stable Swift.
OpenCode retains its existing conservative 100,000 input/context allowance and
4,096 output allowance, the same as Swift. Model identity, quantization, KV
formats, sampling and primary/default selection were preserved. General Qwen initially
failed CUDA compute-buffer allocation at 128K; its existing `--n-cpu-ffn` was
therefore increased from 4 to 12. The other six models keep their original offload.
Mesh retains its separate 8K geometry workflow; image checkpoints are not chat
models. No external provider context was changed.

Authoritative persistence covers the model-lab registry, generated model-lab
manifest, standalone general/uncensored Qwen manifests and reviewed GPU-controller
deployment fingerprints. Only context environment values were patched on the
six stopped deployments; stable Swift itself was not modified. Controller
ownership was never manually cleared, and all model loading used its router API.

## Project and worker errors
The monitored session belonged to the Magpie project while its critics were
asked to read an images project. Those external-directory denials correctly
preserved project isolation. Missing checkpoints also cannot be repaired by
claiming a critic successfully inspected them. Five maintained/live role
contracts and the shared Prompt Builder creator now require project matching,
existing local checkpoint paths and bounded evidence excerpts before handoff.
Permissions remain unchanged. Changing an output path never grants another
project access. Existing sessions were not relocated or resumed.

The GUI shell lacked torch and could not read protected model storage. It is
not an image-inference worker. The contracts explicitly require the installed
approved Model Manager/image-worker interface, and forbid package installation,
protected-weight scans and shell workarounds in the GUI. If that interface is
not exposed, the agent must report the integration gap once. The generation-only MCP image bridge is now maintained separately; see
[image handoff](IMAGE_HANDOFF_20261021.md). It queues until native idle and restores
the previous chat model. This does not certify every pipeline end to end.

Live roles already inherited the selected model, but their maintained source
still pinned some roles to Swift. The five source frontmatters now match the
live inheritance behavior. Global production default and controller restoration
remain stable Swift.

## Maintenance and evidence
The waiting job was interrupted for maintenance, without changing its prompt
or resuming content generation. Durable native admission was fenced for the
runtime changes. The job-specific monitor was paused after interruption.
No new user session was created. A controller socket startup race was retained
as failed evidence; it did not indicate a model/context failure, and the fence
remained held until supported recovery/validation.

Evidence: `/data/ai/helper-scripts/reports/context-routing-fix-20261021/`.
Model metadata, before/after Deployment snapshots, controller configuration
backups, native guard owner/release receipts, static validation, runtime load
results and the benign long-context probe are retained there. All seven runtime
loads passed at 131,072. The direct benign regression accepted 65,026 input
tokens and produced a valid response, exceeding the original failing 63,845. Private recovery
records remain on the server and are not committed.
