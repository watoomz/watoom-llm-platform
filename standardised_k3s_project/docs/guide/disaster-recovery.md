---
title: Disaster recovery — environment and projects
nav: Disaster recovery
summary: Recovery scope, private capture, off-host verification, isolated restore tests and ordered replacement-host rebuild phases.
---

## Recovery contract

Recover the environment, authored projects and persistent service state. Downloaded media, model weights, toolchains and purchased asset libraries may be reacquired. Preserve their exact version, image, filename and acquisition requirements. Personal photo originals are conservatively retained rather than assumed downloadable.

Git is only one recovery input. It does not contain live credentials, private databases, model files or a backup of every service volume. The existing daily off-host job protects WatooM-Code state; it is not a whole-environment backup. A successful SQLite restore test does not qualify a live MariaDB/AgentMemory file archive or a replacement-host deployment.

The current source inventory covers Kubernetes workloads/PVs, host paths, Docker mounts, image references, required secret names, identities and host units. It records zero replicas without treating them as retirement. Secret values, environment values and session contents are deliberately absent from the published inventory.

## Tools and entrypoint

`scripts/rebuild-homelab.sh` in this distribution delegates to `tools/recovery/recovery.py`:

| Command | Behaviour |
|---|---|
| `inventory` | Read-only live inventory; output contains names/paths/pins, not secret values |
| `plan` | Ordered rebuild phases and explicit missing recovery evidence |
| `audit` | Check storage classification plus actual evidence-file presence and SHA-256; missing inputs return exit 2 |
| `capture` | Write a new private environment bundle; no services are stopped or restarted |
| `verify-backup` | Check every file against a backup manifest; reject unsafe paths and links |
| `restore-test` | Restore SQLite snapshots into a new isolated directory and check integrity; read archives without extracting credentials |
| `restore-bundle` | Extract a full bundle into a new isolated target and overlay consistent SQLite snapshots; never activate it |
| `run-phase` | Invoke only the selected owning playbooks on a prepared replacement host; refuse the inventoried production machine |

The supported rebuild interface is the recovery export and restore procedure below; runtime installers and network-changing shortcuts are not part of it. Shared OpenCode agents, skills and native-plugin source remain in place.

## What a private capture contains

`config/recovery/policy.json` is the scope and phase source. Storage classification uses the longest matching prefix, so a model-cache exclusion overrides a broader environment root. Unknown storage blocks readiness instead of disappearing from the plan.

| Material | Recovery treatment |
|---|---|
| Reviewed source and uncommitted operator work | GitHub source plus a private source-tree snapshot; do not rely on a dirty working tree surviving |
| `/etc`, account/group identities, host units, TLS and private configuration | Private archive; review ownership and enablement before restoration |
| Kubernetes Secret/ConfigMap values and resource specs | Private reference exports; never commit or replay all old resources blindly |
| WatooM-Code databases/configuration | Existing consistent SQLite backup implementation plus isolated restoration |
| Other discovered SQLite service databases | Online SQLite snapshots with integrity checks, mapped to their original paths |
| Non-SQLite service databases and live files | Best-effort live capture; require a cold or application-native backup/restore qualification |
| Controller state, private grants, model ledger, worker journals and knowledge cards | Private environment state; reconcile identities and every in-flight job after recovery |
| Projects and service/PV/Docker volume state | Included by default; caches and explicitly reacquirable data are excluded |
| Local image registry and running Docker images | Registry mount plus a portable Docker image archive; verify reference/ID agreement before capture and required digests after restoration |
| Downloaded media, model weights, toolchains, purchased libraries | Reacquire from exact recorded profiles/versions and authorised sources |
| Symlinks | Recorded separately; recreate only reviewed targets through the owning installer |
| Bazzite and workstation workers | Re-stage/reinstall from their maintained source, preserve private transfer credentials and reconcile journals; no automatic replay |

Capture is a private operator action. Its archives contain credentials and personal data. Keep them outside Git, in an owner-controlled directory and the approved off-host destination. The tool sets a private umask, refuses an existing output, avoids recursive capture of backups and enforces storage budgets. It preserves partial evidence on failure and writes no success manifest for an incomplete run.

## Inventory and inspect readiness

From `standardised_k3s_project/`:

```bash
sudo ./scripts/rebuild-homelab.sh inventory --output /secure/environment.json
./scripts/rebuild-homelab.sh plan --inventory /secure/environment.json
./scripts/rebuild-homelab.sh audit --inventory /secure/environment.json --evidence /secure/recovery-evidence.json
```

Create the evidence file from `config/recovery/evidence.example.json`. Every required record needs a real locally available evidence file and matching SHA-256; setting `verified=true` alone cannot pass. Evidence covers source, private state, off-host projects, images, secret/vault recovery, model/toolchain acquisition, host bootstrap, service-consistent data and controller admission/reprovisioning.

An audit verdict of `READY_FOR_ISOLATED_DRILL` means prerequisites are available for a drill, not that a full disaster recovery already passed. A missing archive, image, credential source or restore qualification remains a blocker.

## Capture and publish off-host

Use an unused UTC run stamp. Capture uses the current source policy and defaults to environment plus projects:

```bash
sudo ionice -c3 nice -n 19 ./scripts/rebuild-homelab.sh capture --output /data/backups/recovery/20261107T120000Z
sudo ./scripts/rebuild-homelab.sh verify-backup --backup /data/backups/recovery/20261107T120000Z
```

The timestamp is an example, not an existing recovery run. `--scope environment-only` intentionally omits projects and must not be represented as complete project protection. SQLite snapshots are transaction-consistent; live non-SQLite stores require their native dump or a separately planned quiesced backup. This tool does not interrupt work to obtain one.

Publish completed runs into a separate `environment` subdirectory of the existing jailed export using `ansible/playbooks/watoom-recovery-export.yml`. It does not change SSH, accounts or ports. This keeps the existing daily application backup/export intact.

On the workstation, provision a private `F:\data\homelab_recovery` directory, then use `tools/recovery/pull-environment-recovery.ps1 -Run <stamp>`. It uses the existing key-only SFTP account, verifies every file, uploads a receipt to the separate environment receipt directory, and never prunes or overwrites existing runs. The script refuses a broadly readable destination. The existing `F:\data\homelab_backups` remains the daily application-backup destination.

## Test restoration before relying on a backup

```bash
sudo ./scripts/rebuild-homelab.sh restore-test --backup /private/offhost-copy/<stamp> --target /private/drill/new-sqlite-directory
sudo ./scripts/rebuild-homelab.sh restore-bundle --backup /private/offhost-copy/<stamp> --target /mnt/watoom-recovery/new-root
```

Both targets must be new. Verify the restored files, project source, databases, registry images and private configuration in isolation. Restore account/UID/GID mappings and apply the owning SELinux labels before starting consumers. Keep the replacement host's unique `/etc/machine-id`; do not copy the source machine's marker onto it. The apply guard deliberately rejects the source identity. On the replacement host, load the private Docker image archive and restore the registry before pulling pinned workloads; neither action is performed automatically on the live machine. Do not copy a raw SQLite WAL snapshot over the consistent database extracted from its snapshot map.

The verified application-backup test restores three SQLite databases and checks archive readability. It does not recover lost media, prove AgentMemory engine consistency, or validate a complete replacement host. The sanitised result is stored with publication evidence; private restored databases stay outside Git.

The current SQLite-backed k3s datastore is captured separately as `private/k3s-state.sqlite.gz`, with its token/TLS material in the private bundle. Choose an offline datastore restore matched to the original k3s identity/version or a freshly qualified IaC rebuild; never overwrite a running datastore. Embedded-etcd deployments require their own supported snapshot and qualification, not a live directory copy.

## Ordered replacement-host phases

The exact playbook list lives in policy; `plan` prints it rather than relying on this summary:

1. Provision the replacement OS, mounted storage, matching identities, k3s/Docker and GPU support through existing approved procedures. Place the reviewed source at the canonical path expected by role/helper configuration, or explicitly review every alternate-root mapping in the private vars file; setting the wrapper ROOT alone does not relocate all runtime paths. No installer is run on the current host.
2. Restore verified private state, projects, image registry and secret sources before stateful consumers start.
3. Reconcile foundation paths and secrets through their existing owners.
4. Reconcile the platform and Docker services; preserve intentionally stopped workloads.
5. Re-provision the GPU controller/model lab through its existing guards. New cluster UIDs and admission identities require fresh qualification; old cutover booleans/proofs are not reusable evidence.
6. Restore independently pinned WatooM-Code, AgentMemory and Toolkit; install current agents, native plugins and skills.
7. Reconcile the selected worker, memory, monitoring and backup integrations. Reinstall/re-pin the RIG Unreal lane and Bazzite runtime where necessary; do not rerun completed one-off migrations.
8. Verify API readiness, exact image digests, mounts/secrets, enabled units, memory, project data, controller refusal behaviour, a harmless bounded worker request and a new off-host backup/restore test.

`run-phase` requires a reviewed private vars file and complete evidence, and refuses a machine whose identity matches the source inventory. It runs existing owner playbooks; it does not fabricate safety flags or declare runtime acceptance after an Ansible exit code. Use a fresh private evidence directory for each phase and reconcile partial results before retrying.

Do not automatically re-enable captured unit files for one-off guards, rollbacks or migration runners. Do not seize GPU ownership, clear durable guards, or replay an uncertain remote job. The source machine inventory and recovery policy preserve these review requirements.

## Current qualification boundary

The source package and current recovery inventory can be validated without deployment. The existing off-host application snapshot has an isolated SQLite restore test. A complete new environment/project bundle, its independent off-host verification, service-consistent non-SQLite restore and replacement-host drill are separate required evidence. Until those pass, full disaster-recovery readiness is explicitly blocked.

For source ownership and current extensions see [Software design](software-design.md), [Custom extensions](llm-extensions.md), [Operations](operations.md) and [Recovery](recovery.md).
