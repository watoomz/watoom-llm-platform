# IaC and Ansible Operations

## Control rule

**Git stores desired state. Ansible performs normal infrastructure mutations. `watoom-menu.sh` is the operator frontend.**

Canonical checkout:

```text
/data/github/watoom-standardised-homelab/standardised_k3s_project
```

The repository menu is authoritative; check any installed copy for drift before relying on it.

## Broad reconciliation

```bash
cd /data/github/watoom-standardised-homelab/standardised_k3s_project
./ansible-run playbooks/site.yml
./ansible-run playbooks/validate.yml
```

For rebuilds, use the ordered rebuild sequence in `12_BACKUP_RECOVERY.md` rather than treating `site.yml` as a host installer.

## Targeted operations

Prefer the smallest owner that matches the change:

```bash
# One registered Kubernetes application
./ansible-run playbooks/kubernetes-app.yml   -e kubernetes_app_name=radarr   -e kubernetes_app_action=reconcile

# Docker stack
./ansible-run playbooks/docker-stack.yml   -e docker_stack=wireguard   -e docker_action=restart

# Secrets reconciliation
./ansible-run playbooks/secrets.yml
./ansible-run playbooks/kubernetes-secrets.yml

# Health / production acceptance
./ansible-run playbooks/health.yml
./ansible-run playbooks/validate.yml
```

Use `scripts/watoom-menu.sh` or `https://iac-console.internal.homelab.example/menu` when an interactive operator frontend is more convenient.

## Manifest registry

`ansible/inventories/homelab/group_vars/all.yml` defines deterministic groups for namespaces, infrastructure, media, games and RBAC. Templates, examples and manual jobs are intentionally excluded from the broad registry.

Dispatcharr is intentionally excluded from `kubernetes_app_manifests`: its dedicated control workflow owns VPN/no-VPN variants.

### LLM stack

The llama.cpp backends, LLM router and SearXNG manifests are not in the broad `k3s_manifest_groups`; their owning roles and the tools under `tools/llm/` apply them.

Consequences:

- Do not tell operators that `playbooks/kubernetes.yml` alone fully restores the AI stack.
- Do not add duplicate LLM resources just to make a rebuild appear complete.
- A future IaC improvement may register the LLM set deliberately after a separate validation pass.

## Host-path ownership

The active host-path registry covers game, media, dashboard, monitoring, WireGuard, Home Assistant and Plex paths plus bulk `/data` directories. Removed paths such as `/app/openvpn`, `/app/homepage`, `/app/kali`, `/app/epg` and generic `/app/minecraft` must not be recreated.

## Change discipline

Before a production change:

```bash
git status --short --untracked-files=all
git diff --check
```

After the change:

```bash
./ansible-run playbooks/validate.yml
kubectl get pods -A
docker compose ls
```

Do not broad-reset a dirty working tree to “fix” a single service. Existing changes may represent other approved consolidation work.

## AI owners

Playbooks: `gpu-controller.yml`, `llm-model-lab.yml`, `opencode-llama-mesh-integration.yml`, `llama-mesh-pipeline-recovery.yml`, and for WatooM Code `site.yml --tags platform` and `watoom-code-parts.yml`. Inspect their current variables and activation gates before reconciliation. Syntax validation does not authorize replaying ownership/storage cutover.

The controller remains the sole GPU replica writer. Preserve admission/RBAC, durable journals and credentials. See [backup and recovery](12_BACKUP_RECOVERY.md).

Markdown operations pages feed the browser guide through `scripts/render-glance-guide.py`. HTML uses the existing hostPath; no application rollout is needed for HTML-only publication. Config/helper changes use the separate `scripts/render-glance-configmaps.py` and normal owning workflow.
