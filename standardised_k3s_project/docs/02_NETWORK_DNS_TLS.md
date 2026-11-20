# Network, DNS and TLS

## VLAN and trust layout

| VLAN / network | Router interface | Purpose / trust |
|---|---|---|
| VLAN 10 — `10.99.1.0/24` | `vlan_internal` | trusted management |
| VLAN 20 — `10.99.20.0/24` | `vlan_TheHood` | homelab/LAN; server default route |
| VLAN 30 — `10.99.30.0/24` | `vlan_wifi24` | low-trust Wi-Fi |
| VLAN 40 — `10.99.40.0/24` | `vlan_wifi5` | low-trust Wi-Fi |
| VLAN 50 — `192.168.250.0/24` | `vlan_dmz` | DMZ/game exposure |
| Break-glass — `192.168.99.0/24` | `emergency-mgmt` | emergency management |

The collected RB5009 export shows VLAN filtering, tagged trunks and restricted management services. IPv6 is disabled in the current RouterOS export.

## Server interfaces

```text
enp34s0.20  10.99.20.225/24   default via 10.99.20.1
enp35s0     192.168.250.225/24 no default route
```

Quick check:

```bash
ip -br addr
ip route
```

## DNS

Pi-hole on `10.99.20.225` is the local resolver for homelab clients. Each internal name needs its own `dns.hosts` record (`pihole-FTL --config dns.hosts`); the dnsmasq wildcard in `manifests/10-infrastructure/pihole/pihole.yml` does not resolve names on its own (verified 2026-11-17: an unregistered `*.internal.homelab.example` name returns NXDOMAIN). Internal service names use:

```text
<service>.internal.homelab.example
```

Inside k3s, CoreDNS is `10.243.0.10` and services use normal Kubernetes DNS such as:

```text
service.namespace.svc.cluster.local
```

CS2 helper services run in namespace `platform-workers`, for example:

```text
cs2-server-tracker.platform-workers.svc.cluster.local
```

## Traefik and internal HTTPS

Traefik is the internal ingress controller and is exposed on `10.99.20.225` ports 80/443. Internal application routes use wildcard TLS Secrets named `watoom-tls` in the relevant namespaces.

### Certificates

Every internal HTTPS name uses one Let's Encrypt wildcard certificate for `*.internal.homelab.example` (and `internal.homelab.example`):

- cert-manager (namespace `cert-manager`) issues it through the `letsencrypt-cloudflare-prod` ClusterIssuer with a Cloudflare DNS-01 challenge; a `letsencrypt-cloudflare-staging` issuer exists for tests.
- The `Certificate` `watoom-internal-wildcard-prod` writes Secret `watoom-internal-wildcard-prod-tls` in `cert-manager` and renews automatically.
- `watoom-internal-tls-sync.timer` (`scripts/sync-internal-tls.py`, installed by `homelab_rebuild` `local_tls`) copies it into every namespace's `watoom-tls` Secret, the `watoom-code-lan-tls` Secret and the host files in `/data/watoom-local-tls`. Only namespaces that already hold the Secret are updated.
- `scripts/install-browser-trusted-tls.sh` installs and repairs the whole chain; `STAGING_ONLY=true` tests against the staging issuer.

Browsers trust it with no local CA. If one shows "not secure", check the Secret in that namespace matches the cert-manager one and that the sync timer last ran successfully.

## Internal names

Current `internal.homelab.example` names (from the live IngressRoutes): `arma-reforger`, `artex`, `audiobookshelf`, `bazarr`, `dispatcharr`, `glance`, `grafana`, `iac-console`, `immich`, `jellyfin`, `lidarr`, `llm-router`, `pihole`, `plex`, `prometheus`, `prowlarr`, `qbittorrent`, `qwen38`, `radarr`, `sabnzbd`, `searxng`, `seerr`, `sims4-mods`, `sonarr`, `traefik-dashboard`, `vaultwarden`, `watoom-code` and `wireguard`.

`qwen38` is the direct endpoint of the `llama-cpp-qwen38` experiment backend; models are normally reached through `llm-router`.

## Public publication

Current public application names evidenced by configuration include:

- `stream.homelab.example`
- `psytrance.homelab.example`
- `vaultwarden.homelab.example`

Stream and Psytrance use Cloudflare Tunnel connectors. Do not open inbound web ports on the router merely to support those tunnel paths.
