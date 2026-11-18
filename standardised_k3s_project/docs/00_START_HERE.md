# Start Here

Current AI release: [Unreal and dungeon operations](WATOOM_UNREAL_DUNGEON.md), verified 18 October 2026. Exact release pins, native usage, rollback and private-skill recovery are maintained there.

Current deployment snapshot: 13 October 2026. Runtime-specific status is dated; configured/recovery guidance is not an end-to-end test.

Evidence baseline: **13 October 2026**.

## Platform snapshot

| Item | Current state |
|---|---|
| Host | `watoom-homelab` |
| OS | Fedora 44 Server |
| CPU | AMD Ryzen 5 5500, 6C/12T |
| RAM | 32 GiB |
| GPU | NVIDIA GeForce GPU 20 GB |
| NVIDIA driver | `615.71.09` at collection |
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
3. This guide explains the intended operating model and verified current baseline.
4. `/app/homelab-guide` is legacy/reference material only.

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

> **LLM exception:** the current llama.cpp/router/Open WebUI stack is not fully represented by the broad manifest registry. After a rebuild, reconcile the LLM stack using the dedicated manifests/scripts described in `09_LLM_AI_PLATFORM.md`.

## Intentional stopped/on-demand workloads

At the collection point these deployments were intentionally or acceptably at zero replicas:

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

## Kali security isolation, 13 October 2026

Development-agent Kali MCP access is denied in the native, main and project configuration layers. Nine agents and all three MCP connections are preserved. Explicitly authorized security work uses a separate top-level primary `watoom-kali` session; it cannot be delegated as a child or proxied through the development coordinator.

The actual security positive control returned `WATOOM_KALI_ALLOW_TEST` with exit code 0. All four development catalogs hid Kali. Builder/investigator/reviewer stale-path calls returned Unknown tool before transport; workflow voluntarily refused that probe, which is not runtime-denial evidence. Two repeated normal configuration deployments made zero changes, including the canonical deployment.

Supported commands, IaC owners, precise evidence classifications and rollback: Kali security workflow. Security commit: `e73b65d436e0873860faf40ee7dac8ba26013fd0`; the earlier protected baseline tag remains unchanged.
