# Docker rules
- Preserve runtime, storage, networking, UID/GID and security conventions; do not reinstall Docker.
- Never bake secrets into images; follow existing image/build/pinning conventions.
- Avoid unnecessary package layers/dependency churn and casual changes to host networking, mounts, persistence or privilege.
