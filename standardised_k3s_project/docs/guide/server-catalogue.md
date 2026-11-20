---
title: Server automation reference
nav: Server reference
summary: Complete tracked-source coverage for operator scripts, Ansible playbooks and roles, tools, checks and deployed payloads.
---

This catalogue is generated from tracked source and untracked code candidates by `scripts/render-server-catalogue.py`. It does not run programs or certify their deployment. Source links use the configured WatooM source repository; the separate LLM repository retains the same `standardised_k3s_project/` paths. Descriptions name their evidence basis; a filename summary is not a verified operational contract.

Read [Operations](operations.md), [installation and configuration](llm-project.md), and [the software design](software-design.md) before executing deployment or recovery helpers. Run no bulk scripts from this list.

## Coverage

| Area | Source files | Reference |
|---|---:|---|
| `scripts/` | 77 | [Operator scripts](server-scripts.md) |
| `ansible/playbooks/` | 92 | [Playbooks](server-playbooks.md) |
| `ansible/roles/` | 1309 | [Roles and deployed payloads](server-roles.md) |
| `tools/` | 1445 | [Tools and checks](server-tools.md) |

The [machine-readable inventory](/guide/assets/server-catalogue.json) records every tracked file in these four areas, including non-executable templates, fixtures, bundled dependency files, and private-source placeholders. It contains paths, file hashes and descriptions, not private instruction bodies or secret values. Untracked code candidates are included for completeness; inclusion does not claim they are committed. Runtime helper copies and external application source are outside this catalogue.

## How to use the reference

1. Start with the task in Operations or the LLM project guide.
2. Locate its playbook and the role/tasks it imports.
3. Inspect defaults, required variables, templates, and the exact helper in Git.
4. Validate the change using the documented tier; apply only the owning playbook.
5. Verify runtime behaviour and record rollback evidence.

## Source and runtime boundaries

The operator checkout is desired state. `/data/ai/helper-scripts` contains installed runtime copies and state; fix their owner source rather than editing an installed copy. `archive/`, `retired/` and historical acceptance notes are references, not installation instructions. Test/acceptance/cutover names never imply permission to run on production. Use the [custom extensions map](llm-extensions.md) for plugins, agents, skills and workers, and [GitHub publication](llm-publication.md) for external source and distribution boundaries.
