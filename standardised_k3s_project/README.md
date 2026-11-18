# WatooM Standardised Homelab

Evidence baseline: **13 October 2026**

This repository is the desired-state and operations source for the WatooM single-node homelab. It manages a Fedora 44 host running k3s and Docker/Compose, with Ansible used as the normal mutation and validation layer.

## LLM platform project documentation

- [Project overview, setup, configuration and development](docs/guide/llm-project.md)
- [Custom plugins, agents, skills and integrations](docs/guide/llm-extensions.md)
- [Complete server scripts, playbooks, roles and tools reference](docs/guide/server-catalogue.md)
- [Software design](docs/guide/software-design.md)
- [Private distribution and provenance](docs/guide/llm-publication.md)

## Start here

- Current live state and audit limits (13 October 2026)

- [Operations overview](docs/00_START_HERE.md)
- [Architecture](docs/01_ARCHITECTURE.md)
- [Network, DNS and TLS](docs/02_NETWORK_DNS_TLS.md)
- [Ansible and IaC operations](docs/03_IAC_ANSIBLE_OPERATIONS.md)
- [k3s platform](docs/04_K3S_PLATFORM.md)
- Docker/Compose stacks
- Service catalogue
- Media and streaming
- Game servers
- [LLM / AI platform](docs/09_LLM_AI_PLATFORM.md)
- [Complete LLM software documentation: requirements, design, specification, operations, API/SDK and user guide](docs/llm-platform/README.md)
- [Monitoring and observability](docs/10_MONITORING_OBSERVABILITY.md)
- Security and remote access
- [Backup and recovery](docs/12_BACKUP_RECOVERY.md)
- [Operations runbook](docs/13_OPERATIONS_RUNBOOK.md)
- [Troubleshooting](docs/14_TROUBLESHOOTING.md)
- [Validation and change control](docs/15_VALIDATION_CHANGE_CONTROL.md)
- [Documentation maintenance](docs/16_DOCUMENTATION_MAINTENANCE.md)
- Legacy and retired components
- [Host tuning](docs/18_HOST_TUNING.md)
- [Production Mesh workflow](docs/LLAMA_MESH_WORKFLOW.md)
- [OpenCode production](docs/WATOOM_OPENCODE_V2_CANARY.md)
- [Blender/Fab validation and retired canary policy](docs/BLENDER_PRODUCTION_STATUS.md)
- Authorized Kali security workflow

The browser guide is published through Glance from `config/glance/guide` and is available internally at `https://glance.internal.homelab.example/guide/`.

## Canonical paths

| Purpose | Path |
|---|---|
| Repository | `/data/github/watoom-standardised-homelab/standardised_k3s_project` |
| Glance guide source | `/data/github/watoom-standardised-homelab/standardised_k3s_project/config/glance/guide` |
| Application state | `/app` |
| Bulk data/media | `/data` |
| Legacy guide package | `/app/homelab-guide` (reference only) |

The old `/data/standardised_k3s_project` checkout is retired and must not be reintroduced.

## Operating model

1. **Git defines intended state.**
2. **Ansible is the normal operator API** for host, Kubernetes and Docker changes.
3. **`scripts/watoom-menu.sh` is the operator frontend**, not a second source of desired state.
4. **Live state is used to verify reality**, especially during incident response and documentation reconciliation.
5. **Validation follows change**, using `playbooks/validate.yml` and the WatooM Ansible validation policy.

### Important exception: local LLM stack

The current WatooM Code/llama.cpp/router manifests are active and supported, but the LLM manifests are not presently listed in the broad `k3s_manifest_groups` registry. Treat the LLM stack as a specialised controller/model-lab/OpenCode IaC exception until it is deliberately brought under the main Ansible manifest registry. See [LLM / AI platform](docs/09_LLM_AI_PLATFORM.md).

## Current naming decisions

- **Glance** is the dashboard. Homepage is retired.
- **Seerr** is the media-request application; its host data path remains `/app/overseerr` for historical reasons.
- **WireGuard** is the remote-access VPN. The former standalone `/app/openvpn` service is retired.
- Dispatcharr may still use the **OpenVPN protocol through Gluetun/PIA**; those environment variable names are valid and are unrelated to the retired standalone OpenVPN service.
- The CS2 game server remains in namespace `cs2`; helper services run in namespace `platform-workers`.

## Quick health check

```bash
cd /data/github/watoom-standardised-homelab/standardised_k3s_project
./ansible-run playbooks/health.yml
./ansible-run playbooks/validate.yml
kubectl get pods -A
docker compose ls
```

Intentional `0/0` workloads are not failures by themselves. Several game servers and large llama.cpp backends are designed to be on-demand.

## Frozen production recovery point

- Tag: `baseline/pre-new-agent-engine-20261013`.
- Commit: `6a2dc2e291f358c57df46123fdfba2cd04ffb0d2`; completed G3H ancestry integrated.
- Protected local backup: `/data/ai/backups/baselines/pre-new-agent-engine-20261013`.
- [Baseline, validation and safe rollback](docs/baselines/pre-new-agent-engine-20261013.md).
- [Production Mesh workflow](docs/LLAMA_MESH_WORKFLOW.md) and [OpenCode production guide](docs/WATOOM_OPENCODE_V2_CANARY.md).

Documentation refreshes follow the frozen tag without moving it. Preserve current controller ownership/state and unrelated pending work. Start future agent and inference-engine development on separate branches/worktrees.

## Kali security isolation, 13 October 2026

Development-agent Kali MCP access is denied in the native, main and project configuration layers. Nine agents and all three MCP connections are preserved. Explicitly authorized security work uses a separate top-level primary `watoom-kali` session; it cannot be delegated as a child or proxied through the development coordinator.

The actual security positive control returned `WATOOM_KALI_ALLOW_TEST` with exit code 0. All four development catalogs hid Kali. Builder/investigator/reviewer stale-path calls returned Unknown tool before transport; workflow voluntarily refused that probe, which is not runtime-denial evidence. Two repeated normal configuration deployments made zero changes, including the canonical deployment.

Supported commands, IaC owners, precise evidence classifications and rollback: Kali security workflow. Security commit: `e73b65d436e0873860faf40ee7dac8ba26013fd0`; the earlier protected baseline tag remains unchanged.
