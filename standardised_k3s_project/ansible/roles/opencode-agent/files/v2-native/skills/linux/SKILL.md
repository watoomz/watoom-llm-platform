---
name: linux
description: Use for Linux system administration, systemd, storage, filesystems, packages, processes, permissions, kernel diagnostics, and host-level troubleshooting.
---

# Linux

- Inspect current state first.
- Prefer reversible diagnostics before mutation.
- Preserve existing service/package ownership conventions.
- Do not reinstall major platform components to fix a local problem.
- For storage operations, establish block/LVM/filesystem topology before writing.
- For systemd, inspect unit/drop-in ownership before overriding behavior.
- Validate the smallest changed layer first.
