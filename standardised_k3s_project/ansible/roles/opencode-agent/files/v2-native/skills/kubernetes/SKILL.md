---
name: kubernetes
description: Use for Kubernetes or k3s manifests, Services, Deployments, ConfigMaps, Secrets references, Traefik routes, rollout diagnosis, and cluster-safe validation.
---

# Kubernetes / k3s

- Identify the source of truth before editing a generated manifest.
- Preserve selectors, namespaces, labels, service names, and ownership conventions.
- Prefer `kubectl get/describe/logs/diff` for diagnosis.
- Do not apply broad changes merely to test rendering.
- Avoid embedding secrets.
- Treat rollouts as explicit operations; restart only affected workloads.

## WatooM conventions

When working in the WatooM environment:

- Single-node k3s; do not reinstall k3s.
- Traefik CRDs are used for internal routes.
- Prefer IaC/source config over live-only `kubectl edit`.
- Do not change router/VLAN/firewall configuration as part of a Kubernetes fix unless explicitly requested.
- Local TLS is managed centrally; reuse existing conventions instead of inventing certificate flows.
