# Qwen3.8 uncensored MTP vision

The original render review failed because the selected route advertised only text,
its backend had no projector, and the guard verified only Swift image presentation.
A successful file read did not send verified pixels to this model. The coordinator
then retried a null-model receipt, and its final report used an older checkpoint
oldString mismatch. The guard now preserves the current child-review blocker,
stops unverified retries and never accepts guessed observations.

The existing projector is mounted read-only from
/data/ai/models/gguf/swift-qwen3.8-27b/mmproj-Swift-Qwen3.8-27B-F16.gguf.
SHA256: daa1116c9422fa390cc8688495da0e91781f92841dfc3b31a378ff252571745a.
LLAMA_ARG_MMPROJ=/vision/mmproj.gguf; LLAMA_ARG_MMPROJ_OFFLOAD=false.
The same model, 131072 context, MTP, KV settings and GPU layer policy are retained.
Source replicas remain zero for broker selection; activation preserves live replicas.

The backend loaded its multimodal projector and correctly described both paired
256px fixtures: red rectangle/blue circle and blue rectangle/red circle, from
identical prompts. Evidence: /data/ai/helper-scripts/reports/uncensored-vision-20261025.
The app provider advertises text/image and tools, and its maintained guard verifies
watoom/qwen38-uncensored-mtp presentation from actual outbound pixels plus a
successful response. Registry membership alone never fabricates a review receipt.

Cold loading took about 216 seconds; the first 180-second diagnostic wait timed
out without a model crash. Allow a bounded longer readiness wait after reboot.
Existing failed receipts and completed renders remain intact. No render is replayed
and no prior task is declared complete by enabling vision. A current-session image
presentation is still required before accepting its review.

Rollback: remove the vision env/mount/volume from the deployment, remove this route
from verifiedVisionModels and restore text-only capability in both the config helper
and template, through the normal idle/admission-fenced release. Deployment-before.json
and guarded release snapshots provide exact previous content; do not switch models,
change context/VRAM policy, or clear existing guard history to hide a failure.
