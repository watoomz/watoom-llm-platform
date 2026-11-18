---
name: cybersecurity
description: Route authorized cybersecurity analysis, defensive investigation, vulnerability review and reverse-engineering requests to the appropriate child skills and isolated tools.
---

# Cybersecurity request router

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
| security defensive diagnostics | `security defensive diagnostics` |
| CVE vulnerability review | `CVE vulnerability review` |
| reverse engineering ghidra radare2 | `reverse engineering ghidra radare2` |
| security authorized testing | `security authorized testing` |

## Domain requirements

Resolve the authorized target and requested scope before active testing. Start with the relevant read-only analysis child. Keep secrets out of reports and learned records. Existing network, credential, execution and sandbox permissions still apply; a parent skill does not authorize scanning unrelated systems or modifying security controls.

```skill-routing
{"kind": "router", "aliases": ["cybersecurity workflow", "cybersecurity router"], "requires": []}
```
