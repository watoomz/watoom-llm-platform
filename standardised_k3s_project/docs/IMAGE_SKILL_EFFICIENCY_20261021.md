# Image skill tool-call efficiency

The production image skill now supplies tested restricted-JavaScript examples using `tools["watoom-images"].list_image_models({})` and `submit_image(...)`, with actual catalog IDs/revisions. Python imports/print/exec wrappers and filesystem searches are not the image interface. A current receipt is reused, discovery is refreshed only when needed, and a syntax/signature failure permits one evidence-based correction instead of repeated guesses. Required checkpoint access failures stop after the first failure; permissions and coordinator requirements are not bypassed.

Validation used the installed CodeMode interpreter with fixture-only catalog/submission tools: exactly two host calls, with a separate synchronous search verifying the published bracket-access path. No production generation or AI session was started. The Prompt Builder form contract is unchanged. Source and live skill hashes match, and the live native skill API exposes the new recipe. No application rebuild or restart is needed.

Administrative inspection of the latest production image session found five failed CodeMode programs admitting zero tool calls, a nonexistent optional context path, and five checkpoint-write failures. The selected `/data/ai/projects/images` directory inherits the container's read-only `/data/ai` mount (`statvfs` read-only flag and `/proc/self/mountinfo` both confirm it). App UID 1001 already has supplementary group 1009, matching the directory group and mode 0775; Unix group membership is not the blocker. No image request was queued for that session. This inspection did not change project permissions or resume the job.

Evidence: `/data/ai/helper-scripts/reports/image-skill-efficiency-20261021`.

The selected-project mount blocker was subsequently fixed with a dedicated writable mount; see [image project mount](IMAGE_PROJECT_MOUNT_20261021.md). The original failed job was not resumed.

The normal path was subsequently moved to native schema-described image tools to eliminate wrapper syntax entirely. See [native image tools](IMAGE_NATIVE_TOOLS_20261021.md); the earlier Code Mode recipe is now legacy-only.
