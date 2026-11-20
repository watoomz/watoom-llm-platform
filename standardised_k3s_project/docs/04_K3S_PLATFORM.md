# k3s Platform

## Baseline

- Single node: `homelab-host`
- k3s: `v1.36.3+k3s1`
- node/LAN IP: `10.99.20.225`
- pod network observed: `10.242.0.0/24`
- service network: `10.243.0.0/16`
- cluster DNS: `10.243.0.10`
- ingress: Traefik
- local persistent storage: explicit hostPath/local PV patterns
- NVIDIA device plugin is present for GPU workloads

## Current namespaces

The current cluster includes infrastructure, media, game and LLM namespaces such as `glance`, `monitoring`, `pihole`, `platform-workers`, `llama-cpp`, `searxng`, `watoom-code`, `watoom-code-rig-jobs`, `kali-agent`, `seerr`, `jellyfin`, `cs2`, and game-specific namespaces.

Kali runs as the `kali-agent` MCP Deployment and the Docker `kali-workbench` container. Namespace existence alone does not establish a running service.

## Desired-state groups

The main manifest registry applies in this order:

1. namespaces
2. infrastructure
3. media
4. games
5. RBAC

Current infrastructure includes `platform-workers`, Glance, monitoring, Pi-hole, Traefik, Vaultwarden and the WireGuard admin route. The current media group contains the Arr stack, downloaders, Jellyfin/Plex, Seerr, Immich, Audiobookshelf and related services.

## Normal status checks

```bash
kubectl get nodes -o wide
kubectl get pods -A
kubectl get deploy -A
kubectl get svc -A
kubectl get pvc -A
kubectl get pv
```

When investigating one namespace:

```bash
kubectl -n <namespace> get deploy,sts,ds,job,cronjob,svc,pvc
kubectl -n <namespace> get events --sort-by=.lastTimestamp
kubectl -n <namespace> logs deploy/<deployment> --tail=200
```

## Intentional zero replicas

On-demand game servers and router-managed LLM deployments may be deliberately scaled to zero. Check the intended service state before treating zero replicas as failure.

## CS2 helper consolidation

The game server remains `Deployment/cs2` in namespace `cs2`. Helper processes have been consolidated into `Deployment/platform-workers` in namespace `platform-workers`, with Services including:

- `cs2-glance-api:8080`
- `cs2-glance-direct-api:18080`
- `cs2-metadata:8080`
- `cs2-server-tracker:8080`
- `cs2-stats-tracker:8080`
- `platform-workers:9599`

Only the manifests in this repository define the platform; do not recreate Services, PVCs or helper Deployments that are not in it.

## Documentation publication

Glance mounts the repository directory:

```text
/data/github/watoom-standardised-homelab/standardised_k3s_project/config/glance/guide
```

at `/app/guide` and its helper serves `/guide` and `/guide-api` on port 9000. The normal Glance UI service is on port 8099.
