# Kubernetes rules
- Make declarative IaC changes rather than live-only mutations.
- Use Services/DNS rather than pod IPs and never persist generated pod names.
- Preserve namespaces, labels/annotations, resources, probes, securityContext, storage and ingress conventions.
- Use ConfigMaps/Secrets appropriately and account for subPath restart behavior where relevant.
- Verify rendering/apply/rollout and follow existing Traefik/IngressRoute patterns.
