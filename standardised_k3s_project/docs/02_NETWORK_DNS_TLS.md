# Network, DNS and TLS

## VLAN and trust layout

| VLAN / network | Router interface | Purpose / trust |
|---|---|---|
| VLAN 10 — `10.99.1.0/24` | `vlan_internal` | trusted management |
| VLAN 20 — `10.99.20.0/24` | `vlan_TheHood` | homelab/LAN; server default route |
| VLAN 30 — `10.99.30.0/24` | `vlan_wifi24` | low-trust Wi-Fi |
| VLAN 40 — `10.99.40.0/24` | `vlan_wifi5` | low-trust Wi-Fi |
| VLAN 50 — `192.168.0.0/24` | `vlan_dmz` | DMZ/game exposure |
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

The old `*.agent.example` naming belongs only to legacy documentation and should not be used for new configuration.

Inside k3s, CoreDNS is `10.243.0.10` and services use normal Kubernetes DNS such as:

```text
service.namespace.svc.cluster.local
```

CS2 helper services are now canonical in namespace `platform-workers`, for example:

```text
cs2-server-tracker.platform-workers.svc.cluster.local
```

## Traefik and internal HTTPS

Traefik is the internal ingress controller and is exposed on `10.99.20.225` ports 80/443. Internal application routes use wildcard TLS Secrets named `watoom-tls` in the relevant namespaces.

### Current certificate implementation

The live audit on 5 October 2026 showed a self-signed wildcard certificate with:

- subject/issuer: `CN=*.internal.homelab.example`
- SANs: `*.internal.homelab.example`, `internal.homelab.example`, `10.99.20.225`, `192.168.250.225`
- Kubernetes Secret name: `watoom-tls`

No cert-manager `Certificate` or `ClusterIssuer` CRDs were present in the audited live cluster. Treat self-signed wildcard TLS as the current implementation unless a deliberate TLS migration is performed.

### Preferred / planned certificate model

- wildcard: `*.internal.homelab.example`
- issuer: Let's Encrypt
- challenge: Cloudflare DNS-01
- secret name used by application routes: `watoom-tls`

`scripts/install-browser-trusted-tls.sh` is the migration helper for the preferred model. Do not describe that model as current until cert-manager and the issuer/certificate objects are actually live and validated. `STAGING_ONLY=true` remains available for staging tests.

## Current internal names evidenced by current manifests/config

`arma-reforger`, `audiobookshelf`, `bazarr`, `dispatcharr`, `glance`, `grafana`, `iac-console`, `immich`, `jellyfin`, `lidarr`, `llm-builder`, `opencode`, `open-webui`, `pihole`, `plex`, `prometheus`, `prowlarr`, `qbittorrent`, `llm-router` (router API, from 2026-11-18), `qwen38` (legacy experiment endpoint), `radarr`, `sabnzbd`, `searxng`, `seerr`, `sonarr`, `traefik-dashboard`, `vaultwarden`, and `wireguard` under `internal.homelab.example`.

The `qwen38.internal.homelab.example` ingress belongs to the older retained Qwen3.8 experiment deployment and is not the canonical router entry for normal Open WebUI model selection.

## Public publication

Current public application names evidenced by configuration include:

- `stream.homelab.example`
- `psytrance.homelab.example`
- `vaultwarden.homelab.example`

Stream and Psytrance use Cloudflare Tunnel connectors. Do not open inbound web ports on the router merely to support those tunnel paths.
