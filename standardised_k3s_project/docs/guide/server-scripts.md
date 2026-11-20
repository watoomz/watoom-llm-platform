---
title: Operator script reference
nav: Scripts
summary: Source-backed purpose and interfaces for each tracked component; inspect gates and configuration before running.
---

This catalogue is generated from tracked source and untracked code candidates by `scripts/render-server-catalogue.py`. It does not run programs or certify their deployment. Source links use the configured WatooM source repository; the separate LLM repository retains the same `standardised_k3s_project/` paths. Descriptions name their evidence basis; a filename summary is not a verified operational contract.

Read [Operations](operations.md), [installation and configuration](llm-project.md), and [the software design](software-design.md) before executing deployment or recovery helpers. Run no bulk scripts from this list.

## Invocation and inputs

Python helpers use `python3 scripts/<name>.py`; Bash helpers use `bash scripts/<name>.sh`. Documentation rendering uses `/data/ai/toolchains/docs-render/bin/python`. Extensionless wrappers must be inspected for their shebang. Even `--help` is not assumed safe for an arbitrary operational script. Listed options are static argparse declarations, not defaults or permission to mutate.

## scripts/AGENTS.md

Source component: AGENTS. Inspect the source before use.

Source: [`scripts/AGENTS.md`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/AGENTS.md). Description basis: filename summary.

## scripts/agent-rules/coding/ansible.md

Source component: ansible. Inspect the source before use.

Source: [`scripts/agent-rules/coding/ansible.md`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/agent-rules/coding/ansible.md). Description basis: filename summary.

## scripts/agent-rules/coding/c-cpp.md

Source component: c cpp. Inspect the source before use.

Source: [`scripts/agent-rules/coding/c-cpp.md`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/agent-rules/coding/c-cpp.md). Description basis: filename summary.

## scripts/agent-rules/coding/docker.md

Source component: docker. Inspect the source before use.

Source: [`scripts/agent-rules/coding/docker.md`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/agent-rules/coding/docker.md). Description basis: filename summary.

## scripts/agent-rules/coding/go.md

Source component: go. Inspect the source before use.

Source: [`scripts/agent-rules/coding/go.md`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/agent-rules/coding/go.md). Description basis: filename summary.

## scripts/agent-rules/coding/javascript-typescript.md

Source component: javascript typescript. Inspect the source before use.

Source: [`scripts/agent-rules/coding/javascript-typescript.md`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/agent-rules/coding/javascript-typescript.md). Description basis: filename summary.

## scripts/agent-rules/coding/kubernetes.md

Source component: kubernetes. Inspect the source before use.

Source: [`scripts/agent-rules/coding/kubernetes.md`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/agent-rules/coding/kubernetes.md). Description basis: filename summary.

## scripts/agent-rules/coding/python.md

Source component: python. Inspect the source before use.

Source: [`scripts/agent-rules/coding/python.md`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/agent-rules/coding/python.md). Description basis: filename summary.

## scripts/agent-rules/coding/rust.md

Source component: rust. Inspect the source before use.

Source: [`scripts/agent-rules/coding/rust.md`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/agent-rules/coding/rust.md). Description basis: filename summary.

## scripts/agent-rules/coding/shell.md

Source component: shell. Inspect the source before use.

Source: [`scripts/agent-rules/coding/shell.md`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/agent-rules/coding/shell.md). Description basis: filename summary.

## scripts/agent-rules/coding/sql.md

Source component: sql. Inspect the source before use.

Source: [`scripts/agent-rules/coding/sql.md`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/agent-rules/coding/sql.md). Description basis: filename summary.

## scripts/agent-rules/homelab.md

Source component: homelab. Inspect the source before use.

Source: [`scripts/agent-rules/homelab.md`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/agent-rules/homelab.md). Description basis: filename summary.

## scripts/agent-rules/kali/containers.md

Source component: containers. Inspect the source before use.

Source: [`scripts/agent-rules/kali/containers.md`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/agent-rules/kali/containers.md). Description basis: filename summary.

## scripts/agent-rules/kali/core.md

Source component: core. Inspect the source before use.

Source: [`scripts/agent-rules/kali/core.md`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/agent-rules/kali/core.md). Description basis: filename summary.

## scripts/agent-rules/kali/dns.md

Source component: dns. Inspect the source before use.

Source: [`scripts/agent-rules/kali/dns.md`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/agent-rules/kali/dns.md). Description basis: filename summary.

## scripts/agent-rules/kali/evidence.md

Source component: evidence. Inspect the source before use.

Source: [`scripts/agent-rules/kali/evidence.md`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/agent-rules/kali/evidence.md). Description basis: filename summary.

## scripts/agent-rules/kali/exploitation-lab.md

Source component: exploitation lab. Inspect the source before use.

Source: [`scripts/agent-rules/kali/exploitation-lab.md`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/agent-rules/kali/exploitation-lab.md). Description basis: filename summary.

## scripts/agent-rules/kali/kubernetes.md

Source component: kubernetes. Inspect the source before use.

Source: [`scripts/agent-rules/kali/kubernetes.md`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/agent-rules/kali/kubernetes.md). Description basis: filename summary.

## scripts/agent-rules/kali/network-discovery.md

Source component: network discovery. Inspect the source before use.

Source: [`scripts/agent-rules/kali/network-discovery.md`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/agent-rules/kali/network-discovery.md). Description basis: filename summary.

## scripts/agent-rules/kali/package-management.md

Source component: package management. Inspect the source before use.

Source: [`scripts/agent-rules/kali/package-management.md`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/agent-rules/kali/package-management.md). Description basis: filename summary.

## scripts/agent-rules/kali/packet-analysis.md

Source component: packet analysis. Inspect the source before use.

Source: [`scripts/agent-rules/kali/packet-analysis.md`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/agent-rules/kali/packet-analysis.md). Description basis: filename summary.

## scripts/agent-rules/kali/service-fingerprinting.md

Source component: service fingerprinting. Inspect the source before use.

Source: [`scripts/agent-rules/kali/service-fingerprinting.md`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/agent-rules/kali/service-fingerprinting.md). Description basis: filename summary.

## scripts/agent-rules/kali/smb-ad.md

Source component: smb ad. Inspect the source before use.

Source: [`scripts/agent-rules/kali/smb-ad.md`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/agent-rules/kali/smb-ad.md). Description basis: filename summary.

## scripts/agent-rules/kali/snmp.md

Source component: snmp. Inspect the source before use.

Source: [`scripts/agent-rules/kali/snmp.md`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/agent-rules/kali/snmp.md). Description basis: filename summary.

## scripts/agent-rules/kali/web-assessment.md

Source component: web assessment. Inspect the source before use.

Source: [`scripts/agent-rules/kali/web-assessment.md`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/agent-rules/kali/web-assessment.md). Description basis: filename summary.

## scripts/agent-rules/universal.md

Source component: universal. Inspect the source before use.

Source: [`scripts/agent-rules/universal.md`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/agent-rules/universal.md). Description basis: filename summary.

## scripts/apply-all.sh

\# Apply ONLY manifests explicitly registered in k3s\_manifest\_groups.

Source: [`scripts/apply-all.sh`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/apply-all.sh). Description basis: Purpose comment.

## scripts/audit-host-stability-before-ai-deploy.sh

Source component: audit host stability before ai deploy. Inspect the source before use.

Source: [`scripts/audit-host-stability-before-ai-deploy.sh`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/audit-host-stability-before-ai-deploy.sh). Description basis: filename summary.

## scripts/check-image-pinning.sh

Audits manifests for floating image tags. Prefer digest-pinned images for repeatable rebuilds, and keep fallback tag comments beside digests for humans.

Source: [`scripts/check-image-pinning.sh`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/check-image-pinning.sh). Description basis: Purpose comment.

## scripts/check-md-links.py

Fail on broken relative links in tracked Markdown \(T-0115\).

Source: [`scripts/check-md-links.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/check-md-links.py). Description basis: module docstring.

## scripts/check-required-secrets.sh

Checks whether required generated Kubernetes secret files exist before deploying workloads that depend on private tokens or passwords.

Source: [`scripts/check-required-secrets.sh`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/check-required-secrets.sh). Description basis: Purpose comment.

## scripts/create-hostpaths.sh

Creates host directories used by hostPath-backed workloads. Run before first deploy or after rebuilding a node so pods can mount expected paths.

Source: [`scripts/create-hostpaths.sh`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/create-hostpaths.sh). Description basis: Purpose comment.

## scripts/cutover-watoom-code-rename.sh

Source component: cutover watoom code rename. Inspect the source before use.

Source: [`scripts/cutover-watoom-code-rename.sh`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/cutover-watoom-code-rename.sh). Description basis: filename summary.

## scripts/deploy-watoom-ai-redesign-after-host-stable.sh

Source component: deploy watoom ai redesign after host stable. Inspect the source before use.

Source: [`scripts/deploy-watoom-ai-redesign-after-host-stable.sh`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/deploy-watoom-ai-redesign-after-host-stable.sh). Description basis: filename summary.

## scripts/export-live-image-lock.sh

Reads live workload images and exports a lock-style reference for reproducible future rebuilds.

Source: [`scripts/export-live-image-lock.sh`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/export-live-image-lock.sh). Description basis: Purpose comment.

## scripts/git-hooks/pre-commit

Source component: pre commit. Inspect the source before use.

Source: [`scripts/git-hooks/pre-commit`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/git-hooks/pre-commit). Description basis: filename summary.

## scripts/gpu-controller-repin-primary.py

Re-pin the GPU controller's approved spec digest for the primary model Deployment.

Source: [`scripts/gpu-controller-repin-primary.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/gpu-controller-repin-primary.py). Description basis: module docstring.

Declared CLI options: `--apply`, `--config`, `--name`, `--state`.

## scripts/install-browser-trusted-tls.sh

Install or repair the browser-trusted Let's Encrypt wildcard for

Source: [`scripts/install-browser-trusted-tls.sh`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/install-browser-trusted-tls.sh). Description basis: Purpose comment.

## scripts/kali-tools

Source component: kali tools. Inspect the source before use.

Source: [`scripts/kali-tools`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/kali-tools). Description basis: filename summary.

Declared CLI options: `--json`, `--limit`, `--task`.

## scripts/llama-mesh

Source component: llama mesh. Inspect the source before use.

Source: [`scripts/llama-mesh`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/llama-mesh). Description basis: filename summary.

## scripts/llm-models

Source component: llm models. Inspect the source before use.

Source: [`scripts/llm-models`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/llm-models). Description basis: filename summary.

Declared CLI options: `--fallback`.

## scripts/lotce-tools

Source component: lotce tools. Inspect the source before use.

Source: [`scripts/lotce-tools`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/lotce-tools). Description basis: filename summary.

## scripts/monitor-opencode-overnight.sh

Source component: monitor opencode overnight. Inspect the source before use.

Source: [`scripts/monitor-opencode-overnight.sh`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/monitor-opencode-overnight.sh). Description basis: filename summary.

## scripts/move-state-to-ssd.sh

Source component: move state to ssd. Inspect the source before use.

Source: [`scripts/move-state-to-ssd.sh`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/move-state-to-ssd.sh). Description basis: filename summary.

## scripts/opencode-kali

Source component: opencode kali. Inspect the source before use.

Source: [`scripts/opencode-kali`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/opencode-kali). Description basis: filename summary.

## scripts/opencode-overnight

Source component: opencode overnight. Inspect the source before use.

Source: [`scripts/opencode-overnight`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/opencode-overnight). Description basis: filename summary.

## scripts/opencode-pipeline

Source component: opencode pipeline. Inspect the source before use.

Source: [`scripts/opencode-pipeline`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/opencode-pipeline). Description basis: filename summary.

## scripts/post-reboot-health-check.sh

Runs the standard after-reboot health checks for DNS, HTTPS routes, pods, and key services.

Source: [`scripts/post-reboot-health-check.sh`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/post-reboot-health-check.sh). Description basis: Purpose comment.

## scripts/probe-model-tool-compat.py

Source component: probe model tool compat. Inspect the source before use.

Source: [`scripts/probe-model-tool-compat.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/probe-model-tool-compat.py). Description basis: filename summary.

Declared CLI options: `--json-out`, `--marker`, `--model`, `--url`.

## scripts/project_groups.py

Owner project groups, read from the watoom-code role defaults \(the mounted source of truth\).

Source: [`scripts/project_groups.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/project_groups.py). Description basis: module docstring.

## scripts/rebuild-homelab.sh

Recovery inventory, coverage checks and ordered replacement-host phases.

Source: [`scripts/rebuild-homelab.sh`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/rebuild-homelab.sh). Description basis: Purpose comment.

## scripts/render-glance-configmaps.py

Source component: render glance configmaps. Inspect the source before use.

Source: [`scripts/render-glance-configmaps.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/render-glance-configmaps.py). Description basis: filename summary.

## scripts/render-glance-guide.py

Render docs/guide/\*.md into the multi-page Glance operations guide.

Source: [`scripts/render-glance-guide.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/render-glance-guide.py). Description basis: module docstring.

Declared CLI options: `--check`.

## scripts/render-glance-knowledge.py

Project existing reference metadata into a dedicated Glance bookmarks page; no scraping or execution.

Source: [`scripts/render-glance-knowledge.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/render-glance-knowledge.py). Description basis: module docstring.

Declared CLI options: `--catalog`, `--check`.

## scripts/render-job-reference.py

Render the reviewed job catalogue as static, searchable documentation; never execute jobs.

Source: [`scripts/render-job-reference.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/render-job-reference.py). Description basis: module docstring.

Declared CLI options: `--check`.

## scripts/render-native-agents.py

Assemble the watoom-code native agent definitions from single-source fragments.

Source: [`scripts/render-native-agents.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/render-native-agents.py). Description basis: module docstring.

## scripts/render-pipeline-prompts.py

Render copyable pipeline prompts; no execution, credentials, inference or deployment.

Source: [`scripts/render-pipeline-prompts.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/render-pipeline-prompts.py). Description basis: module docstring.

Declared CLI options: `--check`.

## scripts/render-secrets.sh

Renders generated secret manifests from local secret material. Generated files should not be treated as templates.

Source: [`scripts/render-secrets.sh`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/render-secrets.sh). Description basis: Purpose comment.

## scripts/render-server-catalogue.py

Build the server source catalogue from tracked files; --check detects drift.

Source: [`scripts/render-server-catalogue.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/render-server-catalogue.py). Description basis: module docstring.

Declared CLI options: `--check`.

## scripts/repair-project-perms.sh

Source component: repair project perms. Inspect the source before use.

Source: [`scripts/repair-project-perms.sh`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/repair-project-perms.sh). Description basis: filename summary.

## scripts/requirements-docs.txt

Source component: requirements docs. Inspect the source before use.

Source: [`scripts/requirements-docs.txt`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/requirements-docs.txt). Description basis: filename summary.

## scripts/restore-vault-secrets.sh

Restores Vaultwarden-related secrets into Kubernetes from saved local material.

Source: [`scripts/restore-vault-secrets.sh`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/restore-vault-secrets.sh). Description basis: Purpose comment.

## scripts/set-change-approval-pin.sh

Creates or rotates the operator PIN for approving model change requests in Glance and stores it in the encrypted vault.

Source: [`scripts/set-change-approval-pin.sh`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/set-change-approval-pin.sh). Description basis: Purpose comment.

## scripts/sync-internal-tls.py

Propagate the cert-manager Let's Encrypt wildcard to every place that serves it \(T-0116\).

Source: [`scripts/sync-internal-tls.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/sync-internal-tls.py). Description basis: module docstring.

Declared CLI options: `--canonical-dir`, `--domain`, `--dry-run`, `--source-namespace`, `--source-secret`, `--target-secret`.

## scripts/sync-skill-shared.py

Keep helper files that are shipped in several places identical to one source \(T-0115\).

Source: [`scripts/sync-skill-shared.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/sync-skill-shared.py). Description basis: module docstring.

## scripts/test-pipeline-prompts.cjs

Test fixture/check: test pipeline prompts. Inspect the source before use.

Source: [`scripts/test-pipeline-prompts.cjs`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/test-pipeline-prompts.cjs). Description basis: filename summary.

## scripts/tests/test_watoom_model_perf_accumulator.py

Test fixture/check: test watoom model perf accumulator. Inspect the source before use.

Source: [`scripts/tests/test_watoom_model_perf_accumulator.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/tests/test_watoom_model_perf_accumulator.py). Description basis: filename summary.

## scripts/tool-knowledge

Source component: tool knowledge. Inspect the source before use.

Source: [`scripts/tool-knowledge`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/tool-knowledge). Description basis: filename summary.

## scripts/validate-yaml.py

Source component: validate yaml. Inspect the source before use.

Source: [`scripts/validate-yaml.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/validate-yaml.py). Description basis: filename summary.

## scripts/verify-homelab-documentation.py

Check maintained documentation links and Glance anchors without network access.

Source: [`scripts/verify-homelab-documentation.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/verify-homelab-documentation.py). Description basis: module docstring.

## scripts/watoom-agent-rules

Source component: watoom agent rules. Inspect the source before use.

Source: [`scripts/watoom-agent-rules`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/watoom-agent-rules). Description basis: filename summary.

Declared CLI options: `--format`, `--root`.

## scripts/watoom-ansible-validate.sh

Source component: watoom ansible validate. Inspect the source before use.

Source: [`scripts/watoom-ansible-validate.sh`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/watoom-ansible-validate.sh). Description basis: filename summary.

## scripts/watoom-kali-rules

Source component: watoom kali rules. Inspect the source before use.

Source: [`scripts/watoom-kali-rules`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/watoom-kali-rules). Description basis: filename summary.

Declared CLI options: `--capability`, `--format`.

## scripts/watoom-model-perf-accumulator.py

Accumulate lifetime per-model performance counters for Grafana's all-time comparison panel.

Source: [`scripts/watoom-model-perf-accumulator.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/watoom-model-perf-accumulator.py). Description basis: module docstring.

Declared CLI options: `--output`, `--prometheus-url`, `--state-file`.

## scripts/watoom-node-textfile.sh

Source component: watoom node textfile. Inspect the source before use.

Source: [`scripts/watoom-node-textfile.sh`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/watoom-node-textfile.sh). Description basis: filename summary.

## scripts/watoom-platform-alerts.py

Snapshot-first reconcile of the Grafana route that forwards Prometheus alerts to Discord.

Source: [`scripts/watoom-platform-alerts.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/watoom-platform-alerts.py). Description basis: module docstring.

Declared CLI options: `--dry-run`, `--evidence`, `--helpers`, `--spec`, `--webhook-file`.

## scripts/watoom-qwen-maintenance.py

Guarded host-side single-model reasoning upgrade; no inference-agent dependency. Usage: --check \(read only\), --apply --approve-downtime \(explicit maintenance\). Resumption is a durable outbox, never a fabricated/unauthorized OpenCode API cal

Source: [`scripts/watoom-qwen-maintenance.py`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/scripts/watoom-qwen-maintenance.py). Description basis: module docstring.

Declared CLI options: `--apply`, `--approve-downtime`, `--check`, `--session-id`, `--timeout`.

