---
name: watoom-prompt-creator
description: Build concise pipeline task prompts from a free request and essential follow-up answers; used by the Prompt Builder page and direct prompt-writing requests.
---
# Pipeline prompt creation

Use the selected watoom-prompt-* pipeline skill. Ask its essential questions in one short batch, incorporating information already supplied. Keep optional detail optional. Return a copyable task prompt; do not execute the requested pipeline while composing it. Avoid importing an entire skills library or turning one fixture into a universal design. The page reads the versioned contract below and the selected pipeline skill; edit those skills to maintain questions and workflow guidance.

```prompt-builder
{
  "version": 1,
  "kind": "creator",
  "instructions": [
    "Turn the request and supplied details into one concise, actionable task for the existing WatooM coordinator. Load only the selected pipeline skill and relevant execution skills on demand.",
    "Treat labelled defaults as conservative proposals. Explicit user requirements override them; briefly state any important inferred dimensions or budgets before acting. A default never grants new permissions or certifies compatibility.",
    "Use supplied values exactly. Resolve essential contradictions or genuinely missing information before execution; do not silently invent scale, functionality or acceptance.",
    "For images, preserve the full requested scope and output count. Treat the supplied positive block as authoritative and pass the supplied negative block unchanged. Light wording polish during draft preparation may improve clarity but must not add, remove or replace required scene details or tags. Preserve the reviewed negative block exactly. Keep the requested per-image positive differences and useful light refinement; only force identical positive text when the user explicitly selects verbatim. The native transport preserves per-image positive arguments and enforces the negative text. Explicit counts override per-image defaults. Queue one distinct job per requested image before ending the turn; do not substitute a one-image test or invent an approval gate.",
    "Before execution, match the requested path to the native session's selected project. If they differ, ask the user to select the correct project/session; an output path does not grant cross-project access. Keep checkpoints and critic evidence inside that project, verify files exist, and pass concise evidence excerpts in handoffs.",
    "Inspect installed interfaces and relevant existing work first. Reuse verified recipes through AgentMemory, keep GPU execution serial with stable IDs (for an explicit image batch, queue all requested images before ending the turn), and reconcile uncertain jobs before retrying.",
    "Use installed approved workers for ML/engine execution. Never run torch/diffusers or read protected weights in the GUI shell. If an image-generation worker interface is not exposed, report that specific integration gap instead of installing packages or trying another shell.",
    "Preserve originals and unrelated work. Use a fresh canonical project/revision, checkpoint accepted stages, retain failed outputs, and resume from verified hashes. Respect existing admission and approval rules.",
    "Deliver paths, actual previews and concise evidence. Separate technical validation, visual review, unsupported and not-run checks. Remember only verified scoped recipes."
  ]
}
```
