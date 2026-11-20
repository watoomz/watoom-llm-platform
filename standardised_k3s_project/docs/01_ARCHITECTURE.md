# Architecture

## High-level model

```text
Internet
  |
  +-- router RB5009 edge/router
  |      +-- VLAN 10  10.99.1.0/24       trusted management
  |      +-- VLAN 20  10.99.20.0/24      homelab/LAN
  |      +-- VLAN 30  10.99.30.0/24      low-trust Wi-Fi
  |      +-- VLAN 40  10.99.40.0/24      low-trust Wi-Fi
  |      +-- VLAN 50  192.168.250.0/24    DMZ
  |      +-- break-glass 192.168.99.0/24
  |
  +-- homelab-host
         +-- Fedora 44
         +-- k3s single node
         |    +-- Traefik ingress
         |    +-- Pi-hole DNS
         |    +-- media / monitoring / games / LLM / platform services
         +-- Docker Compose
              +-- WireGuard / wg-easy
              +-- AzuraCast + Psytrance Cloudflare tunnel
              +-- stream-app + stream-nginx + Cloudflare tunnel
```

## Host attachment

- LAN/management: `enp34s0.20` on VLAN 20, `10.99.20.225/24`.
- Default route: `10.99.20.1` over VLAN 20.
- DMZ: `enp35s0`, `192.168.250.225/24`, deliberately without a default route.
- k3s pod network observed: `10.242.0.0/24` on the single node.
- k3s Service network uses `10.243.0.0/16`; cluster DNS is `10.243.0.10`.

## Platform layers

### Host

Fedora owns physical networking, filesystems, GPU driver/runtime, k3s and Docker. Host tuning keeps BBR/fq, low swappiness, a throughput-oriented tuned profile, a large inotify watch limit, and bounded journald use.

### Kubernetes

k3s hosts most internal applications. Traefik exposes internal HTTPS names under `*.internal.homelab.example`. Persistent application data is predominantly explicit hostPath/local storage under `/app` and bulk data under `/data`.

### Docker Compose

Compose is used for three current edge/special-purpose stacks:

- `wireguard`
- `azuracast`
- `dispatcharr-cloudflare`

### Edge/publication

- Local application HTTP(S) enters through Traefik on `10.99.20.225`.
- Selected game ports are dst-natted by the router to the DMZ address `192.168.250.225`.
- Public web publication for Stream and Psytrance uses outbound Cloudflare Tunnel connectors.
- Vaultwarden also has a current public `vaultwarden.homelab.example` endpoint in collected configuration/documentation.

## Desired-state ownership

The primary Ansible inventory/group vars define:

- k3s manifest apply order,
- host paths,
- Docker stack registry,
- game-server registry,
- targeted Kubernetes app manifest sets,
- required Kubernetes Secret names (not values).

Do not recreate retired one-off deployment logic outside these owners without a deliberate architecture change.

## Known management exception

The current LLM stack is live but is not listed in the broad `k3s_manifest_groups`. It is managed with dedicated manifests and scripts. This is a documentation and recovery caveat, not permission to duplicate it into ad-hoc files.

## Production AI control plane

WatooM Code and the model-lab tools use the controller-compatible router. G3H is the sole GPU replica writer with eleven deployment barriers. OpenCode Mesh MCP -> host bridge -> durable pipeline -> exclusive controller -> Mesh -> Qwen restoration -> CPU asset preparation. The normal primary is Swift Qwen3.8 27B IQ4_XS at 131072 context/Q4 KV, with one inference slot.

Controller, bridge and credential rotation and recovery are persisted through their IaC owners (`llm-model-lab`, `tools/llm/watoom-gpu-controller`).
