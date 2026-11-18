---
name: watoom-prompt-asset-index
description: Create an efficient task prompt for index selected downloaded assets, collecting pipeline-specific inputs before execution.
---
# Index selected downloaded assets

Index the receipt-verified files in the specified source directory using the existing asset.index route and shared Catalog. Reuse existing IDs/adapters, preserve prior records and verify a subsequent search. Exclude incomplete downloads and unsupported formats; do not create another Catalog.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "asset-index",
  "title": "Index selected downloaded assets",
  "category": "Assets",
  "availability": "available",
  "keywords": [
    "index assets",
    "catalogue index"
  ],
  "fields": [
    {
      "id": "source",
      "label": "Source asset, file or catalogue ID",
      "help": "Give the exact server path or catalogue ID; use none for a new asset.",
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
