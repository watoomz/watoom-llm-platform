---
name: watoom-prompt-image
description: Create an efficient task prompt for generate an image with an installed model, collecting pipeline-specific inputs before execution.
---
# Generate an image with an installed model


<!-- WATOOM_GUIDED_IMAGE_CREATOR_V1 -->
## Shared guided prompt workflow

Use `watoom-explicit-image-creator` for this skill's prompt preparation and staged interaction. Load that installed skill before drafting. Both skills now use the same positive review, negative review, optional prefilled details and final preview/Generate workflow, the same CPU-only helper, model profiles and skill-scoped preference file. Preserve the existing form and image queue protocol below; submission instructions apply only after the final Generate choice for the exact displayed preview. Do not submit merely because a form was filled, the initial message says generate, or a positive prompt was approved. If the shared skill is unavailable, report the missing dependency and continue drafting in conversation without rendering.

The user may accept or edit each block, skip optional fields, save prompts without rendering, save presets or refine a prior revision. Keep supplied negative prompts exact. Changing a field invalidates the final preview approval. Use adult/default appearance only when unspecified, preserve references and established identities, and apply Pony scores only with verified checkpoint/revision compatibility. Applicable content limits remain in force. Once the complete reviewed image/batch has received final Generate approval, follow the existing native queue and receipt rules without inventing additional per-image approvals.


Generate the specified image using the requested installed managed model or installation ID. Discover the current generation interface and published sampling recommendations. For a LoRA, select an explicit compatible installed base. Use the existing GPU controller; preserve active jobs and verify restoration of the previously loaded chat model. Save the output and generation settings under this project, inspect the actual image and report limitations honestly.


Run generation through the approved Model Manager/image worker interface exposed in this session. The GUI shell is not the inference worker: never import torch/diffusers, install packages or read protected model weights there. If the approved interface is absent, report that specific integration gap once. Match the requested project to the selected native session before execution and keep receipts inside it.

Use the `watoom-images` MCP interface: discover its installed models once, then submit exactly one job per explicitly requested image, each with its own stable request ID and pinned installation revision. Default to one image only when no output count was requested. An explicit request for three stills means queue all three distinct stills in this same turn; it is not a duplicate retry. Its safe generation defaults are 1024 by 1024, 30 steps and guidance 7; pass validated per-job settings for requested dimensions or documented model-specific sampling. Report the actual returned settings. Runtime, precision and base-weight selection cannot be overridden by this tool.

After all requested jobs have accepted submission receipts, finish the current chat turn. The worker waits for native idle before taking the GPU. Do not poll in a tool loop, resubmit with another ID, or create/resume a session automatically. The chat automatically reads the durable receipt and displays the verified image after restoration; no follow-up prompt is needed. Do not claim that generation is blocked merely because the chat turn has ended. `image_job`, `image_result`, and Model Manager remain available for explicit diagnostic requests. Only announce completion after PNG integrity and prior-chat-model restoration are verified. Copy the image at the receipt's `published.path` (`/data/ai/projects/images/generated/<run>/image.png`) and its `published.receipt` into this selected project before local critic review. A non-vision model must not claim visual inspection.

<!-- WATOOM_IMAGE_SCOPE_FIDELITY_V1 -->
## Preserve the requested scope

Before submission, extract the requested output count, complete scene description, positive prompt/tags, negative prompt, model and explicit settings from the user's task and form. Use explicit user requirements ahead of defaults. A per-image resolution such as 1,024 × 1,024 is not an output count. If no count is supplied, default to one. If the task requests three images, the acceptance target is three accepted distinct jobs, not one preview or test.

While preparing a draft, light clarity/grammar polish may improve readability, but it must retain every requested subject, attribute, action, composition and supplied positive tag. By default, preserve the supplied scope while allowing light positive-prompt refinement and the requested per-image differences. Keep the three per-image positives distinct when the requested views/scenes differ. The native transport preserves each per-image positive argument; it must not replace all variants with the common base. Only explicit verbatim mode copies the common positive block unchanged to every job. The supplied negative block is always copied unchanged by native transport. Do not replace, simplify, soften or embellish the requested scene with new subject details. Keep a supplied complete positive block as the authoritative base, not merely inspiration for a new prompt. If the user asks for exact text, pass it verbatim. Never rewrite, expand, reverse or drop the supplied negative block: pass that block unchanged as `negative_prompt`. Quality/style additions must be compatible, non-conflicting and must not displace supplied details. A request to generate is not permission to redesign it.

For a multi-image request, preserve this common scope in every job; apply only user-requested per-image differences. Do not collapse several requested images into one contact sheet or combine their scenes. Before calling the tools, check each positive prompt against the description and supplied tags, check exact equality of its negative block, and reconcile the requested count. Queue all N jobs in this turn with distinct stable request IDs. Before ending, compare accepted receipt count with N, copy the exact returned IDs, state any wording polish briefly, and report missing submissions honestly. Do not invent a critic/approval stop after the first image. GPU execution stays serial under the existing exclusive-ownership guard; batch submission and automatic receipt delivery do not require additional chat prompts.

<!-- WATOOM_IMAGE_NATIVE_TOOLS_V1 -->
<!-- WATOOM_IMAGE_EXPLICIT_BATCH_V1 -->
## Direct tool calls: no wrapper code

The image adapter is exposed as native, schema-described tools. Call `watoom-images_list_image_models` with `{}` directly, then call `watoom-images_submit_image` with JSON arguments matching its published schema. These are tool calls, not text for `execute`, shell, Python, or JavaScript. Do not import tools, construct wrappers, use heredocs, or search the filesystem for MCP interfaces. Reuse a current successful installation/revision receipt instead of rediscovering it in each subagent.

For submission, map the catalog's `id` to `installation_id` and retain its exact `revision`. Required keys are `request_id`, `installation_id`, `revision`, and `prompt`. Optional sampling values belong inside `settings`: `width`, `height`, `steps`, `guidance`, `seed`, `scheduler`. The field is `settings.guidance`, never `guidance_scale`. Do not add a model/repository name or unsupported top-level sampling keys. Omitting settings uses safe worker defaults. Use the published schema, not trial-and-error variants.

Target one catalog read and one submission per distinct requested image. Queue the complete explicitly requested batch before ending the turn so GPU handoff can begin. Copy each returned job ID exactly from its tool receipt; never reconstruct or retype it. Report the requested count, accepted count and per-image job IDs. The worker processes the queued jobs serially and the chat displays each verified image automatically. Do not wait for image 1 or require another user prompt to submit images 2 and 3. An approval/review gate between images applies only when the user explicitly requests staged iteration or a real native guard requires it. Never invent such a gate. A submission error must be reported with the accepted and remaining counts; do not claim the batch is complete or blindly replay accepted jobs. The chat displays the verified result automatically; do not poll or resubmit with a different request ID. If a response is uncertain, reconcile the existing receipt instead of replaying generation.

If these direct tools are absent, inspect the current tool catalog once. Only when that catalog explicitly exposes the image adapter through legacy Code Mode may you use restricted JavaScript: `return await tools["watoom-images"].list_image_models({});`. Never use Python `import`, `print`, `exec`, guessed underscore namespaces, or shell wrappers in `execute`. Make at most one schema/catalog-based correction; a second failure is an integration blocker, not a reason to keep guessing.

Honor mandatory coordinator handoff and critic gates. `COORDINATOR_HANDOFF_REQUIRED` or a critic-required error means stop passive-tool/repair retries and follow the native coordinator protocol. Do not treat that guard as a shell, Python, model, or GPU failure. If a required checkpoint write fails, report its path and access error once. Do not bypass guards, change permissions, switch projects or send another agent to repeat discovery. Missing optional context files do not justify filesystem scans.

<!-- WATOOM_IMAGE_PROMPT_FORM_V1 -->
Build clearly labelled positive and negative image prompts from this form. The positive block must be one natural-language descriptive paragraph immediately followed by the comma-separated positive quality and visual tags, matching prose-plus-tags model-card examples. Keep execution instructions, paths and sampling settings outside that block. The positive prompt combines the supplied scene description (or the main request if blank), comma-separated visual tags and, only when the selected model card supports them, the positive Pony quality scores. Preserve the user's exact tags and do not invent additional subject details. Pony score tags describe quality/style, not content ratings.
Keep negative quality scores and exclusions in a separate negative-prompt block. Never append them to the positive prompt. Pass this separate block verbatim as the top-level `negative_prompt` string in `watoom-images_submit_image`. Never silently discard it or merge it into the positive prompt. If a stale tool schema lacks `negative_prompt`, report the interface mismatch and stop before submission; do not generate an image with missing conditioning. Form completion and prompt building must not submit a generation job or start a session.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "image",
  "title": "Create an image through guided prompt review",
  "category": "Images",
  "availability": "Prompt-only drafting always available; rendering uses the Model Manager queue",
  "keywords": [
    "generate image",
    "create illustrations",
    "illustrate page",
    "comic panel art",
    "page images",
    "concept art"
  ],
  "fields": [
    {
      "id": "output-count",
      "label": "Number of images",
      "help": "Enter the total count if needed. When blank, use the count in your request; otherwise default to one. Every requested image is queued before the turn ends.",
      "required": false
    },
    {
      "id": "positive-fidelity",
      "label": "Positive prompt handling",
      "help": "Default: allow light polish and the requested per-image variations while preserving your scope. Enter verbatim only if every image must receive the exact same supplied positive block. Negative prompts are always passed unchanged.",
      "required": false,
      "default": "Light polish and requested per-image variations"
    },
    {
      "id": "description",
      "label": "Initial image description",
      "help": "Describe your idea or paste an existing prompt. The guided workflow drafts an editable positive, then reviews negatives and optional details before final approval.",
      "required": false,
      "default": ""
    },
    {
      "id": "danbooru-tags",
      "label": "Danbooru-style tags",
      "help": "Optional comma-separated visual tags, for example: scenery, tree, outdoors, sunlight. Keep descriptive prose as well.",
      "required": false,
      "default": ""
    },
    {
      "id": "positive-score-tags",
      "label": "Positive quality rating (Pony)",
      "help": "Quality/style scores, not a content rating. Use only when the selected model card supports Pony scoring; otherwise omit them. Leave blank during the guided workflow; add scores only after checkpoint compatibility is verified.",
      "required": false,
      "default": ""
    },
    {
      "id": "negative-score-tags",
      "label": "Negative quality rating (Pony)",
      "help": "Keep these in the negative prompt, separate from the positive description. Apply only to a compatible model and supported negative-prompt interface. Leave blank during the guided workflow; add scores only after checkpoint compatibility is verified.",
      "required": false,
      "default": ""
    },
    {
      "id": "negative-description",
      "label": "Negative prompt / exclusions",
      "help": "Exclusions to pass unchanged to negative_prompt; the execution model must not rewrite or add exclusions.",
      "required": false,
      "default": ""
    },
    {
      "id": "model",
      "label": "Model or repository",
      "help": "Keep the safe discovery default if you do not know the model ID, or enter an installed model ID. Verify any LoRA has a compatible installed base.",
      "required": true,
      "default": "Discover compatible installed image models and recommend a safe default for this request. Use an existing installed model; do not download or install models without asking. If none is available, report the blocker."
    },
    {
      "id": "image",
      "label": "Image size and composition",
      "help": "Per-image resolution, aspect ratio and framing. Output count comes from Number of images or your explicit request.",
      "required": true,
      "default": "1,024 \u00d7 1,024 per image. Use the image worker safe defaults of 30 steps and guidance 7 unless verified model-specific recommendations require an explicit validated override. Use a compatible installed base for any LoRA."
    },
    {
      "id": "style",
      "label": "Style and references",
      "help": "Art direction, palette and reference paths/URLs; say none if there are no references.",
      "required": false,
      "default": "Use the requested style and references. If none are specified, preserve the model\u2019s normal style without adding new scene details."
    }
  ],
  "format": {
    "kind": "prose-tags",
    "descriptionField": "description",
    "positiveFields": [
      "positive-score-tags",
      "danbooru-tags"
    ],
    "negativeFields": [
      "negative-score-tags",
      "negative-description"
    ],
    "positiveLabel": "Positive prompt",
    "negativeLabel": "Negative prompt",
    "settingsLabel": "Execution settings"
  },
  "description": "Create image prompts and generate approved illustrations, concept art or comic panels through the installed image workflow.",
  "requires": [
    "watoom-explicit-image-creator"
  ]
}
```
