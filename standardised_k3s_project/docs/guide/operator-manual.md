---
title: Operator manual
nav: Operator manual
summary: A task-first manual for running the homelab — how to check health, fix, approve, start, stop and restart things safely, what every approval gate means, and when to stop and ask the owner.
---

This page is written for someone who did not build the system. Start at **[I want to…](#i-want-to)** and follow the links. Every command runs on the server (`homelab-host`) over SSH unless it says otherwise. If a step is not covered here, **stop and ask the owner**; do not improvise on the GPU, the router, secrets or Git.

> [!RULE]
> Five things that are never the answer: scaling a model Deployment by hand, editing GPU-controller state, force-deleting things to "clear" them, running `git add .` / `git reset --hard` / `git clean -fd`, and pasting secrets into chat, Git or logs. Each is explained below.

## How the pieces fit (one minute)

| Piece | What it is | You will touch it when |
|---|---|---|
| **Glance** (`https://glance.internal.homelab.example`) | The dashboard and this guide. Mostly read-only; it also hosts Model Manager and the Change-requests approval page | Checking health, approving a change request |
| **k3s** | Runs almost every service as a Kubernetes app | Restarting or checking an app |
| **Docker Compose** | Runs the edge stacks: WireGuard, AzuraCast, the stream, the Cloudflare tunnel | Restarting a stack |
| **GPU controller** | A host service that is the *only* thing allowed to start or stop AI models on the single GPU | Reading its state; recovering after a failed switch |
| **LLM router** | The front door for AI requests; asks the controller for the right model | Reading model status |
| **WatooM Code** | The AI coding/asset workspace and its helper timers | Jobs, approvals, backups |
| **Git + Ansible** | Source of truth. Changes are made in Git, then applied with `./ansible-run` | Any lasting change |

Rule of thumb: **change the source, apply with the owning playbook, then verify.** A one-off live fix is a temporary patch that the next deploy may undo.

## I want to…

| Goal | Go to |
|---|---|
| See whether everything is healthy | [Daily check](#daily-check) |
| Something is red or not loading | [Fix it: start here](#fix-it-start-here) |
| Restart one service | [Start, stop and restart](#start-stop-and-restart) |
| Start or stop a game server | [Game servers](#game-servers) |
| An AI request fails or is slow | [AI and the GPU](#ai-and-the-gpu) |
| Approve something an AI asked for | [Approvals and gates](#approvals-and-gates) |
| Reboot the server safely | [Reboot checklist](#reboot-checklist) |
| Disk is filling up | [Disk space](#disk-space) |
| Restore from backup / rebuild | [Backups and recovery](#backups-and-recovery) |
| Know what a script or timer does | [Scripts, timers and helpers](#scripts-timers-and-helpers) |
| Work out what a word means | [Glossary](#glossary) |

## Daily check

Open Glance. On **Home**, look at *Needs Attention* and *Core Status*; on **Command Center**, *Homelab Health* and *Namespace Workloads* (restart hotspots show anything crash-looping); on **LLM Lab**, *LLM Health*.

Then, from the server, the three-line health check:

```bash
kubectl get nodes
kubectl get pods -A | grep -v -E 'Running|Completed'     # anything listed needs a look
cat /data/ai/helper-scripts/state/gpu-controller/state.json   # want: qwen-ready, owner null, uncertain false
```

Normal and not a fault: zero-replica games and utilities (they are *on demand*); non-primary AI models at `0/0`; the controller `owner` being set while a model switch or Mesh job is running.

For the full check run `cd /data/github/watoom-standardised-homelab/standardised_k3s_project && ./ansible-run playbooks/health.yml`. Alerts (disk, memory, backups, primary model down, failed systemd units) are listed in [Monitoring](monitoring.md); firing alerts can be read with the command shown there.

## Fix it: start here

Work top to bottom and stop at the first thing that is wrong.

1. **Can you reach the server at all?** `ip -br addr`, `ping -c 4 10.99.20.1`. If not, this is network: see [Troubleshooting](troubleshooting.md#host-or-network-unreachable). Do not touch router, VLAN, firewall or DNS settings without the owner.
2. **Is the node and are the pods fine?** `kubectl get nodes`; `kubectl get pods -A | grep -v -E 'Running|Completed'`.
3. **A pod is not starting:** `kubectl -n <ns> describe pod <pod>` and read *Events*. `Insufficient nvidia.com/gpu` is normal when another model holds the GPU. `hostPath … is not a directory` means a data folder was moved: restore the folder, do not create an empty one. Full table: [Pod not starting](troubleshooting.md#pod-not-starting).
4. **A website gives 404 / 502 / 503:** 404 = no route; 502 = backend refused; 503 = no endpoints (often a deliberately stopped app). See [HTTPS errors](troubleshooting.md#https-returns-404-502-or-503).
5. **A Glance widget shows an error:** read the helper logs; the JSON `error` field names the failing upstream. See [Glance widget](troubleshooting.md#glance-widget-shows-an-error).
6. **A systemd unit shows failed:** `systemctl --failed --no-pager`, then `journalctl -u <unit> -n 50 --no-pager`. A unit that fails every few seconds is a timer retrying (see [timers](#scripts-timers-and-helpers)); read the first error line, not the repeats.
7. **AI problem:** go to [AI and the GPU](#ai-and-the-gpu).
8. **Still unclear:** collect `kubectl get pods -A`, the controller `state.json`, and the relevant log lines, and send them to the owner. Do not restart things "to see".

## Start, stop and restart

Always use the smallest owner that covers the thing. The wrapper `./ansible-run` (in `standardised_k3s_project/`) presets inventory, vault and execution environment.

| Thing | Command |
|---|---|
| One Kubernetes app | `./ansible-run playbooks/kubernetes-app.yml -e kubernetes_app_name=radarr -e kubernetes_app_namespace=radarr -e kubernetes_app_action=restart` |
| One Docker stack | `./ansible-run playbooks/docker-stack.yml -e docker_stack_target=wireguard -e docker_action=restart` |
| A game server | `./ansible-run playbooks/game.yml -e game_name=valheim -e game_action=start` |
| Interactive menu | `scripts/watoom-menu.sh` (or `https://iac-console.internal.homelab.example/menu` — the console itself is on demand) |

App actions: `status`, `start`, `stop`, `restart`, `reconcile`, `set_image`. Docker actions: `status`, `up`, `down`, `restart`, `pull`, `reconcile`; targets `wireguard`, `azuracast`, `dispatcharr_cloudflare`, `all`. The menu offers the same for apps (status, start/stop/restart, logs, describe, shell, apply manifest) and stacks.

> [!WARNING]
> Never use these for AI models (`llama-cpp-*`) or the GPU controller. Models are started and stopped only by the controller. See [AI and the GPU](#ai-and-the-gpu).

Stopping an app that other things depend on (Pi-hole = all DNS, Traefik = all websites, the Cloudflare connector = all public access) takes those things down too. Check Services before stopping anything marked *running*.

## Game servers

Enshrouded normally runs; the others start on demand. Registered names: `cs2`, `enshrouded`, `dayz`, `arma_reforger`, `valheim`.

```bash
./ansible-run playbooks/game.yml -e game_name=cs2 -e game_action=status
./ansible-run playbooks/game.yml -e game_name=cs2 -e game_action=start
./ansible-run playbooks/game.yml -e game_name=cs2 -e game_action=stop
```

A start fails fast if the server's required Secret is missing (see [Secrets](#secrets-and-the-vault)). If players cannot connect, work through [Game server unreachable](troubleshooting.md#game-server-unreachable). Minecraft servers are LAN-only by design. Tell players before a `restart`.

## AI and the GPU

Only one big model fits on the GPU. The **GPU controller** decides which one, records every step, and can recover an interrupted switch. Everything else asks it.

**Read the state first:**

```bash
cat /data/ai/helper-scripts/state/gpu-controller/state.json
systemctl status watoom-gpu-controller --no-pager
kubectl -n llama-cpp get deploy | awk '$2!="0/0"'      # which model is actually up
nvidia-smi
```

| You see | Meaning | Do |
|---|---|---|
| `phase: qwen-ready`, `owner: null`, `uncertain: false` | Idle and healthy | Nothing |
| `owner` is set | A model switch, Mesh job or operator task is running | **Wait.** Do not interrupt |
| `uncertain: true` | A transition was interrupted | Use controller recovery (below), never manual scaling |
| `phase: recovery-required` for a long time | The switch failed and is stuck | See [Stuck in recovery-required](#stuck-in-recovery-required) |
| Router returns 503 for a model | Usually the controller is mid-switch or in recovery | Check the state above |
| Target model at `0/0` before a request | Normal; it is started on demand | Nothing |
| `CUDA out of memory` | Model + context + cache exceed 20 GiB | Owner decision; do not shrink settings silently |

Never run a job that needs the GPU while the owner field is set. An active coding session or busy slot blocks disruptive work — **low GPU use does not mean idle**.

**Checking models through the router:**

```bash
kubectl -n llama-cpp port-forward svc/llm-router 18000:8000 &
curl -s localhost:18000/healthz            # router is alive (local check)
curl -s localhost:18000/health             # also names the active model
curl -s localhost:18000/models/status
```

### Stuck in recovery-required

1. Read `state.json` and the controller log: `journalctl -u watoom-gpu-controller -n 80 --no-pager`. The audit trail is `/data/ai/helper-scripts/state/gpu-controller/audit.jsonl`.
2. If the message is **`Unsafe: deployment identity or model configuration changed`**, the primary Deployment was changed outside the controller and its pinned fingerprint is stale. This needs a **re-pin** after a human reviews the change — see [Re-pinning](#re-pinning-the-primary-model).
3. If the owner is a router process that is still alive, that router needs restarting before `recover` is accepted: `kubectl -n llama-cpp rollout restart deploy/llm-router`.
4. Ask the controller to restore the primary model through the router: `curl -s -X POST localhost:18000/models/load -H 'content-type: application/json' -d '{"model":"swift-qwen38-coder"}'` (with the port-forward above). Then confirm `qwen-ready`, `uncertain:false`, and that a real request answers.
5. If it will not clear, stop and collect `state.json`, the last 80 controller log lines and the audit rows around the failure for the owner.

### Break glass: reset a wedged AI stack

Use this when the AI stack is stuck and you cannot clear it by hand: a held deployment guard, execution claims nobody owns, running-job flags that never clear, a stuck worker, or GPU ownership that will not release. Open **Glance → Break glass** (`/command-center/break-glass.html`). The page shows what is stuck right now and offers two buttons, both protected by the operator PIN.

| Button | What it does | What it never does |
|---|---|---|
| **Clear stale** | Clears only what is provably orphaned: claims whose owner is interrupted and idle, finished or very old worker pods and units, a GPU owner whose process has ended (through the GPU controller). | Touch running work. |
| **Force reset** (PIN plus typing `RESET`) | Snapshots the database, stops the app and every worker, clears claims, queued inputs, running-job flags and a held deployment guard, recovers GPU ownership through the GPU controller, restarts the router and the app, then checks the guard, executions and model catalogue. | Delete sessions or history. Queued inputs it clears are saved in the run's evidence. |

Glance never touches the cluster itself. It queues a request that the root service `watoom-break-glass` validates (recent, known mode, cooldown) and runs. Each run writes an evidence bundle (before and after state, steps, database snapshot, cleared rows) to `/data/ai/helper-scripts/state/break-glass/runs/<timestamp>/`; the five newest snapshots are kept. If a force run dies after stopping the app, the next refresh (within a minute) starts the app again.

From the host: `python3 tools/break-glass/break_glass.py diagnose` (read-only), or `python3 tools/break-glass/break_glass.py run --mode stale|force --i-approve` as root. Install the service with `ansible-playbook ansible/playbooks/watoom-break-glass.yml`.

### Re-pinning the primary model

The controller remembers each model Deployment's identity and a hash of its spec. If the primary Deployment is edited (for example an env var), the hash no longer matches and **every** controller action, including recover, is refused until a human approves the new hash. This is a safety gate, not a bug.

The gate only opens if the controller is `qwen-ready`, unowned and certain, the Deployment UID is unchanged, and only the primary's hash differs. Review the change first, then:

```bash
cd /data/github/watoom-standardised-homelab/standardised_k3s_project
python3 scripts/gpu-controller-repin-primary.py            # dry run: prints DRIFT old -> new, changes nothing
python3 scripts/gpu-controller-repin-primary.py --apply    # writes the new hash (backup kept next to the config)
systemctl restart watoom-gpu-controller.service
python3 scripts/gpu-controller-repin-primary.py            # should now print UNCHANGED
```

Then copy the new hash into `ansible/roles/llm-model-lab/files/gpu-controller.json` (the matching `spec_sha256` line) so a plain playbook rerun does not revert it, and commit that file. The playbook route (`playbooks/gpu-controller.yml -e gpu_controller_repin_primary=true`) additionally requires `gpu_controller_cutover_verified=true`, which is a deliberate extra gate for a full controller promotion; do not set it to get past a refusal.

### Changing a model setting safely

Model settings live in the manifest (for example `manifests/10-infrastructure/llm/llama-cpp-swift-qwen38.yml`). The sequence is: edit in Git → `kubectl diff -f <manifest>` and confirm only the intended lines differ → apply at a **quiet time** (the model restarts, taking a few minutes) → re-pin → verify `qwen-ready` and a real answer → keep the old value ready as the rollback. Policy: prefer full GPU residency, never change quantisation, context size or KV precision silently, and validate any placement change with rollback.

### Installing or removing models

Use **LLM Lab → Model Manager** (`https://glance.internal.homelab.example/model-manager/`). Paste a Hugging Face URL, choose the revision and variant, check the exact size, then **Download & set up**. *Downloaded*, *configured*, *registered* and *tested* are separate states. Removal unregisters and keeps files unless you explicitly confirm quarantine.

### AI agents (WatooM Code)

The coordinator hands work to a builder, investigator, critic and reviewer, one at a time. After two failed attempts the critic must be consulted before another repair. If an agent seems stuck: read its checkpoint under the project's `.opencode/work/`, do not delete inbox or controller state, and do not kill unknown processes. "Call the critic" from you means exactly one critic review. Source and rules: [WatooM Code](watoom-code.md).

## Approvals and gates

A **gate** is a deliberate stop that needs a human (or a verified condition) before something risky proceeds. Never work around one; each exists because the unsafe path was hit before. All gates, in plain words:

| Gate | What it protects | Where you act |
|---|---|---|
| **Change request** | AI cannot edit host-owned files (e.g. the ESP32 worker contract). It files a request; a human approves the exact diff | Glance → *Observe and search* → **Change requests**, or `python3 tools/change-requests/change_request.py list / show <id> / approve <id> / reject <id>` |
| **Operator PIN** | Stops models or other LAN clients approving change requests. Five wrong PINs lock the page for five minutes | PIN is in the root-only file `/root/.watoom-change-request-pin`; rotate with `scripts/set-change-approval-pin.sh` (as root) |
| **Fab download approval** | AI cannot download paid or owned assets without you | The agent asks in chat; answer **Approve download** to the exact request. The `watoom-fab-approvals` timer then fetches it within a minute |
| **GPU ownership / admission** | Only one job at a time owns the GPU | Wait for `owner: null`; never bypass |
| **Controller fingerprint (re-pin)** | A changed primary Deployment must be reviewed before the controller trusts it | [Re-pinning](#re-pinning-the-primary-model) |
| **Release fence** | App, agent, guard, skill and Toolkit releases wait for an idle app and GPU, apply, verify, and roll back on failure | Run the owning `playbooks/watoom-code-*.yml` or `tools/watoom-code/deploy-platform.py …`; do not hand-apply |
| **`gpu_controller_cutover_verified`** | Promoting a new controller runtime | Owner-run only, after the reviewed cutover gates |
| **Idle fence (RIG stage updates)** | Installing a new async-stage release while jobs may be queued | Pause the desktop RIG consumers, stop `watoom-rig-async-stage.timer`, hold the queue fence, run `tools/rig-async-stage/install-runtime.py`; see the README in that folder |
| **Learning curator** | Nightly lesson mining is off by default; nothing durable changes without the idle gate and owner approval | Levers: `watoom_learning_curator_enabled: false`, a `curator-disabled` file, or `memory_curator.py rollback --txn <id>` |
| **Git** | AI does not stage, commit or push unless asked | You decide; stage by explicit path only |
| **Kali security tools** | Only a top-level `watoom-kali` session may use them | Start that session deliberately; never delegate it |
| **Purchases and downloads** | Finding an asset is not buying it | Always an explicit approval |

**Approving a change request, step by step:** open the page; read the reason and the exact diff (red/green lines); confirm the file is one you expect; type the PIN; press **Approve and apply** (or **Reject**). The host applies it within about a minute, only if the request is still the version you reviewed, runs fixed checks, commits and pushes just that file, and restores it if a check fails. Every action is logged to `/data/ai/helper-scripts/reports/change-requests/audit.jsonl`. If unsure, reject — the model can file a new one.

## Reboot checklist

**Before:**

```bash
git -C /data/github/watoom-standardised-homelab status --short
kubectl get pods -A | grep -v -E 'Running|Completed'
docker compose ls
df -h / /app /data
cat /data/ai/helper-scripts/state/gpu-controller/state.json    # expect qwen-ready, owner null
```

Do not reboot while the controller has an owner or a WatooM Code job is running — an unplanned reboot interrupts work and can leave pods in a bad state.

**After:**

```bash
ip -br addr; ip route
systemctl --failed --no-pager
kubectl get nodes -o wide
kubectl get pods -A | grep -v -E 'Running|Completed'
docker compose ls
nvidia-smi
cd /data/github/watoom-standardised-homelab/standardised_k3s_project
./ansible-run playbooks/health.yml && ./ansible-run playbooks/validate.yml
```

The controller starts the primary model by itself; wait for `qwen-ready`. If the model pod reports **`UnexpectedAdmissionError … no healthy devices`**, the GPU device plugin had not registered yet: wait a minute or two for `kube-system/nvidia-device-plugin-daemonset` to be Running, and a replacement pod normally schedules; a leftover pod in `Unknown`/`Failed` can then be removed with `kubectl -n llama-cpp delete pod <name>`. Zero-replica games and utilities stay down by design.

## Disk space

Alerts fire at `/` 80%, and `/app` and `/data` 90%. Check `df -h / /app /data`. Most root usage is the container store under `/var/lib/rancher/k3s/agent/containerd` (images). Do **not** run broad prune commands. To clear space safely, list only images that are untagged **and** referenced by no container, confirm the digest is not named in the repo and is still served by the local registry (`127.0.0.1:5000`), then remove those one at a time with `k3s crictl rmi <id>`. Never delete under `/data/ai/models`, `/app` service state or `/data/backups`. Capacity growth beyond that is an owner decision.

## Backups and recovery

Only **WatooM Code** state (database, config, AgentMemory) has an automated off-host copy: daily at 03:30, 14 kept in `/data/backups/watoom-code`. Media and `/app` service state have **no** off-host backup. Check:

```bash
systemctl list-timers watoom-code-backup.timer watoom-backup-offhost-check.timer --no-pager
ls -lt /data/backups/watoom-code | head -3
```

Recovery tooling is read-only by default: `python3 tools/recovery/recovery.py {inventory,plan,audit,verify-backup,restore-test,restore-bundle,run-phase,capture}`. Restores go into a **new empty directory**; there is deliberately no live overwrite. Never restore over live state, and never replay historical jobs. Full procedures: [Recovery](recovery.md) and [Disaster recovery](disaster-recovery.md).

## Secrets and the vault

Secrets are stored encrypted in Git (`secrets-vault/env.local.vault`); the vault password is **not** in Git (`/data/secrets/homelab-host/ansible-vault-password.txt`). Refer to secrets by name only — never print or paste values.

```bash
scripts/check-required-secrets.sh      # confirms names exist; never prints values
scripts/restore-vault-secrets.sh       # needs the vault password file
scripts/render-secrets.sh              # then: kubectl apply -f manifests/05-secrets/
```

## Making and publishing a lasting change

1. Check `git status --short --untracked-files=all`; leave other people's changes alone.
2. Edit the **source** (not a generated file). Generated files: agent prompts (`v2-native/agents/*.md` from `_src`), the Glance guide HTML, server catalogue, Glance ConfigMaps.
3. Validate: `git diff --check`, `./scripts/watoom-ansible-validate.sh standard`, and the relevant renderer's `--check`.
4. Apply through the owning playbook or script; verify the live result and the health signals.
5. Stage **explicit paths only** (`git add path/one path/two`), never `git add .` or `-A`. Do not commit or push unless the owner asks.

Regenerating documentation:

```bash
/data/ai/toolchains/docs-render/bin/python scripts/render-glance-guide.py          # guide pages
python3 scripts/render-server-catalogue.py                                          # source catalogue
python3 scripts/render-native-agents.py --check                                     # agent prompt drift
/data/ai/toolchains/docs-render/bin/python scripts/verify-homelab-documentation.py  # links
```

Guide HTML goes live as soon as the checkout updates; no restart is needed. Never install the markdown library into the system Python; use the `docs-render` environment.

## Scripts, timers and helpers

**Scripts** (in `scripts/`):

| Script | Use it to |
|---|---|
| `watoom-menu.sh` | Interactive status/start/stop/restart/logs for apps, Docker stacks and games |
| `post-reboot-health-check.sh` | Run the checks after a reboot |
| `check-required-secrets.sh`, `render-secrets.sh`, `restore-vault-secrets.sh` | Verify, render and restore secrets |
| `set-change-approval-pin.sh` | Create or rotate the change-request approval PIN (root) |
| `gpu-controller-repin-primary.py` | Re-pin the controller after a reviewed primary Deployment change |
| `check-image-pinning.sh`, `export-live-image-lock.sh` | Check that images are pinned by digest; record live image versions |
| `watoom-ansible-validate.sh` | Validation tiers `fast` / `standard` / `full` |
| `render-*.py`, `verify-homelab-documentation.py` | Rebuild and check docs, guide, catalogue, agent prompts |
| `repair-project-perms.sh`, `create-hostpaths.sh` | Fix project-folder permissions; create required host folders |
| `cutover-watoom-code-rename.sh`, `move-state-to-ssd.sh`, `rebuild-homelab.sh` | One-time or recovery tools — **owner only** |

**Host timers** (`systemctl list-timers --no-pager`):

| Timer | Purpose |
|---|---|
| `watoom-code-backup` (03:30) / `watoom-backup-offhost-check` | Daily backup and off-host verification |
| `watoom-change-requests` | Validates AI change requests and publishes the diff for approval; never applies |
| `watoom-fab-approvals` (1 min) | Processes owner-approved asset downloads |
| `watoom-rig-async-stage` (5 s) | Dispatches RIG game jobs and delivers completions |
| `watoom-game-worker` (30 s) | Runs bounded Godot validation jobs |
| `watoom-image-review` (1 min) | Copies project captures into the review folder |
| `watoom-capability-health` (1 h) | Refreshes the skill/catalogue health view (no inference) |
| `watoom-gpu-controller-credentials` | Rotates controller credentials |

A timer whose service is **failed** is retried on its interval, so a broken one fills the journal quickly. Read the **first** error, fix the cause, and the next run recovers. Example: `watoom-rig-async-stage` reporting `namespaces "opencode-watoom-stage" not found` means the installed (release-pinned) copy still points at the old namespace; it needs the README's controlled update in `tools/rig-async-stage/`, not a hand edit of the installed files.

**Web helpers:** Glance (`/guide`, `/command-center`), Model Manager (`/model-manager/`), Skill Editor (`/skills/`), Grafana, Prometheus, the IaC console (on demand), Pi-hole admin.

## When to stop and ask the owner

Stop and escalate if any of these apply: the controller is `uncertain` or `recovery-required` and the steps above do not clear it; you would need `sudo`/root for something this page does not list; the fix touches the router, VLANs, firewall or DNS; it needs a secret value; it would delete data you cannot re-create; a backup or off-host alert is firing; a command's output differs from what this page says to expect. Say what you ran, what you saw, and attach the relevant `state.json` and log lines.

## Glossary

| Term | Meaning |
|---|---|
| **Owner** (controller field) | Whoever currently holds the GPU for a job or switch. Null = idle |
| **qwen-ready** | Healthy idle: the primary model is up and nothing owns the GPU |
| **Uncertain** | An interrupted transition; needs controller recovery |
| **Generation** | A counter that only increases each time ownership changes; never hard-code it |
| **Re-pin / fingerprint** | The controller's remembered hash of a model Deployment; must be re-approved after a reviewed change |
| **Fence / idle gate** | A precondition that waits for no active work before a risky step |
| **On demand** | Scaled to zero and started when needed — not a fault |
| **RIG / Bazzite** | The remote GPU workstation lanes used for heavy Blender/Godot/capture jobs |
| **Critic / reviewer** | AI roles that challenge a plan (critic) and independently accept finished work (reviewer) |
| **Receipt** | A recorded proof (hashes, status) that a job or step really ran |
| **Generated file** | Built by a renderer from a source file; never edit by hand |
