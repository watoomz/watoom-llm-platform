# WatooM Kubernetes Manifest Rules

These rules apply under `standardised_k3s_project/manifests/`.

## Source of truth

Before editing a manifest, determine whether it is hand-maintained or generated from `config/`, an Ansible template, or another renderer.

If a renderer/source exists, edit the source of truth and regenerate. Do not hand-edit generated output as the persistent fix.

## Conventions

- Namespace resources explicitly.
- Reuse the project's existing labels, Service/IngressRoute patterns, TLS secrets, hostPath conventions, and ConfigMap/Secret patterns.
- Pin images consistently with the surrounding project; do not change image policy incidentally.
- Keep resource requests/limits and health probes consistent with the existing workload pattern where applicable.
- Keep secrets out of plaintext manifests.
- Avoid adding cluster-wide RBAC or network-policy changes unless the task explicitly requires them.

## Validation and deployment

- Validate YAML/rendered output before apply.
- Prefer the existing Ansible deployment path when that component is Ansible-managed.
- When a direct `kubectl` validation is appropriate, use the narrowest applicable resource/file.
- After deployment, wait for the affected rollout and verify pod/service/endpoint health.
- Do not delete/recreate healthy resources merely to force an update if a normal rollout will work.

## Boundaries

- Do not change unrelated namespaces or workloads.
- Do not change RBAC, authentication, network policy, router/VLAN/firewall, or DNS unless explicitly requested.
- Do not replace persistent volumes/host paths or delete data as part of routine validation.
