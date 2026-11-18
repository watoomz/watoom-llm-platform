# Backup and Recovery

Current deployment snapshot: 13 October 2026. Runtime-specific status is dated; configured/recovery guidance is not an end-to-end test.

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

## Backup coverage status

The previous rebuild documentation states that NAS/restic backup automation was not yet configured. Do not represent a full off-host backup system as complete until it exists and has restore tests.

The `/data/cleanup-backups` tree created during controlled cleanup passes is useful rollback material for those changes, but it is not a complete disaster-recovery strategy.

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

Restore `/app/ai/services` and required `/data/ai` projects, assets, models and caches. Use [current layout](AI_DIRECTORY_LAYOUT.md), not retired pre-migration host paths. Account for OpenCode/Pi/Kali roles and specialised model scripts separately from the broad manifest registry. Preserve both Moonstone state trees; future state is project-local.

Model switching or service restart can affect active chats. Check persisted workflow checkpoints and unresolved children first. A package PASS checkpoint awaiting confirmation must leave the next package PENDING until explicit user continuation; startup recovery is not confirmation. Backups and file presence do not establish a restore test.

## Protected pre-development baseline

Frozen tag: `baseline/pre-new-agent-engine-20261013` at `6a2dc2e291f358c57df46123fdfba2cd04ffb0d2`. G3H commit `c293647bed8176b97123884fcad453b20ecd65b6` is an ancestor.

Protected recovery directory: `/data/ai/backups/baselines/pre-new-agent-engine-20261013`. It contains verified Git history, committed source, sanitised runtime recovery records, inventory/fingerprints, checksums, verification and `ROLLBACK.md`. Files are read-only and immutable. Preserve the separately protected pre-G3H bundle at `/data/ai/archive/projects-20261029/pipelines/mesh-switch-coordination/g3h-snapshots/20261012T070337Z/repository.bundle`.

Read [the baseline recovery procedure](baselines/pre-new-agent-engine-20261013.md) and the backup's `ROLLBACK.md` before restoration. Verify bundle/archive integrity and restore into an isolated checkout first. Restore only reviewed affected fields through existing owners, preserving current ownership, admission/RBAC, durable state and credential locations. Do not broad-reset the canonical checkout or apply old replica writers. Credentials, model weights and complete application data require their separately managed sources.

The tag/backup is a verified local recovery point, not an off-host disaster-recovery test. Current documentation follows the frozen tag without rewriting it. New agent/inference-engine development must begin in separate branches or worktrees.
