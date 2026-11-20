---
name: ansible
description: Route Ansible role, playbook, inventory, linting and infrastructure-automation requests to the relevant homelab or product child skills.
---

# Ansible request router

This parent selects child instructions without granting execution permission.

1. Extract the requested outcome, relevant project, inputs, output format, engine/version and constraints. Resolve only missing information that affects the route.
2. Call the native `watoom_skill_search` directly with concise intent keywords. Search each materially different stage separately. The prompt skill list is partial. Imported entries, pipelines and native tools have different lifecycle/selection status; a catalogue hit alone does not mean the route works.
3. Compare the closest routes by fit, current dependencies, compatibility, execution environment and verified outcome evidence. Prefer a compatible verified recipe over repeated discovery, after checking its source/interface hashes. An unavailable worker or unknown validation status is an explicit blocker, not permission to improvise a route.
4. Load the chosen child with `skill` using its returned exact canonical ID. Load required dependencies before the dependent stage. Start with the strongest primary child; add supporting children only when their instructions are needed. Do not load all children, re-enter this parent, or recursively load sibling routers without a distinct need. An enabled imported package may be pinned on explicit loading; unapproved packages require the owner lifecycle. Never enable or install a package merely to satisfy this router.
5. Execute using the child's actual advertised native tool/schema and the active project's permissions. A skill is instructions, a pipeline is a staged workflow, and a worker is an execution route. Keep those distinctions in the handoff. Stop on a missing dependency or unsupported route rather than bypassing its guard.
6. Record selected IDs/versions, the reason for the route, receipts and artifact references in the current checkpoint. Review the actual result. Feed only verified, non-secret outcomes into the existing memory/self-learning path; unverified suggestions remain candidates. If a stage fails, inspect its evidence and make one bounded recovery; preserve uncertain/running work and do not replay it.

## Child discovery intents

Search these intents as appropriate; this is not a fixed allowlist of children.

| Stage | Catalogue query |
|---|---|
| Ansible IaC role playbook | `Ansible IaC role playbook` |
| Ansible inventory secrets vault | `Ansible inventory secrets vault` |
| Ansible validation idempotence | `Ansible validation idempotence` |

## Domain requirements

Use the authorized project checkout and current inventory. Keep secrets out of output and commits. Separate syntax/check-mode validation from actual changes; check mode is not proof an operation is harmless. Use focused idempotence and rollback checks; never use a production deployment merely as a test.

```skill-routing
{"kind": "router", "aliases": ["ansible workflow", "ansible router"], "requires": []}
```

## Running things

You cannot run shell, ansible or kubectl yourself. Load the `operator-commands` skill and hand the operator the exact command (dry run first), its check, and a revert command.

Homelab-specific conventions: see `references/watoom.md`.
