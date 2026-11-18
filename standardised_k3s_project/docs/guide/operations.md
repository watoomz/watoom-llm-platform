---
title: Operations and change control
nav: Operations
summary: How changes are made — the IaC layout, the playbooks for routine work, validation tiers, Git discipline and how this documentation is published.
---

## Operating model

**Git stores desired state. Ansible performs changes. The menu and IaC console are front ends.**

| Item | Location |
|---|---|
| Operator checkout (serves Glance, runs host timers) | `/data/github/watoom-standardised-homelab/standardised_k3s_project` |
| Wrapper | `./ansible-run <playbook>` (inventory, vault and execution environment preset) |
| Interactive menu | `scripts/watoom-menu.sh`, or `https://iac-console.internal.homelab.example/menu` |
| Inventory and registries | `ansible/inventories/homelab/group_vars/all.yml` |
| Roles / playbooks | `ansible/roles`, `ansible/playbooks` |
| Manifests | `manifests/00-namespaces` … `manifests/40-rbac` |
| Source config and render inputs | `config/` |
| Maintained helpers | `scripts/`, `tools/` |

Before editing, check whether a file is authoritative or generated. Generated files (Glance ConfigMaps, guide HTML, Secret manifests) are rebuilt from their sources by a renderer.

## Routine playbooks

| Task | Command |
|---|---|
| Health check | `./ansible-run playbooks/health.yml` |
| Production validation | `./ansible-run playbooks/validate.yml` |
| One Kubernetes app | `./ansible-run playbooks/kubernetes-app.yml -e kubernetes_app_name=radarr -e kubernetes_app_namespace=radarr -e kubernetes_app_action=restart` |
| One Docker stack | `./ansible-run playbooks/docker-stack.yml -e docker_stack_target=wireguard -e docker_action=restart` |
| One game server | `./ansible-run playbooks/game.yml -e game_name=valheim -e game_action=start` |
| Secrets | `./ansible-run playbooks/secrets.yml`, then `playbooks/kubernetes-secrets.yml` |
| Image drift | `./ansible-run playbooks/image-audit.yml -e image_audit_action=check` |
| Broad reconcile | `./ansible-run playbooks/site.yml` (not a host installer) |

App actions: `status`, `start`, `stop`, `restart`, `reconcile`, `set_image`. Docker actions: `status`, `up`, `down`, `restart`, `pull`, `reconcile`; stack targets: `wireguard`, `azuracast`, `dispatcharr_cloudflare` or `all`. Use the smallest owner that covers the change; restart through the owner before deleting pods.

The AI stack and WatooM Code have dedicated playbooks (`gpu-controller.yml`, `llm-model-lab.yml`, `watoom-code-*.yml`, `watoom-native-skills.yml`). Inspect their variables and fences before running them.

## Validation tiers

| Tier | Checks | Use |
|---|---|---|
| `fast` | YAML, production-profile `ansible-lint`, WatooM policy | Local iteration |
| `standard` | `fast` + syntax check in the production execution environment | Production-bound content |
| `full` | `standard` + safe dynamic and idempotence hook | High-assurance changes |

```bash
./scripts/watoom-ansible-validate.sh standard
```

Choose acceptance to match the change. Documentation needs renderer, link and served-content checks; runtime changes need real behaviour and rollback evidence. A zero exit code from `kubectl apply` is not acceptance.

## Change sequence

1. Inspect current source and nearby conventions; reuse existing roles and helpers.
2. Make the smallest source change; keep environment values in vars and templates.
3. Validate (`git diff --check`, the relevant tier, renderer `--check`).
4. Deploy only the affected component through its owner.
5. Verify the live result and the health signals on [Monitoring](monitoring.md).
6. Confirm the Git index holds only the intended paths.

## Git discipline

```bash
git status --short --untracked-files=all
git diff --check
git add <explicit paths>
```

Never use `git add .`, `git add -A`, `git reset --hard`, `git clean -fd`, `git checkout .` or broad `git restore`. A dirty tree may hold other approved work; isolate a fix by path, not by discarding changes.

## Documentation

| Output | Source | Renderer |
|---|---|---|
| Guide pages (`config/glance/guide/*.html`) | `docs/guide/*.md` | `scripts/render-glance-guide.py` |
| Job reference | `config/glance/job-reference.json` | `scripts/render-job-reference.py` |
| Pipeline prompts | `config/glance/pipeline-prompts.json` | `scripts/render-pipeline-prompts.py` |
| Glance Knowledge page | skill registry catalogue | `scripts/render-glance-knowledge.py --catalog …` |
| Glance ConfigMaps | `config/glance/glance.yml`, `helper.py` | `scripts/render-glance-configmaps.py` |

```bash
/data/ai/toolchains/docs-render/bin/python scripts/render-glance-guide.py          # write
/data/ai/toolchains/docs-render/bin/python scripts/render-glance-guide.py --check  # drift + link check
```

Guide HTML is served by hostPath from the operator checkout, so it goes live when that checkout updates; no restart is needed. Dashboard changes need the ConfigMap rendered and applied, then a Glance rollout.

### Feature and reference releases

Changes to agents, skills, language-knowledge, Bazzite routing, game workers and the RIG lane belong to their owning roles/tools and deployment pins. Updating a skill does not rebuild the application image; changing the language-knowledge package does not update the main app pin. Review the exact owner and immutable release identity before promotion. For worker changes, validate the source/receipt path and keep job reconciliation separate from rollout. Never use production playbooks or restart services as part of a documentation-only update.

The server catalogue is generated from maintained comments/contracts. If a catalogue entry is thin, improve its source docstring/comment and regenerate; never edit `docs/guide/server-*.md` or the corresponding guide HTML by hand. The guide's maintained source is Markdown under `docs/guide/`, and all generated pages should be rendered and checked with the established scripts before commit.
| `/data/ai/projects/development`, `/data/ai/projects/pipelines` | Project groups; `llm/pipelines` |

## Project and source reference

See the [LLM project guide](llm-project.md) for requirements, configuration, deployment,
development and troubleshooting; [custom extensions](llm-extensions.md) for plugins,
agents, skills and worker integrations; and the [server automation reference](server-catalogue.md)
for every tracked script, playbook, role and tool. [GitHub publication](llm-publication.md)
covers the separate private distribution and source provenance.

## Environment disaster recovery

The [disaster recovery guide](disaster-recovery.md) defines the environment/project/service-state scope, private capture, off-host verification, isolated restoration and guarded replacement-host phases. Git alone is not a full backup; readiness remains blocked until the required recovery evidence exists. Media and purchased libraries may be reacquired, while private state and authored projects need independent protection.

## Tickets (to-do list with Discord alerts)

A shared to-do list for you and the models, with every change posted to Discord. Log an item with `watoom-ticket add "title"`; the models log and update tickets through request files. See [Tickets](tickets.md) for the commands, the model workflow, the Discord setup and troubleshooting.
