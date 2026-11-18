---
name: kubernetes-router
description: Route Kubernetes requests by cluster type and operation to appropriate child skills and IaC workflows; distinguish existing K3s operations from local KIND testing.
---

# Kubernetes Router request router

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
| Kubernetes K3s IaC diagnostics | `Kubernetes K3s IaC diagnostics` |
| Kubernetes local KIND development | `Kubernetes local KIND development` |
| Kubernetes manifests deployment validation | `Kubernetes manifests deployment validation` |

## Domain requirements

The existing kubernetes child is specifically a KIND local-development skill. Do not use its cluster-install commands against the WatooM K3s host. Identify the real cluster and namespace, inspect live state, preserve workloads, and use maintained IaC and deployment guards. Do not reinstall K3s or Docker to fix an application.

```skill-routing
{"kind": "router", "aliases": ["kubernetes router workflow", "kubernetes router router"], "requires": []}
```
