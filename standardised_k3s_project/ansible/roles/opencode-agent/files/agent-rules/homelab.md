# WatooM homelab rules
- Infrastructure changes are IaC-first and must survive rebuild/redeployment.
- Prefer existing Ansible roles/defaults/group_vars/templates/manifests/helpers over parallel mechanisms.
- Preserve unrelated dirty working-tree state.
- Never persist transient pod names or generated ClusterIPs; use Services/DNS and configuration variables.
- Do not reinstall k3s or Docker or alter unrelated router/network topology.
- Follow discovered WatooM namespace, TLS, Traefik, storage, UID/GID and naming conventions.
- Changes should be idempotent and secrets must stay out of ordinary source files.
