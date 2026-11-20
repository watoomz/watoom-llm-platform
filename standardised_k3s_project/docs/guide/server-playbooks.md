---
title: Ansible playbook reference
nav: Playbooks
summary: Source-backed purpose and interfaces for each tracked component; inspect gates and configuration before running.
---

This catalogue is generated from tracked source and untracked code candidates by `scripts/render-server-catalogue.py`. It does not run programs or certify their deployment. Source links use the configured WatooM source repository; the separate LLM repository retains the same `standardised_k3s_project/` paths. Descriptions name their evidence basis; a filename summary is not a verified operational contract.

Read [Operations](operations.md), [installation and configuration](llm-project.md), and [the software design](software-design.md) before executing deployment or recovery helpers. Run no bulk scripts from this list.

## Invocation and inputs

From the project root, use `./ansible-run playbooks/<name>.yml` only after reading that playbook and its role defaults. The wrapper sets inventory/vault/execution environment. Play-level variables, vars files, includes and gates remain authoritative; there is no universal safe apply command. Use `scripts/watoom-ansible-validate.sh standard` for production-bound Ansible source.

## ansible/playbooks/ansible-lint-api.yml

Reconcile ansible-lint API host service

Source: [`ansible/playbooks/ansible-lint-api.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/ansible-lint-api.yml). Description basis: first named play/task.

Named steps: Reconcile ansible-lint API host service.

## ansible/playbooks/artex.yml

Deploy ARTEX \(FailSafe source build, internal ingress only\)

Source: [`ansible/playbooks/artex.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/artex.yml). Description basis: first named play/task.

Named steps: Deploy ARTEX \(FailSafe source build, internal ingress only\).

## ansible/playbooks/creation-studio.yml

Creation Studio \(SDXL \+ MOSS Image Studio proxy; Mesh telemetry only\)

Source: [`ansible/playbooks/creation-studio.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/creation-studio.yml). Description basis: first named play/task.

Named steps: Creation Studio \(SDXL \+ MOSS Image Studio proxy; Mesh telemetry only\).

## ansible/playbooks/creative-asset-readers.yml

Maintain narrowly verified asset-reader access without changing ownership

Source: [`ansible/playbooks/creative-asset-readers.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/creative-asset-readers.yml). Description basis: first named play/task.

Named steps: Maintain narrowly verified asset-reader access without changing ownership; Allow existing creative executor group to read verified legacy generated assets.

## ansible/playbooks/docker-host.yml

Manage WatooM Docker host prerequisites

Source: [`ansible/playbooks/docker-host.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/docker-host.yml). Description basis: first named play/task.

Named steps: Manage WatooM Docker host prerequisites.

## ansible/playbooks/foundation.yml

Prepare homelab host foundations

Source: [`ansible/playbooks/foundation.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/foundation.yml). Description basis: first named play/task.

Named steps: Prepare homelab host foundations.

## ansible/playbooks/godot-mcp-ssh.yml

Generate and stage the lab's SSH identity for the rig's Godot MCP account

Source: [`ansible/playbooks/godot-mcp-ssh.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/godot-mcp-ssh.yml). Description basis: first named play/task.

Named steps: Generate and stage the lab's SSH identity for the rig's Godot MCP account; Key directory; Generate the lab's SSH identity for this route only; Read the generated public key; Show the public key to install on the rig \(see README step 2\); Try to learn the rig's host key, if its SSH server is already up \(best-effort\); Pin the rig's host key once known \(idempotent; re-run this playbook after the rig's sshd is up\); Compute the fingerprint of the host key just pinned; Verify the pinned host key out of band \(the first connection is trust-on-first-use\); Warn if the rig's host key is not yet known. Further steps are in source.

## ansible/playbooks/gpu-controller.yml

Promote reviewed GPU controller runtime only

Source: [`ansible/playbooks/gpu-controller.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/gpu-controller.yml). Description basis: first named play/task.

Named steps: Promote reviewed GPU controller runtime only; Install the reviewed controller runtime.

## ansible/playbooks/gpu-host.yml

Reconcile WatooM GPU host policy

Source: [`ansible/playbooks/gpu-host.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/gpu-host.yml). Description basis: first named play/task.

Named steps: Reconcile WatooM GPU host policy.

## ansible/playbooks/gpu-unlock.yml

Install pinned GPU unlock without rebooting the host

Source: [`ansible/playbooks/gpu-unlock.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/gpu-unlock.yml). Description basis: first named play/task.

Named steps: Install pinned GPU unlock without rebooting the host; Reconcile only the GPU unlock component.

## ansible/playbooks/health.yml

Validate WatooM host health

Source: [`ansible/playbooks/health.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/health.yml). Description basis: first named play/task.

Named steps: Validate WatooM host health.

## ansible/playbooks/host-paths.yml

Reconcile WatooM host paths

Source: [`ansible/playbooks/host-paths.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/host-paths.yml). Description basis: first named play/task.

Named steps: Reconcile WatooM host paths.

## ansible/playbooks/host-repair.yml

Manage WatooM host repair action

Source: [`ansible/playbooks/host-repair.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/host-repair.yml). Description basis: first named play/task.

Named steps: Manage WatooM host repair action.

## ansible/playbooks/image-audit.yml

Audit WatooM workload images

Source: [`ansible/playbooks/image-audit.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/image-audit.yml). Description basis: first named play/task.

Named steps: Audit WatooM workload images.

## ansible/playbooks/install-collections.yml

Verify Ansible collection dependencies are installed

Source: [`ansible/playbooks/install-collections.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/install-collections.yml). Description basis: first named play/task.

Named steps: Verify Ansible collection dependencies are installed; Dependency installation command.

## ansible/playbooks/kubeconfig.yml

Reconcile WatooM user kubeconfigs

Source: [`ansible/playbooks/kubeconfig.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/kubeconfig.yml). Description basis: first named play/task.

Named steps: Reconcile WatooM user kubeconfigs.

## ansible/playbooks/kubernetes-app.yml

Manage one WatooM Kubernetes application

Source: [`ansible/playbooks/kubernetes-app.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/kubernetes-app.yml). Description basis: first named play/task.

Named steps: Manage one WatooM Kubernetes application.

## ansible/playbooks/kubernetes-secrets.yml

Reconcile WatooM Kubernetes secrets

Source: [`ansible/playbooks/kubernetes-secrets.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/kubernetes-secrets.yml). Description basis: first named play/task.

Named steps: Reconcile WatooM Kubernetes secrets.

## ansible/playbooks/kubernetes.yml

Reconcile Kubernetes workloads

Source: [`ansible/playbooks/kubernetes.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/kubernetes.yml). Description basis: first named play/task.

Named steps: Reconcile Kubernetes workloads.

## ansible/playbooks/llama-mesh-pipeline-recovery.yml

Persist WatooM LLaMA-Mesh host queue recovery

Source: [`ansible/playbooks/llama-mesh-pipeline-recovery.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/llama-mesh-pipeline-recovery.yml). Description basis: first named play/task.

Named steps: Persist WatooM LLaMA-Mesh host queue recovery; Reconcile only mesh pipeline recovery.

## ansible/playbooks/llm-bge-embeddings.yml

Deploy BGE embeddings \(CPU by default\)

Source: [`ansible/playbooks/llm-bge-embeddings.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/llm-bge-embeddings.yml). Description basis: first named play/task.

Named steps: Deploy BGE embeddings \(CPU by default\); Maintain the model directories; Install the official BGE revision \(checksum-pinned\); Install the GGUF conversion \(checksum-pinned\); Prove the GGUF equals the official weights, tokenizer and pooling; Publish the chunking proxy; Apply the BGE Service and NetworkPolicy; Apply the BGE Deployment and wait until Available; Read the Service address \(the host cannot resolve cluster DNS\); Check a 384-dimension embedding through the Service.

## ansible/playbooks/llm-model-lab.yml

Deploy the LLM model lab

Source: [`ansible/playbooks/llm-model-lab.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/llm-model-lab.yml). Description basis: first named play/task.

Named steps: Deploy the LLM model lab.

## ansible/playbooks/model-manager.yml

Install isolated model manager and narrow lifecycle broker

Source: [`ansible/playbooks/model-manager.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/model-manager.yml). Description basis: first named play/task.

Named steps: Install isolated model manager and narrow lifecycle broker.

## ansible/playbooks/moss-image.yml

MOSS Image Studio \(GPU sessions via the GPU controller\)

Source: [`ansible/playbooks/moss-image.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/moss-image.yml). Description basis: first named play/task.

Named steps: MOSS Image Studio \(GPU sessions via the GPU controller\).

## ansible/playbooks/opencode-llama-mesh-integration.yml

Persist narrow OpenCode LLaMA-Mesh integration

Source: [`ansible/playbooks/opencode-llama-mesh-integration.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/opencode-llama-mesh-integration.yml). Description basis: first named play/task.

Named steps: Persist narrow OpenCode LLaMA-Mesh integration; Reconcile only authorized mesh integration.

## ansible/playbooks/platform.yml

Converge watoom-code

Source: [`ansible/playbooks/platform.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/platform.yml). Description basis: first named play/task.

Named steps: Converge watoom-code; Converge watoom-native-skills; Converge creation-studio; Converge writing-studio; Converge tickets-board; Converge skill-editor; Converge artex; Converge moss-image; Converge llm-bge-embeddings; Converge watoom-kali-workbench-mcp. Further steps are in source.

## ansible/playbooks/project-layout.yml

Maintain project storage and capture viewing layout without application rollout

Source: [`ansible/playbooks/project-layout.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/project-layout.yml). Description basis: first named play/task.

Named steps: Maintain project storage and capture viewing layout without application rollout.

## ansible/playbooks/projects-share.yml

Share the projects folder with the rig

Source: [`ansible/playbooks/projects-share.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/projects-share.yml). Description basis: first named play/task.

Named steps: Share the projects folder with the rig.

## ansible/playbooks/rebuild-homelab.yml

Rebuild WatooM homelab host

Source: [`ansible/playbooks/rebuild-homelab.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/rebuild-homelab.yml). Description basis: first named play/task.

Named steps: Rebuild WatooM homelab host.

## ansible/playbooks/secrets.yml

Restore WatooM homelab secret source

Source: [`ansible/playbooks/secrets.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/secrets.yml). Description basis: first named play/task.

Named steps: Restore WatooM homelab secret source.

## ansible/playbooks/secure-sensitive-files.yml

Restrict credential-bearing files in the project checkout

Source: [`ansible/playbooks/secure-sensitive-files.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/secure-sensitive-files.yml). Description basis: first named play/task.

Named steps: Restrict credential-bearing files in the project checkout; Inspect sensitive files; Require every sensitive file to be a regular file; Apply owner and mode \(content never read\).

## ansible/playbooks/site.yml

Reconcile the LLM platform host

Source: [`ansible/playbooks/site.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/site.yml). Description basis: first named play/task.

Named steps: Reconcile the LLM platform host.

## ansible/playbooks/skill-editor.yml

Install the Glance skill editor \(SKILL.md edits committed to Git\)

Source: [`ansible/playbooks/skill-editor.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/skill-editor.yml). Description basis: first named play/task.

Named steps: Install the Glance skill editor \(SKILL.md edits committed to Git\).

## ansible/playbooks/tasks/watoom-backup-libexec.yml

Maintain the root-owned backup tool directory

Source: [`ansible/playbooks/tasks/watoom-backup-libexec.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/tasks/watoom-backup-libexec.yml). Description basis: first named play/task.

Named steps: Maintain the root-owned backup tool directory; Install the backup tools from the reviewed source.

## ansible/playbooks/templates/bge-embeddings.yml.j2

Source component: bge embeddings.yml. Inspect the source before use.

Source: [`ansible/playbooks/templates/bge-embeddings.yml.j2`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/templates/bge-embeddings.yml.j2). Description basis: filename summary.

Named steps: llama-server; embed-proxy; model; proxy; gpu-observation.

## ansible/playbooks/tickets-board.yml

Install the tickets board \(kanban over the ticket store, served under Glance at /tickets/\)

Source: [`ansible/playbooks/tickets-board.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/tickets-board.yml). Description basis: first named play/task.

Named steps: Install the tickets board \(kanban over the ticket store, served under Glance at /tickets/\).

## ansible/playbooks/tuned-virtual-guest.yml

Configure TuneD virtual-guest profile

Source: [`ansible/playbooks/tuned-virtual-guest.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/tuned-virtual-guest.yml). Description basis: first named play/task.

Named steps: Configure TuneD virtual-guest profile.

## ansible/playbooks/ue-mcp-ssh.yml

Generate and stage the lab's SSH identity for the rig's ue-mcp account

Source: [`ansible/playbooks/ue-mcp-ssh.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/ue-mcp-ssh.yml). Description basis: first named play/task.

Named steps: Generate and stage the lab's SSH identity for the rig's ue-mcp account; Key directory; Generate the lab's SSH identity for this route only; Read the generated public key; Show the public key to install on the rig \(see README step 2\); Try to learn the rig's host key, if its SSH server is already up \(best-effort\); Pin the rig's host key once known \(idempotent; re-run this playbook after the rig's sshd is up\); Compute the fingerprint of the host key just pinned; Verify the pinned host key out of band \(the first connection is trust-on-first-use\); Warn if the rig's host key is not yet known. Further steps are in source.

## ansible/playbooks/unreal-engine-publish.yml

Publish already built and validated Unreal output without rebuilding

Source: [`ansible/playbooks/unreal-engine-publish.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/unreal-engine-publish.yml). Description basis: first named play/task.

Named steps: Publish already built and validated Unreal output without rebuilding; Materialize the versioned runtime using the normal build role.

## ansible/playbooks/unreal-engine.yml

Build the pinned Unreal toolchain from source through maintained IaC

Source: [`ansible/playbooks/unreal-engine.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/unreal-engine.yml). Description basis: first named play/task.

Named steps: Build the pinned Unreal toolchain from source through maintained IaC.

## ansible/playbooks/unreal-mcp-tunnel.yml

Install the Unreal MCP tunnel endpoint and proxy

Source: [`ansible/playbooks/unreal-mcp-tunnel.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/unreal-mcp-tunnel.yml). Description basis: first named play/task.

Named steps: Install the Unreal MCP tunnel endpoint and proxy; Tunnel-only account; Authorized keys directory; Rig tunnel key, restricted to the single reverse forward; sshd rules for the tunnel account; Install the drop-in; Validate sshd configuration; Remove the drop-in again if sshd rejects it; Stop here; Reload sshd. Further steps are in source.

## ansible/playbooks/unreal-project.yml

Stage an explicitly selected Unreal complete-project starter

Source: [`ansible/playbooks/unreal-project.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/unreal-project.yml). Description basis: first named play/task.

Named steps: Stage an explicitly selected Unreal complete-project starter.

## ansible/playbooks/validate.yml

Validate WatooM homelab

Source: [`ansible/playbooks/validate.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/validate.yml). Description basis: first named play/task.

Named steps: Validate WatooM homelab.

## ansible/playbooks/watoom-asset-archive.yml

Install the asset archive host worker

Source: [`ansible/playbooks/watoom-asset-archive.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-asset-archive.yml). Description basis: first named play/task.

Named steps: Install the asset archive host worker; Worker script; Shared request queue \(the pod can only write under projects/\*\); Worker service; Enable and start the worker; Restart asset archive worker.

## ansible/playbooks/watoom-backup-offhost.yml

Publish verified backups for the rig to pull

Source: [`ansible/playbooks/watoom-backup-offhost.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-backup-offhost.yml). Description basis: first named play/task.

Named steps: Publish verified backups for the rig to pull; Install the backup tools outside any checkout; Maintain the pull group; Maintain the jailed pull-only account; Maintain the off-host export and receipt trees; Check existing jail bind mounts; Create jail mountpoints only when not mounted; Bind the export read-only and the receipts writable into the jail; Label only the off-host tree for SSH access; Apply the off-host labels. Further steps are in source.

## ansible/playbooks/watoom-blender-compatibility-labels.yml

Label the separately installed Blender 5.2 compatibility runtime

Source: [`ansible/playbooks/watoom-blender-compatibility-labels.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-blender-compatibility-labels.yml). Description basis: first named play/task.

Named steps: Label the separately installed Blender 5.2 compatibility runtime; Persist runtime directory label; Persist executable release labels; Apply labels only to the new release; Apply parent directory label.

## ansible/playbooks/watoom-blender-unified-v3.yml

Activate validated WatooM Blender v3 helpers

Source: [`ansible/playbooks/watoom-blender-unified-v3.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-blender-unified-v3.yml). Description basis: first named play/task.

Named steps: Activate validated WatooM Blender v3 helpers; Require explicit approval; Read supplied package digest; Read release manifest digest; Verify pinned release provenance; Verify all installed helper hashes; Activate with validated receipt and automatic rollback; Record activation result.

## ansible/playbooks/watoom-break-glass.yml

Install the break-glass recovery service

Source: [`ansible/playbooks/watoom-break-glass.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-break-glass.yml). Description basis: first named play/task.

Named steps: Install the break-glass recovery service; Create the break-glass state and inbox directories; Create the evidence directory \(root only; holds database snapshots\); Install break-glass service; Install break-glass request trigger; Install break-glass status timer; Reload systemd and enable the trigger and timer.

## ansible/playbooks/watoom-change-requests.yml

Install the audited host change-request scanner

Source: [`ansible/playbooks/watoom-change-requests.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-change-requests.yml). Description basis: first named play/task.

Named steps: Install the audited host change-request scanner; Create model-writable change-request queues; Install change-request scan service; Install change-request scan timer; Activate change-request timer.

## ansible/playbooks/watoom-code-agent-routing.yml

Deploy only reviewed agent routing and coordinator guard

Source: [`ansible/playbooks/watoom-code-agent-routing.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-agent-routing.yml). Description basis: first named play/task.

Named steps: Deploy only reviewed agent routing and coordinator guard; Require native idle deployment guard; Install scoped agent routing.

## ansible/playbooks/watoom-code-asset-capture-skill.yml

Install owner-requested asset image and clip capture skill

Source: [`ansible/playbooks/watoom-code-asset-capture-skill.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-asset-capture-skill.yml). Description basis: first named play/task.

Named steps: Install owner-requested asset image and clip capture skill; Install maintained capture skill only; Preserve container-readable capture skill label.

## ansible/playbooks/watoom-code-backup.yml

Schedule verified WatooM-Code backups

Source: [`ansible/playbooks/watoom-code-backup.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-backup.yml). Description basis: first named play/task.

Named steps: Schedule verified WatooM-Code backups; Install the backup tools outside any checkout; Create the private backup destination; Install the backup service and daily timer; watoom-code-backup.service; watoom-code-backup.timer; Enable the daily backup timer.

## ansible/playbooks/watoom-code-capture-scope.yml

Activate precise capture admission diagnostics under native fence

Source: [`ansible/playbooks/watoom-code-capture-scope.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-capture-scope.yml). Description basis: first named play/task.

Named steps: Activate precise capture admission diagnostics under native fence; Require native release fence; Install immutable capture guard diagnostics; Install capture project preflight guidance.

## ansible/playbooks/watoom-code-context.yml

Deploy WatooM Code context reliability application only

Source: [`ansible/playbooks/watoom-code-context.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-context.yml). Description basis: first named play/task.

Named steps: Deploy WatooM Code context reliability application only; Require the durable application admission fence; Set only the reviewed application image; app; Wait for the application rollout.

## ansible/playbooks/watoom-code-coordinator-guard.yml

Deploy only the reviewed native coordinator guard

Source: [`ansible/playbooks/watoom-code-coordinator-guard.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-coordinator-guard.yml). Description basis: first named play/task.

Named steps: Deploy only the reviewed native coordinator guard; Require native idle deployment guard; Install and select the immutable coordinator guard.

## ansible/playbooks/watoom-code-cutover.yml

Apply reviewed WatooM Code production candidate

Source: [`ansible/playbooks/watoom-code-cutover.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-cutover.yml). Description basis: first named play/task.

Named steps: Apply reviewed WatooM Code production candidate; Require explicit production approval; Read the reviewed deployment; Fence ownership to the existing application deployment; Reconcile the existing application deployment; Wait for the reviewed release.

## ansible/playbooks/watoom-code-data-access.yml

Maintain agent evidence access without application rollout

Source: [`ansible/playbooks/watoom-code-data-access.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-data-access.yml). Description basis: first named play/task.

Named steps: Maintain agent evidence access without application rollout; Install maintained agent permissions; Apply maintained bounded receipt access.

## ansible/playbooks/watoom-code-engineering-skills.yml

Install engineering-discipline skills

Source: [`ansible/playbooks/watoom-code-engineering-skills.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-engineering-skills.yml). Description basis: first named play/task.

Named steps: Install engineering-discipline skills; Install skill directories; Install licence and source record; Restore skill labels.

## ansible/playbooks/watoom-code-fab-assets.yml

Maintain Fab acquisition instructions

Source: [`ansible/playbooks/watoom-code-fab-assets.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-fab-assets.yml). Description basis: first named play/task.

Named steps: Maintain Fab acquisition instructions; Install maintained agent instructions; Install owner-answer approval worker.

## ansible/playbooks/watoom-code-game-worker-memory.yml

Activate controller-owned CPU game worker handoff

Source: [`ansible/playbooks/watoom-code-game-worker-memory.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-game-worker-memory.yml). Description basis: first named play/task.

Named steps: Activate controller-owned CPU game worker handoff; Install reviewed controller service module; Activate reviewed controller service module; Install maintained worker units.

## ansible/playbooks/watoom-code-game-worker.yml

Activate bounded native game worker interface

Source: [`ansible/playbooks/watoom-code-game-worker.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-game-worker.yml). Description basis: first named play/task.

Named steps: Activate bounded native game worker interface; Maintain operator request worker; Install versioned native tools; Install maintained worker instructions.

## ansible/playbooks/watoom-code-godot-mcp.yml

Maintain only the Godot MCP integration in the watoom-code configuration

Source: [`ansible/playbooks/watoom-code-godot-mcp.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-godot-mcp.yml). Description basis: first named play/task.

Named steps: Maintain only the Godot MCP integration in the watoom-code configuration; Merge \(or remove\) the watoom-godot MCP entry in existing configuration.

## ansible/playbooks/watoom-code-guard-knowledge.yml

Deploy the native coordinator guard and language-knowledge cards under the held release fence

Source: [`ansible/playbooks/watoom-code-guard-knowledge.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-guard-knowledge.yml). Description basis: first named play/task.

Named steps: Deploy the native coordinator guard and language-knowledge cards under the held release fence; Require native idle deployment guard; Install and select the immutable coordinator guard; Install and select the language-knowledge package and cards.

## ansible/playbooks/watoom-code-homelab-project.yml

Maintain the Homelab LLM checkout and native policy only

Source: [`ansible/playbooks/watoom-code-homelab-project.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-homelab-project.yml). Description basis: first named play/task.

Named steps: Maintain the Homelab LLM checkout and native policy only; Apply project-only tasks without restarting application or inference.

## ansible/playbooks/watoom-code-lan-route.yml

Publish isolated WatooM Code LAN route

Source: [`ansible/playbooks/watoom-code-lan-route.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-lan-route.yml). Description basis: first named play/task.

Named steps: Publish isolated WatooM Code LAN route; Require explicit release approval; Read authoritative existing LAN certificate; Install isolated copy of existing LAN certificate; Publish validated isolated application on existing TLS entrypoint.

## ansible/playbooks/watoom-code-memory-catalogue.yml

Promote the verified native memory and catalogue candidate only

Source: [`ansible/playbooks/watoom-code-memory-catalogue.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-memory-catalogue.yml). Description basis: first named play/task.

Named steps: Promote the verified native memory and catalogue candidate only; Require native release fence and an immutable candidate; Install reviewed pipeline descriptions and dependencies; Preserve explicitly verified model capabilities; Set candidate image and read-only observation access; app; ownership-observations; Wait for the pinned application rollout.

## ansible/playbooks/watoom-code-memory-embeddings.yml

Configure AgentMemory embeddings

Source: [`ansible/playbooks/watoom-code-memory-embeddings.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-memory-embeddings.yml). Description basis: first named play/task.

Named steps: Configure AgentMemory embeddings; Fix the snapshot name once; Set the snapshot paths; Confirm AgentMemory can reach the embedding service; Export a portable, human-readable memory snapshot before stopping AgentMemory; Restrict the export snapshot's permissions; Stop, snapshot and reconfigure AgentMemory \(restore the replica on any failure\); Stop AgentMemory for a consistent snapshot \(clients queue in their outbox\); Wait for the AgentMemory pod to exit; Snapshot the memory store. Further steps are in source.

## ansible/playbooks/watoom-code-memory-health.yml

Restore WatooM Code AgentMemory within bounded host capacity

Source: [`ansible/playbooks/watoom-code-memory-health.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-memory-health.yml). Description basis: first named play/task.

Named steps: Restore WatooM Code AgentMemory within bounded host capacity; Set the evidenced AgentMemory startup memory ceiling; agentmemory; Verify AgentMemory readiness.

## ansible/playbooks/watoom-code-memory-observability.yml

Install read-only GPU observations without changing models or routing

Source: [`ansible/playbooks/watoom-code-memory-observability.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-memory-observability.yml). Description basis: first named play/task.

Named steps: Install read-only GPU observations without changing models or routing; Require verified idle release boundary; Create root-owned observation directory; Install observation-aware controller modules; Read current controller configuration; Preserve configuration and add observation destination; Install existing controller unit with the observation write directory; Label the observation directory for read-only container access; Apply observation labels; Activate the existing controller at the verified idle boundary. Further steps are in source.

## ansible/playbooks/watoom-code-moss-image-plugin.yml

Update only the MOSS Image plugin \(versioned dir \+ selection\)

Source: [`ansible/playbooks/watoom-code-moss-image-plugin.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-moss-image-plugin.yml). Description basis: first named play/task.

Named steps: Update only the MOSS Image plugin \(versioned dir \+ selection\).

## ansible/playbooks/watoom-code-native-tool-selection.yml

Deploy scoped native tool selection guidance

Source: [`ansible/playbooks/watoom-code-native-tool-selection.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-native-tool-selection.yml). Description basis: first named play/task.

Named steps: Deploy scoped native tool selection guidance; Require native idle release guard; Install managed native agent guidance.

## ansible/playbooks/watoom-code-operator-commands.yml

Install operator-commands guidance

Source: [`ansible/playbooks/watoom-code-operator-commands.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-operator-commands.yml). Description basis: first named play/task.

Named steps: Install operator-commands guidance; Install skill directories; Restore skill labels.

## ansible/playbooks/watoom-code-parts.yml

Update selected watoom-code parts

Source: [`ansible/playbooks/watoom-code-parts.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-parts.yml). Description basis: first named play/task.

Named steps: Update selected watoom-code parts; Native agents, guard-independent agent files and OpenSpec skill; Engine inspection skill; Image MCP; Image review collector; Image prompt scope; GUI reasoning variants; Kali isolation for built-in agents; SearXNG search plugin; Engine visual diagnosis skill. Further steps are in source.

## ansible/playbooks/watoom-code-pose-worker.yml

Activate fixed pose worker integration under native admission guard

Source: [`ansible/playbooks/watoom-code-pose-worker.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-pose-worker.yml). Description basis: first named play/task.

Named steps: Activate fixed pose worker integration under native admission guard; Require existing scoped admission fence; Install immutable native capture mode registration; Install maintained pose helper skill; Install matching capture and animation routing; Install qualified Shadowheart rig routing reference; Restore owned skill labels.

## ansible/playbooks/watoom-code-read-access.yml

Deploy scoped native read access under the held release fence

Source: [`ansible/playbooks/watoom-code-read-access.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-read-access.yml). Description basis: first named play/task.

Named steps: Deploy scoped native read access under the held release fence; Require native idle deployment guard; Install immutable coordinator guard; Install managed role policies; Expose server repositories as read-only evidence.

## ansible/playbooks/watoom-code-render-routing.yml

Activate reviewed render-capture defaults under the coordinator admission fence

Source: [`ansible/playbooks/watoom-code-render-routing.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-render-routing.yml). Description basis: first named play/task.

Named steps: Activate reviewed render-capture defaults under the coordinator admission fence; Require admission-fenced invocation from the release coordinator; Install and select the tested immutable application-shell engine guard; Install only the shared capture skill and its maintained references; Apply only the maintained critic step budget; Restore existing container-readable labels on only the owned paths; Install external capture worker contract.

## ansible/playbooks/watoom-code-self-learning-controller.yml

Arm only the reviewed learning recovery checkpoint

Source: [`ansible/playbooks/watoom-code-self-learning-controller.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-self-learning-controller.yml). Description basis: first named play/task.

Named steps: Arm only the reviewed learning recovery checkpoint; Require an owned checkpoint root; Install the independently scheduled controller; Install the nightly memory curator \(off unless watoom\_learning\_curator\_enabled\).

## ansible/playbooks/watoom-code-self-learning-cutover.yml

Apply only an explicitly authorised WatooM learning configuration

Source: [`ansible/playbooks/watoom-code-self-learning-cutover.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-self-learning-cutover.yml). Description basis: first named play/task.

Named steps: Apply only an explicitly authorised WatooM learning configuration; Require the exact approval and scoped release paths; Install the immutable native plugin package; Create only the new owned learning directories; Install the reviewed configuration atomically; Apply existing SELinux labels only to new release paths; Apply the checksum-pinned application deployment; Wait for actual candidate rollout.

## ansible/playbooks/watoom-code-self-learning-optimisation.yml

Schedule guarded existing Skill improvement and rollback

Source: [`ansible/playbooks/watoom-code-self-learning-optimisation.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-self-learning-optimisation.yml). Description basis: first named play/task.

Named steps: Schedule guarded existing Skill improvement and rollback; Require the private approved release evidence root; Install the deterministic existing Skill controller; Install the bounded optimisation schedule; Enable guarded periodic improvement.

## ansible/playbooks/watoom-code-self-learning-runner.yml

Run the reviewed learning migration independently of Codex

Source: [`ansible/playbooks/watoom-code-self-learning-runner.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-self-learning-runner.yml). Description basis: first named play/task.

Named steps: Run the reviewed learning migration independently of Codex; Require a dedicated private evidence root; Install the bounded resumable runner; Start the approved runner.

## ansible/playbooks/watoom-code-self-learning-stage.yml

Deploy only the isolated WatooM learning candidate

Source: [`ansible/playbooks/watoom-code-self-learning-stage.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-self-learning-stage.yml). Description basis: first named play/task.

Named steps: Deploy only the isolated WatooM learning candidate; Require explicitly scoped staging inputs; Create only the explicitly named isolated learning namespace; Provide the isolated application Service for maintenance acceptance; Persist labels only for isolated candidate data; Restore isolated data labels; Apply reviewed candidate manifest; Verify candidate memory readiness; Verify candidate application readiness; Install independently scheduled release recovery.

## ansible/playbooks/watoom-code-ue-mcp.yml

Maintain only the ue-mcp integration in the watoom-code configuration

Source: [`ansible/playbooks/watoom-code-ue-mcp.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-ue-mcp.yml). Description basis: first named play/task.

Named steps: Maintain only the ue-mcp integration in the watoom-code configuration; Merge \(or remove\) the watoom-ue MCP entry in existing configuration.

## ansible/playbooks/watoom-code-uploads.yml

Enable durable WatooM Code uploads

Source: [`ansible/playbooks/watoom-code-uploads.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-uploads.yml). Description basis: first named play/task.

Named steps: Enable durable WatooM Code uploads; Require native idle admission fence; Create private persistent upload staging; Apply existing production SELinux policy; Mount the writable upload staging directory; app; uploads.

## ansible/playbooks/watoom-code-workstation-capture.yml

Activate the qualified workstation capture backend under native admission fence

Source: [`ansible/playbooks/watoom-code-workstation-capture.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code-workstation-capture.yml). Description basis: first named play/task.

Named steps: Activate the qualified workstation capture backend under native admission fence; Require native admission fence; Maintain qualified backend and SFTP transport; Select the immutable capture tool description and preserve app shell guard; Maintain the admitted capture backend selection.

## ansible/playbooks/watoom-code.yml

Deploy WatooM Code

Source: [`ansible/playbooks/watoom-code.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-code.yml). Description basis: first named play/task.

Named steps: Deploy WatooM Code.

## ansible/playbooks/watoom-native-skills.yml

Install approved native skills without restarting services

Source: [`ansible/playbooks/watoom-native-skills.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-native-skills.yml). Description basis: first named play/task.

Named steps: Install approved native skills without restarting services; Reconcile maintained native skills only.

## ansible/playbooks/watoom-node-textfile.yml

Publish WatooM host health metrics to node-exporter

Source: [`ansible/playbooks/watoom-node-textfile.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-node-textfile.yml). Description basis: first named play/task.

Named steps: Publish WatooM host health metrics to node-exporter; Create the node-exporter textfile directories \(readable by nobody\); Install the failed-unit metric writer; Install the lifetime model-performance accumulator; Install the metric writer service and timer; watoom-node-textfile.service; watoom-node-textfile.timer; watoom-model-perf-accumulator.service; watoom-model-perf-accumulator.timer; Enable the metric writer timers.

## ansible/playbooks/watoom-platform-alerts.yml

Forward Prometheus platform alerts to Discord through Grafana

Source: [`ansible/playbooks/watoom-platform-alerts.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-platform-alerts.yml). Description basis: first named play/task.

Named steps: Forward Prometheus platform alerts to Discord through Grafana; Reconcile platform folder, contact point, route and forwarding rule; Show reconcile result.

## ansible/playbooks/watoom-recovery-export.yml

Publish verified environment recovery bundles through the existing backup jail

Source: [`ansible/playbooks/watoom-recovery-export.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-recovery-export.yml). Description basis: first named play/task.

Named steps: Publish verified environment recovery bundles through the existing backup jail; Require an exact completed recovery run; Check the selected private recovery manifest; Refuse incomplete or missing captures; Require the existing pull-only account; Install existing reviewed backup export helpers; Maintain only the separate environment receipt directory; Publish verified runs without pruning application backups.

## ansible/playbooks/watoom-workstation-render-stage.yml

Isolated workstation render staging transport

Source: [`ansible/playbooks/watoom-workstation-render-stage.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/watoom-workstation-render-stage.yml). Description basis: first named play/task.

Named steps: Isolated workstation render staging transport.

## ansible/playbooks/worker-status.yml

Install the worker status collector

Source: [`ansible/playbooks/worker-status.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/worker-status.yml). Description basis: first named play/task.

Named steps: Install the worker status collector; Collector directories; Ensure the node-exporter textfile destination exists; Install the collector and the Bazzite access helper it reuses \(outside any checkout\); Collector service; Collector timer; Enable the timer.

## ansible/playbooks/writing-studio.yml

Writing Studio \(creative-writing skills via the LLM router; graphic-novel art via MOSS\)

Source: [`ansible/playbooks/writing-studio.yml`](https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/ansible/playbooks/writing-studio.yml). Description basis: first named play/task.

Named steps: Writing Studio \(creative-writing skills via the LLM router; graphic-novel art via MOSS\).

