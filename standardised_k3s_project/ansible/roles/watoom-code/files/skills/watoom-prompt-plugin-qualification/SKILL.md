---
name: watoom-prompt-plugin-qualification
description: Create an efficient task prompt for assess an unreal plugin or integration kit, collecting pipeline-specific inputs before execution.
---
# Assess an Unreal plugin or integration kit

Assess the specified plugin or archive for the specified project and engine version. Inspect its descriptor, source documentation, licence, platform allowlist, dependencies and binary/build IDs without executing downloaded code or auto-connecting MCP. Nwiro/POT Linux support and arbitrary engine-version compatibility must not be assumed. Identify a supported isolated qualification/build route; preserve the accepted engine and existing project. Only enable the integration after actual load, relevant behaviour and rollback validation. If no supported route exists, report the exact boundary and keep the integration disabled.

```prompt-builder
{
  "version": 1,
  "kind": "pipeline",
  "id": "plugin-qualification",
  "title": "Assess an Unreal plugin or integration kit",
  "category": "Validation",
  "availability": "inspection first",
  "keywords": [
    "plugin",
    "integration kit"
  ],
  "fields": [
    {
      "id": "source",
      "label": "Source asset, file or catalogue ID",
      "help": "Give the exact server path or catalogue ID; use none for a new asset.",
      "required": true
    },
    {
      "id": "version",
      "label": "Engine and platform",
      "help": "Target engine version and platform, for example Unreal 5.8.3 on Linux.",
      "required": true,
      "default": "Use the verified installed engine and Linux-compatible route. Inspect the actual version before execution."
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
