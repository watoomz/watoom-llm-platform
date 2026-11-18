---
title: Security and secrets
nav: Security
summary: Trust boundaries, how secrets are stored and rendered, agent isolation and the controls that changes must not weaken.
---

## Trust boundaries

| Boundary | Control |
|---|---|
| Internet → services | No inbound web ports; web publication only through Cloudflare Tunnel. Game ports dst-nat to the DMZ address only |
| VLANs | Router VLAN filtering; management services reachable only from management networks; low-trust Wi-Fi separated |
| Remote users | WireGuard (`wg-easy`), clients limited to `10.99.0.0/16` and `192.168.0.0/24` |
| Internal HTTPS | Traefik with wildcard TLS; clients trust the internal CA |
| GPU and models | Only the GPU controller scales model Deployments; router and agents request access through admission |
| Agents → filesystem | WatooM Code mounts project groups read-write, the rest of `/data/ai` read-only |
| Agents → security tools | Kali tools hidden from development agents; only a top-level `watoom-kali` session can use them |

Do not flatten VLANs, open router ports or widen mounts to make a service reachable. Find the owning route instead.

## Secrets

| Item | Location |
|---|---|
| Encrypted source (committed) | `secrets-vault/env.local.vault` |
| Vault password (not committed) | `/data/secrets/watoom-homelab/ansible-vault-password.txt` (mode `0640`, group `wheel`) |
| Decrypted working copy (ignored) | `secrets/.env.local` |
| Rendered Kubernetes Secrets (ignored) | `manifests/05-secrets/*-generated.yml` |
| Tunnel tokens | Local secret files, bind-mounted read-only |
| Local service passwords | `.private/` in the checkout (excluded from Git) |
| Change-request approval PIN | Plain PIN: `CHANGE_REQUEST_PIN` inside the vault and the root-only `/root/.watoom-change-request-pin`. Cluster copy: the `glance-change-approval` Secret holds only its salted hash (`GLANCE_CHANGE_APPROVAL_PIN_HASH` in the vault). Create or rotate with `scripts/set-change-approval-pin.sh` |

Restore and apply:

```bash
scripts/restore-vault-secrets.sh          # needs the vault password file
scripts/render-secrets.sh
kubectl apply -f manifests/05-secrets/
scripts/check-required-secrets.sh         # checks names exist, never prints values
```

Required Secret names:

| Namespace | Secret | Used by |
|---|---|---|
| `cs2` | `cs2-secrets` | Steam token, RCON |
| `dayz` | `dayz-secrets` | Admin and server passwords |
| `valheim` | `valheim-secrets` | Server password |
| `arma-reforger` | `arma-manager-secret` | Manager database, auth, API |
| `immich` | `immich-secrets` | Database credentials |
| `monitoring` | `grafana-secrets` | Grafana admin |
| `vaultwarden` | `vaultwarden-secret` | Admin token |
| `cloudflare` | `cloudflared-token` | Tunnel token |
| `glance` | `glance-secrets` | Dashboard keys: Arr apps, Jellyfin, qBittorrent, SABnzbd, Seerr, Dispatcharr, Grafana, Steam |
| `glance` | `glance-change-approval` | Salted hash of the operator PIN that lets the Change requests page approve model change requests |

> [!RULE]
> Secret values never go into Git, documentation, command lines or logs. Refer to Secrets by name. Ansible tasks that handle secrets use `no_log`.

## Host accounts and identities

Three numeric identities are kept apart: `opencode` (uid/gid 1001) is the WatooM Code application, which runs as uid 1001 in its container; `codex` (uid/gid 1011) is the Codex CLI account used for delegated hands-on work, with wheel, docker and passwordless sudo; the toolkit and asset workers use uid 1009, and `watoom` (1000) is the interactive desktop account. Project folders grant each identity access through named extended ACLs on its numeric uid, so a container identity never inherits the Codex account's rights. Grant access to a new identity by adding an ACL entry for its uid, not by sharing an account.

## Projects share for the rig

`playbooks/projects-share.yml` (role `projects_share`) exposes `/data/ai/projects` as an SMB share named `projects` so the rig can map it as a drive. The rig still only initiates connections. The share is read-only, SMB3 with encryption and signing required, bound to the LAN address only, reachable only from `network.rig_host` (the firewall rich rule and `hosts allow` both name it), and served through a dedicated `rigshare` login that has no shell and no unix privileges (files are read as the `watoom` user). Symlinks and wide links are off, and `.env`, `*.pem`, `*.key`, SSH key and password-vault files are never served. The login has no password until the operator runs `sudo smbpasswd -a rigshare`; the password is not stored in Git. Making the share writable (`projects_share_read_only: false`) lets the rig change project files, so do that only on purpose. To remove it: stop and disable `smb`, remove the `samba` rich rule from the firewall zone, and restore `/etc/samba/smb.conf.distribution`.

## Agent isolation

- The coordinator routes work and cannot implement directly; delegation follows fixed handoff rules, and only the critic may be called as a child by builder, investigator and reviewer.
- Every project write is checked against the project groups by the coordinator guard.
- Kali MCP access is denied in the native, main and project configuration layers for development agents.
- Toolkit jobs read only hash-pinned inputs, run in bounded pods and write to their own output directory.

## Change-control controls

`scripts/watoom-ansible-validate.sh` enforces the WatooM policy on Ansible content: secret handling and `no_log`, TLS verification, download integrity, idempotency, handler discipline and anti-bypass checks. A required check that cannot run is a failure, not a pass. Never weaken a control to make a change pass.
