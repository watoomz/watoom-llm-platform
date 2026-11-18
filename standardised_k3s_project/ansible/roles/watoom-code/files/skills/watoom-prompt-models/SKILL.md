---
name: watoom-prompt-models
description: Create an efficient task prompt for download and register a model, collecting pipeline-specific inputs before execution.
---
# Download and register a model

Set up the specified hugging face repository url through the existing Model Manager at https://glance.internal.homelab.example/model-manager/. Inspect revisions, exact variant sizes, model type and dependency requirements. Distinguish GGUF, diffusion checkpoint/pipeline and LoRA. Use safe applicable settings (100000 context,4096 output,q4_0 K/V for compatible language models; lower model limits take precedence), preserving explicit saved overrides. Report downloaded/configured/registered/tested separately. No arbitrary remote-code execution, direct scaling or deletion of existing data.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "models",
  "title": "Download and register a model",
  "category": "Models",
  "availability": "available",
  "keywords": [
    "install model",
    "download model",
    "hugging face"
  ],
  "fields": [
    {
      "id": "model",
      "label": "Model or repository",
      "help": "Installed model ID, exact repository URL and variant; include a compatible base for LoRA.",
      "required": true
    },
    {
      "id": "scope",
      "label": "Scope and acceptance",
      "help": "What must work, what is excluded, and the observable checks that define success.",
      "required": true,
      "default": "Inspect compatible variants and resource requirements, propose the smallest suitable installed/managed configuration, and preserve existing saved overrides. Use the existing Model Manager admission and approval flow."
    }
  ]
}
```
