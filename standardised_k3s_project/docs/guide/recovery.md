---
title: Backup and recovery
nav: Recovery
summary: What is backed up, how to bring the host back after a reboot, and the ordered rebuild from bare metal.
---

## What protects what

The repository rebuilds **desired state**. It does not contain application data. Full recovery needs both:

1. the Git checkout plus the vault password, and
2. the persistent data under `/app` and `/data`.

| Data | Protection |
|---|---|
| Repository and manifests | Git remote; encrypted secrets in `secrets-vault/` |
| Vault password | `/data/secrets/watoom-homelab/` and the owner's password manager |
| WatooM Code database, config, AgentMemory | Daily verified backup (03:30, 14 kept) in `/data/backups/watoom-code`, plus an off-host copy pulled by the workstation |
| Protected AI baseline | Read-only recovery bundle in `/data/ai/backups/baselines/` |
| RouterOS | Redacted `.rsc` exports (reviewable) and password-protected binary backups, kept outside this repository |
| Media libraries, `/app` service state | **No automated off-host backup** |

> [!WARNING]
> Only WatooM Code state has an automated off-host copy. A disk failure on `/app` or `/data` loses media, service configuration and models. File presence is not a tested restore.

Check backup health:

```bash
systemctl list-timers watoom-code-backup.timer watoom-backup-offhost-check.timer --no-pager
ls -lt /data/backups/watoom-code | head -3
```

`WatoomBackupStale` and `WatoomOffhostBackupStale` fire when either falls behind.

## Before a planned reboot

```bash
git -C /data/github/watoom-standardised-homelab status --short
kubectl get pods -A | grep -v -E 'Running|Completed'
docker compose ls
df -h / /app /data
cat /data/ai/helper-scripts/state/gpu-controller/state.json   # expect qwen-ready, owner null
```

Do not reboot while the GPU controller has an owner or a WatooM Code job is active.

## After a reboot

```bash
ip -br addr; ip route                      # enp34s0.20 and enp35s0 up, default via 10.99.20.1
systemctl --failed --no-pager
kubectl get nodes -o wide
kubectl get pods -A | grep -v -E 'Running|Completed'
docker compose ls
nvidia-smi
cd /data/github/watoom-standardised-homelab/standardised_k3s_project
./ansible-run playbooks/health.yml
./ansible-run playbooks/validate.yml
```

The GPU controller starts the primary model on its own. Wait for `qwen-ready` rather than scaling anything by hand. Zero-replica games and utilities stay down by design.

## Rebuild sequence

Preconditions: `/app` and `/data` mounted; checkout at `/data/github/watoom-standardised-homelab`; vault password restored; network interfaces match [Network](network.md); application data restored before stateful workloads start.

```bash
cd /data/github/watoom-standardised-homelab/standardised_k3s_project
./ansible-run playbooks/rebuild-homelab.yml --tags audit
./ansible-run playbooks/foundation.yml
./ansible-run playbooks/secrets.yml
./ansible-run playbooks/kubernetes.yml
./ansible-run playbooks/docker.yml
./ansible-run playbooks/validate.yml
```

Then bring up the dedicated stacks, which the broad registry does not cover:

1. GPU controller and model lab: `gpu-controller.yml`, `llm-model-lab.yml`
2. WatooM Code: `watoom-code.yml`, then the guard, agents and `watoom-native-skills.yml`
3. Host dispatchers and the render stage roles

### Priority order

1. Network, default route, DNS
2. Storage mounts
3. k3s and Docker runtimes
4. Secrets
5. Core infrastructure: Traefik, Pi-hole, Glance, monitoring
6. Stateful media services
7. Docker edge stacks
8. On-demand games
9. AI stack and WatooM Code
10. Validation and external checks (tunnels, public game ports)

## Restoring WatooM Code state

Stop the app through its owner, restore the database and config from the newest verified backup in `/data/backups/watoom-code`, then start it through the owner. Check that open sessions and checkpoints are as expected before resuming work. The protected baseline in `/data/ai/backups/baselines/` carries its own `ROLLBACK.md`; restore into an isolated checkout first and apply only the reviewed fields.

## Environment disaster recovery

The [disaster recovery guide](disaster-recovery.md) defines the environment/project/service-state scope, private capture, off-host verification, isolated restoration and guarded replacement-host phases. Git alone is not a full backup; readiness remains blocked until the required recovery evidence exists. Media and purchased libraries may be reacquired, while private state and authored projects need independent protection.
