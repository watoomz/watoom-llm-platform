# Backup and Recovery

## Recovery objective

The repository rebuilds desired state; it does **not** replace application-state backups. Recovery requires both:

1. a usable canonical Git checkout and secrets source, and
2. required `/app`/`/data` persistent data restored from backup where applicable.

## Fresh-install sequence

```bash
cd /data/github/watoom-standardised-homelab/standardised_k3s_project
./ansible-run playbooks/rebuild-homelab.yml --tags audit
./ansible-run playbooks/foundation.yml
./ansible-run playbooks/secrets.yml
./ansible-run playbooks/kubernetes.yml
./ansible-run playbooks/docker.yml
./ansible-run playbooks/validate.yml
```

Then reconcile the specialised LLM stack separately; it is not currently fully covered by the broad Kubernetes manifest registry.

## Required preconditions

- `/app` and `/data` mounted correctly
- canonical checkout at `/data/github/watoom-standardised-homelab/standardised_k3s_project`
- secret environment restored from the approved password/secret source
- network interfaces match the current LAN/DMZ design
- application state restored before starting stateful workloads that depend on it

## Post-reboot acceptance

```bash
cd /data/github/watoom-standardised-homelab/standardised_k3s_project
./ansible-run playbooks/health.yml
./ansible-run playbooks/validate.yml
kubectl get pods -A
docker compose ls
```

## What is backed up

- **Git:** all desired state (this repository) is pushed to `origin` (`main`, and `dev` for model work).
- **WatooM Code state:** `watoom-code-backup.timer` (daily 03:30, `playbooks/watoom-code-backup.yml`, `tools/watoom-code/backup.py`) writes `/data/backups/watoom-code/<UTC stamp>/` with consistent online SQLite copies (application, catalog, home databases), configuration and AgentMemory archives, the Deployment list and a verified manifest (integrity check, row counts, sha256). It keeps 14 runs, prunes only after a verified run, and exports a last-success metric.
- **Off-host copy:** `playbooks/watoom-backup-offhost.yml` publishes the newest verified runs for the rig to pull over a jailed, key-only SFTP account; `watoom-backup-offhost-check.timer` checks the rig's receipts against the manifests and raises `WatoomOffhostBackupStale` when the copy falls behind.
- **Not covered:** model weights (re-downloadable, under `/data/ai/models`), media libraries and the purchased asset library, which rely on their own sources. A backup is not a restore test: restore into an isolated location and verify before relying on it.

## Router backups

The network repository contains redacted RouterOS text exports and password-protected binary backups. Prefer the redacted `.rsc` form as the reviewable/cross-device rebuild source. Keep sensitive exports outside Git.

## Recovery priorities

1. network/default route/DNS
2. storage mounts
3. k3s/Docker runtimes
4. secrets
5. core infrastructure (Traefik, Pi-hole, Glance, monitoring)
6. stateful media/services
7. Docker edge stacks
8. games/on-demand services
9. specialised LLM reconciliation and profile sync
10. validation and external/public checks

## AI state recovery

Restore WatooM Code state from `/data/backups/watoom-code`, then the required `/data/ai` projects, assets, models and caches and `/app/ai/services`, following the [directory layout](AI_DIRECTORY_LAYOUT.md). WatooM Code, Kali and the model lab are restored through their own roles, separately from the broad manifest registry. Preserve both Moonstone state trees; new state is project-local.

Model switching or service restart can affect active chats. Check persisted workflow checkpoints and unresolved children first. A package PASS checkpoint awaiting confirmation must leave the next package PENDING until explicit user continuation; startup recovery is not confirmation. Backups and file presence do not establish a restore test.
