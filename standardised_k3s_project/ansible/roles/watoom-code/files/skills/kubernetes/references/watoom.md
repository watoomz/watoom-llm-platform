# WatooM Kubernetes reference

- Single-node k3s; do not reinstall k3s.
- Traefik CRDs are used for internal routes.
- Prefer IaC/source config over live-only `kubectl edit`.
- Do not change router/VLAN/firewall configuration as part of a Kubernetes fix unless explicitly requested.
- Local TLS is managed centrally; reuse existing conventions instead of inventing certificate flows.
