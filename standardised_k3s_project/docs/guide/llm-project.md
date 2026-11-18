---
title: WatooM LLM platform — project guide
nav: Project guide
summary: Project overview, requirements, installation, configuration, development and operating procedures for the self-hosted WatooM-Code environment.
---

## What the project provides

WatooM is a self-hosted coding and creative-work environment built around a customised OpenCode application, local llama.cpp inference and an Ansible-managed single-node k3s deployment. WatooM-Code provides the browser workspace, project selection, agents and native tools. The surrounding platform adds model routing, exclusive GPU reservations, persistent memory, guarded handoffs, independent image review, bounded asset workers and operator observability.

This is an operator-managed environment, not a one-command portable appliance. Host paths, image registry pins, inventory and ingress names describe a specific deployment and must be adapted for another installation. The source references below name the supported operating path for each component.

Start with the [software design](software-design.md), [custom extensions](llm-extensions.md), [API reference](llm-api.md) and [server automation catalogue](server-catalogue.md). For browser workflows, see the [user guide](llm-user-guide.md).

## Features and boundaries

The active inference path is WatooM-Code → `llm-router` → managed llama.cpp backends. `llm-router` is the only model entry point; no other model runtime is an installation prerequisite.

| Capability | Implementation | Operating boundary |
|---|---|---|
| Browser coding workspace | Custom OpenCode application and embedded UI | Application source is separate from the IaC checkout |
| Local inference | llama.cpp backends, router and model profiles | Capacity depends on the selected weights, KV budget and GPU |
| Model arbitration | Host GPU controller and inference leases | Never use direct replica changes as a model-switch API |
| Agent coordination | Native agents and coordinator-guard plugin | Serial child identity, budgets and durable recovery boundaries |
| Project spaces | Role-generated group configuration and mounts | Projects stay in their configured workspace; purchased sources remain read-only |
| Image review | Image-scope plugin, evidence receipts and native presentation | Capturing an image is not independent visual acceptance |
| Memory and learning | AgentMemory, embeddings and guarded learning tooling | Feature flags and reviewed cutovers govern activation |
| Creative work | Toolkit plus Blender, Godot, Unreal and workstation bridges | Jobs are bounded, source-preserving and reconciled after uncertainty |
| Operations | Ansible, Glance, Prometheus/Loki and backups | Dashboard observation does not grant lifecycle ownership |

## Repository layout

The private distribution keeps the infrastructure tree under `standardised_k3s_project/` and the exact application snapshot under `application/`.

| Path | Contents |
|---|---|
| `application/` | Pinned WatooM-Code/OpenCode source, packages, lockfiles, UI, native plugin interfaces and tests |
| `standardised_k3s_project/ansible/` | Playbooks, roles, defaults, templates and deployment pins |
| `standardised_k3s_project/config/` | Source configuration, prompts, model templates and Glance guide inputs |
| `standardised_k3s_project/manifests/` | Namespaces, workload and service definitions, monitoring and access policies |
| `standardised_k3s_project/scripts/` | Operator wrappers, renderers, checks and recovery entrypoints |
| `standardised_k3s_project/tools/` | Controllers, workers, release tooling, contracts and focused tests |
| `standardised_k3s_project/docs/` | Design, user/API guides, operations and generated source inventory |
| `publication/` | Provenance, exclusions, inventory and publication-readiness report |

The canonical server IaC remains `/data/github/watoom-standardised-homelab/standardised_k3s_project`. A distribution snapshot does not transfer production ownership to a second checkout.

## Requirements

- A Linux operator environment with Git, Python 3, Ansible and the collections declared by this repository. Use the existing execution environment and validation wrapper where available.
- An existing, healthy k3s/containerd host; this guide does not reinstall k3s or Docker. NVIDIA driver/device-plugin integration is required for GPU inference.
- Storage for application state, local model files, image builds and workspace assets. Keep these outside Git. The current deployment uses `/data` for bulk data and `/app` for application/registry storage.
- A reachable image registry and reviewed immutable images. The server's `127.0.0.1:5000` pins are not publicly downloadable images.
- Provisioned credentials and TLS/ingress appropriate to the destination environment. Example files contain placeholders; generated Secret objects and private state are not distribution inputs.
- Bun and native build dependencies for application development; the application snapshot's `package.json` declares its exact package-manager version. Use the lockfile and package-specific scripts, not an arbitrary latest Bun.
- Optional Blender/Godot/Unreal and workstation tooling only for the corresponding worker paths. Model weights, engine source and purchased assets have their own download/license requirements.

## Installation and configuration

### Review before deploying

1. Read the [server roles](server-roles.md), [playbooks](server-playbooks.md) and [Operations](operations.md). Check which component each playbook actually changes.
2. Create a destination inventory and private credentials through the established mechanism. Review `ansible/inventories/homelab`, `ansible/roles/watoom-code/defaults/main.yml`, `ansible/roles/llm-model-lab/defaults/main.yml` and the owning manifest inputs.
3. Adapt host paths, registry references, project roots, DNS/ingress and storage classes in an isolated checkout. Some guards intentionally require the original namespace/root; port those invariants explicitly rather than disabling checks.
4. Build or obtain the matching application, AgentMemory, Toolkit and inference images. Record image digest and source commit together. `ansible/vars/watoom-code.yml` is the current independent pin source for application, Toolkit and AgentMemory.
5. Install the model weights separately and select a profile that fits the destination GPU. Preserve the controller and admission/fencing requirements; a model manifest alone is not the full platform.
6. Validate the exact source changes before selecting any deployment entrypoint.

### Existing-host validation

Run from `standardised_k3s_project/` in a configured operator environment:

```bash
git status --short
./scripts/watoom-ansible-validate.sh standard
python3 scripts/render-server-catalogue.py --check
/data/ai/toolchains/docs-render/bin/python scripts/render-glance-guide.py --check
python3 scripts/verify-homelab-documentation.py
```

The catalogue uses Python's standard library. The guide renderer needs the versions in `scripts/requirements-docs.txt`; YAML operations use the existing Ansible/PyYAML environment. Syntax checks do not establish safe deployment, resource capacity or functional acceptance.

### Component entrypoints

| Component | Owning entrypoint | What to inspect first |
|---|---|---|
| WatooM-Code application | `watoom-code.yml` imports `watoom-code.yml` | `watoom-code` role, release pins, namespace/root assertions, state preservation |
| Router/model lab | `llm-model-lab.yml` | Both plays: Pi model-lab controls and `llm-model-lab` role; activation gates |
| GPU controller runtime | `gpu-controller.yml` | `llm-model-lab` role's `gpu-controller` tasks and existing ownership state |
| Native skills | `watoom-native-skills.yml` | `watoom-code` role's `native-skills` tasks and approved source catalogue |
| Coordinator/image scope | Dedicated `watoom-code-coordinator-guard.yml` and `watoom-code-image-scope.yml` | Native idleness/admission, package identity and rollback |
| Game/asset workers | Dedicated game-worker, Fab, pose and workstation playbooks | Request contracts, source mounts, resource bounds and fallback policy |
| Backups | `watoom-code-backup.yml` | Backend-specific backup limits and off-host destination |

After reviewing a component's requirements, the existing operator wrapper accepts an explicit playbook, for example `./ansible-run playbooks/watoom-code.yml`. This is a mutation, not an installation smoke test. Do not run broad `site.yml` to discover dependencies.

## Everyday operation

Check Kubernetes readiness, controller status and the native authenticated `/api/info` endpoint. Use the browser's configured project spaces and native model selection. The router mediates inference; `qwen-ready` with `owner=null` means the primary model is available and no exclusive specialist job holds a reservation. Inference requests have separate leases.

For a worker request, retain the original request ID, source fingerprint, parent session and receipt. `QUEUED` is admission, `RUNNING` is execution, and a completed process is not automatically visual acceptance. On restart/uncertainty reconcile the exact existing job; do not resubmit blindly.

Back up state before release or schema changes. `tools/watoom-code/backup.py` verifies SQLite snapshots and archives configuration; read its README for AgentMemory engine limitations. A Deployment rollback does not undo a database migration. Preserve known-good image pins and backups until restored behaviour is verified.

## Development and tests

Work in an isolated checkout; preserve other dirty files and active sessions. Application changes belong in the application source, platform helpers in `tools/`, and durable installation/configuration in the owning role or manifest input. See [the extensions map](llm-extensions.md) for the correct layer.

The application root intentionally rejects `bun test`; select the affected package and its declared test script. Start with `application/package.json` and the relevant package's `package.json`. Use the pinned lockfile and inspect the build helper before invoking it: `tools/watoom-code/build.py` contains environment-specific build paths and registry expectations.

Focused platform checks include:

```bash
node tools/watoom-code/test-coordinator-guard.mjs
python3 -m unittest discover -s docs/llm-platform/examples -p 'test_*.py'
python3 docs/llm-platform/validate.py
```

Choose checks for the changed component. Many acceptance/recovery scripts inspect or mutate a live system; do not bulk-execute every `test*`, `acceptance*`, `cutover*` or `recover*` file. A tested source change is not evidence that a production runtime was updated.

## Troubleshooting

| Symptom | First evidence | Next step |
|---|---|---|
| Browser loads but API fails | `/api/info`, authentication, app readiness and native logs | Check configured origin/auth and matching source/image identity |
| Model unavailable | Router health, exact backend readiness, controller phase and lease state | Use the owner lifecycle; never force GPU replicas |
| Worker remains queued | Exact status reason and dispatcher/remote worker availability | Restore the required worker or seek an approved fallback; keep request identity |
| Guard rejects a handoff | Exact rejection, pending child and canonical checkpoint | Continue the recorded child or return through the existing critic boundary |
| Image review does not qualify | Presentation evidence, image hash and structured receipt | Repeat only the missing qualified review step; never fabricate a receipt |
| Node slows down | Memory/swap, I/O pressure, disk free space and pod resource limits | Identify the workload before changing limits or restarting services |
| Guide source/output drift | Catalogue and renderer `--check`, then local link verifier | Regenerate from source; don't patch generated HTML |

### New extension requirements and limits

The language-knowledge plugin requires the configured versioned card data; vector search additionally depends on its vector files and embedding service, while lexical lookup can continue without them. The production card data covers Godot and Blender (about 124,000 cards; the app needs roughly 650 MiB more memory than with the Godot-only subset). Bazzite heavy-work routes require the remote worker, staged toolkit/capture image as applicable, and enough free RAM; jobs remain queued until service recovers or their status permits the agent to request a RIG equivalent. The 10-minute wait does not automatically dispatch to the RIG. Keep the default server local fallback disabled because it would reserve GPU headroom.

The MetaHuman path requires an owned package and its target-engine licence review; the skin-map stage additionally requires the RIG Unreal lane, installed MetaHuman optional content, and a tested memory limit. Current verification covers one editable Base_Female character only. Game templates must retain their attribution/licence and be copied into a project; DEM terrain contains elevation, not roads/buildings. Fab acquisition remains individually owner-approved. See [Custom extensions](llm-extensions.md#what-s-new-2026-11-03-to-2026-11-07) for source paths and verification scope.

See [Recovery](recovery.md), [Troubleshooting](troubleshooting.md), [Monitoring](monitoring.md) and [GitHub publication](llm-publication.md) for the corresponding procedures.

## Environment disaster recovery

The [disaster recovery guide](disaster-recovery.md) defines the environment/project/service-state scope, private capture, off-host verification, isolated restoration and guarded replacement-host phases. Git alone is not a full backup; readiness remains blocked until the required recovery evidence exists. Media and purchased libraries may be reacquired, while private state and authored projects need independent protection.
