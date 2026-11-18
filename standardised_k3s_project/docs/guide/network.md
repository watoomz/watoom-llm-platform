---
title: Network, DNS and TLS
nav: Network
summary: VLAN segmentation, host interfaces, name resolution, internal HTTPS and the two ways services reach the internet.
---

## Segmentation

The router RB5009 is the edge router. Bridge VLAN filtering separates trust zones; management services are restricted to the management network. IPv6 is disabled.

| Network | Router interface | Purpose |
|---|---|---|
| VLAN 10 · `10.99.1.0/24` | `vlan_internal` | Trusted management |
| VLAN 20 · `10.99.20.0/24` | `vlan_TheHood` | Homelab LAN; server default route |
| VLAN 30 · `10.99.30.0/24` | `vlan_wifi24` | Low-trust Wi-Fi (2.4 GHz) |
| VLAN 40 · `10.99.40.0/24` | `vlan_wifi5` | Low-trust Wi-Fi (5 GHz) |
| VLAN 50 · `192.168.0.0/24` | `vlan_dmz` | DMZ for public game traffic |
| `192.168.99.0/24` | `emergency-mgmt` | Break-glass management |

## Host interfaces

```text
enp34s0.20   10.99.20.225/24    default via 10.99.20.1     LAN, ingress, DNS, VPN
enp35s0      192.168.250.225/24  no default route           DMZ, public game NAT target
```

The DMZ interface deliberately has no default route: replies to DMZ-originated flows leave through it, and nothing else does.

| Kubernetes network | Range |
|---|---|
| Pod CIDR | `10.242.0.0/24` |
| Service CIDR | `10.243.0.0/16` |
| Cluster DNS (CoreDNS) | `10.243.0.10` |

## Name resolution

Pi-hole runs in k3s with `hostNetwork: true` and answers on `10.99.20.225:53`. It is the resolver for LAN and VPN clients and holds the local records for internal names:

```text
<service>.internal.homelab.example  →  10.99.20.225  (Traefik)
```

Inside the cluster, CoreDNS resolves `service.namespace.svc.cluster.local`. Pi-hole local records are maintained in Pi-hole itself, not in this repository; a new Traefik route also needs its A record there.


## Internal HTTPS

Traefik (namespace `kube-system`) is exposed by the k3s service load balancer on `10.99.20.225:80/443`. Routes are `IngressRoute` objects matching `Host(...)`, with optional `PathPrefix` for services that share the Glance host (`/guide`, `/guide-api`, `/model-manager/`, `/pi-lab`).

| Property | Value |
|---|---|
| Certificate | Self-signed wildcard, `CN=*.internal.homelab.example` |
| SANs | `*.internal.homelab.example`, `internal.homelab.example`, `10.99.20.225`, `192.168.250.225` |
| Expiry | 24 November 2028 |
| Secret | `watoom-tls` in each namespace that terminates TLS |

Clients must trust the internal CA. There is no cert-manager in the cluster. `scripts/install-browser-trusted-tls.sh` implements an optional migration to Let's Encrypt via Cloudflare DNS-01; it is not active.

Verify what Traefik is serving:

```bash
echo | openssl s_client -connect 10.99.20.225:443 -servername glance.internal.homelab.example 2>/dev/null \
  | openssl x509 -noout -subject -enddate
kubectl get ingressroute -A
```

## Public exposure

Two mechanisms exist, and they are kept independent of internal DNS and Traefik.

**Cloudflare Tunnel (web).** Outbound connectors publish selected origins without opening inbound ports.

| Hostname | Connector | Origin |
|---|---|---|
| `stream.homelab.example` | Docker `cloudflared-stream` | `stream-nginx` (HLS) |
| `psytrance.homelab.example` | Docker `cloudflared-psytrance` | AzuraCast |
| Other tunnel routes | k3s `cloudflare/cloudflared` | configured in Cloudflare Zero Trust |

Tunnel tokens are mounted from secret files and never appear in Git or documentation.

**Router dst-nat (games).** Selected game ports are forwarded to the DMZ address `192.168.250.225`. Minecraft is intentionally not forwarded. See Game servers for the port list and router checks.

## Remote access

WireGuard runs as Docker `wg-easy`: UDP `51820` for tunnels, admin UI on `10.99.20.225:51821` and at `https://wireguard.internal.homelab.example`. Clients receive `10.9.0.x`, use Pi-hole for DNS and may reach `10.99.0.0/16` and `192.168.0.0/24`.

## Checks

```bash
ip -br addr; ip route
dig +short glance.internal.homelab.example @10.99.20.225
kubectl -n kube-system get svc traefik
curl -skI https://glance.internal.homelab.example/guide/
```

RouterOS (from the management VLAN):

```routeros
/interface bridge vlan print detail
/ip firewall nat print detail where chain=dstnat
/ip firewall filter print detail where chain=forward
```
