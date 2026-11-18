---
title: LLM platform documentation
nav: LLM documentation
summary: The complete software documentation set for the WatooM local AI platform, with requirements, design, interfaces, operations and user workflows.
---

## Start here

This set documents the complete WatooM homelab LLM platform: WatooM Code, native agents and memory, inference routing, GPU ownership, model lifecycle, bounded specialist workers, deployment, observability and recovery. It is a description of the maintained implementation with explicit requirements and acceptance criteria. It is not a claim that every installed skill, model or retained experiment has passed live acceptance.

| Document | Audience | Contains |
|---|---|---|
| [Software Requirements Specification](llm-requirements.md) | Owner, reviewers, maintainers | Scope, actors, functional/nonfunctional requirements, acceptance and traceability |
| [Software Design Document](llm-design.md) | Architects and developers | Boundaries, components, trust, state machines, flows and design decisions |
| [Technical Specification](llm-specification.md) | Implementers and release engineers | Deployment contracts, configuration, runtime profile, persistence and invariants |
| [System documentation](llm-operations.md) | Operators | Installation/reconciliation, monitoring, backup, recovery, release and troubleshooting |
| [API and SDK documentation](llm-api.md) | Integrators | Native API, router API, controller client, Model Manager, worker contracts and examples |
| [User documentation](llm-user-guide.md) | Platform users | Projects, sessions, agents, images, tools, models, permissions and recovery from common problems |

Read the user guide to operate the platform. Use the operations guide before changing it. Start at the requirements and design documents for a review or rebuild. Existing [AI platform](ai.md), [WatooM Code](watoom-code.md), [recovery](recovery.md) and [security](security.md) pages provide related homelab context.

## Version and authority

Baseline verified 3 November 2026, Australia/Brisbane: llamAmpere v0.6.2 with the owner-adopted combined turbo profile, 300 W configured cap, fixed MTP depth 5, CUDA graphs and ubatch 1024. Application source is pinned to `786682b1489e92cba4e4b5a277bd49c565c94e4f`. Runtime image pins are maintained in the owning manifests and `ansible/vars/watoom-code.yml`, not selected by these documents.

Authority order is: live inspected state and acceptance evidence; the exact owning IaC/source and immutable release pins; this documentation; older dated notes. A mismatch is a finding to investigate, not permission to rewrite live state. Stable requirements are separated from changeable capacity and tuning values. The specification lists the current profile; operators must reverify it before maintenance.

## Scope and boundaries

Included: interactive coding/research/writing sessions; local text/vision inference; native project access and permissions; coordinator handoff/evidence guards; AgentMemory and embedding integration; model installation/enrollment/removal; CPU/engine/image/Mesh specialist boundaries; API clients; Git and Glance documentation publication.

External dependencies: Fedora, existing k3s/container runtime, NVIDIA driver, persistent storage, internal DNS/TLS/Traefik, workstation workers, SearXNG and artifact inputs. This set documents their interfaces without prescribing network redesign or reinstalling the host. Game engines and purchased asset pipelines retain their own specialist instructions and licenses.

Excluded from automatic operation: production adoption without owner authorization, networking/firewall changes, purchases, exposing secrets, bypassing GPU ownership, resetting state to clear errors, and arbitrary remote-code execution from downloaded model metadata. Public internet exposure and multi-tenant isolation are not qualified features.

## Source map

Paths below are relative to `standardised_k3s_project/` unless stated otherwise.

| Subject | Authoritative source |
|---|---|
| Production application/AgentMemory/Toolkit image pins | `ansible/vars/watoom-code.yml` |
| Native app deployment, projects, skills and memory | `ansible/roles/watoom-code/` |
| Inference primary, weights, KV and placement | `manifests/10-infrastructure/llm/llama-cpp-swift-qwen38.yml` |
| Controller runtime and identities | `tools/llm/watoom-gpu-controller/`; `ansible/roles/llm-model-lab/files/gpu-controller.json` |
| Production Python router | `ansible/roles/llm-model-lab/files/gpu-controller-router.py` |
| Model Manager | `tools/model-manager/`; `ansible/playbooks/model-manager.yml` |
| Toolkit worker API | `tools/watoom-toolkit/agent.py` and its contracts |
| Guard, native agents and skills | `ansible/roles/watoom-code/files/` |
| Operator maintenance, backup and release | `tools/watoom-code/` |
| Host GPU cap | `ansible/roles/gpu_host/` |
| Documentation source and renderer | `docs/guide/llm-*.md`; `scripts/render-glance-guide.py` |

The full pinned native API schema, route index, verification metadata and runnable client examples are maintained under `docs/llm-platform/` for Git publication. Download links are on the API page. Source snapshots are references, not replacement services.

## Publication and maintenance

The Markdown files are the canonical human-readable documents in Git and are rendered into Glance by the existing guide renderer. No second website or application runtime is introduced. Navigation, local links, section anchors, search index and downloadable reference files are validated together.

For any application, model, routing or controller release: update the owning source first, verify acceptance, revise the affected specification/API/requirements traceability, refresh the schema from the matching pinned application source, render, check and verify served pages. Do not publish private runtime configuration, tokens, session contents, image-review grants, databases, weights or raw benchmark prompts. A source commit is not proof of deployment; a pod rollout is not proof of acceptance.
