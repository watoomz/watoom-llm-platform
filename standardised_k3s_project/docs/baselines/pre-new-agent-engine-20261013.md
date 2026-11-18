# Production baseline before new agent and inference-engine development

Baseline date: 2026-10-13 (host time, Australia/Brisbane).
Annotated tag: baseline/pre-new-agent-engine-20261013.
Final commit: resolve with git rev-parse 'baseline/pre-new-agent-engine-20261013^{commit}'; the exact SHA is
recorded in the protected backup inventory and external final report.
Validated implementation commit before this freeze document: 41e701717e78a7fdc79389d528fc84d5a89d10b1.
Branch: dev. Canonical source: /data/github/watoom-standardised-homelab/standardised_k3s_project.
Protected backup: /data/ai/backups/baselines/pre-new-agent-engine-20261013.
Private audit and complete cleanup/exception manifests: /data/ai/audits/baseline-20261013.

## Observed runtime

- Host: watoom-homelab; CPU(s):                                  12; Model name:                              AMD Ryzen 5 5500.
- Memory: MemTotal:       32479528 kB; kernel 7.2.7-200.fc44.x86_64.
- k3s: v1.36.3+k3s1; container runtime containerd://2.3.2-k3s2.
- GPU: NVIDIA GeForce GPU, GPU-27e6356b-3d09-3b4c-8a28-3aab8e72db55, 615.71.09, 250.00 W, 20480 MiB. Power policy is 250 W in both
  runtime and persisted systemd startup configuration.
- Primary backend: llama-cpp-swift-qwen38-coder; alias swift-qwen38-coder;
  one ready replica. All other ten GPU deployments are idle at zero replicas.
- Model: /data/ai/models/gguf/swift-qwen3.8-27b/Swift-Qwen3.8-27B-IQ4_XS.gguf;
  recorded SHA256 27f5531a012a4bb3c3e379318dc62216f057131d34347498fabfc23186a4ffda.
  This is an existing SHA256SUMS provenance record, not a new full model rehash.
- Multimodal projector: the same directory, mmproj-Swift-Qwen3.8-27B-F16.gguf.
- Context 131072; K/V q4_0; Flash Attention on; GPU layers all; one parallel slot;
  CPU threads 8; CPU FFN offload 0; draft-mtp with draft maximum 4;
  reasoning off. Source now reflects observed settings; no tuning was performed.
- llama.cpp: 0.3.0-dev build 10666, commit 4e97ac86e; GNU 14.2.0 Linux x86_64.
  Runtime executable /app/llama-server SHA256
  4b4bb12579d086393d784f81c2efe67765a5e1b93bc36160aaa3a01bef588e41.
  Deployment image: ghcr.io/ggml-org/llama.cpp@sha256:150b59966fb5b2cb1a8fa9d226267c56ebd22c520c7b3640331cde87f3c4fb01.
- LLaMA-Mesh: /data/ai/models/gguf/llama-mesh/LLaMA-Mesh-Q8_0.gguf;
  recorded SHA256 e67bf3af4693f2be81aca6a9b6f519442a1b6ab32b0665846daee64e478f39af;
  active.gguf resolves to that file. Sampling and file-stat verification are
  maintained in ansible/roles/llm-model-lab/files/llama-mesh-pipeline.json.
- Router: active controller-compatible llm-router-app ConfigMap. Both
  llm-router.yml and llm-router-gpu-controller.yml preserve the same implementation.
  The model-lab role cannot reinstall the legacy replica writer.
- OpenCode: V2 2.0.18 production service selects opencode-v2-canary, image
  2.0.18-unreal1-browser1-godot1-blender42-1. Main config rendered from source
  equals the live ConfigMap. Native agent policies and project registry match
  their deployed files. Active-model provider context limit is 102400;
  the explicit Swift provider limit remains the observed 63488.
- AgentMemory, Kali and LLaMA-Mesh MCP servers are connected. Mesh is registered
  under mcp.servers with codemode enabled. Installed tools are generate, submit,
  status, manifest, retrieve and list; generate requires a stable request_id.
- Controller: completed G3H source c293647bed8176b97123884fcad453b20ecd65b6
  is an ancestor of this baseline. Current generation 3,
  owner null, phase qwen-ready, uncertain false.
  Controller config SHA256 c63360c06067c82610551869ec760e41e735c862484bbe353c13a97d52d7bd8d.
  Nine installed modules are byte-identical; client.py has only trailing
  whitespace differences. All ten installed modules match source Python ASTs.
- Credential timer, controller and bridge are active. Recovery is an inactive,
  successful oneshot (exit 0), rather than a continuously running daemon.

## Evidence and validation

- 102 G3H controller tests and 12 parser tests passed.
- Installed stdio MCP tools/list returned the six expected tools and a required
  generate request_id. The authenticated running-server API reports connected.
- Real routed Qwen inference passed at 2026-10-12T20:13:37.872504+00:00,
  returning the correct alias and matching the retained primary baseline.
- Twenty-one relevant live GPU/router/admission/RBAC objects match source
  explicit fields; controller-managed replica transitions and server defaults
  are excluded from drift comparisons.
- All eleven GPU deployment barriers remain covered by admission fencing.
  No competing GPU deployment was active in the final idle snapshot.
- Relevant Ansible syntax checks passed for controller, model-lab, recovery,
  OpenCode, host GPU, host rebuild, secret mapping and validator playbooks.
- Validator static regression suite passed. Its retired repair-model alias and
  completed policy fixes were reconciled through ansible-lint-api.yml
  (18 ok, 5 changed, 0 failed); health and installed source hashes passed.
- Current parser validated the accepted G3H cube (8 vertices, 12 faces).
- Python compilation, git diff --check, systemd-analyze verify, active launch
  paths, narrow SELinux labels and critical survivor checks passed.
- Historical disruptive Mesh acceptance remains in
  tools/llm/watoom-gpu-controller/README.md and its referenced private evidence.
  No new Mesh generation was submitted for this maintenance task.
  Concurrent user Mesh jobs completed their GPU restoration during the audit.
- Backup verification records, checksums, restore-clone fsck and exact tag/HEAD
  verification are stored in this backup and the external audit directory.

## Cleanup and preserved exceptions

28 obsolete one-time helpers were removed after dependency and hash checks.
Their exact paths, reasons, replacements, sizes and SHA256 values are recorded
in cleanup-manifest.json outside Git. Active helpers, credentials, controller
state, journals, job records, models, game assets and forensic records remain.

Four archives are byte-identical to independently retained extracted source;
backup-candidates.json records every member hash and its retained counterpart.
Pruning is permitted only after the new tagged backup passes restoration
verification. The final external report records the completed deletions.

122 pre-existing non-baseline paths remain intentionally uncommitted.
remaining-exceptions.json records every path and hash. They include unrelated
Kali/Pi/workflow work, prospective WebUI profile/retirement changes, historical
documentation refreshes and inactive native-router experiments. Some content
has current service relevance but has not been established as complete or safe
for general replay. It is not asserted deployed by this freeze.
Original and remaining files are preserved in protected audit archives and
binary patches. Use a fresh worktree from the tag for future development;
do not bundle, stage or deploy the dirty canonical working directory wholesale.

## Protected recovery assets and secrets

Retain the pre-G3H bundle and its associated source/runtime snapshots:
 /data/ai/projects/pipelines/mesh-switch-coordination/g3h-snapshots/20261012T070337Z/repository.bundle

The new backup contains Git history/tag, committed-source.tar.gz, sanitized
inventory/fingerprints and a separate protected runtime-recovery.tar.gz.
The private runtime archive excludes credential directories and includes
controller state/intents/audit/cache, bridge receipts, primary recovery baseline,
pipeline configuration and job metadata. Generated models/assets remain at
their existing durable paths; they are not copied into this source backup.

Secrets stay separately managed: /etc/rancher/k3s/k3s.yaml;
 /data/ai/helper-scripts/state/gpu-controller-credentials;
 /app/ai/services/opencode/home/.config/opencode/service.json;
 Kubernetes Secrets and the existing ignored secret environment files.
No credential values, private keys or kubeconfigs are added to baseline Git
or its general-purpose archive. After restoration, use the installed credential
refresh service/timer to renew short-lived controller access.

## Safe recovery procedure

1. Verify SHA256SUMS in the protected backup and git bundle verify repository.bundle.
2. Clone into a fresh directory; never reset the dirty canonical checkout:
   git clone --branch dev /data/ai/backups/baselines/pre-new-agent-engine-20261013/repository.bundle /data/ai/projects/baseline-recovery-20261013
   git -C /data/ai/projects/baseline-recovery-20261013 switch --detach baseline/pre-new-agent-engine-20261013
   Verify git rev-parse HEAD against inventory.json.
3. Inspect current controller ownership and live GPU replicas. Preserve current
   credentials, durable state, intent journals and request-ID receipts. Do not
   restore an older state archive over a healthy or actively owned controller.
4. If an ended worker requires recovery, use the existing controller-mediated
   oneshot: systemctl start watoom-llama-mesh-recovery.service.
   It must defer live workers. Recheck real Qwen inference and qwen-ready.
5. For source rollback, compare the selected tagged files with the failed
   deployment, run the relevant syntax/offline checks, then use the affected
   canonical Ansible role only after its four reviewed activation gates are
   satisfied. Set llm_model_lab_project_root to the recovery project's
   standardised_k3s_project directory when using the recovered source.
   The persisted parser pointer follows that selected source root.
   Keep deployment UIDs, model hashes/stat records and cutover proof consistent.
6. Restore runtime-recovery.tar.gz only after independently establishing actual
   state corruption and confirming no live worker. Reconcile newer receipts and
   generation/intent records first. Preserve surviving state and secrets.
7. Verify controller/bridge/timer, router readiness, exact model alias, real Qwen
   inference, GPU exclusivity, admission/RBAC and successful recovery service.

Never replay the storage cutover, initialize ownership again, force-push,
reinstall k3s/Docker, bulk-apply experiment manifests or change networking.

## Freeze and limitations

New agent/orchestration and inference-engine development must start on separate
branches/worktrees from baseline/pre-new-agent-engine-20261013. Experimental assets must not replace stable
binaries, GGUFs, manifests or deployment configuration. Keep this baseline even
when later experiments fail.

This is recovery of the existing production environment, not an unattended
fresh-cluster installer: recorded deployment identities and file-stat proofs
are host/cluster-specific and require reviewed re-binding after reconstruction.
The source archive deliberately excludes ignored files, secrets, runtime data
and 122 non-baseline changes. Historical GUI profile IDs and retained
forensic artifacts are not independently retired here. General mesh artistic
quality and new performance benchmarks remain unverified and explicitly deferred.
