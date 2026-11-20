# WatooM Standardised Homelab

This repository is the desired-state and operations source for the WatooM single-node homelab: a Fedora 44 host running k3s and Docker/Compose, with Ansible as the normal way to change and validate it.

## Everyday commands

- `make check` (run here): every deterministic check and test suite; `make lint` for ansible-lint/yamllint.
- `ansible-run playbooks/site.yml`: base layers (host paths, k3s manifests, Docker stacks, validation).
- `ansible-run playbooks/site.yml --tags platform` (or one component tag such as `tickets_board`): converge the AI/app platform, see `ansible/playbooks/platform.yml`.
- `ansible-run playbooks/watoom-code-parts.yml --tags agents` (also `image_scope`, `searxng`, `dev`, ...): update one part of WatooM Code. Agent prompts are generated from `ansible/roles/watoom-code/files/native/_src` by `scripts/render-native-agents.py`.
- Coordinator guard and language-knowledge changes go live only through `tools/watoom-code/recover-idle-admission.py` (idle fence + restart).

## LLM platform project documentation

- [Project overview, setup, configuration and development](docs/guide/llm-project.md)
- [Custom plugins, agents, skills and integrations](docs/guide/llm-extensions.md)
- [Complete server scripts, playbooks, roles and tools reference](docs/guide/server-catalogue.md)
- [Software design](docs/guide/software-design.md)
- [Private distribution and provenance](docs/guide/llm-publication.md)

## Start here

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
- [Host tuning](docs/18_HOST_TUNING.md)
- [Mesh workflow](docs/LLAMA_MESH_WORKFLOW.md)
- [Blender and Fab production status](docs/BLENDER_PRODUCTION_STATUS.md)
- Kali security workflow

The browser guide is published through Glance from `config/glance/guide` at `https://glance.internal.homelab.example/guide/`.

## Canonical paths

| Purpose | Path |
|---|---|
| Repository | `/data/github/watoom-standardised-homelab/standardised_k3s_project` |
| Glance guide source | `/data/github/watoom-standardised-homelab/standardised_k3s_project/config/glance/guide` |
| Application state | `/app` |
| Bulk data/media | `/data` |
| AI data, models, projects | `/data/ai` |

## Operating model

1. **Git defines intended state.**
2. **Ansible is the normal operator API** for host, Kubernetes and Docker changes.
3. **`scripts/watoom-menu.sh` is the operator frontend**, not a second source of desired state.
4. **Live state verifies reality**, especially during incident response.
5. **Validation follows change**, using `playbooks/validate.yml` and `make check`.

The LLM manifests in `manifests/10-infrastructure/llm/` are applied by their owning roles (`llm-model-lab`, the GPU controller and WatooM Code playbooks), not by the general `k3s_manifest_groups` registry. See [LLM / AI platform](docs/09_LLM_AI_PLATFORM.md).

## Naming

- **Glance** is the dashboard; the guide lives under `/guide/`.
- **Seerr** is the media-request application; its host data path is `/app/overseerr`.
- **WireGuard** (`wg-easy`) is the remote-access VPN. Dispatcharr uses the OpenVPN protocol through Gluetun/PIA.
- The CS2 game server runs in namespace `cs2`; its helper services run in `platform-workers`.
- Internal services use the Let's Encrypt wildcard for `*.internal.homelab.example`, issued by cert-manager and copied to each `watoom-tls` Secret by `watoom-internal-tls-sync.timer`.

## Quick health check

```bash
cd /data/github/watoom-standardised-homelab/standardised_k3s_project
./ansible-run playbooks/health.yml
./ansible-run playbooks/validate.yml
kubectl get pods -A
docker compose ls
```

Intentional `0/0` workloads are not failures by themselves: several game servers and large llama.cpp backends run on demand.

## Kali security isolation

Kali tools are denied to every development agent in the native, main and project configuration layers. Kali and Nmap work runs only in `watoom-kali`, either as a child the coordinator delegates to or as a session the owner starts. Commands, IaC owners and rollback: Kali security workflow.
