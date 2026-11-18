---
title: GitHub distribution and source provenance
nav: GitHub publication
summary: How the private LLM/WatooM-Code repository packages application source, custom extensions and infrastructure without runtime data or private history.
---

## Publication model

The LLM environment is packaged in a separate private repository. The existing homelab repository remains private and authoritative for production IaC. The distribution is a reviewed current-source snapshot; it does not import the homelab or application's complete Git history. History may contain private instructions or data even when the current file tree appears safe.

The distribution includes the pinned application source and the platform project tree so custom plugins, skills, workers, UI changes, manifests, configuration inputs and deployment tooling stay together. Including a file is not an instruction to run it.

## Package contents and provenance

| Area | Included source | Provenance |
|---|---|---|
| Application | Exact clean source snapshot behind the deployed application pin | Source commit, upstream URL, tracked file hashes and upstream license |
| Platform/IaC | Tracked files under `standardised_k3s_project/`, subject to exclusions | Homelab HEAD plus explicit current working-tree differences |
| Plugins, skills and workers | Role payloads, tooling, configuration templates and their tests | Original relative paths retained in catalogue and file manifest |
| Documentation | Project guide, software design, API/user guides, automation catalogue and generated Glance pages | Rebuild commands and drift/link checks |
| Publication metadata | File manifest, exclusions, scan findings and external prerequisites | Private operator report; publish only the sanitised report |

Use the independent pins in `ansible/vars/watoom-code.yml` for application, Toolkit and AgentMemory. A matching application source pin does not establish that a separately built dependency's source is bundled. Record each independently and mark unavailable source/build recipes explicitly.

## Exclusions

- Secret stores, generated Kubernetes Secrets, plaintext credential files, private keys, kubeconfigs, private deployment evidence and recovery grants.
- Runtime databases, session/prompt histories, caches, uploaded files, active jobs, receipts containing private inputs and application-state backups.
- Model weights, purchased asset libraries, Unreal Engine source and other redistribution-restricted inputs.
- Existing Git object stores, bundles, backup archives and unrelated project workspaces.
- The private source explicitly named by `tools/git/private-publication-excludes.json`, including its history. Its source body stays in the existing private mechanism.
- Dependency/build caches and generated large binaries; retained lockfiles and original license notices support rebuilding.

Private GitHub visibility is not a substitute for excluding credentials. A static scanner is an aid, not proof that no secret or personal information exists. Never print matched secret values into documentation or a console log; findings should identify only paths, lines and rule IDs.

## Before the first push

1. Establish exact source roots and clean application source/image identity. Record platform dirty paths without staging unrelated work.
2. Build a fresh export from explicit source file lists, apply exclusions and preserve third-party notices.
3. Generate a per-file SHA-256 manifest and a provenance document; verify no links escape the export and no files exceed GitHub limits.
4. Scan the exported bytes and inspect credential-bearing/configuration and license findings. Keep unresolved findings out of the published tree.
5. Run documentation catalogue drift, rendering, local links and package-specific static checks.
6. Initialise a new Git repository with no source ancestry, review its staged paths, and commit only the prepared snapshot.
7. Create the destination as private, push a normal initial branch and verify repository visibility, branch/commit and key files through GitHub.

Do not use `publish-private-safe.py --publish-main` for this task: that helper targets the existing homelab `main`, requires a clean tree and has its own specific ancestry checks. The separate distribution does not change that repository's visibility or production branch.

## Reproducing and updating

The README links to the project guide for prerequisites, configuration, component deployment and smoke checks. The distribution retains environment-specific guards and private-image references honestly; do not describe it as a clean-machine installer until a separate clean-room deployment has passed.

For an update, regenerate the export from reviewed source roots and compare manifests. Review added/removed files, source/image pins, third-party notices and publication findings. Re-run documentation and focused component checks, then push only the prepared distribution changes. Do not merge runtime state back into IaC.

When changing scripts, playbooks, roles or tooling, update source comments/contracts and run:

```bash
python3 scripts/render-server-catalogue.py
python3 scripts/render-server-catalogue.py --check
/data/ai/toolchains/docs-render/bin/python scripts/render-glance-guide.py
/data/ai/toolchains/docs-render/bin/python scripts/render-glance-guide.py --check
python3 scripts/verify-homelab-documentation.py
```

Glance serves generated guide files from the operator checkout by hostPath; documentation updates need no application restart. Keep catalogue output and software design cross-links in the same reviewed change.
