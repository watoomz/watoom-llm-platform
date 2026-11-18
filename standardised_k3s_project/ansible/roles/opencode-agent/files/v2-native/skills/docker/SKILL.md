---
name: docker
description: Use for Dockerfiles, Compose, image builds, container runtime diagnosis, build context, and container-safe dependency/image changes.
---

# Docker

- Inspect existing image/base/build conventions first.
- Prefer deterministic, cache-aware layers.
- Do not bake secrets into images.
- Keep runtime images minimal without breaking required diagnostics.
- Avoid broad prune/cleanup operations as a debugging shortcut.
- Do not reinstall Docker to solve an application/container issue.
- Validate the exact image/config changed.
