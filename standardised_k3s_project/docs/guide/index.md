---
title: Agent Export
nav: Overview
summary: A single-node k3s and Docker platform for media, game servers, local AI inference and the WatooM Code agent workspace. This guide describes how it is built, how requests flow and how to operate it safely.
---

## Operator manual

New to running this system? The [Operator manual](operator-manual.md) is a task-first guide to checking health, fixing, approving, starting, stopping and restarting things safely, including every approval gate and when to stop and ask the owner.

## Complete LLM documentation

The [LLM API & reference](llm-api.md) covers the native, router, controller, Model Manager and Toolkit contracts, the platform source map and operations, with pinned API schemas and reference clients. The [LLM user guide](llm-user-guide.md) covers day-to-day use.

For features added from 2026-11-03 to 2026-11-07, start at [What's new in custom extensions](llm-extensions.md#what-s-new-2026-11-03-to-2026-11-07). It links detailed explanations of language-knowledge triggers, Bazzite-first routing and RIG eligibility, MetaHuman conversion, terrain and game-template workflows, owned-asset discovery, learning, model/UI changes, and Glance observability.

## System at a glance

| Layer | Implementation |
|---|---|
| Host | `homelab-host`, Fedora 44 Server, AMD Ryzen 5 5500 (6C/12T), 32 GiB RAM |
| GPU | NVIDIA GeForce GPU, 20 GiB VRAM, 300 W power limit |
| Orchestration | k3s `v1.36.3+k3s1` single node, containerd, Traefik ingress |
| Edge stacks | Docker Compose: WireGuard, AzuraCast, browser stream publication |
| Network | router RB5009, VLAN-segmented; host on VLAN 20 (`10.99.20.225`) and DMZ (`192.168.250.225`) |
| DNS | Pi-hole on the host network; internal names under `*.internal.homelab.example` |
| Desired state | Git + Ansible in `standardised_k3s_project`; the operator menu and IaC console are front ends |
| AI | llama.cpp backends behind `llm-router`, with GPU ownership held by an exclusive controller |

## Architecture

```text
Internet
  │
  ├── router RB5009 ── VLAN 10 mgmt · 20 homelab · 30/40 Wi-Fi · 50 DMZ
  │        │
  │        └── dst-nat (selected game ports) ─────────────► 192.168.250.225 (DMZ NIC)
  │
  └── Cloudflare Tunnel (outbound only) ◄── cloudflared connectors
                                                    │
homelab-host (10.99.20.225)                        │
  ├── k3s
  │    ├── Traefik :80/:443 ── *.internal.homelab.example routes
  │    ├── Pi-hole (hostNetwork :53)
  │    ├── media · monitoring · games · platform-workers
  │    ├── llama-cpp: llm-router ── managed llama.cpp backends ── GPU
  │    └── WatooM Code: app · AgentMemory · Toolkit workers
  ├── host services: GPU controller · model-manager broker · dispatch timers
  └── Docker Compose: wg-easy · AzuraCast · stream-app/nginx · cloudflared
```

## Request paths

Each path below is drawn interactively above. They are the routes to check, in order, when something is unreachable.

| Path | Hops |
|---|---|
| Internal web app | client → Pi-hole (`10.99.20.225:53`) → Traefik (`:443`, wildcard TLS) → Service (`10.243.0.0/16`) → pod (`10.242.0.0/24`) |
| Media request | Seerr → Radarr / Sonarr / Lidarr → Prowlarr → SABnzbd / qBittorrent → `/data` library → Jellyfin |
| Browser stream | Dispatcharr M3U (`:9191`) → stream-app (FFmpeg → HLS) → stream-nginx (`:8888`) → cloudflared → `stream.homelab.example` |
| AI inference | WatooM Code → `llm-router:8000/v1` → GPU controller admission → llama.cpp backend → GPU |
| Public web | browser → Cloudflare Access → tunnel → origin container; no inbound web port is opened |

## Storage layout

| Mount | Size | Holds |
|---|---|---|
| `/` | 117 GiB | OS, k3s and containerd images (`/var/lib/rancher/k3s`) |
| `/app` | 218 GiB | application configuration and state (`/app/<service>`), AI service state under `/app/ai` |
| `/data` | 3.5 TiB | media libraries, downloads, AI models, projects, toolchains, backups |

Under `/data/ai`: `models/` (weights), `projects/<group>/<project>` (work), `toolchains/` (Blender, Unreal, Godot), `assets/` (shared library), `artifacts/` (ESP32 builds, Unreal exports) and `helper-scripts/` (host tooling, worker state and reports).

## Using this guide

| If you need to… | Go to |
|---|---|
| Find a service URL, namespace or port | Service catalogue |
| Understand VLANs, DNS, TLS or public exposure | [Network](network.md) |
| Run or change something through IaC | [Operations](operations.md) |
| Work with models, GPU ownership or the router | [AI platform](ai.md) |
| Build, flash or fix the ESP32 voice companion | [Voice companion](voice-companion.md) |
| Log a to-do, or see what models have logged | [Tickets](tickets.md) |
| Run a skill or pipeline in WatooM Code | [WatooM Code](watoom-code.md), [Job reference](/guide/job-reference.html) |
| Recover after a reboot or failure | [Recovery](recovery.md), [Troubleshooting](troubleshooting.md) |

> [!RULE]
> Git holds desired state, Ansible makes changes, and the GPU controller is the only writer of model replicas. Fix defects in source and redeploy through the owning playbook; do not patch live objects by hand.

## Project and source reference

See the [LLM project guide](llm-project.md) for requirements, configuration, deployment,
development and troubleshooting; [custom extensions](llm-extensions.md) for plugins,
agents, skills and worker integrations; and the [server automation reference](server-catalogue.md)
for every tracked script, playbook, role and tool. [GitHub publication](llm-publication.md)
covers the separate private distribution and source provenance.
