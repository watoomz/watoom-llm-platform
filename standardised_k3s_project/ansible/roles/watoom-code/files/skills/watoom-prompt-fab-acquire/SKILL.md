---
name: watoom-prompt-fab-acquire
description: Create an efficient task prompt for acquire owned fab assets, collecting pipeline-specific inputs before execution.
---
# Acquire owned FAB assets

Check my existing server-authenticated FAB library for the specified asset name. Reconcile acquisition receipts before downloading. Use the maintained single-owner queue with hashes and resource bounds; never duplicate a downloader or re-download PASS assets. Index only verified complete files into the shared Catalog. Separate downloaded, indexed and runtime-compatible states. Do not purchase anything or expose account credentials. If host acquisition is unavailable to this session, report the precise missing capability once.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "fab-acquire",
  "title": "Acquire owned FAB assets",
  "category": "Assets",
  "availability": "host workflow",
  "keywords": [
    "fab",
    "download owned",
    "acquire pack"
  ],
  "fields": [
    {
      "id": "pack",
      "label": "Exact owned pack name",
      "help": "Use the name from your Fab library; acquisition does not purchase or certify conversion.",
      "required": true
    },
    {
      "id": "scope",
      "label": "Scope and acceptance",
      "help": "What must work, what is excluded, and the observable checks that define success.",
      "required": true,
      "default": "Implement the smallest useful version of the requested job. State the acceptance checks and keep unrelated systems unchanged."
    }
  ]
}
```
