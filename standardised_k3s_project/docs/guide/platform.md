---
title: Platform — k3s, Docker and host
nav: Platform
summary: The single-node Kubernetes runtime, the Compose stacks that sit beside it, persistent storage conventions and host tuning.
---

## k3s

| Property | Value |
|---|---|
| Node | `watoom-homelab` (control plane, sole worker) |
| Version | `v1.36.3+k3s1`, containerd `2.3.2-k3s2` |
| Kernel | `7.2.7-200.fc44.x86_64` |
| System components | CoreDNS, Traefik, local-path-provisioner, metrics-server |
| GPU | `nvidia-device-plugin-daemonset` advertises the GPU as `nvidia.com/gpu` |
| Kubeconfig | `/etc/rancher/k3s/k3s.yaml` |

### Manifest registry

`ansible/inventories/homelab/group_vars/all.yml` defines `k3s_manifest_groups`, applied in this order by `playbooks/kubernetes.yml`:

| Order | Group | Path | Contents |
|---|---|---|---|
| 1 | namespaces | `manifests/00-namespaces` | All application namespaces |
| 2 | infrastructure | `manifests/10-infrastructure` | Glance, monitoring, Pi-hole, Traefik extras, platform-workers, Vaultwarden, WireGuard route |
| 3 | media | `manifests/20-media` | Arr stack, downloaders, Jellyfin, Plex, Seerr, Immich, Audiobookshelf |
| 4 | games | `manifests/30-games` | Game servers (registered in `game_servers`) |
| 5 | rbac | `manifests/40-rbac` | Cluster roles and bindings |

Secrets are rendered separately from the vault into `manifests/05-secrets/*-generated.yml` (ignored by Git). The AI stack (llama-cpp, router, SearXNG) and WatooM Code are owned by dedicated roles and playbooks, not by this registry; see [AI platform](ai.md) and [WatooM Code](watoom-code.md).

`kubernetes_app_manifests` lists the exact manifests for each individually reconcilable application. Dispatcharr is deliberately absent: `dispatcharr_control` owns its VPN and no-VPN variants.

### Namespaces by function

| Function | Namespaces |
|---|---|
| Core | `kube-system`, `pihole`, `glance`, `cloudflare`, `platform-workers` |
| Monitoring | `monitoring` |
| Media | `jellyfin`, `plex`, `seerr`, `radarr`, `sonarr`, `lidarr`, `prowlarr`, `sabnzbd`, `qbittorrent`, `bazarr`, `flaresolverr`, `dispatcharr`, `audiobookshelf`, `immich` |
| Games | `cs2`, `dayz`, `enshrouded`, `valheim`, `arma-reforger`, `minecraft-pixel`, `minecraft-zom` |
| AI inference | `llama-cpp`, `searxng` |
| WatooM Code | `watoom-code` (production), `watoom-code-rig-jobs` (RIG async stage) |
| Security tooling | `kali-agent` |
| Utility | `iac-web-console`, `vaultwarden`, `wireguard`, `pi-agent` |

`watoom-code` is the production WatooM Code namespace; the name does not indicate a pre-production environment.

### Zero replicas are often intentional

Game servers, on-demand utilities and every non-primary model are normally `0/0`. Check the owning registry or controller before treating a scaled-down Deployment as a fault. Model Deployments in `llama-cpp` are only ever scaled by the GPU controller.

## Docker Compose

Compose runs edge workloads that need host networking, UDP listeners or tunnel connectors. Registered stacks live under `docker/<stack>` and are listed in `docker_stacks`.

| Stack | Containers | Purpose |
|---|---|---|
| `wireguard` | `wg-easy` | Remote-access VPN (`51820/udp`, admin `10.99.20.225:51821`) |
| `azuracast` | `azuracast`, `azuracast_updater`, `cloudflared-psytrance` | Psytrance radio station and its tunnel |
| `dispatcharr-cloudflare` | `stream-app`, `stream-nginx`, `cloudflared-stream` | Browser HLS stream publication |

Unregistered containers with a defined role:

| Container | Role |
|---|---|
| `watoom-local-registry` | Image registry on `127.0.0.1:5000`; all WatooM images are pinned by digest from here |
| `kali-workbench`, `kali-pentest` | Isolated security tooling used only by the `watoom-kali` agent |

Local Docker build cache is bounded by `watoom-docker-storage-retention.timer` (hourly, verified retention policy).

## Persistent storage

Workloads use explicit `hostPath` volumes; there is no dynamic storage class in use for application data.

| Convention | Example |
|---|---|
| App configuration and state | `/app/<service>/config`, `/app/<service>/data` |
| Media libraries | `/data/Movies`, `/data/TV`, `/data/music`, `/data/audiobooks`, `/data/podcasts` |
| Downloads | `/data/downloads`, `/data/downloads/incomplete` |
| AI service state | `/app/ai/services/<service>` |
| AI builds | `/app/ai/builds/<component>` |
| Models, projects, toolchains | `/data/ai/models`, `/data/ai/projects`, `/data/ai/toolchains` |

Product names and directory names do not always match: Seerr keeps its data at `/app/overseerr`. Do not rename a working path to match a product name.

## Host tuning

| Setting | Value |
|---|---|
| tuned profile | `throughput-performance` |
| TCP | BBR congestion control, `fq` qdisc |
| Memory | `vm.swappiness=10`, `vm.dirty_ratio=15`, `vm.dirty_background_ratio=5` |
| Files | `fs.inotify.max_user_watches=1048576`, `fs.file-max=2097152` |
| journald | `SystemMaxUse=512M` |
| GPU | Driver `615.71.09`, power limit 300 W (since 2026-11-03), persistence enabled |

### Capacity

| Filesystem | Size | Watch |
|---|---|---|
| `/` | 117 GiB | containerd images and snapshots are the largest consumer |
| `/app` | 218 GiB | application databases and caches |
| `/data` | 3.5 TiB | media, models and Toolkit build layers |

Prometheus alerts when `/`, `/app` or `/data` stays above 90% for 30 minutes. Reclaim root space by removing unused images explicitly; do not prune k3s or containerd wholesale.

```bash
df -h / /app /data
sudo du -xhd1 /var/lib/rancher/k3s | sort -h
sudo k3s crictl images | sort -k4 -h | tail
```
