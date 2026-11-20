# Start Here

AI release pins, native usage, rollback and private-skill recovery: [Unreal and dungeon operations](WATOOM_UNREAL_DUNGEON.md).

## Platform snapshot

| Item | Current state |
|---|---|
| Host | `homelab-host` |
| OS | Fedora 44 Server |
| CPU | AMD Ryzen 5 5500, 6C/12T |
| RAM | 32 GiB |
| GPU | NVIDIA GeForce GPU 20 GB |
| NVIDIA driver | `615.71.09` |
| CUDA reported by `nvidia-smi` | 13.4 |
| k3s | `v1.36.3+k3s1` |
| LAN | `10.99.20.225/24` on `enp34s0.20`, default route `10.99.20.1` |
| DMZ | `192.168.250.225/24` on `enp35s0`, no default route |
| Internal DNS suffix | `internal.homelab.example` |
| Public domain | `homelab.example` |
| Dashboard | Glance |
| IaC console | `https://iac-console.internal.homelab.example/menu` |

## Source-of-truth hierarchy

Use these sources together rather than treating one source as infallible:

1. Current Git/IaC expresses **intended state**.
2. Live Kubernetes/Docker/host state expresses **what is actually running now**.
3. This guide explains the operating model.

When Git and live state disagree, investigate and reconcile; do not silently make documentation match whichever side is convenient.

## Normal change workflow

```bash
cd /data/github/watoom-standardised-homelab/standardised_k3s_project
git status --short
# make/review the desired-state change
./ansible-run playbooks/<targeted-playbook>.yml
./ansible-run playbooks/validate.yml
git diff --check
```

Use a targeted playbook for routine changes. Use broad convergence or rebuild playbooks only when the scope justifies it.

## Rebuild sequence

```bash
cd /data/github/watoom-standardised-homelab/standardised_k3s_project
./ansible-run playbooks/rebuild-homelab.yml --tags audit
./ansible-run playbooks/foundation.yml
./ansible-run playbooks/secrets.yml
./ansible-run playbooks/kubernetes.yml
./ansible-run playbooks/docker.yml
./ansible-run playbooks/validate.yml
```

The target host must already have the required `/app` and `/data` filesystems/state restored as appropriate.

> **LLM stack:** the llama.cpp backends, router and GPU controller are applied by their own roles, not the broad manifest registry. After a rebuild, converge them as described in `09_LLM_AI_PLATFORM.md`, then WatooM Code with `playbooks/site.yml --tags platform`.

## Intentional stopped/on-demand workloads

These deployments are normally at zero replicas until started:

- `arma-reforger/arma-server-manager` and `arma-manager-mysql`
- `cs2/cs2`
- `dayz/dayz`
- `valheim/valheim`
- `minecraft-pixel/minecraft-pixel`
- `minecraft-zom/minecraft-zom`
- the larger controller-managed llama.cpp backends when not selected

Do not classify `0/0` alone as an outage.

## Documentation

The guide source is `config/glance/guide`. Glance mounts that path into `/app/guide` and serves it at `/guide` and `/guide-api` through `glance.internal.homelab.example`.

## Kali security isolation

Only `watoom-kali` can use the Kali MCP tools; the coordinator delegates Kali and Nmap work to it, and the owner can also start a `watoom-kali` session directly. Check the live rules with `python3 scripts/verify-opencode-kali-security.py`. Details: Kali security workflow.
